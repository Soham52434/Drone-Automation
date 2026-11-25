import { Activity, ChevronDown, Eye, FileText, MapPin, Sparkles, Tags } from "lucide-react";
import { memo, useMemo, useState } from "react";

import type { Session, SessionLlm, Summary } from "../api/types";
import type { AnalysisEntry } from "../lib/analysisFeed";
import { ClassChips } from "./ClassChips";
import { TelemetryPanel } from "./TelemetryPanel";
import { formatIntervalShort } from "../lib/sessionSetup";
import { SummaryList } from "./SummaryList";

interface InsightPanelProps {
  session: Session;
  readings: readonly AnalysisEntry[];
  summaries: readonly Summary[];
  llm: SessionLlm;
  active: boolean;
  summarizing: boolean;
  onOpenAlert: (key: string) => void;
}

type Tab = "detections" | "summaries" | "telemetry";

/** Right column: vision readings and LLM summaries. */
export function InsightPanel({ session, readings, summaries, llm, active, summarizing, onOpenAlert }: InsightPanelProps) {
  const kind = session.kind;
  const [tab, setTab] = useState<Tab>("detections");
  const periodic = summaries.filter((summary) => summary.kind !== "alert");
  return (
    <aside className="panel feed-panel">
      <header className="panel-head tabs-head">
        <div className="tabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === "detections"} className={tab === "detections" ? "active" : ""} onClick={() => setTab("detections")}>
            <Eye size={15} /> Detections <span className="count">{readings.length}</span>
          </button>
          <button type="button" role="tab" aria-selected={tab === "summaries"} className={tab === "summaries" ? "active" : ""} onClick={() => setTab("summaries")}>
            <FileText size={15} /> Summaries <span className="count">{periodic.length}</span>
            {summarizing ? <span className="tab-dot" title="Writing a summary" /> : null}
          </button>
          <button type="button" role="tab" aria-selected={tab === "telemetry"} className={tab === "telemetry" ? "active" : ""} onClick={() => setTab("telemetry")}>
            <Tags size={15} /> Telemetry
          </button>
        </div>
        {tab === "detections" && active ? (
          <span className="activity-tag">
            <Activity size={13} /> Vision active
          </span>
        ) : null}
        {tab === "summaries" && llm.enabled ? (
          <span className="activity-tag" title="LLM summary interval">
            <Sparkles size={13} /> every {formatIntervalShort(llm.summary_interval_minutes)}
          </span>
        ) : null}
      </header>
      <div className="panel-scroll">
        {tab === "detections" ? (
          <DetectionList readings={readings} active={active} />
        ) : tab === "summaries" ? (
          <SummaryList kind={kind} summaries={periodic} llm={llm} summarizing={summarizing} onOpenAlert={onOpenAlert} />
        ) : (
          <TelemetryPanel session={session} readingCount={readings.length} />
        )}
      </div>
    </aside>
  );
}

function DetectionList({ readings, active }: { readings: readonly AnalysisEntry[]; active: boolean }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const newestFirst = useMemo(() => [...readings].reverse(), [readings]);
  if (readings.length === 0) {
    return (
      <div className="empty-hint">
        <Eye size={22} />
        <span>{active ? "Waiting for the vision model's first reading…" : "No readings in this view."}</span>
      </div>
    );
  }
  return (
    <>
      {newestFirst.map((entry, i) => (
        <DetectionCard
          key={entry.id}
          entry={entry}
          latest={i === 0 && active}
          open={expanded === entry.id}
          onToggle={() => setExpanded((current) => (current === entry.id ? null : entry.id))}
        />
      ))}
    </>
  );
}

const DetectionCard = memo(function DetectionCard({
  entry,
  latest,
  open,
  onToggle,
}: {
  entry: AnalysisEntry;
  latest: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const parts = entry.meta.split(" · ");
  const time = parts[parts.length - 1];
  const label = parts.slice(0, -1).join(" · ");
  return (
    <article className={`reading${latest ? " latest" : ""}`}>
      <header>
        <time className="mono">{time}</time>
        <span className="reading-label">{label}</span>
      </header>
      {entry.location ? (
        <p className="reading-place">
          <MapPin size={12} /> {entry.location}
        </p>
      ) : null}
      <p>{entry.text}</p>
      <ClassChips classes={entry.classes} />
      {entry.detail ? (
        <button type="button" className="link-btn" onClick={onToggle} aria-expanded={open}>
          {open ? "Hide" : "Show"} parse <ChevronDown size={13} className={open ? "rot" : ""} />
        </button>
      ) : null}
      {open && entry.detail ? <pre className="vision-json">{entry.detail}</pre> : null}
    </article>
  );
});
