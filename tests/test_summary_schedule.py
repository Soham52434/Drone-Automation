import json

import pytest

from drone_security.indexing import SessionStore, SummaryArchive
from drone_security.models import AlertNote, LlmSummary, LlmSettings, SessionKind, SessionStatus, SummaryKind
from drone_security.models.perception import SceneObservation
from drone_security.pipeline.summary_schedule import SessionEvidence, SummaryScheduler


def test_scheduler_closes_periods_from_the_first_frame():
    scheduler = SummaryScheduler(60_000)
    assert scheduler.advance(5_000) == []
    assert scheduler.advance(64_999) == []
    assert scheduler.advance(65_000) == [(5_000, 65_000)]
    assert scheduler.advance(190_000) == [(65_000, 125_000), (125_000, 185_000)]
    assert scheduler.first_ms == 5_000
    assert scheduler.last_ms == 190_000
    assert scheduler.period_start == 185_000


def test_evidence_hands_out_each_period_once():
    evidence = SessionEvidence()
    for at in (1_000, 30_000, 61_000):
        evidence.record(SceneObservation(at, 0, True, "man", 0.8, "man"))
    evidence.add_alert(AlertNote(0, 30_000, "person_on_property", "warn", "man"))
    observations, alerts = evidence.take_period(0, 60_000)
    assert [o.timestamp_ms for o in observations] == [1_000, 30_000]
    assert len(alerts) == 1
    assert [o.timestamp_ms for o in evidence.remaining()] == [61_000]
    evidence.remember_summary(60_000, "second")
    evidence.remember_summary(0, "first")
    assert evidence.earlier_summaries() == ("first", "second")
    assert len(evidence.all_alerts()) == 1


@pytest.mark.parametrize("minutes", [0, 2, 7, 61])
def test_llm_settings_only_accept_slider_stops(minutes):
    with pytest.raises(ValueError):
        LlmSettings(True, minutes)


def test_llm_settings_defaults_and_stops():
    assert LlmSettings().enabled is False
    assert LlmSettings(True, 1).summary_interval_ms == 60_000
    assert LlmSettings(True, 15, detailed_alerts=True).writes_alert_details
    assert not LlmSettings(False, 15, detailed_alerts=True).writes_alert_details


def test_store_keeps_llm_settings(tmp_path):
    store = SessionStore(tmp_path / "db.sqlite")
    created = store.create(SessionKind.LIVE, "Gate", SessionStatus.IDLE, llm=LlmSettings(True, 10, True))
    assert store.get(created.id).llm == LlmSettings(True, 10, True)
    plain = store.create(SessionKind.LIVE, "Yard", SessionStatus.IDLE)
    assert store.get(plain.id).llm == LlmSettings()
    store.close()


def test_archive_writes_and_lists_final_last(tmp_path):
    archive = SummaryArchive(tmp_path / "summaries")
    base = dict(session_id="s", created_ms=1, status="ok", model="m", attempts=1)
    archive.write(LlmSummary(kind=SummaryKind.FINAL, start_ms=0, end_ms=90_000, text="final", **base))
    archive.write(LlmSummary(kind=SummaryKind.PERIOD, start_ms=60_000, end_ms=120_000, text="p2", **base))
    archive.write(LlmSummary(kind=SummaryKind.PERIOD, start_ms=0, end_ms=60_000, text="p1", **base))
    (tmp_path / "summaries" / "broken.summary.json").write_text("{")
    assert [s.text for s in archive.list()] == ["p1", "p2", "final"]
    stored = json.loads((tmp_path / "summaries" / "final.summary.json").read_text())
    assert stored["kind"] == "final"
