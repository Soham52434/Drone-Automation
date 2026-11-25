import { Bell, Film, LoaderCircle, MessagesSquare, Radio, ScanEye, ShieldAlert, ShieldCheck, Sparkles, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { Chunk, LiveStats, Session, SessionDetail, Summary } from "../api/types";
import { type AlertRecord, type AnalysisEntry, ruleLabel } from "../lib/analysisFeed";
import { formatTimeline } from "../lib/format";
import { formatInterval } from "../lib/sessionSetup";
import type { LiveConnection } from "../live/liveConnection";
import { ChatPanel } from "./ChatPanel";
import { CostButton } from "./CostButton";
import { EvidenceDialog } from "./EvidenceDialog";
import { type IncidentFilter, IncidentPanel } from "./IncidentPanel";
import { InsightPanel } from "./InsightPanel";
import { LiveStage } from "./LiveStage";
import { UploadStage } from "./UploadStage";

interface SessionViewProps {
  session: Session;
  connection: LiveConnection | undefined;
  entries: readonly AnalysisEntry[];
  /** Live buffer readout pushed over the session's event stream. */
  liveStats: LiveStats | null;
  records: readonly AlertRecord[];
  acked: ReadonlySet<string>;
  /** Incident to open in the evidence dialog (e.g. from an alert pop-up). */
  focusKey: string | null;
  onFocusHandled: () => void;
  onAcknowledge: (keys: string[]) => void;
  onStartCamera: (sessionId: string) => void;
  onStopLive: (sessionId: string) => void;
  onError: (message: string) => void;
}

export function SessionView({
  session,
  connection,
  entries,
  liveStats,
  records: rawRecords,
  acked,
  focusKey,
  onFocusHandled,
  onAcknowledge,
  onStartCamera,
  onStopLive,
  onError,
}: SessionViewProps) {
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [filter, setFilter] = useState<IncidentFilter>("all");
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [replayKey, setReplayKey] = useState<string | null>(null);
  const [hiddenError, setHiddenError] = useState<string | null>(null);
  const [briefOpen, setBriefOpen] = useState(false);
  const [summaries, setSummaries] = useState<Summary[]>([]);

  const load = useCallback(async () => {
    try {
      setDetail(await api.getSession(session.id));
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not load session");
    }
  }, [session.id, onError]);

  useEffect(() => {
    load();
  }, [load]);

  const summaryEvents = useMemo(() => entries.filter((entry) => entry.kind === "summary").length, [entries]);
  useEffect(() => {
    if (!session.llm.enabled) return;
    let cancelled = false;
    api
      .listSummaries(session.id)
      .then((list) => !cancelled && setSummaries(list))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [session.id, session.llm.enabled, summaryEvents]);

  const chunks = detail?.id === session.id ? detail.chunks : [];
  const records = useMemo(
    () => rawRecords.map((record) => attachRecording(record, chunks, session.kind)),
    [rawRecords, chunks, session.kind],
  );
  const savedClips = rawRecords.filter((record) => record.proofUrl).length;
  useEffect(() => {
    if (savedClips > 0) load();
  }, [savedClips, load]);

  useEffect(() => {
    if (!focusKey) return;
    setOpenKey(focusKey);
    setReplayKey(focusKey);
    onFocusHandled();
  }, [focusKey, onFocusHandled]);

  const readings = useMemo(() => entries.filter((entry) => entry.kind === "observation"), [entries]);
  const [chatOpen, setChatOpen] = useState(false);
  const latestReading = readings[readings.length - 1] ?? null;
  const latestDecision = useMemo(() => [...entries].reverse().find((entry) => entry.kind === "decision"), [entries]);
  const decisions = entries.filter((entry) => entry.kind === "decision").length;
  const latestError = useMemo(() => [...entries].reverse().find((entry) => entry.kind === "error"), [entries]);
  const lastStatus = useMemo(() => [...entries].reverse().find((entry) => entry.kind === "status")?.meta ?? "", [entries]);
  const summarizing = lastStatus === "summarizing";
  const analyzing = useMemo(() => isAnalyzing(session, entries), [session, entries]);
  const openCount = records.filter((record) => !acked.has(record.key)).length;
  const manualClips = chunks.filter((chunk) => chunk.trigger !== "alert");

  const ordered = useMemo(() => [...records].reverse(), [records]);
  const openIndex = ordered.findIndex((record) => record.key === openKey);
  const openRecord = openIndex >= 0 ? ordered[openIndex] : null;

  const replayRecord =
    records.find((record) => record.key === replayKey && record.proofUrl) ??
    [...records].reverse().find((record) => record.proofUrl) ??
    null;
  const playback =
    replayKey && replayRecord?.proofUrl
      ? { url: replayRecord.proofUrl, label: replayRecord.timeframe || ruleLabel(replayRecord.rule) }
      : null;

  const openIncident = (key: string) => {
    setOpenKey(key);
    setReplayKey(key);
  };
  const reviewFirstOpen = () => {
    const first = records.find((record) => !acked.has(record.key));
    if (first) openIncident(first.key);
    else setFilter("all");
  };

  const onSaved = (chunk: Chunk) =>
    setDetail((current) => (current ? { ...current, chunks: [...current.chunks, chunk] } : current));

  const alerting = analyzing && Boolean(latestDecision?.alert);
  const KindIcon = session.kind === "live" ? Radio : Film;

  const endedView = (
    <div className="stage-column">
      <div className="ended-card">
        <span className="ended-icon">
          <Radio size={22} />
        </span>
        <h3>Live session ended</h3>
        <p className="muted">
          {records.length > 0
            ? "Pick an incident to replay its clip here, or review the open ones."
            : "Nothing matched the watch brief while the camera was on."}
        </p>
        <div className="stat-grid">
          <Stat label="Readings" value={readings.length} />
          <Stat label="Windows checked" value={decisions} />
          <Stat label="Incidents" value={records.length} tone={records.length ? "warn" : undefined} />
          <Stat label="Open" value={openCount} tone={openCount ? "danger" : undefined} />
        </div>
        {openCount > 0 ? (
          <button type="button" className="btn btn-danger" onClick={reviewFirstOpen}>
            <Bell size={15} /> Review {openCount} open incident{openCount === 1 ? "" : "s"}
          </button>
        ) : null}
      </div>
    </div>
  );

  return (
    <section className={`session-view${chatOpen ? " with-chat" : ""}`}>
      <header className="session-bar">
        <span className={`kind-tile ${session.kind}`} aria-hidden>
          <KindIcon size={18} />
        </span>
        <div className="session-heading">
          <div className="title-line">
            <h2>{session.title}</h2>
            <StatusPill session={session} analyzing={analyzing} summarizing={summarizing} />
            <span className={`pill llm${session.llm.enabled ? " on" : ""}`} title="LLM summaries">
              <Sparkles size={12} />
              {session.llm.enabled ? `Summary every ${formatInterval(session.llm.summary_interval_minutes)}` : "LLM off"}
            </span>
          </div>
          <button
            type="button"
            className={`brief${briefOpen ? " open" : ""}`}
            onClick={() => setBriefOpen((v) => !v)}
            title={briefOpen ? "Collapse" : "Show full watch brief"}
          >
            <ScanEye size={13} />
            <span>{session.watch_brief || "Person, vehicle, package, animal, and hazard detection."}</span>
          </button>
        </div>
        <div className="bar-actions">
          <button
            type="button"
            className={`btn ${chatOpen ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setChatOpen((v) => !v)}
            title="Search the day log by class and time, or ask for a summary"
          >
            <MessagesSquare size={15} /> Ask
          </button>
          <CostButton session={session} activity={entries.length} />
          <WatchState analyzing={analyzing} alert={alerting} hasDecision={Boolean(latestDecision)} />
          <button
            type="button"
            className={`btn ${openCount ? "btn-danger-soft" : "btn-ghost"}`}
            onClick={reviewFirstOpen}
            disabled={records.length === 0}
            title="Review open incidents"
          >
            <Bell size={15} />
            {openCount ? `${openCount} open` : "No open incidents"}
          </button>
        </div>
      </header>

      {latestError && latestError.text !== hiddenError ? (
        <div className="banner danger" role="alert">
          <TriangleAlert size={16} />
          <span>{latestError.text}</span>
          <button type="button" className="icon-btn ghost sm" aria-label="Dismiss" onClick={() => setHiddenError(latestError.text)}>
            <X size={15} />
          </button>
        </div>
      ) : null}

      <div className="workspace">
        <div className="primary-col">
          {session.kind === "live" ? (
            <LiveStage
              session={session}
              connection={connection}
              reading={latestReading}
              stats={liveStats}
              alerting={alerting}
              playback={session.status === "ended" ? playback : null}
              endedView={endedView}
              onStartCamera={() => onStartCamera(session.id)}
              onStop={() => onStopLive(session.id)}
              onSaved={onSaved}
              onError={onError}
            />
          ) : (
            <UploadStage
              session={session}
              analyzing={analyzing}
              reading={latestReading}
              alerting={alerting}
              onSaved={onSaved}
              onError={onError}
            />
          )}
          <IncidentPanel
            kind={session.kind}
            records={records}
            acked={acked}
            filter={filter}
            selectedKey={openKey ?? replayKey}
            manualClips={manualClips}
            onFilter={setFilter}
            onOpen={openIncident}
            onAcknowledgeAll={() => onAcknowledge(records.filter((r) => !acked.has(r.key)).map((r) => r.key))}
          />
        </div>
        <InsightPanel
          session={session}
          readings={readings}
          summaries={summaries}
          llm={session.llm}
          active={analyzing}
          summarizing={summarizing}
          onOpenAlert={openIncident}
        />
      </div>

      {chatOpen ? <ChatPanel session={session} onClose={() => setChatOpen(false)} /> : null}

      {openRecord ? (
        <EvidenceDialog
          record={openRecord}
          index={openIndex}
          total={ordered.length}
          acknowledged={acked.has(openRecord.key)}
          kind={session.kind}
          writeUp={summaries.find((summary) => summary.kind === "alert" && summary.alert_key === openRecord.key) ?? null}
          writeUpPending={session.llm.enabled && session.llm.detailed_alerts}
          onClose={() => setOpenKey(null)}
          onAcknowledge={() => onAcknowledge([openRecord.key])}
          onPrevious={() => openIndex > 0 && openIncident(ordered[openIndex - 1]!.key)}
          onNext={() => openIndex < ordered.length - 1 && openIncident(ordered[openIndex + 1]!.key)}
        />
      ) : null}
    </section>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "warn" | "danger" }) {
  return (
    <div className={`stat${tone ? ` ${tone}` : ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function StatusPill({ session, analyzing, summarizing }: { session: Session; analyzing: boolean; summarizing: boolean }) {
  if (summarizing)
    return (
      <span className="pill accent">
        <LoaderCircle size={12} className="spin" /> Writing final summary
      </span>
    );
  if (session.kind === "live") {
    if (session.status === "streaming") return <span className="pill live"><span className="rec-dot" /> Live</span>;
    if (session.status === "idle") return <span className="pill">Not started</span>;
    return <span className="pill">Ended</span>;
  }
  if (analyzing) return <span className="pill accent">Analyzing</span>;
  return <span className="pill">{session.status === "ended" ? "Reviewed" : "Video"}</span>;
}

function WatchState({ analyzing, alert, hasDecision }: { analyzing: boolean; alert: boolean; hasDecision: boolean }) {
  if (!analyzing && !hasDecision) return null;
  if (alert)
    return (
      <span className="watch-state alert">
        <ShieldAlert size={15} /> Alert in last window
      </span>
    );
  if (hasDecision)
    return (
      <span className="watch-state clear">
        <ShieldCheck size={15} /> {analyzing ? "All clear" : "Last window clear"}
      </span>
    );
  return (
    <span className="watch-state">
      <ScanEye size={15} /> Watching
    </span>
  );
}

function isAnalyzing(session: Session, entries: readonly AnalysisEntry[]): boolean {
  const lastStatus = [...entries].reverse().find((entry) => entry.kind === "status");
  if (lastStatus) return lastStatus.meta === "live" || lastStatus.meta === "playing";
  return session.status === "streaming";
}

function attachRecording(record: AlertRecord, chunks: readonly Chunk[], kind: Session["kind"]): AlertRecord {
  if (record.proofUrl || record.startMs == null) return record;
  const chunk = chunks.find(
    (item) =>
      item.trigger === "alert" &&
      item.detection_ms >= record.startMs! - 8_000 &&
      (record.endMs == null || item.detection_ms <= record.endMs + 2_000),
  );
  if (!chunk) return record;
  return {
    ...record,
    clip: "saved",
    proofUrl: chunk.video_url,
    timeframe: `${formatTimeline(kind, chunk.chunk_start_ms)}–${formatTimeline(kind, chunk.chunk_end_ms)}`,
  };
}
