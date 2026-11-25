export type SessionKind = "live" | "upload";
export type SessionStatus = "idle" | "streaming" | "ready" | "ended";
export type ChunkTrigger = "manual" | "alert";

export interface Session {
  id: string;
  kind: SessionKind;
  title: string;
  status: SessionStatus;
  created_ms: number;
  duration_ms: number | null;
  source_url: string | null;
  watch_brief: string;
  llm: SessionLlm;
}

export interface SessionLlm {
  enabled: boolean;
  summary_interval_minutes: number;
  detailed_alerts: boolean;
  advanced_analytics: boolean;
}

export type SummaryKind = "alert" | "period" | "final";

export interface SummaryEvidence {
  at_ms: number;
  label: string;
  note: string;
  chunk_file: string | null;
  seek_offset_sec: number | null;
  video_url?: string | null;
}

export interface Summary {
  kind: SummaryKind;
  start_ms: number;
  end_ms: number;
  created_ms: number;
  status: "ok" | "quiet" | "failed";
  text: string;
  model: string;
  attempts: number;
  alert_key: string | null;
  evidence: SummaryEvidence[];
  /** Keyframe image URLs the LLM looked at. */
  frames: string[];
}

export interface Chunk {
  chunk_file: string;
  chunk_start_ms: number;
  chunk_end_ms: number;
  detection_ms: number;
  seek_offset_sec: number;
  duration_sec: number;
  frame_count: number;
  fps: number;
  trigger: ChunkTrigger;
  created_ms: number;
  video_url: string;
  metadata_url: string;
}

export interface SessionDetail extends Session {
  chunks: Chunk[];
}

export interface LiveStats {
  frames_received: number;
  frames_buffered: number;
  buffered_seconds: number;
  latest_timestamp_ms: number | null;
}

export interface SessionDescriptionMessage {
  sdp: string;
  type: string;
}

export interface ClassHit {
  name: string;
  score: number;
  count: number;
}

export interface ClassCount {
  name: string;
  frames: number;
  best_score: number;
  alerts: number;
}

export interface HourDigest {
  day: string;
  hour: string;
  start_ms: number;
  frames: number;
  alerts: number;
  classes: ClassCount[];
  first_ms: number | null;
  last_ms: number | null;
}

export interface IndexedFrame {
  observation_id: string;
  timestamp_ms: number;
  day: string;
  hour: string;
  minute: string;
  summary: string;
  label: string;
  confidence: number;
  classes: string[];
  scene: string;
  alert: { rule: string; severity: string | null; video_url: string | null; seek_offset_sec: number | null } | null;
}

export interface ChatClip {
  source: "alert" | "video";
  url: string;
  start_sec: number;
  label: string;
}

export interface FramePlan {
  classes: string[];
  start_ms: number | null;
  end_ms: number | null;
  alerts_only: boolean;
  unmatched_terms: string[];
  confident: boolean;
  interpretation: string;
  planner: "llm" | "keywords";
}

export interface EntityMatch {
  description: string;
  class_name: string;
  signature: string;
  sightings: number;
  visits: { start_ms: number; end_ms: number; sightings: number }[];
}

export interface ChatTurn {
  thread_id: string;
  status: "answered" | "needs_verification";
  intent: "frames" | "summary" | "sightings";
  answer: string;
  plan: FramePlan | null;
  frames: IndexedFrame[];
  total: number;
  clips: ChatClip[];
  verification: {
    question: string;
    proposed: string[];
    available: ClassCount[];
    unmatched_terms: string[];
    interpretation: string;
  } | null;
  hours: HourDigest[];
  /** Advanced analytics: matched entities and their separate visits. */
  entities: EntityMatch[];
  llm_used: boolean;
  classes: ClassCount[];
  /** Why the LLM was skipped (quota, timeout); empty when it was used or not wanted. */
  notice: string;
}


export interface ClassActivity {
  name: string;
  frames: number;
  first_ms: number;
  last_ms: number;
  best_score: number;
  avg_score: number;
  alerts: number;
  /** [start_ms, end_ms] runs of consecutive readings carrying this tag. */
  spans: [number, number][];
}

export interface TaggedReading {
  timestamp_ms: number;
  /** [class, score], strongest first. */
  classes: [string, number][];
  scene: string;
  summary: string;
  label: string;
  alert_rule: string | null;
  /** Advanced analytics: the LLM's entity descriptions for this reading. */
  descriptions: string[];
}

/** Session telemetry built from class tags. `log` is newest first and capped; `readings` is the full count. */
export interface SessionTelemetry {
  readings: number;
  alerts: number;
  first_ms: number | null;
  last_ms: number | null;
  duration_ms: number;
  classes: ClassActivity[];
  log: TaggedReading[];
}

export interface CostLine {
  key: string;
  label: string;
  requests: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
  usd: number;
}

/** LLM/API usage for one session; `usd` is what it would cost at paid-tier prices. */
export interface SessionCost {
  requests: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
  usd: number;
  by_job: CostLine[];
  by_model: CostLine[];
  /** Project-wide requests today (Pacific day) against each model's free daily limit. */
  quotas: { model: string; label: string; requests_today: number; free_per_day: number | null }[];
}
