from types import SimpleNamespace

import pytest

from drone_security.agent import LangGraphSummarizer, build_summarizer
from drone_security.models import AlertNote, SessionKind, SummaryKind, SummaryRequest
from drone_security.models.perception import SceneObservation


class FakeSummaryLlm:
    def __init__(self, replies: list[object]) -> None:
        self.replies = list(replies)
        self.calls: list[list[object]] = []

    def invoke(self, messages: list[object]) -> object:
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=reply)


def _reading(at_ms: int, event: bool = True, label: str = "person") -> SceneObservation:
    return SceneObservation(at_ms, at_ms // 100, event, label, 0.9, f"{label} near the gate")


ALERT = AlertNote(
    window_start_ms=1_000,
    detection_ms=4_000,
    rule="person_on_property",
    severity="warn",
    summary="A person is at the gate.",
    chunk_file="chunk_0.mp4",
    seek_offset_sec=4.0,
)


def _request(kind: SummaryKind = SummaryKind.PERIOD, **overrides) -> SummaryRequest:
    values = dict(
        session_id="s1",
        session_kind=SessionKind.UPLOAD,
        kind=kind,
        start_ms=0,
        end_ms=60_000,
        watch_brief="Watch the gate.",
        observations=(_reading(2_000), _reading(3_000, event=False, label="empty yard")),
        alerts=(ALERT,),
        alert_key="window-1000" if kind is SummaryKind.ALERT else None,
    )
    values.update(overrides)
    return SummaryRequest(**values)


def test_period_summary_cites_evidence_and_reads_only_text():
    llm = FakeSummaryLlm(["- 0:00:04 person at the gate [clip=chunk_0.mp4 @ 4.00s]"])
    summary = LangGraphSummarizer(llm, "model-test").summarize(_request())
    assert summary.status == "ok"
    assert summary.attempts == 1
    assert summary.model == "model-test"
    assert "chunk_0.mp4" in summary.text
    system, human = llm.calls[0]
    assert "Watch the gate." in system.content
    assert "clip=chunk_0.mp4 @ 4.00s" in human.content
    assert "t=0:00:02" in human.content
    refs = summary.evidence
    clip_refs = [ref for ref in refs if ref.chunk_file]
    assert len(clip_refs) == 1 and clip_refs[0].seek_offset_sec == 4.0 and clip_refs[0].at_ms == 4_000
    assert [ref.at_ms for ref in refs] == sorted(ref.at_ms for ref in refs)


@pytest.mark.parametrize(
    ("kind", "phrase"),
    [(SummaryKind.ALERT, "single alert"), (SummaryKind.FINAL, "final summary"), (SummaryKind.PERIOD, "this period")],
)
def test_each_job_has_its_own_writer(kind, phrase):
    llm = FakeSummaryLlm(["text"])
    summary = LangGraphSummarizer(llm).summarize(_request(kind))
    assert phrase in llm.calls[0][0].content
    assert summary.kind is kind


def test_retries_once_then_succeeds():
    llm = FakeSummaryLlm([RuntimeError("quota"), "second try"])
    summary = LangGraphSummarizer(llm).summarize(_request(SummaryKind.FINAL))
    assert summary.status == "ok"
    assert summary.attempts == 2
    assert summary.text == "second try"


def test_two_failures_leave_a_failure_record():
    llm = FakeSummaryLlm([RuntimeError("down"), ""])
    summary = LangGraphSummarizer(llm).summarize(_request(SummaryKind.FINAL))
    assert summary.status == "failed"
    assert summary.attempts == 2
    assert "empty summary" in summary.text
    assert len(llm.calls) == 2


def test_quiet_period_skips_the_llm():
    llm = FakeSummaryLlm([])
    summary = LangGraphSummarizer(llm).summarize(_request(observations=(), alerts=()))
    assert summary.status == "quiet"
    assert llm.calls == []


def test_without_a_key_nothing_is_called_and_the_reason_is_kept():
    summarizer = build_summarizer("", "model-a")
    assert summarizer.available is False
    summary = summarizer.summarize(_request())
    assert summary.status == "failed"
    assert "GOOGLE_API_KEY" in summary.text


def test_alert_summary_requires_its_key():
    with pytest.raises(ValueError):
        SummaryRequest("s1", SessionKind.LIVE, SummaryKind.ALERT, 0, 1, "brief")


def test_graph_has_a_node_per_feature():
    nodes = set(LangGraphSummarizer(None).graph.get_graph().nodes)
    assert {
        "gather",
        "quiet",
        "unavailable",
        "write_alert_detail",
        "write_period_summary",
        "write_final_summary",
        "finalize",
        "record_failure",
    } <= nodes
