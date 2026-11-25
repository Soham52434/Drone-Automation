import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from drone_security.agent.chat_graph import LangGraphChat
from drone_security.agent.entity_graph import LangGraphEntityDescriber
from drone_security.config import AppConfig
from drone_security.decisions import LangGraphDecisionGate
from drone_security.indexing import GraphIndex, observation_id
from drone_security.models import ClassHit, EntitySighting, LlmSettings, Session, SessionKind, SessionStatus, group_visits
from drone_security.models.perception import SceneObservation
from drone_security.perception import LangGraphPerception
from main import create_app
from tests.conftest import write_test_video
from tests.test_analysis_stream import ScriptedClassifier, _events, _upload_with_llm


class Reply:
    def __init__(self, *replies) -> None:
        self.replies = list(replies)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=reply if isinstance(reply, str) else json.dumps(reply))


F150 = {"class": "vehicle", "description": "blue Ford F150 pickup", "color": "Blue", "make": "Ford", "model": "F150", "kind": "pickup"}


def test_visits_split_on_long_gaps_and_signatures_ignore_wording():
    assert [(v.start_ms, v.end_ms, v.sightings) for v in group_visits([0, 60_000, 400_000], 120_000)] == [(0, 60_000, 2), (400_000, 400_000, 1)]
    a = EntitySighting(0, "vehicle", "blue Ford F-150 pickup truck", "Blue", "Ford", "F150", "pickup")
    b = EntitySighting(1, "vehicle", "a blue Ford F150", "blue", "ford", "f150", "Pickup")
    assert a.signature == b.signature == "vehicle|blue|ford|f150|pickup"


def test_describer_keeps_known_classes_and_blanks_unknowns():
    llm = Reply({"entities": [F150, {"class": "tree", "description": "oak"}, {"class": "person", "description": "man in red jacket", "make": "unknown", "clothing": "red jacket"}]})
    sightings = LangGraphEntityDescriber(llm).describe("img", "a truck and a man", ("vehicle", "person"), 5_000, "s:5000:1")
    assert [s.class_name for s in sightings] == ["vehicle", "person"]
    assert sightings[0].signature == "vehicle|blue|ford|f150|pickup" and sightings[0].observation_id == "s:5000:1"
    assert sightings[1].make == "" and sightings[1].clothing == "red jacket"


def test_describer_skips_a_frame_when_the_model_fails_or_is_off():
    assert LangGraphEntityDescriber(Reply(RuntimeError("503 high demand"))).describe("img", "", (), 0, "o") == ()
    assert LangGraphEntityDescriber(Reply("not json")).describe("img", "", (), 0, "o") == ()
    assert LangGraphEntityDescriber(None).describe("img", "", (), 0, "o") == ()


@pytest.fixture
def index(tmp_path):
    graph = GraphIndex(tmp_path / "g.db")
    graph.register_session("s", SessionKind.UPLOAD, "drive", "brief", 0)
    for at, cls in [(10_000, "vehicle"), (70_000, "vehicle"), (400_000, "vehicle"), (420_000, "person")]:
        observation = SceneObservation(at, at // 100, True, cls, 0.8, f"{cls} on the driveway", classes=(ClassHit(cls, 0.8),), scene="driveway")
        oid = graph.record_observation("s", observation)
        if cls == "vehicle":
            graph.record_sightings("s", (EntitySighting(at, "vehicle", "blue Ford F150 pickup", "blue", "Ford", "F150", "pickup", observation_id=oid),))
        else:
            graph.record_sightings("s", (EntitySighting(at, "person", "man in a red jacket", "red", kind="man", clothing="red jacket", observation_id=oid),))
    yield graph
    graph.close()


def _session(advanced: bool, llm: bool = True) -> Session:
    return Session("s", SessionKind.UPLOAD, "drive", SessionStatus.ENDED, 0, llm=LlmSettings(enabled=llm, advanced_analytics=advanced))


def test_sightings_are_stored_and_show_in_the_telemetry_log(index):
    assert [s.description for s in index.sightings("s")][:1] == ["blue Ford F150 pickup"]
    readings = index.tagged_readings("s")
    assert readings[0].descriptions == ("blue Ford F150 pickup",)


def test_blue_f150_entered_twice(index):
    llm = Reply({"matches": [0]})
    turn = LangGraphChat(index, lambda _s: [], llm).ask(_session(True), "How many times did the blue Ford F150 come by?")
    assert turn.intent == "sightings" and turn.llm_used
    (match,) = turn.entities
    assert match.description == "blue Ford F150 pickup" and len(match.visits) == 2 and match.sightings == 3
    assert "seen twice" in turn.answer
    assert {f.timestamp_ms for f in turn.frames} == {10_000, 70_000, 400_000}


def test_word_match_answers_without_the_llm(index):
    turn = LangGraphChat(index, lambda _s: []).ask(_session(True), "was the man in the red jacket here again?")  # no chat model
    assert turn.intent == "sightings" and not turn.llm_used
    assert [m.description for m in turn.entities] == ["man in a red jacket"] and "once" in turn.answer


def test_without_advanced_analytics_the_question_goes_to_frame_search(index):
    turn = LangGraphChat(index, lambda _s: []).ask(_session(False, llm=False), "show the blue vehicle again")
    assert turn.intent == "frames" and turn.entities == ()


def test_advanced_session_end_to_end_records_sightings(tmp_path):
    class _Car:
        loaded = True

        def describe(self, packet):
            return {"reasoning": "A blue pickup at the gate.", "scene": {"setting": "gate"}, "objects": [{"name": "blue pickup truck", "score": 0.9}]}

    config = AppConfig(data_dir=tmp_path / "data")
    describer_llm = Reply({"entities": [F150]})
    app = create_app(
        config,
        perception=LangGraphPerception(_Car()),
        gate=LangGraphDecisionGate(ScriptedClassifier(0.1, "none"), 0.6),
        playback_pace=False,
        describer=LangGraphEntityDescriber(describer_llm),
    )
    video = write_test_video(tmp_path / "gate.mp4", seconds=12)
    with TestClient(app) as client:
        on = _upload_with_llm(client, video, llm_enabled=True, summary_interval_minutes=60, advanced_analytics=True)
        _events(client, on["id"])
        assert describer_llm.calls >= 1
        assert app.state.manager.index.sightings(on["id"])[0].signature == "vehicle|blue|ford|f150|pickup"
        calls = describer_llm.calls
        off = _upload_with_llm(client, video, llm_enabled=True, summary_interval_minutes=60, advanced_analytics=False)
        _events(client, off["id"])
        assert describer_llm.calls == calls and app.state.manager.index.sightings(off["id"]) == []
