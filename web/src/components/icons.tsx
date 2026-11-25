import {
  Car,
  Clock,
  Flame,
  type LucideIcon,
  Moon,
  Package,
  PawPrint,
  ScanEye,
  ShieldAlert,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import type { ClipState } from "../lib/analysisFeed";

const RULE_ICONS: Record<string, LucideIcon> = {
  person_on_property: UserRound,
  vehicle: Car,
  package_delivery: Package,
  animal: PawPrint,
  hazard: Flame,
  brief_match: ScanEye,
  loitering: Clock,
  after_hours: Moon,
  none: ShieldCheck,
};

export function ruleIcon(rule: string): LucideIcon {
  return RULE_ICONS[rule] ?? ShieldAlert;
}

export function RuleBadge({ rule, severity, size = "md" }: { rule: string; severity: string; size?: "sm" | "md" | "lg" }) {
  const Icon = ruleIcon(rule);
  const px = size === "lg" ? 22 : size === "sm" ? 14 : 18;
  return (
    <span className={`rule-badge ${severity || "warn"} ${size}`} aria-hidden>
      <Icon size={px} strokeWidth={2} />
    </span>
  );
}

export const CLIP_LABELS: Record<ClipState, string> = {
  saving: "Saving clip",
  saved: "Clip ready",
  failed: "No clip",
  cooldown: "In cooldown",
};

export function severityLabel(severity: string): string {
  if (severity === "critical") return "Critical";
  if (severity === "info") return "Info";
  return "Warning";
}
