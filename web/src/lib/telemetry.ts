/** "1 h 04 min", "3 min 20 s", "45 s". */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h} h ${String(m).padStart(2, "0")} min`;
  if (m > 0) return `${m} min${s ? ` ${s} s` : ""}`;
  return `${s} s`;
}

/** True when a reading carries any of the chosen classes (no filter = everything). */
export function matchesClasses(classes: readonly [string, number][], filter: ReadonlySet<string>): boolean {
  return filter.size === 0 || classes.some(([name]) => filter.has(name));
}
