import {
  Armchair,
  Building2,
  Car,
  Flame,
  Lamp,
  type LucideIcon,
  Monitor,
  Mountain,
  Package,
  PawPrint,
  Shapes,
  Swords,
  Trees,
  UserRound,
} from "lucide-react";

import type { ClassHit } from "../api/types";

export const CLASS_ICONS: Record<string, LucideIcon> = {
  person: UserRound,
  vehicle: Car,
  animal: PawPrint,
  package: Package,
  hazard: Flame,
  weapon: Swords,
  electronics: Monitor,
  furniture: Armchair,
  lighting: Lamp,
  vegetation: Trees,
  structure: Building2,
  terrain: Mountain,
  other: Shapes,
};

/** Classes that usually matter for security; the rest are scene context. */
export const KEY_CLASSES = new Set(["person", "vehicle", "animal", "package", "hazard", "weapon"]);

/** Security-relevant classes first, then the rest, keeping the given order within each group. */
export function keyClassesFirst<T extends { name: string }>(items: readonly T[]): T[] {
  return [...items.filter((c) => KEY_CLASSES.has(c.name)), ...items.filter((c) => !KEY_CLASSES.has(c.name))];
}

export function classIcon(name: string): LucideIcon {
  return CLASS_ICONS[name] ?? Shapes;
}

interface ClassChipsProps {
  classes: readonly (ClassHit | string)[];
  max?: number;
  glass?: boolean;
  showScore?: boolean;
}

/** Object classes for a reading, e.g. [person 82%] [vehicle 64%]. Security-relevant classes stand out. */
export function ClassChips({ classes, max = 6, glass = false, showScore = true }: ClassChipsProps) {
  if (classes.length === 0) return null;
  const hits = classes.map((c) => (typeof c === "string" ? { name: c, score: -1, count: 1 } : c));
  const shown = hits.slice(0, max);
  const hidden = hits.length - shown.length;
  return (
    <div className="chip-row">
      {shown.map((hit) => {
        const Icon = classIcon(hit.name);
        return (
          <span
            key={hit.name}
            className={`class-chip${KEY_CLASSES.has(hit.name) ? " key" : ""}${glass ? " glass" : ""}`}
            title={hit.count > 1 ? `${hit.count} objects` : undefined}
          >
            <Icon size={12} />
            {hit.name}
            {showScore && hit.score >= 0 ? <em>{Math.round(hit.score * 100)}%</em> : null}
          </span>
        );
      })}
      {hidden > 0 ? <span className={`class-chip more${glass ? " glass" : ""}`}>+{hidden}</span> : null}
    </div>
  );
}
