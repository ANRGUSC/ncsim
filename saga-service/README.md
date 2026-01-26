# saga-service

**TCP Service for HEFT/CPOP Task Scheduling**

saga-service provides a TCP interface to the [anrg-saga](https://github.com/ANRGUSC/saga) scheduling library, enabling real-time task-to-node assignment for networked computing systems.

## Overview

This service acts as a bridge between visualization/simulation components and the SAGA scheduling algorithms:

```
┌─────────────┐     TCP/9999     ┌──────────────┐
│  iobt-viz   │◄────────────────►│ saga-service │
│   (or)      │  JSON protocol   │              │
│   ncsim     │                  │  HEFT/CPOP   │
└─────────────┘                  └──────────────┘
```

## Features

- **HEFT Scheduler**: Heterogeneous Earliest Finish Time algorithm
- **CPOP Scheduler**: Critical Path on Processor algorithm
- **Network-aware**: Considers link bandwidth and latency
- **Real-time**: Low-latency scheduling responses
- **Fallback**: Round-robin if SAGA unavailable

## Installation

```bash
cd saga-service
pip install -r requirements.txt
```

### Dependencies

- Python 3.10+
- anrg-saga >= 2.0.0
- networkx >= 3.0
- numpy >= 1.24

## Usage

### Starting the Service

```bash
# From repository root
.\runsched

# Or directly
python saga-service/scheduler_service.py
```

The service listens on **port 9999** by default.

### Testing Connection

```bash
python saga-service/test_connection.py
```

## Protocol

### Request Format

```json
{
  "type": "schedule_request",
  "nodes": [
    {"id": "n0", "compute_capacity": 100},
    {"id": "n1", "compute_capacity": 50}
  ],
  "links": [
    {"id": "l01", "from": "n0", "to": "n1", "bandwidth": 100, "latency": 0.001}
  ],
  "dag": {
    "id": "dag_1",
    "tasks": [
      {"id": "T0", "compute_cost": 100},
      {"id": "T1", "compute_cost": 200}
    ],
    "edges": [
      {"from": "T0", "to": "T1", "data_size": 50}
    ]
  }
}
```

### Response Format

```json
{
  "type": "schedule_response",
  "assignments": {
    "T0": "n0",
    "T1": "n0"
  }
}
```

### Field Definitions

**Nodes:**
- `id`: Unique node identifier
- `compute_capacity`: Compute units per second

**Links:**
- `id`: Unique link identifier
- `from`, `to`: Connected node IDs
- `bandwidth`: MB/second
- `latency`: Seconds

**Tasks:**
- `id`: Unique task identifier within DAG
- `compute_cost`: Total compute units required

**Edges:**
- `from`, `to`: Source and destination task IDs
- `data_size`: MB to transfer

## Integration

### With iobt-viz

The visualization automatically connects to saga-service on port 9999 when launched. If the service is unavailable, it falls back to round-robin scheduling.

### With ncsim

ncsim uses the SAGA library directly via `SagaTaskMapper`, not the TCP service. The service is primarily for real-time visualization.

## Architecture

```
scheduler_service.py
├── SchedulerServer       # TCP server (asyncio)
├── SchedulerProtocol     # Message handling
├── SagaScheduler         # HEFT/CPOP wrapper
└── RoundRobinScheduler   # Fallback scheduler
```

## Configuration

Environment variables (optional):
- `SAGA_PORT`: TCP port (default: 9999)
- `SAGA_HOST`: Bind address (default: 0.0.0.0)

## License

See [LICENSE](../LICENSE) for license details.
