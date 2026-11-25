import type { Chunk, SessionKind } from "../api/types";

export function formatMediaTime(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const mm = String(minutes).padStart(hours > 0 ? 2 : 1, "0");
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function formatClockTime(epochMs: number, locale?: string): string {
  return new Date(epochMs).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** Live sessions use epoch time; uploads use position inside the video. */
export function formatTimeline(kind: SessionKind, ms: number, locale?: string): string {
  return kind === "live" ? formatClockTime(ms, locale) : formatMediaTime(ms);
}

export function describeChunk(kind: SessionKind, chunk: Chunk, locale?: string): string {
  const at = formatTimeline(kind, chunk.detection_ms, locale);
  return `Clip saved at ${at} · ${chunk.duration_sec.toFixed(1)} s · ${chunk.frame_count} frames`;
}

export function chunkPlaybackUrl(chunk: Chunk): string {
  return `${chunk.video_url}#t=${chunk.seek_offset_sec.toFixed(2)}`;
}
