import time

import pytest

from drone_security.indexing import GraphIndex, observation_id
from drone_security.models import AlertNote, ClassHit, SessionKind
from drone_security.models.index import FrameQuery, TimeBucket
from drone_security.models.perception import SceneObservation


def _obs(at_ms: int, *classes: str, scene: str = "front yard") -> SceneObservation:
    return SceneObservation(
        at_ms, at_ms // 100, bool(classes), classes[0] if classes else "none", 0.8, f"{'/'.join(classes) or 'empty'} in {scene}",
        classes=tuple(ClassHit(name, 0.8) for name in classes), scene=scene,
    )


@pytest.fixture
def index(tmp_path):
    graph = GraphIndex(tmp_path / "graph.db")
    graph.register_session("up", SessionKind.UPLOAD, "yard", "brief", anchor_ms=0)
    yield graph
    graph.close()


def test_upload_buckets_by_position_and_live_by_clock():
    bucket = TimeBucket.of(SessionKind.UPLOAD, 3_725_000, 0)
    assert (bucket.hour, bucket.minute, bucket.hour_start_ms, bucket.minute_start_ms) == (1, 2, 3_600_000, 3_720_000)
    now = int(time.time() * 1000)
    live = TimeBucket.of(SessionKind.LIVE, now, 0)
    assert live.day == time.strftime("%Y-%m-%d") and live.minute_label == time.strftime("%H:%M", time.localtime(now / 1000))
    assert now - live.minute_start_ms < 60_000


def test_frames_are_queryable_by_class_and_time(index):
    for at, classes in [(5_000, ("person",)), (65_000, ("vehicle",)), (70_000, ("person", "vehicle")), (130_000, ())]:
        index.record_observation("up", _obs(at, *classes))
    people = index.find_frames("up", FrameQuery(classes=("person",)))
    assert [f.timestamp_ms for f in people.frames] == [5_000, 70_000]
    assert people.frames[1].classes == ("person", "vehicle")
    assert people.frames[0].minute_label == "00:00" and people.frames[1].minute_label == "00:01"
    windowed = index.find_frames("up", FrameQuery(classes=("vehicle",), start_ms=66_000, end_ms=200_000))
    assert [f.timestamp_ms for f in windowed.frames] == [70_000]
    assert index.find_frames("up", FrameQuery()).total == 4
    assert index.find_frames("up", FrameQuery(limit=2)).total == 4


def test_alerts_hang_off_the_reading_that_raised_them(index):
    raised = _obs(10_000, "person")
    oid = index.record_observation("up", raised)
    assert oid == observation_id("up", raised)
    index.record_observation("up", _obs(20_000, "person"))
    note = AlertNote(0, 10_000, "person_on_property", "warn", "man at gate", "chunk_0.mp4", 8.0)
    index.record_alert("up", note, oid)
    only = index.find_frames("up", FrameQuery(alerts_only=True)).frames
    assert len(only) == 1 and only[0].alert_rule == "person_on_property" and only[0].chunk_file == "chunk_0.mp4"
    assert only[0].to_dict()["alert"]["seek_offset_sec"] == 8.0
    person = next(c for c in index.classes("up") if c.name == "person")
    assert (person.frames, person.alerts) == (2, 1)


def test_day_log_digests_each_hour(index):
    index.record_observation("up", _obs(1_000, "person"))
    index.record_observation("up", _obs(2_000, "person", "vehicle"))
    index.record_observation("up", _obs(3_700_000, "animal"))
    log = index.day_log("up")
    hours = log.hours
    assert [h.hour_label for h in hours] == ["00:00", "01:00"]
    first = hours[0]
    assert first.frames == 2
    assert [(c.name, c.frames) for c in first.classes] == [("person", 2), ("vehicle", 1)]
    assert hours[1].classes[0].name == "animal"


def test_delete_removes_only_that_session(index):
    index.register_session("other", SessionKind.UPLOAD, "b", "brief", 0)
    index.record_observation("up", _obs(1_000, "person"))
    index.record_observation("other", _obs(1_000, "person"))
    index.delete_session("up")
    assert index.find_frames("up", FrameQuery()).total == 0
    assert index.find_frames("other", FrameQuery()).total == 1


def test_unregistered_session_is_refused(index):
    with pytest.raises(KeyError):
        index.record_observation("ghost", _obs(0, "person"))


def test_query_validates_its_span():
    with pytest.raises(ValueError):
        FrameQuery(start_ms=10, end_ms=5)


def test_text_that_looks_like_json_is_stored_and_read_back(index):
    tricky = SceneObservation(
        1_000, 1, True, "[]", 0.5, '{"objects": []}', raw={"objects": [], "text": []},
        classes=(ClassHit("other", 0.5),), scene="[]",
    )
    index.record_observation("up", tricky)
    frame = index.find_frames("up", FrameQuery()).frames[0]
    assert (frame.label, frame.summary, frame.scene) == ("[]", '{"objects": []}', "[]")


def test_index_survives_close_and_reopen(tmp_path):
    path = tmp_path / "persist.db"
    first = GraphIndex(path)
    first.register_session("s", SessionKind.UPLOAD, "yard", "brief", 0)
    first.record_observation("s", _obs(1_000, "person"))
    first.close()
    again = GraphIndex(path)
    try:
        assert again.find_frames("s", FrameQuery(classes=("person",))).total == 1
        again.record_observation("s", _obs(2_000, "vehicle"))
        assert {c.name for c in again.classes("s")} == {"person", "vehicle"}
    finally:
        again.close()
