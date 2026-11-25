from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from drone_security.agent.entity_graph import LangGraphEntityDescriber
from drone_security.agent.metering import MeteredModel, UsageMeter, metered_session
from drone_security.config import AppConfig
from drone_security.decisions import LangGraphDecisionGate
from drone_security.indexing.usage_ledger import UsageLedger
from drone_security.models.cost import UsageRecord, build_session_cost, usd

LLM = AppConfig.summary_model
CLASSIFIER = AppConfig.decision_model
from drone_security.perception import LangGraphPerception
from main import create_app
from tests.conftest import write_test_video
from tests.test_analysis_stream import ScriptedClassifier, _events, _upload_with_llm


class FakeLlm:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def invoke(self, _messages):
        if self.fail:
            raise RuntimeError("429 quota")
        return SimpleNamespace(
            content='{"entities": [{"class": "vehicle", "description": "blue pickup", "color": "blue"}]}',
            usage_metadata={"input_tokens": 1200, "output_tokens": 80},
            response_metadata={"model_name": LLM},
        )


@pytest.fixture
def ledger(tmp_path):
    book = UsageLedger(tmp_path / "usage.sqlite3")
    yield book
    book.close()


def test_prices_follow_the_pricing_page():
    assert usd(LLM, 1_000_000, 1_000_000) == 0.0  # free only
    assert usd(CLASSIFIER, 1_000_000, 0) == pytest.approx(0.10)
    assert usd("some-new-model", 5_000, 5_000) == 0.0


def test_metered_model_records_tokens_failures_and_the_session(ledger):
    meter = UsageMeter(ledger, clock=lambda: 1_000.0)
    with metered_session("s1"):
        MeteredModel(FakeLlm(), meter, "chat", LLM).invoke([])
        with pytest.raises(RuntimeError):
            MeteredModel(FakeLlm(fail=True), meter, "chat", LLM).invoke([])
    ok, failed = ledger.records("s1")
    assert (ok.job, ok.model, ok.input_tokens, ok.output_tokens, ok.ok) == ("chat", LLM, 1200, 80, True)
    assert (failed.input_tokens, failed.ok) == (0, False)


def test_decision_classifier_usage_is_read_too(ledger):
    reply = SimpleNamespace(usage=SimpleNamespace(input_tokens=900, output_tokens=None))
    meter = UsageMeter(ledger)
    with metered_session("s"):
        MeteredModel(SimpleNamespace(invoke=lambda _p: reply), meter, "decision", CLASSIFIER).invoke({})
    assert ledger.records("s")[0].input_tokens == 900


def test_session_cost_totals_by_job_and_model_with_free_tier_use():
    records = [
        UsageRecord("s", "decision", CLASSIFIER, 2_000_000, 0, True, 0),
        UsageRecord("s", "chat", LLM, 3000, 200, True, 0),
        UsageRecord("s", "chat", LLM, 0, 0, False, 0),
    ]
    cost = build_session_cost(records, {CLASSIFIER: 40, LLM: 7})
    assert (cost.requests, cost.failed, cost.usd) == (3, 1, pytest.approx(0.20))
    assert [(x.key, x.requests) for x in cost.by_job] == [("chat", 2), ("decision", 1)]
    assert cost.by_job[1].label == "Alert classifier"
    assert {q.label for q in cost.quotas} == {"Alert classifier", "Language model"}
    assert {(q.model, q.requests_today, q.free_per_day) for q in cost.quotas} == {
        (CLASSIFIER, 40, 10_000),
        (LLM, 7, 14_400),
    }


def test_free_tier_day_starts_at_midnight_pacific(ledger):
    pacific = ZoneInfo("America/Los_Angeles")
    before = int(datetime(2026, 11, 24, 23, 59, tzinfo=pacific).timestamp() * 1000)
    after = int(datetime(2026, 11, 25, 0, 1, tzinfo=pacific).timestamp() * 1000)
    for at in (before, after):
        ledger.record(UsageRecord("s", "chat", LLM, 1, 1, True, at))
    assert ledger.requests_today(after + 60_000) == {LLM: 1}


def test_cost_route_counts_a_sessions_model_calls(tmp_path):
    class _Car:
        loaded = True

        def describe(self, packet):
            return {"reasoning": "A blue pickup.", "scene": {"setting": "gate"}, "objects": [{"name": "pickup truck", "score": 0.9}]}

    config = AppConfig(data_dir=tmp_path / "data")
    usage = UsageLedger(config.usage_path)
    meter = UsageMeter(usage)
    app = create_app(
        config,
        perception=LangGraphPerception(_Car()),
        gate=LangGraphDecisionGate(MeteredModel(ScriptedClassifier(0.1, "none"), meter, "decision", CLASSIFIER), 0.6),
        playback_pace=False,
        describer=LangGraphEntityDescriber(MeteredModel(FakeLlm(), meter, "analytics", LLM)),
        usage=usage,
    )
    video = write_test_video(tmp_path / "gate.mp4", seconds=12)
    with TestClient(app) as client:
        session = _upload_with_llm(client, video, llm_enabled=True, summary_interval_minutes=60, advanced_analytics=True)
        _events(client, session["id"])
        body = client.get(f"/api/sessions/{session['id']}/cost").json()
        assert body["requests"] >= 1 and body["usd"] == 0.0
        jobs = {line["key"]: line for line in body["by_job"]}
        assert jobs["analytics"]["input_tokens"] >= 1200 and jobs["decision"]["requests"] >= 1
        assert {q["model"]: q["free_per_day"] for q in body["quotas"]} == {CLASSIFIER: 10_000, LLM: 14_400}
        assert client.get("/api/sessions/nope/cost").status_code == 404
    unattributed = usage._conn.execute("SELECT COUNT(*) FROM usage WHERE session_id = ''").fetchone()[0]
    assert unattributed == 0
