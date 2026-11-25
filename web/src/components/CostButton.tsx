import { CircleDollarSign, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { Session, SessionCost } from "../api/types";
import { costBadge, formatTokens, formatUsd, quotaShare } from "../lib/cost";

interface CostButtonProps {
  session: Session;
  /** Grows with every analysis event; the cost is re-fetched (at most every few seconds) while it does. */
  activity: number;
}

const REFRESH_MS = 5_000;

/** Beside Ask: what this session's LLM/API calls used, in requests, tokens, and dollars at paid prices. */
export function CostButton({ session, activity }: CostButtonProps) {
  const [cost, setCost] = useState<SessionCost | null>(null);
  const [open, setOpen] = useState(false);
  const lastFetch = useRef(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const wait = open ? 0 : Math.max(0, lastFetch.current + REFRESH_MS - Date.now());
    const timer = window.setTimeout(() => {
      lastFetch.current = Date.now();
      api
        .cost(session.id)
        .then((next) => alive && setCost(next))
        .catch(() => undefined);
    }, wait);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [session.id, activity, open]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return (
    <div className="cost" ref={box}>
      <button
        type="button"
        className={`btn ${open ? "btn-primary" : "btn-ghost"}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title="LLM and API usage for this session"
      >
        <CircleDollarSign size={15} /> Cost
        {cost ? <span className="cost-badge mono">{costBadge(cost)}</span> : null}
      </button>
      {open ? <CostPopover cost={cost} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}

function CostPopover({ cost, onClose }: { cost: SessionCost | null; onClose: () => void }) {
  return (
    <div className="cost-pop" role="dialog" aria-label="Session cost">
      <header>
        <div>
          <span className="cost-kicker">This session</span>
          <strong className="cost-total mono">{cost ? formatUsd(cost.usd) : "…"}</strong>
          <span className="cost-note">at paid-tier prices · the free tier bills $0</span>
        </div>
        <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
          <X size={15} />
        </button>
      </header>

      {!cost ? (
        <p className="empty-hint">Loading…</p>
      ) : cost.requests === 0 ? (
        <p className="empty-hint">No model requests yet. The alert classifier runs on each 10 s window; summaries, chat, and advanced analytics use the LLM.</p>
      ) : (
        <>
          <div className="cost-tiles">
            <Tile label="Requests" value={String(cost.requests)} />
            <Tile label="Input tokens" value={formatTokens(cost.input_tokens)} />
            <Tile label="Output tokens" value={formatTokens(cost.output_tokens)} />
          </div>
          {cost.failed ? (
            <p className="cost-failed">
              <TriangleAlert size={13} /> {cost.failed} request{cost.failed === 1 ? "" : "s"} failed (quota, busy, or timeout)
            </p>
          ) : null}

          <section>
            <h6>By job</h6>
            <table className="cost-table">
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Req</th>
                  <th>Tokens in · out</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {cost.by_job.map((line) => (
                  <tr key={line.key}>
                    <td>{line.label}</td>
                    <td className="mono">
                      {line.requests}
                      {line.failed ? <em> · {line.failed} failed</em> : null}
                    </td>
                    <td className="mono">
                      {formatTokens(line.input_tokens)} · {formatTokens(line.output_tokens)}
                    </td>
                    <td className="mono">{formatUsd(line.usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <h6>Free tier used today (all sessions)</h6>
            <ul className="quota-list">
              {cost.quotas.map((q) => {
                const share = quotaShare(q.requests_today, q.free_per_day);
                return (
                  <li key={q.model}>
                    <div className="quota-top">
                      <span>{q.label}</span>
                      <span className="mono muted">
                        {q.requests_today.toLocaleString()}
                        {q.free_per_day ? ` / ${q.free_per_day.toLocaleString()} req` : " req"}
                      </span>
                    </div>
                    {share !== null ? (
                      <div
                        className={`quota-bar${share >= 0.8 ? " high" : ""}`}
                        role="meter"
                        aria-valuemin={0}
                        aria-valuemax={q.free_per_day ?? 0}
                        aria-valuenow={q.requests_today}
                        aria-label={`${q.label} free requests used today`}
                      >
                        <span style={{ width: `${Math.max(share * 100, share > 0 ? 1.5 : 0)}%` }} />
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
            <p className="cost-note">Free limits reset at midnight Pacific. Prices from Google AI Studio (Nov 2026).</p>
          </section>
        </>
      )}
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="cost-tile">
      <span>{label}</span>
      <strong className="mono">{value}</strong>
    </div>
  );
}
