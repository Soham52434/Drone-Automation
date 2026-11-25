import { CircleAlert, Clapperboard, FileText, Flag, LoaderCircle, Moon, Sparkles } from "lucide-react";

import type { SessionKind, SessionLlm, Summary } from "../api/types";
import { ruleLabel } from "../lib/analysisFeed";
import { formatTimeline } from "../lib/format";
import { formatInterval } from "../lib/sessionSetup";

interface SummaryListProps {
  kind: SessionKind;
  summaries: readonly Summary[];
  llm: SessionLlm;
  summarizing: boolean;
  onOpenAlert: (key: string) => void;
}

/** LLM period summaries and the dead-hand final summary, newest first. */
export function SummaryList({ kind, summaries, llm, summarizing, onOpenAlert }: SummaryListProps) {
  if (!llm.enabled) {
    return (
      <div className="empty-hint">
        <Sparkles size={22} />
        <span>LLM summaries are off for this session. Choose “Yes” under LLM usage when you start a session.</span>
      </div>
    );
  }
  const newestFirst = [...summaries].reverse();
  return (
    <>
      {summarizing ? (
        <div className="summary-pending">
          <LoaderCircle size={15} className="spin" /> The LLM is writing the final summary…
        </div>
      ) : null}
      {newestFirst.length === 0 && !summarizing ? (
        <div className="empty-hint">
          <FileText size={22} />
          <span>
            The first summary arrives after {formatInterval(llm.summary_interval_minutes)} of footage. A final summary is
            written when the session ends.
          </span>
        </div>
      ) : null}
      {newestFirst.map((summary) => (
        <SummaryCard key={`${summary.kind}-${summary.start_ms}-${summary.created_ms}`} kind={kind} summary={summary} onOpenAlert={onOpenAlert} />
      ))}
    </>
  );
}

export function SummaryCard({
  kind,
  summary,
  onOpenAlert,
  compact = false,
}: {
  kind: SessionKind;
  summary: Summary;
  onOpenAlert?: (key: string) => void;
  compact?: boolean;
}) {
  const span = `${formatTimeline(kind, summary.start_ms)}–${formatTimeline(kind, summary.end_ms)}`;
  const Icon = summary.status === "failed" ? CircleAlert : summary.status === "quiet" ? Moon : summary.kind === "final" ? Flag : FileText;
  const title = summary.kind === "final" ? "Final summary" : summary.kind === "alert" ? "Alert write-up" : "Period summary";
  const clips = summary.evidence.filter((ref) => ref.chunk_file);
  return (
    <article className={`summary-card ${summary.kind} ${summary.status}${compact ? " compact" : ""}`}>
      {compact ? null : (
        <header>
          <span className="summary-icon">
            <Icon size={15} />
          </span>
          <div>
            <strong>{title}</strong>
            <span className="mono">{span}</span>
          </div>
          {summary.status === "failed" ? <span className="pill sev critical">Failed</span> : null}
          {summary.status === "quiet" ? <span className="pill">Quiet</span> : null}
        </header>
      )}
      {summary.frames?.length ? (
        <div className="summary-frames" aria-label="Frames LLM looked at">
          {summary.frames.map((url, i) => (
            <a key={url} href={url} target="_blank" rel="noreferrer" title={`Frame ${i + 1}`}>
              <img src={url} alt={`Key frame ${i + 1}`} loading="lazy" />
              <span>{i + 1}</span>
            </a>
          ))}
        </div>
      ) : null}
      <div className="summary-text">{summary.text}</div>
      {clips.length > 0 && onOpenAlert ? (
        <div className="evidence-links">
          {clips.map((ref) => (
            <a
              key={`${ref.chunk_file}-${ref.at_ms}`}
              href={ref.video_url ? `${ref.video_url}#t=${(ref.seek_offset_sec ?? 0).toFixed(2)}` : undefined}
              target="_blank"
              rel="noreferrer"
              className="evidence-link"
              title={ref.note}
            >
              <Clapperboard size={12} />
              <span className="mono">{formatTimeline(kind, ref.at_ms)}</span>
              {ruleLabel(ref.label)}
            </a>
          ))}
        </div>
      ) : null}
      {compact ? null : (
        <footer className="summary-meta">
          LLM · {summary.attempts} attempt{summary.attempts === 1 ? "" : "s"}
        </footer>
      )}
    </article>
  );
}
