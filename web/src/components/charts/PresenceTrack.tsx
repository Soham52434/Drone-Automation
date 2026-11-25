import { useState } from "react";

import type { ClassActivity } from "../../api/types";
import { formatDuration } from "../../lib/telemetry";
import { classIcon } from "../ClassChips";

interface PresenceTrackProps {
  classes: readonly ClassActivity[];
  startMs: number;
  endMs: number;
  formatTime: (ms: number) => string;
}

/** When each class was in view: one labelled row per class, one segment per run of readings. */
export function PresenceTrack({ classes, startMs, endMs, formatTime }: PresenceTrackProps) {
  const [hover, setHover] = useState<{ name: string; span: [number, number] } | null>(null);
  const span = Math.max(1, endMs - startMs);
  const pct = (ms: number) => ((ms - startMs) / span) * 100;
  return (
    <figure className="presence-track">
      <figcaption>
        <span>When each class was in view</span>
        {hover ? (
          <strong className="mono">
            {hover.name} · {formatTime(hover.span[0])}–{formatTime(hover.span[1])}
            {hover.span[1] > hover.span[0] ? ` · ${formatDuration(hover.span[1] - hover.span[0])}` : ""}
          </strong>
        ) : null}
      </figcaption>
      <div className="track-rows">
        {classes.map((activity) => {
          const Icon = classIcon(activity.name);
          return (
            <div key={activity.name} className="track-row">
              <span className="track-label">
                <Icon size={12} /> {activity.name}
              </span>
              <div className="track-lane">
                {activity.spans.map((run) => (
                  <button
                    key={`${run[0]}-${run[1]}`}
                    type="button"
                    className={`track-seg${hover?.name === activity.name && hover.span === run ? " on" : ""}`}
                    style={{ left: `${pct(run[0])}%`, width: `max(3px, ${pct(run[1]) - pct(run[0])}%)` }}
                    aria-label={`${activity.name} from ${formatTime(run[0])} to ${formatTime(run[1])}`}
                    onPointerEnter={() => setHover({ name: activity.name, span: run })}
                    onPointerLeave={() => setHover(null)}
                    onFocus={() => setHover({ name: activity.name, span: run })}
                    onBlur={() => setHover(null)}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <div className="x-axis mono" aria-hidden>
        <span>{formatTime(startMs)}</span>
        <span>{formatTime(endMs)}</span>
      </div>
    </figure>
  );
}
