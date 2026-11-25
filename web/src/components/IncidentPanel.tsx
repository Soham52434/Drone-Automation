import { CheckCheck, CircleCheck, Clapperboard, LoaderCircle, Play, ShieldCheck, VideoOff } from "lucide-react";

import type { Chunk, SessionKind } from "../api/types";
import { type AlertRecord, ruleLabel } from "../lib/analysisFeed";
import { ChunkMessage } from "./ChunkMessage";
import { RuleBadge } from "./icons";

export type IncidentFilter = "all" | "open" | "footage";

interface IncidentPanelProps {
  kind: SessionKind;
  records: readonly AlertRecord[];
  acked: ReadonlySet<string>;
  filter: IncidentFilter;
  selectedKey: string | null;
  manualClips: readonly Chunk[];
  onFilter: (filter: IncidentFilter) => void;
  onOpen: (key: string) => void;
  onAcknowledgeAll: () => void;
}

export function IncidentPanel({
  kind,
  records,
  acked,
  filter,
  selectedKey,
  manualClips,
  onFilter,
  onOpen,
  onAcknowledgeAll,
}: IncidentPanelProps) {
  const open = records.filter((r) => !acked.has(r.key)).length;
  const withClip = records.filter((r) => r.proofUrl).length;
  const visible = records
    .filter((r) => (filter === "open" ? !acked.has(r.key) : filter === "footage" ? Boolean(r.proofUrl) : true))
    .slice()
    .reverse();

  return (
    <section className="panel incident-panel">
      <header className="panel-head">
        <h3>
          <ShieldCheck size={15} /> Incidents
        </h3>
        <div className="segmented" role="tablist" aria-label="Filter incidents">
          <Segment active={filter === "all"} onClick={() => onFilter("all")} label="All" count={records.length} />
          <Segment active={filter === "open"} onClick={() => onFilter("open")} label="Open" count={open} hot={open > 0} />
          <Segment active={filter === "footage"} onClick={() => onFilter("footage")} label="With clip" count={withClip} />
        </div>
        {open > 0 ? (
          <button type="button" className="btn btn-ghost sm push" onClick={onAcknowledgeAll}>
            <CheckCheck size={15} /> Acknowledge all
          </button>
        ) : null}
      </header>
      <div className="panel-scroll">
        {visible.length === 0 && manualClips.length === 0 ? (
          <div className="empty-hint">
            <ShieldCheck size={22} />
            <span>
              {records.length === 0
                ? "No incidents. The alert classifier raises one when a window matches the watch brief."
                : "Nothing in this filter."}
            </span>
          </div>
        ) : null}
        {visible.map((record) => {
          const isAcked = acked.has(record.key);
          return (
            <button
              key={record.key}
              type="button"
              className={`incident${isAcked ? " is-acked" : ""}${record.key === selectedKey ? " is-selected" : ""}`}
              onClick={() => onOpen(record.key)}
            >
              <RuleBadge rule={record.rule} severity={record.severity} size="sm" />
              <span className="incident-copy">
                <span className="incident-line">
                  <strong>{ruleLabel(record.rule)}</strong>
                  <span className="mono">{record.timeframe || "time pending"}</span>
                  {!isAcked ? <span className="new-dot" title="Not acknowledged" /> : null}
                </span>
                <span className="incident-text">{record.text}</span>
              </span>
              <ClipTag record={record} />
              {isAcked ? <CircleCheck size={16} className="acked-icon" aria-label="Acknowledged" /> : null}
            </button>
          );
        })}
        {manualClips.length > 0 ? (
          <div className="manual-clips">
            <h4>
              <Clapperboard size={14} /> Saved clips
            </h4>
            {manualClips.map((chunk) => (
              <ChunkMessage key={chunk.chunk_file} kind={kind} chunk={chunk} />
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function ClipTag({ record }: { record: AlertRecord }) {
  if (record.proofUrl)
    return (
      <span className="clip-tag saved">
        <Play size={12} /> Clip
      </span>
    );
  if (record.clip === "saving")
    return (
      <span className="clip-tag saving">
        <LoaderCircle size={12} className="spin" /> Saving
      </span>
    );
  return (
    <span className="clip-tag none">
      <VideoOff size={12} /> {record.clip === "cooldown" ? "Cooldown" : "No clip"}
    </span>
  );
}

function Segment({
  active,
  onClick,
  label,
  count,
  hot = false,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
  hot?: boolean;
}) {
  return (
    <button type="button" role="tab" aria-selected={active} className={`segment${active ? " active" : ""}`} onClick={onClick}>
      {label}
      <span className={`segment-count${hot ? " hot" : ""}`}>{count}</span>
    </button>
  );
}
