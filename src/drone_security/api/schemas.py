from drone_security.models.cost import CostLine, SessionCost
from pydantic import BaseModel, Field, field_validator

from drone_security.models import (
    BufferStats,
    ChunkArtifact,
    ChunkTrigger,
    LlmSummary,
    LlmSettings,
    Session,
    SessionKind,
    SessionStatus,
    SummaryKind,
)
from drone_security.models.chat import ChatTurn
from drone_security.models.index import ClassCount, DayLog, HourDigest, IndexedFrame
from drone_security.models.session import SUMMARY_INTERVAL_CHOICES
from drone_security.models.telemetry import SessionTelemetry


class LlmSettingsIO(BaseModel):
    """The LLM settings from the session setup form."""

    enabled: bool = False
    summary_interval_minutes: int = 60
    detailed_alerts: bool = False
    advanced_analytics: bool = False

    @field_validator("summary_interval_minutes")
    @classmethod
    def _interval(cls, value: int) -> int:
        if value not in SUMMARY_INTERVAL_CHOICES:
            raise ValueError(f"must be 1 or a multiple of 5 up to 60, got {value}")
        return value

    def to_model(self) -> LlmSettings:
        return LlmSettings(self.enabled, self.summary_interval_minutes, self.detailed_alerts, self.advanced_analytics)

    @classmethod
    def from_model(cls, llm: LlmSettings) -> "LlmSettingsIO":
        return cls(
            enabled=llm.enabled,
            summary_interval_minutes=llm.summary_interval_minutes,
            detailed_alerts=llm.detailed_alerts,
            advanced_analytics=llm.advanced_analytics,
        )


class SessionOut(BaseModel):
    id: str
    kind: SessionKind
    title: str
    status: SessionStatus
    created_ms: int
    duration_ms: int | None
    source_url: str | None
    watch_brief: str
    llm: LlmSettingsIO

    @classmethod
    def from_model(cls, session: Session) -> "SessionOut":
        source_url = f"/api/sessions/{session.id}/source" if session.source_file else None
        return cls(
            id=session.id,
            kind=session.kind,
            title=session.title,
            status=session.status,
            created_ms=session.created_ms,
            duration_ms=session.duration_ms,
            source_url=source_url,
            watch_brief=session.watch_brief,
            llm=LlmSettingsIO.from_model(session.llm),
        )


class ChunkOut(BaseModel):
    chunk_file: str
    chunk_start_ms: int
    chunk_end_ms: int
    detection_ms: int
    seek_offset_sec: float
    duration_sec: float
    frame_count: int
    fps: float
    trigger: ChunkTrigger
    created_ms: int
    video_url: str
    metadata_url: str

    @classmethod
    def from_model(cls, chunk: ChunkArtifact) -> "ChunkOut":
        base = f"/api/sessions/{chunk.session_id}/chunks"
        return cls(
            chunk_file=chunk.chunk_file,
            chunk_start_ms=chunk.chunk_start_ms,
            chunk_end_ms=chunk.chunk_end_ms,
            detection_ms=chunk.detection_ms,
            seek_offset_sec=chunk.seek_offset_sec,
            duration_sec=chunk.duration_sec,
            frame_count=chunk.frame_count,
            fps=chunk.fps,
            trigger=chunk.trigger,
            created_ms=chunk.created_ms,
            video_url=f"{base}/{chunk.chunk_file}",
            metadata_url=f"{base}/{chunk.metadata_file}",
        )


class SessionDetailOut(SessionOut):
    chunks: list[ChunkOut]


class CreateLiveSessionIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    watch_brief: str | None = Field(default=None, max_length=2_000)
    llm: LlmSettingsIO | None = None


class EvidenceOut(BaseModel):
    at_ms: int
    label: str
    note: str
    chunk_file: str | None
    seek_offset_sec: float | None
    video_url: str | None


class SummaryOut(BaseModel):
    kind: SummaryKind
    start_ms: int
    end_ms: int
    created_ms: int
    status: str
    text: str
    model: str
    attempts: int
    alert_key: str | None
    evidence: list[EvidenceOut]
    #: URLs of the keyframes the LLM looked at.
    frames: list[str]

    @classmethod
    def from_model(cls, summary: LlmSummary) -> "SummaryOut":
        base = f"/api/sessions/{summary.session_id}/chunks"
        return cls(
            kind=summary.kind,
            start_ms=summary.start_ms,
            end_ms=summary.end_ms,
            created_ms=summary.created_ms,
            status=summary.status,
            text=summary.text,
            model=summary.model,
            attempts=summary.attempts,
            alert_key=summary.alert_key,
            evidence=[
                EvidenceOut(
                    at_ms=ref.at_ms,
                    label=ref.label,
                    note=ref.note,
                    chunk_file=ref.chunk_file,
                    seek_offset_sec=ref.seek_offset_sec,
                    video_url=f"{base}/{ref.chunk_file}" if ref.chunk_file else None,
                )
                for ref in summary.evidence
            ],
            frames=[f"/api/sessions/{summary.session_id}/keyframes/{name}" for name in summary.frames],
        )


class SdpIn(BaseModel):
    sdp: str
    type: str = Field(pattern="^offer$")


class SdpOut(BaseModel):
    sdp: str
    type: str


class SaveClipIn(BaseModel):
    detection_ms: int | None = Field(default=None, ge=0)


class LiveStatsOut(BaseModel):
    frames_received: int
    frames_buffered: int
    buffered_seconds: float
    latest_timestamp_ms: int | None

    @classmethod
    def from_model(cls, stats: BufferStats) -> "LiveStatsOut":
        return cls(
            frames_received=stats.frames_received,
            frames_buffered=stats.frames_buffered,
            buffered_seconds=stats.buffered_seconds,
            latest_timestamp_ms=stats.latest_timestamp_ms,
        )


class ClassCountOut(BaseModel):
    name: str
    frames: int
    best_score: float
    alerts: int

    @classmethod
    def from_model(cls, count: ClassCount) -> "ClassCountOut":
        return cls(name=count.name, frames=count.frames, best_score=round(count.best_score, 3), alerts=count.alerts)


class HourDigestOut(BaseModel):
    day: str
    hour: str
    start_ms: int
    frames: int
    alerts: int
    classes: list[ClassCountOut]
    first_ms: int | None
    last_ms: int | None

    @classmethod
    def from_model(cls, hour: HourDigest) -> "HourDigestOut":
        return cls(
            day=hour.day,
            hour=hour.hour_label,
            start_ms=hour.start_ms,
            frames=hour.frames,
            alerts=hour.alerts,
            classes=[ClassCountOut.from_model(c) for c in hour.classes],
            first_ms=hour.first_ms,
            last_ms=hour.last_ms,
        )


class DayLogOut(BaseModel):
    hours: list[HourDigestOut]

    @classmethod
    def from_model(cls, log: DayLog) -> "DayLogOut":
        return cls(hours=[HourDigestOut.from_model(h) for h in log.hours])


class FrameAlertOut(BaseModel):
    rule: str
    severity: str | None
    video_url: str | None
    seek_offset_sec: float | None


class IndexedFrameOut(BaseModel):
    observation_id: str
    timestamp_ms: int
    day: str
    hour: str
    minute: str
    summary: str
    label: str
    confidence: float
    classes: list[str]
    scene: str
    alert: FrameAlertOut | None

    @classmethod
    def from_model(cls, session_id: str, frame: IndexedFrame) -> "IndexedFrameOut":
        alert = None
        if frame.alert_rule is not None:
            alert = FrameAlertOut(
                rule=frame.alert_rule,
                severity=frame.alert_severity,
                video_url=f"/api/sessions/{session_id}/chunks/{frame.chunk_file}" if frame.chunk_file else None,
                seek_offset_sec=frame.seek_offset_sec,
            )
        return cls(
            observation_id=frame.observation_id,
            timestamp_ms=frame.timestamp_ms,
            day=frame.day,
            hour=frame.hour_label,
            minute=frame.minute_label,
            summary=frame.summary,
            label=frame.label,
            confidence=round(frame.confidence, 3),
            classes=list(frame.classes),
            scene=frame.scene,
            alert=alert,
        )


class ClipOut(BaseModel):
    source: str
    url: str
    start_sec: float
    label: str


class FramePlanOut(BaseModel):
    classes: list[str]
    start_ms: int | None
    end_ms: int | None
    alerts_only: bool
    unmatched_terms: list[str]
    confident: bool
    interpretation: str
    planner: str


class VerificationOut(BaseModel):
    question: str
    proposed: list[str]
    available: list[ClassCountOut]
    unmatched_terms: list[str]
    interpretation: str


class VisitOut(BaseModel):
    start_ms: int
    end_ms: int
    sightings: int


class EntityMatchOut(BaseModel):
    description: str
    class_name: str
    signature: str
    sightings: int
    visits: list[VisitOut]


class ChatTurnOut(BaseModel):
    thread_id: str
    status: str
    intent: str
    answer: str
    plan: FramePlanOut | None
    frames: list[IndexedFrameOut]
    total: int
    clips: list[ClipOut]
    verification: VerificationOut | None
    hours: list[HourDigestOut]
    llm_used: bool
    classes: list[ClassCountOut]
    notice: str
    entities: list[EntityMatchOut]

    @classmethod
    def from_model(cls, session_id: str, turn: ChatTurn) -> "ChatTurnOut":
        base = f"/api/sessions/{session_id}"
        return cls(
            thread_id=turn.thread_id,
            status=turn.status,
            intent=turn.intent,
            answer=turn.answer,
            plan=FramePlanOut(**turn.plan.to_dict()) if turn.plan else None,
            frames=[IndexedFrameOut.from_model(session_id, f) for f in turn.frames],
            total=turn.total,
            clips=[
                ClipOut(
                    source=clip.source,
                    url=f"{base}/chunks/{clip.chunk_file}" if clip.chunk_file else f"{base}/source",
                    start_sec=round(clip.start_sec, 2),
                    label=clip.label,
                )
                for clip in turn.clips
            ],
            verification=VerificationOut(
                question=turn.verification.question,
                proposed=list(turn.verification.proposed),
                available=[ClassCountOut.from_model(c) for c in turn.verification.available],
                unmatched_terms=list(turn.verification.unmatched_terms),
                interpretation=turn.verification.interpretation,
            )
            if turn.verification
            else None,
            hours=[HourDigestOut.from_model(h) for h in turn.hours],
            llm_used=turn.llm_used,
            classes=[ClassCountOut.from_model(c) for c in turn.classes],
            notice=turn.notice,
            entities=[
                EntityMatchOut(
                    description=m.description,
                    class_name=m.class_name,
                    signature=m.signature,
                    sightings=m.sightings,
                    visits=[VisitOut(start_ms=v.start_ms, end_ms=v.end_ms, sightings=v.sightings) for v in m.visits],
                )
                for m in turn.entities
            ],
        )


class ChatAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ChatVerifyIn(BaseModel):
    classes: list[str] = Field(default_factory=list, max_length=32)


class ClassActivityOut(BaseModel):
    name: str
    frames: int
    first_ms: int
    last_ms: int
    best_score: float
    avg_score: float
    alerts: int
    spans: list[tuple[int, int]]


class TaggedReadingOut(BaseModel):
    timestamp_ms: int
    classes: list[tuple[str, float]]
    scene: str
    summary: str
    label: str
    alert_rule: str | None
    descriptions: list[str]


class CostLineOut(BaseModel):
    key: str
    label: str
    requests: int
    failed: int
    input_tokens: int
    output_tokens: int
    usd: float


class ModelQuotaOut(BaseModel):
    model: str
    requests_today: int
    free_per_day: int | None
    label: str


class SessionCostOut(BaseModel):
    requests: int
    failed: int
    input_tokens: int
    output_tokens: int
    usd: float
    by_job: list[CostLineOut]
    by_model: list[CostLineOut]
    quotas: list[ModelQuotaOut]

    @classmethod
    def from_model(cls, cost: SessionCost) -> "SessionCostOut":
        def line(x: CostLine) -> CostLineOut:
            return CostLineOut(**{**x.__dict__, "usd": round(x.usd, 6)})

        return cls(
            requests=cost.requests,
            failed=cost.failed,
            input_tokens=cost.input_tokens,
            output_tokens=cost.output_tokens,
            usd=round(cost.usd, 6),
            by_job=[line(x) for x in cost.by_job],
            by_model=[line(x) for x in cost.by_model],
            quotas=[ModelQuotaOut(**q.__dict__) for q in cost.quotas],
        )


class SessionTelemetryOut(BaseModel):
    """Telemetry built from class tags: per-class activity and the tagged reading log (newest first)."""

    readings: int
    alerts: int
    first_ms: int | None
    last_ms: int | None
    duration_ms: int
    classes: list[ClassActivityOut]
    log: list[TaggedReadingOut]

    @classmethod
    def from_model(cls, telemetry: SessionTelemetry) -> "SessionTelemetryOut":
        return cls(
            readings=telemetry.readings,
            alerts=telemetry.alerts,
            first_ms=telemetry.first_ms,
            last_ms=telemetry.last_ms,
            duration_ms=telemetry.duration_ms,
            classes=[
                ClassActivityOut(
                    name=c.name,
                    frames=c.frames,
                    first_ms=c.first_ms,
                    last_ms=c.last_ms,
                    best_score=c.best_score,
                    avg_score=c.avg_score,
                    alerts=c.alerts,
                    spans=list(c.spans),
                )
                for c in telemetry.classes
            ],
            log=[
                TaggedReadingOut(
                    timestamp_ms=r.timestamp_ms,
                    classes=[(name, round(score, 3)) for name, score in r.classes],
                    scene=r.scene,
                    summary=r.summary,
                    label=r.label,
                    alert_rule=r.alert_rule,
                    descriptions=list(r.descriptions),
                )
                for r in telemetry.log
            ],
        )
