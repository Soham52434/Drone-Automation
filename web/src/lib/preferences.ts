export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface AlertPreferences {
  /** Pop an alert card on screen when the alert classifier raises an alert. */
  popups: boolean;
  /** Short chime with each new alert. */
  sound: boolean;
  /** System notification when the tab is in the background. */
  desktop: boolean;
}

export const DEFAULT_PREFERENCES: AlertPreferences = { popups: true, sound: true, desktop: false };

const PREFERENCES_KEY = "drone-alert-preferences";
const LEGACY_MUTE_KEY = "drone-alert-mute";

/** Operator settings kept in the browser. */
export class PreferenceStore {
  constructor(private readonly storage: KeyValueStorage) {}

  load(): AlertPreferences {
    const stored = parse(this.storage.getItem(PREFERENCES_KEY));
    const legacyMuted = this.storage.getItem(LEGACY_MUTE_KEY) === "1";
    return {
      popups: typeof stored.popups === "boolean" ? stored.popups : DEFAULT_PREFERENCES.popups,
      sound: typeof stored.sound === "boolean" ? stored.sound : !legacyMuted,
      desktop: typeof stored.desktop === "boolean" ? stored.desktop : DEFAULT_PREFERENCES.desktop,
    };
  }

  save(preferences: AlertPreferences): void {
    this.storage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
  }
}

/** Acknowledged incident keys, per session. */
export class AckStore {
  constructor(private readonly storage: KeyValueStorage) {}

  load(sessionId: string): Set<string> {
    const ids = parseArray(this.storage.getItem(`drone-ack:${sessionId}`));
    return new Set(ids.filter((id): id is string => typeof id === "string"));
  }

  add(sessionId: string, keys: readonly string[]): Set<string> {
    const next = this.load(sessionId);
    for (const key of keys) next.add(key);
    this.storage.setItem(`drone-ack:${sessionId}`, JSON.stringify([...next]));
    return next;
  }
}

function parse(raw: string | null): Record<string, unknown> {
  try {
    const value = raw ? (JSON.parse(raw) as unknown) : {};
    return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function parseArray(raw: string | null): unknown[] {
  try {
    const value = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

/** In-memory storage for tests and for browsers that block localStorage. */
export class MemoryStorage implements KeyValueStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

export function browserStorage(): KeyValueStorage {
  try {
    const probe = "__drone_probe__";
    window.localStorage.setItem(probe, probe);
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    return new MemoryStorage();
  }
}
