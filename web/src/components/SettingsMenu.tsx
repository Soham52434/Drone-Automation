import { Bell, BellOff, MonitorPlay, Settings2, Volume2 } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { AlertPreferences } from "../lib/preferences";

interface SettingsMenuProps {
  preferences: AlertPreferences;
  onChange: (next: AlertPreferences) => void;
}

export function SettingsMenu({ preferences, onChange }: SettingsMenuProps) {
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!panel.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const setDesktop = async (on: boolean) => {
    if (on && "Notification" in window && Notification.permission !== "granted") {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") return;
    }
    onChange({ ...preferences, desktop: on });
  };

  const desktopBlocked = "Notification" in window ? Notification.permission === "denied" : true;

  return (
    <div className="settings" ref={panel}>
      {open ? (
        <div className="settings-panel" role="dialog" aria-label="Alert settings">
          <h4>Alert settings</h4>
          <Toggle
            icon={<Bell size={16} />}
            label="Alert pop-ups"
            hint="Show a card the moment the alert classifier raises an alert"
            checked={preferences.popups}
            onChange={(on) => onChange({ ...preferences, popups: on })}
          />
          <Toggle
            icon={<Volume2 size={16} />}
            label="Alert sound"
            hint="Short chime with each new alert"
            checked={preferences.sound}
            onChange={(on) => onChange({ ...preferences, sound: on })}
          />
          <Toggle
            icon={<MonitorPlay size={16} />}
            label="Desktop notifications"
            hint={desktopBlocked ? "Blocked by the browser for this site" : "Notify when this tab is in the background"}
            checked={preferences.desktop}
            disabled={desktopBlocked}
            onChange={(on) => void setDesktop(on)}
          />
        </div>
      ) : null}
      <button type="button" className={`settings-trigger${open ? " open" : ""}`} onClick={() => setOpen((v) => !v)}>
        <Settings2 size={16} />
        <span>Settings</span>
        <span className="settings-state" title={preferences.popups ? "Pop-ups on" : "Pop-ups off"}>
          {preferences.popups ? <Bell size={14} /> : <BellOff size={14} />}
        </span>
      </button>
    </div>
  );
}

function Toggle({
  icon,
  label,
  hint,
  checked,
  disabled = false,
  onChange,
}: {
  icon: ReactNode;
  label: string;
  hint: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <label className={`toggle-row${disabled ? " disabled" : ""}`}>
      <span className="toggle-icon">{icon}</span>
      <span className="toggle-copy">
        <strong>{label}</strong>
        <span>{hint}</span>
      </span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="switch" aria-hidden />
    </label>
  );
}
