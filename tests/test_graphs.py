from drone_security.graphs import GRAPH_TITLES, build_graphs, langgraph_mermaid


def test_every_model_feature_is_a_langgraph_with_its_nodes():
    graphs = build_graphs()
    assert set(graphs) == set(GRAPH_TITLES) == {"perception", "decision", "summaries", "chat", "entities"}
    nodes = {name: set(graph.get_graph().nodes) for name, graph in graphs.items()}
    assert {"describe", "map_observation", "classify_objects", "reject"} <= nodes["perception"]
    assert {"route", "plan_frame_query", "verify_classes", "query_frames", "answer_summary"} <= nodes["chat"]
    assert {"classify", "apply_time_rules", "accept_alert", "reject"} <= nodes["decision"]
    assert {"describe_entities", "normalize"} <= nodes["entities"]
    assert "search_sightings" in nodes["chat"]
    assert {"write_alert_detail", "write_period_summary", "write_final_summary", "record_failure"} <= nodes["summaries"]


def test_mermaid_source_is_produced_for_each_graph():
    sources = langgraph_mermaid()
    assert all("graph TD" in source or "flowchart" in source for source in sources.values())
    assert "write_final_summary" in sources["summaries"]
