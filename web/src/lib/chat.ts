import type { IndexedFrame } from "../api/types";

export interface MinuteGroup {
  label: string;
  frames: IndexedFrame[];
}

export interface HourGroup {
  key: string;
  day: string;
  hour: string;
  frames: IndexedFrame[];
  minutes: MinuteGroup[];
}

/** Day → hour → minute, the same shape as the graph index. Order follows the frames (oldest first). */
export function groupFramesByHour(frames: readonly IndexedFrame[]): HourGroup[] {
  const hours: HourGroup[] = [];
  for (const frame of frames) {
    const key = `${frame.day}|${frame.hour}`;
    let hour = hours[hours.length - 1];
    if (!hour || hour.key !== key) {
      hour = { key, day: frame.day, hour: frame.hour, frames: [], minutes: [] };
      hours.push(hour);
    }
    hour.frames.push(frame);
    let minute = hour.minutes[hour.minutes.length - 1];
    if (!minute || minute.label !== frame.minute) {
      minute = { label: frame.minute, frames: [] };
      hour.minutes.push(minute);
    }
    minute.frames.push(frame);
  }
  return hours;
}
