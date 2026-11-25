import type { ClassHit, SessionKind } from "../api/types";
import { formatTimeline } from "./format";

export interface AnalysisEntry {
  id: string;
  kind: "observation" | "decision" | "alert" | "status" | "error" | "summary";
  text: string;
  meta: string;
  detail: string;
  proofUrl: string;
  timeframe: string;
  startMs: number | null;
  endMs: number | null;
  rule: string;
  severity: string;
  alert: boolean;
  debounced: boolean;
  /** Alert-classifier explanation for a decision entry; empty otherwise. */
  note: string;
  /** Object classes Vision model saw (person, vehicle, …), strongest first. */
  classes: ClassHit[];
  /** Where the vision model says this was, e.g. "driveway" or "indoor room". */
  location: string;
}

/** Where the evidence clip for an alert stands. */
export type ClipState = "saving" | "saved" | "failed" | "cooldown";

/** One incident: an alert-classifier alert merged with the saved clip that followed it. */
export interface AlertRecord extends AnalysisEntry {
  /** Stable across reconnects: the alert-classifier window start, or the clip start. */
  key: string;
  clip: ClipState;
}

const noSpan = { startMs: null, endMs: null };

function blank(id: string, kind: AnalysisEntry["kind"]): AnalysisEntry {
  return {
    id,
    kind,
    text: "",
    meta: "",
    detail: "",
    proofUrl: "",
    timeframe: "",
    ...noSpan,
    rule: "",
    severity: "",
    alert: false,
    debounced: false,
    note: "",
    classes: [],
    location: "",
  };
}

export function analysisEntry(
  event: string,
  data: Record<string, unknown>,
  seq: number,
  kind: SessionKind = "upload",
): AnalysisEntry | null {
  if (event === "observation") {
    const reading = visionReading(data, "The vision model returned no description.");
    return {
      ...blank(`observation-${seq}`, "observation"),
      text: reading.text,
      detail: reading.detail,
      ...windowTimes(data.timestamp_ms, data.timestamp_ms),
      meta: `${stringField(data.label, "activity")} · ${percent(data.confidence)} · ${formatTimeline(kind, numberField(data.timestamp_ms))}`,
      ...placeOf(data),
    };
  }
  if (event === "decision") {
    const decision = record(data.decision);
    const alert = decision.alert === true;
    const rules = Array.isArray(decision.rules_fired) ? decision.rules_fired.join(", ") : "";
    const timeframe = spanText(data.start_ms, data.end_ms, kind);
    return {
      ...blank(`decision-${seq}`, "decision"),
      text: alert ? "The alert classifier raised an alert for this window." : "The alert classifier did not raise an alert.",
      timeframe,
      ...windowTimes(data.start_ms, data.end_ms),
      meta: [timeframe, rules, percent(decision.confidence), stringField(decision.detail, "")].filter(Boolean).join(" · "),
      rule: ruleOf(decision),
      severity: severityOf(decision),
      alert,
      note: stringField(decision.detail, ""),
    };
  }
  if (event === "alert") {
    const observation = record(data.observation);
    const decision = record(data.decision);
    const debounced = data.debounced === true;
    const reading = visionReading(observation, "Alert");
    const proof = alertProof(data, kind);
    return {
      ...blank(`alert-${seq}`, "alert"),
      text: debounced ? "Alert stayed inside the cooldown, so no second clip was saved." : reading.text,
      detail: debounced ? "" : reading.detail,
      proofUrl: debounced ? "" : proof.url,
      timeframe: debounced ? "" : proof.timeframe,
      ...(debounced ? noSpan : windowTimes(data.chunk_start_ms, data.chunk_end_ms)),
      meta: `${stringField(observation.label, "alert")} · ${percent(observation.confidence)}`,
      rule: ruleOf(decision),
      severity: severityOf(decision),
      alert: true,
      debounced,
      ...placeOf(observation),
    };
  }
  if (event === "status") {
    return {
      ...blank(`status-${seq}`, "status"),
      text: stringField(data.detail, stringField(data.status, "Status update")),
      meta: stringField(data.status, ""),
    };
  }
  if (event === "summary") {
    return {
      ...blank(`summary-${seq}`, "summary"),
      text: stringField(data.text, ""),
      timeframe: spanText(data.start_ms, data.end_ms, kind),
      ...windowTimes(data.start_ms, data.end_ms),
      meta: stringField(data.kind, "period"),
      rule: stringField(data.alert_key, ""),
      note: stringField(data.status, ""),
    };
  }
  if (event === "error") {
    return {
      ...blank(`error-${seq}`, "error"),
      text: stringField(data.detail, "Something went wrong."),
      meta: "Error",
    };
  }
  return null;
}

/** Classes and location from an observation payload. */
function placeOf(data: Record<string, unknown>): Pick<AnalysisEntry, "classes" | "location"> {
  const classes = Array.isArray(data.classes)
    ? data.classes
        .map(record)
        .filter((hit) => typeof hit.name === "string")
        .map((hit) => ({
          name: String(hit.name),
          score: typeof hit.score === "number" ? hit.score : 0,
          count: typeof hit.count === "number" ? hit.count : 1,
        }))
    : [];
  return { classes, location: stringField(data.location, "") };
}

/** Write-up text the LLM produced for an alert, if any. */
export function alertWriteUp(entries: readonly AnalysisEntry[], key: string): string {
  for (let i = entries.length - 1; i >= 0; i -= 1) {
    const entry = entries[i]!;
    if (entry.kind === "summary" && entry.meta === "alert" && entry.rule === key && entry.note !== "failed") return entry.text;
  }
  return "";
}

export function alertRecords(entries: readonly AnalysisEntry[]): AlertRecord[] {
  const records: AlertRecord[] = [];
  let pending: AlertRecord | null = null;
  let lastReading: AnalysisEntry | null = null;
  const flush = () => {
    if (pending) records.push(pending);
    pending = null;
  };
  for (const entry of entries) {
    if (entry.kind === "observation") {
      lastReading = entry;
    } else if (entry.kind === "decision") {
      flush();
      if (entry.alert) pending = raisedAlert(entry, lastReading);
    } else if (entry.kind === "alert" && !entry.debounced) {
      if (pending?.clip === "saving") {
        pending = {
          ...entry,
          key: pending.key,
          clip: entry.proofUrl ? "saved" : "failed",
          rule: entry.rule || pending.rule,
          severity: entry.severity || pending.severity,
          note: pending.note,
        };
      } else {
        flush();
        pending = { ...entry, key: `clip-${entry.startMs ?? entry.id}`, clip: entry.proofUrl ? "saved" : "failed" };
      }
    } else if (entry.kind === "alert" && pending?.clip === "saving") {
      pending = withClip(pending, "cooldown");
    } else if (entry.kind === "error" && pending?.clip === "saving" && /clip/i.test(entry.text)) {
      pending = withClip(pending, "failed");
      flush();
    }
  }
  flush();
  return records;
}

function withClip(record: AlertRecord, clip: ClipState): AlertRecord {
  return { ...record, clip };
}

/** An alert-classifier alert shows the vision reading from its window right away; the clip follows. */
function raisedAlert(decision: AnalysisEntry, reading: AnalysisEntry | null): AlertRecord {
  const inWindow =
    reading !== null &&
    reading.startMs !== null &&
    (decision.startMs === null || reading.startMs >= decision.startMs);
  return {
    ...decision,
    key: `window-${decision.startMs ?? decision.id}`,
    clip: "saving",
    text: inWindow ? reading.text : decision.note || decision.text,
    detail: inWindow ? reading.detail : "",
    classes: inWindow ? reading.classes : [],
    location: inWindow ? reading.location : "",
  };
}

export function openAlertCount(records: readonly AlertRecord[], acked: ReadonlySet<string>): number {
  return records.filter((record) => !acked.has(record.key)).length;
}

const RULE_LABELS: Record<string, string> = {
  person_on_property: "Person",
  vehicle: "Vehicle",
  package_delivery: "Package",
  animal: "Animal",
  hazard: "Hazard",
  brief_match: "Watch brief",
  loitering: "Loitering",
  after_hours: "After hours",
  none: "Clear",
};

export function ruleLabel(rule: string): string {
  return RULE_LABELS[rule] ?? (rule ? rule.replaceAll("_", " ") : "Activity");
}

function ruleOf(decision: Record<string, unknown>): string {
  const rules = decision.rules_fired;
  return Array.isArray(rules) && typeof rules[0] === "string" ? rules[0] : "";
}

function severityOf(decision: Record<string, unknown>): string {
  return decision.severity === "info" || decision.severity === "warn" || decision.severity === "critical"
    ? decision.severity
    : "";
}

function alertProof(data: Record<string, unknown>, kind: SessionKind): { url: string; timeframe: string } {
  return {
    url: stringField(data.video_url, ""),
    timeframe: spanText(data.chunk_start_ms, data.chunk_end_ms, kind),
  };
}

function windowTimes(start: unknown, end: unknown): { startMs: number | null; endMs: number | null } {
  return {
    startMs: typeof start === "number" ? start : null,
    endMs: typeof end === "number" ? end : null,
  };
}

function spanText(start: unknown, end: unknown, kind: SessionKind): string {
  if (typeof start !== "number" || typeof end !== "number") return "";
  return `${formatTimeline(kind, start)}–${formatTimeline(kind, end)}`;
}

function visionReading(data: Record<string, unknown>, fallback: string): { text: string; detail: string } {
  const raw = record(data.raw);
  const reasoning = stringField(raw.reasoning, "");
  return {
    text: reasoning || stringField(data.summary, fallback),
    detail: Object.keys(raw).length > 0 ? JSON.stringify(raw, null, 2) : "",
  };
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function stringField(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function numberField(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

function percent(value: unknown): string {
  const number = typeof value === "number" ? value : 0;
  return `${Math.round(number * 100)}%`;
}
