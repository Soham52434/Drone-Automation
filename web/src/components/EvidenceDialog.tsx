import { Check, ChevronDown, ChevronLeft, ChevronRight, Download, FileJson, LoaderCircle, Sparkles, VideoOff, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { SessionKind, Summary } from "../api/types";
import { type AlertRecord, ruleLabel } from "../lib/analysisFeed";
import { ClassChips } from "./ClassChips";
import { CLIP_LABELS, RuleBadge, severityLabel } from "./icons";
import { SummaryCard } from "./SummaryList";

interface EvidenceDialogProps {
  record: AlertRecord;
  index: number;
  total: number;
  acknowledged: boolean;
  kind: SessionKind;
  /** LLM detailed write-up for this alert, when the session asked for one. */
  writeUp: Summary | null;
  writeUpPending: boolean;
  onClose: () => void;
  onAcknowledge: () => void;
  onPrevious: () => void;
  onNext: () => void;
}

export function EvidenceDialog({
  record,
  index,
  total,
  acknowledged,
  kind,
  writeUp,
  writeUpPending,
  onClose,
  onAcknowledge,
  onPrevious,
  onNext,
}: EvidenceDialogProps) {
  const [showParse, setShowParse] = useState(false);
  const severity = record.severity || "warn";

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight") onNext();
      if (event.key === "ArrowLeft") onPrevious();
      if (event.key.toLowerCase() === "a" && !acknowledged) onAcknowledge();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onNext, onPrevious, onAcknowledge, acknowledged]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="evidence"
        role="dialog"
        aria-modal="true"
        aria-label={`${ruleLabel(record.rule)} alert evidence`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="evidence-stage">
          {record.proofUrl ? (
            <video key={record.proofUrl} src={record.proofUrl} controls autoPlay muted playsInline />
          ) : (
            <div className="evidence-missing">
              {record.clip === "saving" ? <LoaderCircle className="spin" size={30} /> : <VideoOff size={30} />}
              <span>{record.clip === "saving" ? "Saving the clip for this alert…" : "No clip was saved for this alert."}</span>
            </div>
          )}
        </div>

        <aside className="evidence-facts">
          <header className="evidence-head">
            <RuleBadge rule={record.rule} severity={severity} size="lg" />
            <div>
              <p className="eyebrow">
                Incident {index + 1} of {total}
              </p>
              <h3>{ruleLabel(record.rule)}</h3>
            </div>
            <button type="button" className="icon-btn ghost" aria-label="Close" onClick={onClose}>
              <X size={18} />
            </button>
          </header>

          <div className="fact-row">
            <span className={`pill sev ${severity}`}>{severityLabel(severity)}</span>
            <span className={`pill clip ${record.clip}`}>{CLIP_LABELS[record.clip]}</span>
            {acknowledged ? (
              <span className="pill ok">
                <Check size={12} /> Acknowledged
              </span>
            ) : null}
          </div>

          <dl className="facts">
            <dt>Timeframe</dt>
            <dd className="mono">{record.timeframe || "—"}</dd>
            {record.location ? (
              <>
                <dt>Where</dt>
                <dd>{record.location}</dd>
              </>
            ) : null}
            <dt>Vision model saw</dt>
            <dd>{record.text}</dd>
            {record.note ? (
              <>
                <dt>Alert classifier</dt>
                <dd>{record.note}</dd>
              </>
            ) : null}
          </dl>

          <ClassChips classes={record.classes} max={8} />

          {writeUp ? (
            <div className="write-up">
              <p className="eyebrow">
                <Sparkles size={12} /> LLM write-up
              </p>
              <SummaryCard kind={kind} summary={writeUp} compact />
            </div>
          ) : writeUpPending && record.clip !== "failed" ? (
            <p className="write-up pending">
              <LoaderCircle size={14} className="spin" /> The LLM is writing a detailed write-up…
            </p>
          ) : null}

          {record.detail ? (
            <div className="parse-block">
              <button type="button" className="link-btn" onClick={() => setShowParse((v) => !v)}>
                <FileJson size={14} /> {showParse ? "Hide" : "Show"} vision parse
                <ChevronDown size={14} className={showParse ? "rot" : ""} />
              </button>
              {showParse ? <pre className="vision-json">{record.detail}</pre> : null}
            </div>
          ) : null}

          <footer className="evidence-actions">
            <div className="nav-pair">
              <button type="button" className="icon-btn" aria-label="Previous incident" onClick={onPrevious} disabled={index <= 0}>
                <ChevronLeft size={18} />
              </button>
              <button
                type="button"
                className="icon-btn"
                aria-label="Next incident"
                onClick={onNext}
                disabled={index >= total - 1}
              >
                <ChevronRight size={18} />
              </button>
            </div>
            {record.proofUrl ? (
              <a className="btn btn-ghost" href={record.proofUrl} download>
                <Download size={15} /> Clip
              </a>
            ) : null}
            <button type="button" className="btn btn-primary" onClick={onAcknowledge} disabled={acknowledged}>
              <Check size={15} /> {acknowledged ? "Acknowledged" : "Acknowledge"}
            </button>
          </footer>
          <p className="kbd-hint">
            <kbd>←</kbd> <kbd>→</kbd> browse · <kbd>A</kbd> acknowledge · <kbd>Esc</kbd> close
          </p>
        </aside>
      </div>
    </div>
  );
}
