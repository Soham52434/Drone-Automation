"""Every model and LLM feature is a LangGraph. This module builds them all for inspection and diagrams.

    uv run python -m drone_security.graphs > langgraph-structure.mmd
"""

from langgraph.graph.state import CompiledStateGraph

from drone_security.agent.chat_graph import LangGraphChat
from drone_security.agent.entity_graph import LangGraphEntityDescriber
from drone_security.agent.summary_graph import LangGraphSummarizer
from drone_security.decisions.graph import LangGraphDecisionGate
from drone_security.perception.graph import LangGraphPerception

GRAPH_TITLES = {
    "perception": "1 · Vision perception (local, every sampled frame)",
    "decision": "2 · Alert classifier (every 10 s window, max 15 s)",
    "summaries": "3 · LLM summaries (alert write-up · every N minutes · dead hand at session end)",
    "chat": "4 · Chat over the day log (human-in-the-loop class check · hourly / daily answers · repeat visits)",
    "entities": "5 · Advanced analytics (LLM describes people and vehicles in key frames)",
}


class _NoVision:
    loaded = False

    def describe(self, packet: object) -> object:
        raise RuntimeError("diagram only")


def build_graphs() -> dict[str, CompiledStateGraph]:
    """The compiled graphs the server runs, built without models or API keys."""
    return {
        "perception": LangGraphPerception(_NoVision()).graph,
        "decision": LangGraphDecisionGate(None, threshold=0.6).graph,
        "summaries": LangGraphSummarizer(None).graph,
        "chat": LangGraphChat(None, lambda _session_id: []).graph,  # type: ignore[arg-type]
        "entities": LangGraphEntityDescriber(None).graph,
    }


def langgraph_mermaid() -> dict[str, str]:
    """Mermaid source for each graph, keyed like `build_graphs`."""
    return {name: graph.get_graph().draw_mermaid() for name, graph in build_graphs().items()}


if __name__ == "__main__":
    for name, source in langgraph_mermaid().items():
        print(f"%% {GRAPH_TITLES[name]}\n{source}")
