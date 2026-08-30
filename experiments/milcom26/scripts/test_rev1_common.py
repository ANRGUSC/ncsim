from rev1_common import LCHeftScheduler, adjacency, grid_topology, random_topology, schedule_placements, workload


def test_random_graph_has_no_out_of_range_links():
    topo = random_topology(500, 1)
    pos = {n["id"]: (n["x"], n["y"]) for n in topo["nodes"]}
    for link in topo["links"]:
        assert __import__("math").dist(pos[link["from"]], pos[link["to"]]) <= 80.01


def test_lc_assignments_respect_anchor_neighborhood():
    topo = grid_topology(4)
    tasks, edges = workload(8, 1)
    placements = schedule_placements(topo, tasks, edges, 1001)
    lc = placements["lc_heft"]
    assert len(lc["assignments"]) == len(tasks)
    assert lc["diagnostics"]["max_task_finish"] == lc["predicted_makespan"]
    physical = adjacency(topo)
    for task, anchor in lc["anchors"].items():
        anchor_node = lc["assignments"][anchor]
        assert lc["assignments"][task] in ({anchor_node} | physical[anchor_node])
    assert lc["diagnostics"]["critical_chain"][-1]["end"] == lc["predicted_makespan"]
