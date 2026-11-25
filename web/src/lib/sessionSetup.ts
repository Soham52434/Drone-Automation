/** Slider stops for the summary interval: 1 minute, then every 5 minutes up to an hour. */
export const SUMMARY_INTERVALS: readonly number[] = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60];

export interface LlmSettings {
  /** LLM summaries for this session. The alert classifier still decides alerts either way. */
  enabled: boolean;
  summaryIntervalMinutes: number;
  /** Optional richer LLM write-up for each alert. */
  detailedAlerts: boolean;
  /** The LLM describes people and vehicles in key frames (colour, make, clothing) for repeat-visit questions. */
  advancedAnalytics: boolean;
}

export interface SessionSetup {
  watchBrief: string;
  llm: LlmSettings;
}

export const DEFAULT_LLM: LlmSettings = {
  enabled: true,
  summaryIntervalMinutes: 60,
  detailedAlerts: false,
  advancedAnalytics: false,
};

export const WATCH_EXAMPLES: readonly string[] = [
  "Alert when a person comes near the front door",
  "Only vehicles entering the driveway",
  "Packages left or taken from the porch",
  "Animals in the yard",
  "Fire or smoke anywhere in view",
  "A boat coming alongside the dock",
];

export function intervalAt(index: number): number {
  const clamped = Math.min(SUMMARY_INTERVALS.length - 1, Math.max(0, Math.round(index)));
  return SUMMARY_INTERVALS[clamped]!;
}

/** Index of the nearest slider stop for a minute value. */
export function intervalIndex(minutes: number): number {
  let best = 0;
  SUMMARY_INTERVALS.forEach((value, index) => {
    if (Math.abs(value - minutes) < Math.abs(SUMMARY_INTERVALS[best]! - minutes)) best = index;
  });
  return best;
}

export function formatInterval(minutes: number): string {
  if (minutes === 60) return "1 hour";
  return minutes === 1 ? "1 minute" : `${minutes} minutes`;
}

export function formatIntervalShort(minutes: number): string {
  return minutes === 60 ? "1 h" : `${minutes} min`;
}

/** Wire format shared by the live JSON body and the upload form fields. */
export function llmPayload(llm: LlmSettings): {
  enabled: boolean;
  summary_interval_minutes: number;
  detailed_alerts: boolean;
  advanced_analytics: boolean;
} {
  return {
    enabled: llm.enabled,
    summary_interval_minutes: intervalAt(intervalIndex(llm.summaryIntervalMinutes)),
    detailed_alerts: llm.enabled && llm.detailedAlerts,
    advanced_analytics: llm.enabled && llm.advancedAnalytics,
  };
}
