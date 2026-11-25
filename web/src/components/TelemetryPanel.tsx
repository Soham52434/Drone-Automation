import { Activity, Clock3, ListFilter, ShieldAlert, Tags } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { Session, SessionTelemetry } from "../api/types";
import { ruleLabel } from "../lib/analysisFeed";
import { formatTimeline } from "../lib/format";
import { formatDuration, matchesClasses } from "../lib/telemetry";
import { PresenceTrack } from "./charts/PresenceTrack";
import { ClassChips, classIcon, keyClassesFirst } from "./ClassChips";

interface TelemetryPanelProps {
  session: Session;
  /** Grows as readings arrive; the report is re-fetched (at most every few seconds) while it does. */
  readingCount: number;
}

const REFRESH_MS = 4_000;
const LOG_PAGE = 60;

/** Session telemetry from class tags: what was seen, when, how often, and the tagged reading log. */
export function TelemetryPanel({ session, readingCount }: TelemetryPanelProps) {
  const [telemetry, setTelemetry] = useState<SessionTelemetry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Set<string>>(new Set());
  const [shown, setShown] = useState(LOG_PAGE);
  const lastFetch = useRef(0);

  useEffect(() => {
    let alive = true;
    const wait = Math.max(0, lastFetch.current + REFRESH_MS - Date.now());
    const timer = window.setTimeout(() => {
      lastFetch.current = Date.now();
      api
        .telemetry(session.id)
        .then((next) => {
          if (!alive) return;
          setTelemetry(next);
          setError(null);
        })
        .catch((err) => alive && setError(err instanceof Error ? err.message : "Could not load telemetry"));
    }, wait);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [session.id, readingCount]);

  const classes = useMemo(() => keyClassesFirst(telemetry?.classes ?? []), [telemetry]);
  const log = useMemo(() => (telemetry?.log ?? []).filter((r) => matchesClasses(r.classes, filter)), [telemetry, filter]);
  const time = (ms: number) => formatTimeline(session.kind, ms);

  if (error && !telemetry) return <p className="empty-hint">{error}</p>;
  if (!telemetry) return <p className="empty-hint">Loading telemetry…</p>;
  if (telemetry.readings === 0) {
    return (
      <div className="empty-hint">
        <Activity size={22} />
        <span>No readings yet. Telemetry is built from the class tags on every vision reading.</span>
      </div>
    );
  }

  const toggle = (name: string) => {
    setShown(LOG_PAGE);
    setFilter((current) => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  return (
    <div className="telemetry">
      <div className="telemetry-stats">
        <Tile icon={<Activity size={14} />} label="Readings" value={String(telemetry.readings)} />
        <Tile icon={<Clock3 size={14} />} label="Duration" value={formatDuration(telemetry.duration_ms)} />
        <Tile icon={<Tags size={14} />} label="Classes seen" value={String(telemetry.classes.length)} />
        <Tile icon={<ShieldAlert size={14} />} label="Alerts" value={String(telemetry.alerts)} hot={telemetry.alerts > 0} />
      </div>

      {telemetry.first_ms !== null && telemetry.last_ms !== null && classes.length ? (
        <PresenceTrack classes={classes} startMs={telemetry.first_ms} endMs={telemetry.last_ms} formatTime={time} />
      ) : null}

      <section>
        <h5>By class</h5>
        <div className="class-table">
          <table>
            <thead>
              <tr>
                <th>Class</th>
                <th>Readings</th>
                <th>First seen</th>
                <th>Last seen</th>
                <th>Best · avg</th>
                <th>Alerts</th>
              </tr>
            </thead>
            <tbody>
              {classes.map((c) => {
                const Icon = classIcon(c.name);
                return (
                  <tr key={c.name} className={filter.has(c.name) ? "on" : ""} onClick={() => toggle(c.name)}>
                    <td>
                      <span className="cell-class">
                        <Icon size={13} /> {c.name}
                      </span>
                    </td>
                    <td className="mono">{c.frames}</td>
                    <td className="mono">{time(c.first_ms)}</td>
                    <td className="mono">{time(c.last_ms)}</td>
                    <td className="mono">
                      {Math.round(c.best_score * 100)}% · {Math.round(c.avg_score * 100)}%
                    </td>
                    <td className={`mono${c.alerts ? " hot" : ""}`}>{c.alerts}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h5>
          <ListFilter size={13} /> Tagged log
          <span className="muted">
            {filter.size ? `${log.length} matching` : `${telemetry.readings} readings`}
            {telemetry.readings > telemetry.log.length ? ` · latest ${telemetry.log.length} kept here` : ""}
          </span>
        </h5>
        <div className="log-filters" role="group" aria-label="Filter the log by class">
          <button type="button" className={`class-pick${filter.size === 0 ? " on" : ""}`} onClick={() => setFilter(new Set())}>
            All
          </button>
          {classes.map((c) => {
            const Icon = classIcon(c.name);
            return (
              <button
                key={c.name}
                type="button"
                className={`class-pick${filter.has(c.name) ? " on" : ""}`}
                aria-pressed={filter.has(c.name)}
                onClick={() => toggle(c.name)}
              >
                <Icon size={13} /> {c.name}
              </button>
            );
          })}
        </div>
        <ol className="tag-log">
          {log.slice(0, shown).map((r) => (
            <li key={`${r.timestamp_ms}-${r.label}`} className={r.alert_rule ? "alert" : ""}>
              <div className="tag-log-top">
                <time className="mono">{time(r.timestamp_ms)}</time>
                {r.scene ? <span className="tag-scene">{r.scene}</span> : null}
                {r.alert_rule ? <span className="pill sev warn">{ruleLabel(r.alert_rule)} alert</span> : null}
              </div>
              {r.classes.length ? (
                <ClassChips classes={r.classes.map(([name, score]) => ({ name, score, count: 1 }))} max={6} />
              ) : (
                <span className="muted small">No classes</span>
              )}
              {r.descriptions.length ? (
                <div className="tag-described">
                  {r.descriptions.map((d) => (
                    <span key={d} title="Described by the LLM (advanced analytics)">
                      {d}
                    </span>
                  ))}
                </div>
              ) : null}
              {r.summary ? <p>{r.summary}</p> : null}
            </li>
          ))}
        </ol>
        {log.length > shown ? (
          <button type="button" className="btn btn-ghost sm" onClick={() => setShown((n) => n + LOG_PAGE)}>
            Show {Math.min(LOG_PAGE, log.length - shown)} more
          </button>
        ) : null}
      </section>
    </div>
  );
}

function Tile({ icon, label, value, hot = false }: { icon: ReactNode; label: string; value: string; hot?: boolean }) {
  return (
    <div className={`telemetry-tile${hot ? " hot" : ""}`}>
      <span className="tile-label">
        {icon} {label}
      </span>
      <strong>{value}</strong>
    </div>
  );
}
