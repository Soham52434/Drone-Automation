from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from drone_security.agent import LangGraphSummarizer
from drone_security.agent.llm import answered_by, build_llm, model_chain
from drone_security.models import SessionKind, SummaryKind, SummaryRequest
from drone_security.models.perception import SceneObservation


def test_model_chain_parses_comma_lists():
    assert model_chain("model-a, model-b ,") == ("model-a", "model-b")
    assert model_chain("model-a") == ("model-a",)
    assert model_chain("") == ()


def test_build_llm_single_model_chain_and_no_key():
    assert build_llm("", "model-a") is None
    single = build_llm("k", "model-a")
    assert single.model.endswith("model-a") and single.max_retries == 2
    chained = build_llm("k", "model-a,model-b")
    assert chained.runnable.model.endswith("model-a") and chained.runnable.max_retries == 0
    assert [f.model.split("/")[-1] for f in chained.fallbacks] == ["model-b"]


def test_answered_by_reads_the_reply_metadata():
    assert answered_by(AIMessage(content="x", response_metadata={"model_name": "models/model-b"})) == "model-b"
    assert answered_by(SimpleNamespace(content="x"), "fallback") == "fallback"


def test_a_busy_first_model_hands_over_and_the_summary_names_who_wrote_it():
    def busy(_messages):
        raise RuntimeError("503 UNAVAILABLE: high demand")

    backup = RunnableLambda(lambda _m: AIMessage(content="Quiet hour.", response_metadata={"model_name": "model-b"}))
    llm = RunnableLambda(busy).with_fallbacks([backup])
    request = SummaryRequest(
        "s", SessionKind.UPLOAD, SummaryKind.PERIOD, 0, 60_000, "brief",
        observations=(SceneObservation(1_000, 0, True, "man", 0.8, "a man"),),
    )
    summary = LangGraphSummarizer(llm, "model-a").summarize(request)
    assert summary.status == "ok" and summary.attempts == 1
    assert summary.text == "Quiet hour." and summary.model == "model-b"
