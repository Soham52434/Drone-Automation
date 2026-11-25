import { Check, Clock, LoaderCircle, MapPin, PlayCircle, Sparkles, X } from "lucide-react";

import { type AlertRecord, ruleLabel } from "../lib/analysisFeed";
import { ClassChips } from "./ClassChips";
import { CLIP_LABELS, RuleBadge, severityLabel } from "./icons";

export interface PopupItem {
  sessionId: string;
  sessionTitle: string;
  record: AlertRecord;
  /** LLM write-up, shown only when the session turned detailed alerts on. */
  writeUp: string;
  writeUpPending: boolean;
}

interface AlertPopupsProps {
  items: PopupItem[];
  showSession: boolean;
  onReview: (sessionId: string, key: string) => void;
  onAcknowledge: (sessionId: string, key: string) => void;
  onDismiss: (sessionId: string, key: string) => void;
  onDismissAll: () => void;
}

const VISIBLE = 2;

/** On-screen alert cards. Raised by the alert classifier and shown at once with the vision model's reading; never waits on the clip. */
export function AlertPopups({ items, showSession, onReview, onAcknowledge, onDismiss, onDismissAll }: AlertPopupsProps) {
  if (items.length === 0) return null;
  const visible = items.slice(-VISIBLE).reverse();
  const hidden = items.length - visible.length;
  return (
    <div className="popup-stack" role="region" aria-label="New alerts" aria-live="assertive">
      {visible.map((item) => (
        <AlertPopup
          key={`${item.sessionId}:${item.record.key}`}
          item={item}
          showSession={showSession}
          onReview={() => onReview(item.sessionId, item.record.key)}
          onAcknowledge={() => onAcknowledge(item.sessionId, item.record.key)}
          onDismiss={() => onDismiss(item.sessionId, item.record.key)}
        />
      ))}
      {items.length > 1 ? (
        <div className="popup-more">
          <span>{hidden > 0 ? `${hidden} more alert${hidden === 1 ? "" : "s"}` : `${items.length} alerts`}</span>
          <button type="button" className="link-btn" onClick={onDismissAll}>
            Dismiss all
          </button>
        </div>
      ) : null}
    </div>
  );
}

function AlertPopup({
  item,
  showSession,
  onReview,
  onAcknowledge,
  onDismiss,
}: {
  item: PopupItem;
  showSession: boolean;
  onReview: () => void;
  onAcknowledge: () => void;
  onDismiss: () => void;
}) {
  const { record } = item;
  const severity = record.severity || "warn";
  return (
    <article className={`popup ${severity}`} role="alertdialog" aria-label={`${ruleLabel(record.rule)} alert`}>
      <span className="popup-pulse" aria-hidden />
      <header className="popup-head">
        <RuleBadge rule={record.rule} severity={severity} />
        <div className="popup-title">
          <strong>{ruleLabel(record.rule)} detected</strong>
          <span>
            <span className={`sev-dot ${severity}`} /> {severityLabel(severity)}
            {record.timeframe ? ` · ${record.timeframe}` : ""}
            {showSession ? ` · ${item.sessionTitle}` : ""}
          </span>
        </div>
        <button type="button" className="icon-btn ghost sm" aria-label="Dismiss alert" onClick={onDismiss}>
          <X size={16} />
        </button>
      </header>

      <div className="popup-body">
        {record.clip === "saved" && record.proofUrl ? (
          <button type="button" className="popup-thumb" onClick={onReview} aria-label="Play the alert clip">
            <video src={record.proofUrl} muted autoPlay loop playsInline preload="metadata" />
            <PlayCircle size={26} />
          </button>
        ) : null}
        <div className="popup-copy">
          {record.location ? (
            <span className="popup-place">
              <MapPin size={12} /> {record.location}
            </span>
          ) : null}
          <p>{record.text}</p>
          <ClassChips classes={record.classes} max={4} />
        </div>
      </div>
      {item.writeUp ? (
        <div className="popup-writeup">
          <span>
            <Sparkles size={12} /> LLM write-up
          </span>
          <p>{item.writeUp}</p>
        </div>
      ) : item.writeUpPending ? (
        <div className="popup-writeup pending">
          <LoaderCircle size={12} className="spin" /> The LLM is writing the detailed alert…
        </div>
      ) : null}

      <footer className="popup-foot">
        <span className={`clip-state ${record.clip}`}>
          {record.clip === "saving" ? <LoaderCircle className="spin" size={13} /> : <Clock size={13} />}
          {CLIP_LABELS[record.clip]}
        </span>
        <div className="popup-actions">
          <button type="button" className="btn btn-ghost sm" onClick={onAcknowledge}>
            <Check size={15} /> Acknowledge
          </button>
          <button type="button" className="btn btn-danger sm" onClick={onReview}>
            Review
          </button>
        </div>
      </footer>
    </article>
  );
}
