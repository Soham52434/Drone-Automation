import type { SessionCost } from "../api/types";

/** Dollars at paid-tier prices: tiny amounts keep enough digits to be readable. */
export function formatUsd(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.0001) return "<$0.0001";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

export function formatTokens(tokens: number): string {
  if (tokens < 1_000) return String(tokens);
  if (tokens < 1_000_000) return `${(tokens / 1_000).toFixed(tokens < 10_000 ? 1 : 0)}K`;
  return `${(tokens / 1_000_000).toFixed(2)}M`;
}

/** Share of a model's free daily requests used today (0–1), or null when it has no published free limit. */
export function quotaShare(used: number, perDay: number | null): number | null {
  if (!perDay) return null;
  return Math.min(1, used / perDay);
}

/** Short label for the button beside Ask. */
export function costBadge(cost: SessionCost | null): string {
  if (!cost) return "Cost";
  return cost.requests === 0 ? "$0.00" : formatUsd(cost.usd);
}
