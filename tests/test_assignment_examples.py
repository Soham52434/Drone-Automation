"""Test cases named after the assignment's own examples ("truck logged correctly", "alert triggered at midnight")."""

import time
from types import SimpleNamespace

import pytest

from drone_security.decisions import LangGraphDecisionGate
from drone_security.indexing import GraphIndex
from drone_security.models import ClassHit, SessionKind
from drone_security.models.index import FrameQuery
from drone_security.models.perception import DecisionWindow, SceneObservation
from drone_security.models.rules import ClassDwell, TimeRules, WindowContext
from drone_security.perception import LangGraphPerception
from drone_security.pipeline.presence import PresenceTracker, scene_daypart, window_context
from tests.conftest import make_packet


class _Clear:
    """The alert classifier that never sees anything worth reporting, so only the predefined rules can alert."""

    def invoke(self, payload):
        return SimpleNamespace(
            nouls={"alert": SimpleNamespace(noul=0.05)},
            choices={"rule": SimpleNamespace(choice="none"), "severity": SimpleNamespace(choice="info")},
        )


def _person(at_ms: int, *, scene: dict | None = None) -> SceneObservation:
    raw = {"scene": scene} if scene else {}
    return SceneObservation(at_ms, 0, True, "man", 0.8, "a man by the gate", raw=raw, classes=(ClassHit("person", 0.8),), scene="gate")


def _local_ms(hour: int, minute: int) -> int:
    today = time.localtime()
    return int(time.mktime((today.tm_year, today.tm_mon, today.tm_mday, hour, minute, 0, 0, 0, -1)) * 1000)


def _window(end_ms: int, context: WindowContext, *observations: SceneObservation) -> DecisionWindow:
    return DecisionWindow("s", end_ms - 10_000, end_ms, observations or (_person(end_ms - 5_000),), context=context)


# --- predefined time rules -------------------------------------------------------------------


def test_after_hours_window_wraps_midnight_and_can_be_turned_off():
    rules = TimeRules.parse("22:00-06:00")
    assert rules.is_after_hours(0) and rules.is_after_hours(23 * 60) and rules.is_after_hours(5 * 60 + 59)
    assert not rules.is_after_hours(6 * 60) and not rules.is_after_hours(12 * 60)
    assert not TimeRules.parse("").is_after_hours(0)
    assert TimeRules.parse("09:00-17:00").is_after_hours(10 * 60)
    with pytest.raises(ValueError):
        TimeRules(loiter_seconds=0)


def test_alert_triggered_at_midnight():
    tracker = PresenceTracker()
    end = _local_ms(0, 1)
    tracker.record(_person(end - 2_000))
    context = window_context(TimeRules(), live=True, end_ms=end, observations=(), tracker=tracker)
    assert context.after_hours and context.clock == "00:01"
    result = LangGraphDecisionGate(_Clear(), 0.6).evaluate(_window(end, context))
    assert result.worth_reporting and "after_hours" in result.fired_rules
    assert result.severity == "critical" and "00:01" in result.detail


def test_same_person_at_noon_is_not_an_alert():
    tracker = PresenceTracker()
    end = _local_ms(12, 0)
    tracker.record(_person(end - 2_000))
    context = window_context(TimeRules(), live=True, end_ms=end, observations=(), tracker=tracker)
    assert not context.after_hours
    assert not LangGraphDecisionGate(_Clear(), 0.6).evaluate(_window(end, context)).worth_reporting


def test_person_loitering_raises_an_alert_and_a_short_visit_does_not():
    gate = LangGraphDecisionGate(_Clear(), 0.6, rules=TimeRules(loiter_seconds=60))
    end = _local_ms(12, 0)
    long_stay = WindowContext("day", "clock", False, "12:00", (ClassDwell("person", end - 90_000, 90.0),))
    result = gate.evaluate(_window(end, long_stay))
    assert result.worth_reporting and result.fired_rules == ("loitering",) and result.severity == "warn"
    assert "90 s" in result.detail
    short = WindowContext("day", "clock", False, "12:00", (ClassDwell("person", end - 30_000, 30.0),))
    assert not gate.evaluate(_window(end, short)).worth_reporting


def test_loitering_after_hours_is_critical_and_rules_work_without_an_api_key():
    end = _local_ms(23, 30)
    context = WindowContext("night", "clock", True, "23:30", (ClassDwell("person", end - 120_000, 120.0),))
    result = LangGraphDecisionGate(None, 0.6).evaluate(_window(end, context))
    assert result.worth_reporting and set(result.fired_rules) == {"after_hours", "loitering"} and result.severity == "critical"


def test_rules_follow_the_watch_brief():
    end = _local_ms(0, 30)
    context = WindowContext("night", "clock", True, "00:30", (ClassDwell("person", end - 120_000, 120.0),))
    boats_only = LangGraphDecisionGate(_Clear(), 0.6).evaluate(_window(end, context), "Only alert when a boat comes near the dock.")
    assert not boats_only.worth_reporting


def test_presence_survives_missed_frames_but_not_long_gaps():
    tracker = PresenceTracker(max_gap_ms=15_000)
    for at in (0, 5_000, 18_000, 30_000):  # 13 s gap: still the same stay
        tracker.record(_person(at))
    assert tracker.dwell(30_000)[0].seconds == 30.0
    tracker.record(_person(60_000))  # 30 s gap: a new stay
    assert tracker.dwell(60_000)[0].seconds == 0.0
    assert tracker.dwell(200_000) == ()


def test_uploads_tell_night_from_the_scene():
    night = (_person(1_000, scene={"time_of_day": "night"}), _person(2_000, scene={"lighting": "dark"}))
    day = (_person(1_000, scene={"time_of_day": "day", "lighting": "daylight"}),)
    assert scene_daypart(night) == "night" and scene_daypart(day) == "day" and scene_daypart((_person(0),)) == "unknown"
    tracker = PresenceTracker()
    for o in night:
        tracker.record(o)
    context = window_context(TimeRules(), live=False, end_ms=3_000, observations=night, tracker=tracker)
    assert context.after_hours and context.source == "scene" and context.clock == ""


def test_alert_classifier_is_told_the_time_and_who_is_lingering():
    from drone_security.decisions.graph import _evidence_text

    end = _local_ms(0, 1)
    context = WindowContext("night", "clock", True, "00:01", (ClassDwell("person", end - 75_000, 75.0),))
    text = _evidence_text(_window(end, context), video_attached=False)
    assert "Local time: 00:01 (after hours)" in text and "Continuously in view: person 75 s" in text


# --- logging and indexing ----------------------------------------------------------------------


class _Vision:
    loaded = True

    def describe(self, packet):
        return {
            "reasoning": "A white pickup truck pulls up to the gate.",
            "scene": {"setting": "driveway", "time_of_day": "day"},
            "objects": [{"name": "white pickup truck", "score": 0.91}, {"name": "gate", "score": 0.4}],
        }


def test_truck_logged_correctly(tmp_path):
    observation = LangGraphPerception(_Vision()).observe(make_packet(12_000, index=7))
    assert observation.class_names[0] == "vehicle" and observation.scene == "driveway"
    index = GraphIndex(tmp_path / "g.db")
    index.register_session("s", SessionKind.UPLOAD, "yard", "brief", 0)
    try:
        index.record_observation("s", observation)
        found = index.find_frames("s", FrameQuery(classes=("vehicle",), start_ms=10_000, end_ms=15_000)).frames
        assert len(found) == 1 and "truck" in found[0].summary and found[0].minute_label == "00:00"
        assert index.find_frames("s", FrameQuery(classes=("person",))).total == 0
    finally:
        index.close()


class _PersonEveryFrame:
    loaded = True

    def describe(self, packet):
        return {"reasoning": "A man stands at the gate.", "scene": {"setting": "gate"}, "objects": [{"name": "man", "score": 0.82}]}


def test_loitering_alert_end_to_end_on_an_upload(tmp_path):
    from fastapi.testclient import TestClient

    from drone_security.config import AppConfig
    from main import create_app
    from tests.conftest import write_test_video
    from tests.test_analysis_stream import _events

    config = AppConfig(data_dir=tmp_path / "data", loiter_seconds=15)
    video = write_test_video(tmp_path / "gate.mp4", seconds=32)
    gate = LangGraphDecisionGate(_Clear(), 0.6, rules=config.time_rules())
    app = create_app(config, perception=LangGraphPerception(_PersonEveryFrame()), gate=gate, playback_pace=False)
    with TestClient(app) as client:
        with video.open("rb") as data:
            session = client.post("/api/sessions/upload", files={"file": ("gate.mp4", data, "video/mp4")}).json()
        events = _events(client, session["id"])
    decisions = [body["decision"] for name, body in events if name == "decision"]
    assert not decisions[0]["alert"], "first 10 s: present, but not yet loitering"
    assert any(d["alert"] and "loitering" in d["rules_fired"] for d in decisions[1:])
    assert any(name == "alert" for name, _ in events)
