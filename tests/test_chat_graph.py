import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from drone_security.agent.chat_graph import LangGraphChat
from drone_security.config import AppConfig
from drone_security.indexing import GraphIndex
from drone_security.models import AlertNote, ClassHit, LlmSettings, Session, SessionKind, SessionStatus
from drone_security.models.perception import SceneObservation
from drone_security.models.summaries import LlmSummary, SummaryKind
from main import create_app


def _obs(at_ms: int, *classes: str, scene: str = "yard") -> SceneObservation:
    return SceneObservation(
        at_ms, at_ms // 100, True, classes[0], 0.8, f"{' and '.join(classes)} in the {scene}",
        classes=tuple(ClassHit(c, 0.8) for c in classes), scene=scene,
    )


def _session(llm: bool) -> Session:
    return Session("s1", SessionKind.UPLOAD, "yard", SessionStatus.ENDED, 0, llm=LlmSettings(enabled=llm))


class FakeLLM:
    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def invoke(self, messages):
        self.prompts.append(messages[-1].content)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=reply if isinstance(reply, str) else json.dumps(reply))


@pytest.fixture
def index(tmp_path):
    graph = GraphIndex(tmp_path / "g.db")
    graph.register_session("s1", SessionKind.UPLOAD, "yard", "brief", 0)
    for at, classes, zone in [
        (5_000, ("person",), "Main gate"),
        (30_000, ("vehicle",), "Driveway"),
        (70_000, ("person", "vehicle"), "Garage"),
        (95_000, ("animal",), "Backyard"),
    ]:
        oid = graph.record_observation("s1", _obs(at, *classes, scene=zone))
        if at == 70_000:
            graph.record_alert("s1", AlertNote(60_000, 70_000, "vehicle", "warn", "van at garage", "chunk_1.mp4", 8.0), oid)
    yield graph
    graph.close()


def _chat(index, llm=None, summaries=()):
    return LangGraphChat(index, lambda _sid: list(summaries), llm)


def test_exact_class_is_answered_without_asking(index):
    turn = _chat(index).ask(_session(False), "show all person events")
    assert turn.status == "answered" and turn.intent == "frames"
    assert [f.timestamp_ms for f in turn.frames] == [5_000, 70_000]
    assert turn.plan.planner == "keywords" and turn.llm_used is False
    assert "2 readings with person" in turn.answer
    sources = [clip.source for clip in turn.clips]
    assert sources[0] == "alert" and turn.clips[0].chunk_file == "chunk_1.mp4" and "video" in sources


def test_vague_question_pauses_for_the_human_then_resumes(index):
    chat = _chat(index)
    turn = chat.ask(_session(False), "anything suspicious near the shed?")
    assert turn.status == "needs_verification"
    assert {c.name for c in turn.verification.available} == {"person", "vehicle", "animal"}
    assert "suspicious" in turn.verification.unmatched_terms
    answered = chat.verify(turn.thread_id, ["animal", "not-a-class"])
    assert answered.status == "answered"
    assert [f.classes for f in answered.frames] == [("animal",)]


def test_naming_a_class_outright_is_not_a_guess(index):
    index.record_observation("s1", _obs(40_000, "other"))
    turn = _chat(index).ask(_session(False), "show all other events")
    assert turn.status == "answered" and [f.timestamp_ms for f in turn.frames] == [40_000]


def test_time_window_on_an_upload_uses_video_position(index):
    turn = _chat(index).ask(_session(False), "vehicle between 0:20 and 1:00")
    assert turn.status == "answered"
    assert [f.timestamp_ms for f in turn.frames] == [30_000]


def test_alert_words_filter_to_alerts(index):
    turn = _chat(index).ask(_session(False), "show alerts")
    assert [f.alert_rule for f in turn.frames] == ["vehicle"]


def test_llm_planner_maps_synonyms_and_asks_when_it_guessed(index):
    llm = FakeLLM({"classes": ["vehicle"], "start": None, "end": None, "unmatched_terms": ["truck"], "confident": True, "interpretation": "trucks"})
    chat = _chat(index, llm)
    turn = chat.ask(_session(True), "was there a truck?")
    assert turn.status == "needs_verification" and turn.verification.proposed == ("vehicle",)
    assert "Object classes in the index: " in llm.prompts[0] and "vehicle (2 frames, 1 alerts)" in llm.prompts[0]
    answered = chat.verify(turn.thread_id, ["vehicle"])
    assert answered.total == 2 and answered.llm_used is True


def test_confident_llm_plan_goes_straight_to_results(index):
    llm = FakeLLM('```json\n{"classes": ["person"], "start": "0:01:00", "end": "0:02:00", "confident": true}\n```')
    turn = _chat(index, llm).ask(_session(True), "people in the second minute")
    assert turn.status == "answered" and [f.timestamp_ms for f in turn.frames] == [70_000]
    assert turn.plan.planner == "llm"


def test_llm_failure_falls_back_to_the_local_planner_and_says_why(index):
    turn = _chat(index, FakeLLM(RuntimeError("429 RESOURCE_EXHAUSTED"))).ask(_session(True), "show person events")
    assert turn.status == "answered" and turn.plan.planner == "keywords" and turn.total == 2
    assert turn.notice.startswith("The model's quota is used up")
    busy = _chat(index, FakeLLM(RuntimeError("503 UNAVAILABLE high demand"))).ask(_session(True), "show person events")
    assert busy.notice.startswith("The model is busy right now")
    summary = _chat(index, FakeLLM(TimeoutError("timeout"))).ask(_session(True), "summarize each hour")
    assert "timed out" in summary.notice and "Hour-by-hour log" in summary.answer


def test_llm_off_never_calls_the_llm(index):
    llm = FakeLLM()
    _chat(index, llm).ask(_session(False), "show person events")
    assert llm.prompts == []


def test_hourly_summary_question_uses_the_day_log(index):
    final = LlmSummary("s1", SummaryKind.FINAL, 0, 95_000, 1, "ok", "Two people and a van.", "m", 1)
    turn = _chat(index, summaries=[final]).ask(_session(False), "summarize each hour")
    assert turn.intent == "summary" and turn.status == "answered"
    assert "00:00" in turn.answer and "4 readings, 1 alerts" in turn.answer and "Two people and a van." in turn.answer
    assert turn.hours and turn.hours[0].frames == 4
    llm = FakeLLM("At 00:00 a person and a van; one alert at 0:01:10.")
    answered = _chat(index, llm).ask(_session(True), "what happened today?")
    assert answered.answer.startswith("At 00:00") and "Hour-by-hour log" in llm.prompts[0]


def test_verify_without_a_paused_question_is_refused(index):
    with pytest.raises(KeyError):
        _chat(index).verify("missing", ["person"])


def test_chat_api_round_trip(config: AppConfig):
    with TestClient(create_app(config)) as client:
        session = client.post("/api/sessions/live", json={}).json()
        index = client.app.state.manager.index
        index.register_session(session["id"], SessionKind.LIVE, "Live", "brief", 0)
        index.record_observation(session["id"], _obs(session["created_ms"], "person"))
        classes = client.get(f"/api/sessions/{session['id']}/index/classes").json()
        assert classes[0]["name"] == "person"
        assert client.get(f"/api/sessions/{session['id']}/index/daylog").json()["hours"][0]["frames"] == 1
        paused = client.post(f"/api/sessions/{session['id']}/chat", json={"question": "anything odd?"}).json()
        assert paused["status"] == "needs_verification"
        done = client.post(
            f"/api/sessions/{session['id']}/chat/{paused['thread_id']}/verify", json={"classes": ["person"]}
        ).json()
        assert done["status"] == "answered" and done["frames"][0]["classes"] == ["person"]
        again = client.post(f"/api/sessions/{session['id']}/chat/{paused['thread_id']}/verify", json={"classes": []})
        assert again.status_code == 409
        assert client.post(f"/api/sessions/{session['id']}/chat", json={"question": ""}).status_code == 422
