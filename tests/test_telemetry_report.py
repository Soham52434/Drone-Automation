from fastapi.testclient import TestClient

from drone_security.config import AppConfig
from drone_security.indexing import GraphIndex
from drone_security.models import AlertNote, ClassHit, SessionKind, TaggedReading
from drone_security.models.perception import SceneObservation
from drone_security.telemetry import ClassTelemetryBuilder
from main import create_app


def _r(at_ms: int, *classes: tuple[str, float], alert: str | None = None) -> TaggedReading:
    return TaggedReading(at_ms, tuple(classes), "porch", f"reading at {at_ms}", classes[0][0] if classes else "none", alert)


def test_class_activity_counts_scores_alerts_and_spans():
    readings = [
        _r(0, ("person", 0.6)),
        _r(5_000, ("person", 0.9), ("vehicle", 0.5)),
        _r(10_000, ("vehicle", 0.7), alert="vehicle"),  # person absent: its span closes
        _r(40_000, ("person", 0.8), ("vehicle", 0.4)),  # 30 s gap: every span restarts
        _r(45_000),
    ]
    telemetry = ClassTelemetryBuilder(max_gap_ms=15_000).build(list(reversed(readings)))
    assert (telemetry.readings, telemetry.alerts, telemetry.duration_ms) == (5, 1, 45_000)
    by = {c.name: c for c in telemetry.classes}
    assert [c.name for c in telemetry.classes] == ["person", "vehicle"]  # most frequent first (3 each, by name)
    person, vehicle = by["person"], by["vehicle"]
    assert (person.frames, person.first_ms, person.last_ms, person.best_score) == (3, 0, 40_000, 0.9)
    assert person.avg_score == round((0.6 + 0.9 + 0.8) / 3, 3)
    assert person.spans == ((0, 5_000), (40_000, 40_000))
    assert vehicle.spans == ((5_000, 10_000), (40_000, 40_000)) and vehicle.alerts == 1
    assert [r.timestamp_ms for r in telemetry.log] == [45_000, 40_000, 10_000, 5_000, 0]


def test_log_is_capped_newest_first_and_empty_sessions_are_empty():
    many = [_r(i * 1_000, ("person", 0.5)) for i in range(20)]
    telemetry = ClassTelemetryBuilder(log_limit=5).build(many)
    assert telemetry.readings == 20 and [r.timestamp_ms for r in telemetry.log] == [19_000, 18_000, 17_000, 16_000, 15_000]
    empty = ClassTelemetryBuilder().build([])
    assert (empty.readings, empty.classes, empty.log, empty.duration_ms) == (0, (), (), 0)


def test_graph_returns_tagged_readings_with_alerts(tmp_path):
    index = GraphIndex(tmp_path / "g.db")
    index.register_session("s", SessionKind.UPLOAD, "t", "b", 0)
    oid = index.record_observation(
        "s", SceneObservation(2_000, 1, True, "man", 0.8, "a man", classes=(ClassHit("structure", 0.4), ClassHit("person", 0.8)), scene="porch")
    )
    index.record_observation("s", SceneObservation(1_000, 0, False, "none", 0.0, "empty porch", scene="porch"))
    index.record_alert("s", AlertNote(0, 2_000, "person_on_property", "warn", "a man"), oid)
    try:
        readings = index.tagged_readings("s")
    finally:
        index.close()
    assert [r.timestamp_ms for r in readings] == [1_000, 2_000]
    assert readings[0].classes == () and readings[0].alert_rule is None
    assert readings[1].class_names == ("person", "structure") and readings[1].alert_rule == "person_on_property"


def test_telemetry_endpoint(config: AppConfig):
    with TestClient(create_app(config)) as client:
        session = client.post("/api/sessions/live", json={}).json()
        index = client.app.state.manager.index
        index.register_session(session["id"], SessionKind.LIVE, "Live", "b", 0)
        index.record_observation(
            session["id"], SceneObservation(session["created_ms"], 0, True, "man", 0.8, "x", classes=(ClassHit("person", 0.8),), scene="hall")
        )
        body = client.get(f"/api/sessions/{session['id']}/telemetry").json()
        assert body["readings"] == 1 and body["classes"][0]["name"] == "person"
        assert body["log"][0]["classes"] == [["person", 0.8]] and body["log"][0]["scene"] == "hall"
        assert client.get("/api/sessions/missing/telemetry").status_code == 404
        assert client.get("/api/property").status_code in (404, 405)
