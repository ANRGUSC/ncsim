#!/usr/bin/env python3
"""
SAGA Scheduler Service for IoBT-Viz

Connects to the iobt-viz bridge server and provides DAG scheduling
using SAGA library's HEFT/CPOP schedulers.

Protocol: Newline-delimited JSON over TCP
Default port: 9999

Usage:
    python scheduler_service.py [--host HOST] [--port PORT] [--scheduler SCHEDULER]
"""

import argparse
import json
import logging
import socket
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Try to import SAGA - graceful fallback if not available
try:
    from saga.schedulers import HeftScheduler, CpopScheduler
    from saga import Network, TaskGraph, NetworkNode, NetworkEdge, TaskGraphNode, TaskGraphEdge
    SAGA_AVAILABLE = True
    logger.info("SAGA library loaded successfully")

    # Log SAGA version info if available
    try:
        import saga
        logger.info(f"SAGA version: {getattr(saga, '__version__', 'unknown')}")
    except Exception:
        pass

except ImportError as e:
    SAGA_AVAILABLE = False
    logger.warning(f"SAGA library not available: {e}")
    logger.warning("Using fallback round-robin scheduler")


@dataclass
class ScheduleRequest:
    """Parsed schedule request from iobt-viz."""
    dag: dict
    compute_nodes: int
    connectivity: list[list[bool]]
    raw_message: dict


class MockScheduler:
    """Simple round-robin scheduler when SAGA is not available."""

    def schedule(self, tasks: list[str], num_nodes: int, connectivity: list[list[bool]]) -> dict[str, int]:
        """Round-robin assignment of tasks to nodes."""
        assignments = {}
        for i, task_id in enumerate(tasks):
            assignments[task_id] = i % num_nodes
        return assignments


class SAGASchedulerWrapper:
    """Wrapper around SAGA schedulers for use with iobt-viz."""

    def __init__(self, algorithm: str = 'heft'):
        self.algorithm = algorithm.lower()

        if not SAGA_AVAILABLE:
            logger.warning("SAGA not available, using mock scheduler")
            self._mock = MockScheduler()
            return

        if self.algorithm == 'heft':
            self._scheduler = HeftScheduler()
        elif self.algorithm == 'cpop':
            self._scheduler = CpopScheduler()
        else:
            logger.warning(f"Unknown algorithm '{algorithm}', defaulting to HEFT")
            self._scheduler = HeftScheduler()

    def schedule(
        self,
        tasks: list[dict],
        edges: list[dict],
        num_nodes: int,
        connectivity: list[list[bool]]
    ) -> dict[str, int]:
        """
        Compute task-to-node assignments using SAGA.

        Args:
            tasks: List of task dicts with 'id' and 'compute_cost'
            edges: List of edge dicts with 'from', 'to', 'data_size'
            num_nodes: Number of compute nodes
            connectivity: NxN connectivity matrix

        Returns:
            Dict mapping task_id to node_index
        """
        if not SAGA_AVAILABLE:
            task_ids = [t['id'] for t in tasks]
            return self._mock.schedule(task_ids, num_nodes, connectivity)

        try:
            # Validate connectivity matrix
            if not connectivity or len(connectivity) < num_nodes:
                logger.warning(f"Connectivity matrix incomplete: {len(connectivity) if connectivity else 0} rows for {num_nodes} nodes")
                # Assume fully connected if matrix is incomplete
                connectivity = [[True for _ in range(num_nodes)] for _ in range(num_nodes)]

            # Build SAGA Network model
            logger.debug(f"Building SAGA network with {num_nodes} nodes")
            network = self._build_saga_network(num_nodes, connectivity)

            # Build SAGA TaskGraph model
            logger.debug(f"Building SAGA task graph with {len(tasks)} tasks, {len(edges)} edges")
            task_graph = self._build_saga_taskgraph(tasks, edges)

            # Run SAGA scheduler
            logger.debug(f"Running {self.algorithm} scheduler")
            schedule = self._scheduler.schedule(network, task_graph)
            logger.debug(f"SAGA schedule result type: {type(schedule)}, value: {schedule}")

            # Extract assignments
            assignments = self._extract_assignments(schedule, num_nodes)
            logger.info(f"SAGA {self.algorithm.upper()} assignments: {assignments}")
            return assignments

        except Exception as e:
            import traceback
            logger.error(f"SAGA scheduling failed: {e}")
            logger.error(traceback.format_exc())
            # Fall back to round-robin
            task_ids = [t['id'] for t in tasks]
            return MockScheduler().schedule(task_ids, num_nodes, connectivity)

    def _build_saga_network(self, num_nodes: int, connectivity: list[list[bool]]):
        """Build SAGA Network from connectivity matrix."""
        # Create network nodes
        nodes = set()
        for i in range(num_nodes):
            nodes.add(NetworkNode(name=f"node_{i}", speed=1.0))

        # Create network edges based on connectivity
        # IMPORTANT: SAGA requires self-loops for local transfers (same node)
        edges = set()
        for i in range(num_nodes):
            # Add self-loop for local transfers (very high speed = instant)
            edges.add(NetworkEdge(source=f"node_{i}", target=f"node_{i}", speed=float('inf')))

            for j in range(num_nodes):
                if i != j:
                    # Check connectivity safely
                    is_connected = True
                    if i < len(connectivity) and j < len(connectivity[i]):
                        is_connected = connectivity[i][j]

                    if is_connected:
                        edges.add(NetworkEdge(source=f"node_{i}", target=f"node_{j}", speed=100.0))

        logger.debug(f"Built network: {len(nodes)} nodes, {len(edges)} edges")
        return Network(nodes=frozenset(nodes), edges=frozenset(edges))

    def _build_saga_taskgraph(self, tasks: list[dict], edges: list[dict]):
        """Build SAGA TaskGraph from task/edge lists."""
        # Create task nodes
        task_nodes = set()
        for task in tasks:
            task_id = task['id']
            compute_cost = task.get('compute_cost', 1)
            task_nodes.add(TaskGraphNode(name=task_id, cost=float(compute_cost)))

        # Create dependency edges
        dep_edges = set()
        for edge in edges:
            # Support both 'from'/'to' and 'source'/'target' formats
            from_task = edge.get('from') or edge.get('source')
            to_task = edge.get('to') or edge.get('target')
            data_size = edge.get('data_size', 1)
            dep_edges.add(TaskGraphEdge(source=from_task, target=to_task, size=float(data_size)))

        logger.debug(f"Built task graph: {len(task_nodes)} tasks, {len(dep_edges)} edges")
        return TaskGraph(tasks=frozenset(task_nodes), dependencies=frozenset(dep_edges))

    def _extract_assignments(self, schedule, num_nodes: int) -> dict[str, int]:
        """Extract task→node mapping from SAGA schedule."""
        assignments = {}

        logger.debug(f"Extracting assignments from schedule type: {type(schedule)}")

        if schedule is None:
            logger.warning("Schedule is None")
            return assignments

        # SAGA Schedule has a 'mapping' attribute: Dict[node_name, List[ScheduledTask]]
        # Each ScheduledTask has 'name' (task id) and 'node' attributes
        if hasattr(schedule, 'mapping'):
            for node_name, scheduled_tasks in schedule.mapping.items():
                node_idx = self._parse_node_index(node_name, num_nodes)
                if node_idx is not None:
                    for task in scheduled_tasks:
                        task_name = getattr(task, 'name', None)
                        if task_name:
                            assignments[task_name] = node_idx
                            logger.debug(f"  {task_name} -> {node_name} (index {node_idx})")

        logger.debug(f"Extracted {len(assignments)} assignments")
        return assignments

    def _parse_node_index(self, node_info, num_nodes: int) -> int | None:
        """Parse node index from various formats."""
        if node_info is None:
            return None

        if isinstance(node_info, int):
            return node_info % num_nodes

        if isinstance(node_info, dict):
            node_name = node_info.get('node', node_info.get('processor', ''))
        else:
            node_name = str(node_info)

        # Extract node index from name like "node_0"
        if node_name and 'node_' in node_name:
            try:
                idx = int(node_name.split('node_')[-1].split('_')[0])
                return idx % num_nodes
            except (ValueError, IndexError):
                pass

        # Try direct int conversion
        try:
            return int(node_name) % num_nodes
        except (ValueError, TypeError):
            pass

        return None


class BridgeClient:
    """Client for connecting to iobt-viz bridge server."""

    def __init__(self, host: str = 'localhost', port: int = 9999):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.scheduler = SAGASchedulerWrapper()
        self._buffer = ""

    def connect(self) -> bool:
        """Connect to the bridge server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.socket.setblocking(True)
            logger.info(f"Connected to bridge at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.socket = None
            return False

    def disconnect(self):
        """Disconnect from the bridge server."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
            logger.info("Disconnected from bridge")

    def send_message(self, message: dict):
        """Send a JSON message (newline-terminated)."""
        if not self.socket:
            raise ConnectionError("Not connected")

        json_str = json.dumps(message) + "\n"
        self.socket.sendall(json_str.encode('utf-8'))
        logger.info(f">>> Sent message: {message.get('type', 'unknown')}")

    def receive_message(self) -> Optional[dict]:
        """Receive a JSON message (newline-terminated)."""
        if not self.socket:
            return None

        try:
            # Read until we have a complete line
            while "\n" not in self._buffer:
                data = self.socket.recv(4096)
                if not data:
                    return None  # Connection closed
                self._buffer += data.decode('utf-8')

            # Extract first complete message
            line, self._buffer = self._buffer.split("\n", 1)
            return json.loads(line)

        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            return None

    def run(self):
        """Main loop: receive messages and respond."""
        logger.info("SAGA Scheduler Service running...")
        logger.info(f"Algorithm: {self.scheduler.algorithm}")

        while True:
            try:
                if not self.connect():
                    logger.info("Retrying connection in 5 seconds...")
                    time.sleep(5)
                    continue

                # Wait for welcome message
                welcome = self.receive_message()
                if welcome:
                    logger.info(f"Welcome: {welcome}")

                    # Send hello
                    self.send_message({
                        "type": "hello",
                        "client": "saga-scheduler",
                        "algorithm": self.scheduler.algorithm
                    })

                # Main message loop
                while True:
                    msg = self.receive_message()
                    if msg is None:
                        logger.warning("Connection lost")
                        break

                    self.handle_message(msg)

            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(1)
            finally:
                self.disconnect()

    def handle_message(self, msg: dict):
        """Handle a message from the bridge."""
        msg_type = msg.get('type', '')
        logger.info(f"Received: {msg_type}")

        if msg_type == 'pong':
            # Response to our ping
            pass

        elif msg_type == 'schedule_request':
            self.handle_schedule_request(msg)

        elif msg_type == 'error':
            logger.error(f"Error from bridge: {msg.get('message', 'unknown')}")

        else:
            logger.debug(f"Unhandled message type: {msg_type}")

    def handle_schedule_request(self, msg: dict):
        """Handle a schedule request from iobt-viz."""
        try:
            # Extract DAG info
            dag_raw = msg.get('dag', '{}')
            if isinstance(dag_raw, str):
                dag = json.loads(dag_raw)
            else:
                dag = dag_raw

            tasks = dag.get('tasks', [])
            edges = dag.get('edges', [])
            num_nodes = msg.get('compute_nodes', 0)
            connectivity = msg.get('connectivity', [])

            if num_nodes == 0 or not tasks:
                logger.warning("Empty schedule request")
                self.send_message({
                    "type": "schedule_response",
                    "status": "error",
                    "message": "No tasks or nodes"
                })
                return

            logger.info(f"Scheduling {len(tasks)} tasks on {num_nodes} nodes")

            # Run SAGA scheduler
            assignments = self.scheduler.schedule(tasks, edges, num_nodes, connectivity)

            logger.info(f"Schedule computed: {assignments}")

            # Send response
            response = {
                "type": "schedule_response",
                "status": "ok",
                "assignments": assignments,
                "algorithm": self.scheduler.algorithm
            }
            self.send_message(response)
            logger.info(f"Schedule response SENT with {len(assignments)} assignments")

        except Exception as e:
            logger.error(f"Scheduling failed: {e}")
            self.send_message({
                "type": "schedule_response",
                "status": "error",
                "message": str(e)
            })


def test_saga():
    """Test SAGA scheduling with a simple DAG."""
    logger.info("Testing SAGA scheduling...")

    if not SAGA_AVAILABLE:
        logger.error("SAGA not available, cannot test")
        return False

    try:
        # Create a simple 3-node network using correct SAGA API
        nodes = frozenset([
            NetworkNode(name="node_0", speed=1.0),
            NetworkNode(name="node_1", speed=1.0),
            NetworkNode(name="node_2", speed=1.0),
        ])
        edges = frozenset([
            # Self-loops for local transfers (required by SAGA)
            NetworkEdge(source="node_0", target="node_0", speed=float('inf')),
            NetworkEdge(source="node_1", target="node_1", speed=float('inf')),
            NetworkEdge(source="node_2", target="node_2", speed=float('inf')),
            # Inter-node edges
            NetworkEdge(source="node_0", target="node_1", speed=100.0),
            NetworkEdge(source="node_1", target="node_0", speed=100.0),
            NetworkEdge(source="node_1", target="node_2", speed=100.0),
            NetworkEdge(source="node_2", target="node_1", speed=100.0),
            NetworkEdge(source="node_0", target="node_2", speed=100.0),
            NetworkEdge(source="node_2", target="node_0", speed=100.0),
        ])
        network = Network(nodes=nodes, edges=edges)
        logger.info(f"Network created: {len(nodes)} nodes, {len(edges)} edges")

        # Create a simple 3-task DAG: T0 -> T1 -> T2
        tasks = frozenset([
            TaskGraphNode(name="T0", cost=10.0),
            TaskGraphNode(name="T1", cost=20.0),
            TaskGraphNode(name="T2", cost=15.0),
        ])
        dependencies = frozenset([
            TaskGraphEdge(source="T0", target="T1", size=5.0),
            TaskGraphEdge(source="T1", target="T2", size=5.0),
        ])
        taskgraph = TaskGraph(tasks=tasks, dependencies=dependencies)
        logger.info(f"TaskGraph created: {len(tasks)} tasks, {len(dependencies)} edges")

        # Run HEFT
        scheduler = HeftScheduler()
        logger.info("Running HEFT scheduler...")
        schedule = scheduler.schedule(network, taskgraph)

        logger.info(f"Schedule type: {type(schedule)}")
        logger.info(f"Schedule attrs: {[x for x in dir(schedule) if not x.startswith('_')]}")

        # Try to access schedule data
        if hasattr(schedule, 'tasks'):
            logger.info(f"Schedule.tasks: {schedule.tasks}")
        if hasattr(schedule, 'scheduled_tasks'):
            logger.info(f"Schedule.scheduled_tasks: {schedule.scheduled_tasks}")

        # The schedule should have the task assignments
        for attr in dir(schedule):
            if not attr.startswith('_'):
                val = getattr(schedule, attr)
                if not callable(val):
                    logger.info(f"  schedule.{attr} = {val}")

        logger.info("SAGA test PASSED")
        return True

    except Exception as e:
        import traceback
        logger.error(f"SAGA test FAILED: {e}")
        logger.error(traceback.format_exc())
        return False


def main():
    parser = argparse.ArgumentParser(description="SAGA Scheduler Service for IoBT-Viz")
    parser.add_argument('--host', default='localhost', help='Bridge server host')
    parser.add_argument('--port', type=int, default=9999, help='Bridge server port')
    parser.add_argument('--scheduler', default='heft', choices=['heft', 'cpop'],
                        help='Scheduling algorithm')
    parser.add_argument('--test', action='store_true', help='Run SAGA test and exit')

    args = parser.parse_args()

    if args.test:
        success = test_saga()
        return 0 if success else 1

    client = BridgeClient(host=args.host, port=args.port)
    client.scheduler = SAGASchedulerWrapper(algorithm=args.scheduler)

    try:
        client.run()
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == '__main__':
    sys.exit(main())
