import { Film, Plus, Radar, Radio, Search, Trash2, X } from "lucide-react";
import { useState } from "react";

import type { Session } from "../api/types";
import type { AlertPreferences } from "../lib/preferences";
import { groupSessions } from "../lib/sessionGroups";
import { SettingsMenu } from "./SettingsMenu";

interface SidebarProps {
  /** Small screens: the sidebar is a drawer, open or closed. */
  open: boolean;
  onClose: () => void;
  sessions: Session[];
  selectedId: string | null;
  openAlerts: Record<string, number>;
  preferences: AlertPreferences;
  onPreferences: (next: AlertPreferences) => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export function Sidebar({
  open,
  onClose,
  sessions,
  selectedId,
  openAlerts,
  preferences,
  onPreferences,
  onSelect,
  onNew,
  onDelete,
}: SidebarProps) {
  const [query, setQuery] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const needle = query.trim().toLowerCase();
  const visible = needle
    ? sessions.filter((s) => `${s.title} ${s.watch_brief}`.toLowerCase().includes(needle))
    : sessions;
  const liveCount = sessions.filter((s) => s.status === "streaming").length;

  return (
    <aside className={`sidebar${open ? " open" : ""}`} aria-label="Sessions">
      <div className="brand">
        <span className="brand-mark" aria-hidden>
          <Radar size={18} strokeWidth={2.2} />
        </span>
        <div className="brand-copy">
          <strong>Drone Automation</strong>
          <span>{liveCount > 0 ? `${liveCount} watching now` : "Security analyst"}</span>
        </div>
        <button type="button" className="icon-btn ghost drawer-close" aria-label="Close menu" onClick={onClose}>
          <X size={18} />
        </button>
      </div>

      <button type="button" className="btn btn-primary new-session" onClick={onNew}>
        <Plus size={16} strokeWidth={2.4} /> New session
      </button>

      <label className="search">
        <Search size={15} aria-hidden />
        <input value={query} placeholder="Search sessions" onChange={(e) => setQuery(e.target.value)} />
        {query ? (
          <button type="button" className="icon-btn ghost xs" aria-label="Clear search" onClick={() => setQuery("")}>
            <X size={14} />
          </button>
        ) : null}
      </label>

      <nav className="session-list" aria-label="Sessions">
        {sessions.length === 0 ? (
          <p className="sidebar-empty">No sessions yet. Start one to begin watching.</p>
        ) : visible.length === 0 ? (
          <p className="sidebar-empty">No sessions match “{query}”.</p>
        ) : null}
        {groupSessions(visible).map((group) => (
          <section key={group.label}>
            <h3>{group.label}</h3>
            {group.sessions.map((session) => {
              const Icon = session.kind === "live" ? Radio : Film;
              const alerts = openAlerts[session.id] ?? 0;
              const streaming = session.status === "streaming";
              return (
                <div
                  key={session.id}
                  className={`session-item${session.id === selectedId ? " active" : ""}${streaming ? " streaming" : ""}`}
                  onClick={() => onSelect(session.id)}
                  onMouseLeave={() => setConfirming((c) => (c === session.id ? null : c))}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && onSelect(session.id)}
                >
                  <span className={`session-icon ${session.kind}`} aria-hidden>
                    <Icon size={15} />
                  </span>
                  <span className="session-copy">
                    <span className="session-title">{session.title}</span>
                    <span className="session-sub">{subtitle(session)}</span>
                  </span>
                  {alerts > 0 ? (
                    <span className="count-badge" title={`${alerts} open incidents`}>
                      {alerts}
                    </span>
                  ) : null}
                  {confirming === session.id ? (
                    <button
                      type="button"
                      className="confirm-delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirming(null);
                        onDelete(session.id);
                      }}
                    >
                      Delete
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="icon-btn ghost xs session-delete"
                      aria-label={`Delete ${session.title}`}
                      title="Delete session"
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirming(session.id);
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              );
            })}
          </section>
        ))}
      </nav>

      <SettingsMenu preferences={preferences} onChange={onPreferences} />
    </aside>
  );
}

function subtitle(session: Session): string {
  const time = new Date(session.created_ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (session.status === "streaming") return session.kind === "live" ? "Live now" : "Analyzing";
  if (session.kind === "upload") return session.status === "ended" ? `Reviewed · ${time}` : `Video · ${time}`;
  if (session.status === "idle") return `Not started · ${time}`;
  return `Ended · ${time}`;
}
