import { Menu, Plus, Radar, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api/client";
import type { Session } from "./api/types";
import { AlertPopups, type PopupItem } from "./components/AlertPopups";
import { NewSession } from "./components/NewSession";
import { SessionView } from "./components/SessionView";
import { Sidebar } from "./components/Sidebar";
import { AlertWatcher } from "./lib/alertWatcher";
import { type AlertRecord, alertRecords, alertWriteUp, openAlertCount, ruleLabel } from "./lib/analysisFeed";
import { SessionFeedHub } from "./lib/feedHub";
import { SessionListStream } from "./lib/sessionStream";
import type { SessionSetup } from "./lib/sessionSetup";
import { AckStore, type AlertPreferences, PreferenceStore, browserStorage } from "./lib/preferences";
import { CAMERA_CONSTRAINTS, LiveConnection, LiveRegistry } from "./live/liveConnection";

interface PopupRef {
  sessionId: string;
  key: string;
}

const storage = browserStorage();
const preferenceStore = new PreferenceStore(storage);
const ackStore = new AckStore(storage);

export function App() {
  const registry = useRef(new LiveRegistry());
  const hub = useRef(new SessionFeedHub());
  const watcher = useRef(new AlertWatcher());
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState<"live" | "upload" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, setConnectionVersion] = useState(0);
  const [feedVersion, setFeedVersion] = useState(0);
  const [preferences, setPreferences] = useState<AlertPreferences>(() => preferenceStore.load());
  const [acks, setAcks] = useState<Record<string, Set<string>>>({});
  const [popups, setPopups] = useState<PopupRef[]>([]);
  const [focus, setFocus] = useState<PopupRef | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const preferencesRef = useRef(preferences);
  preferencesRef.current = preferences;
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  const showError = useCallback((message: string) => setError(message), []);

  // The server pushes the session list on connect and on every change; nothing polls.
  useEffect(() => {
    const stream = new SessionListStream();
    stream.open(setSessions);
    const live = registry.current;
    return () => {
      stream.close();
      live.closeAll();
    };
  }, []);

  // Selected session plus every session that is streaming: alerts reach the operator from anywhere.
  const watchKey = sessions
    .filter((s) => s.id === selectedId || s.status === "streaming")
    .map((s) => `${s.id}:${s.kind}`)
    .join(",");
  useEffect(() => {
    hub.current.sync(
      watchKey
        ? watchKey.split(",").map((item) => {
            const [id, kind] = item.split(":");
            return { id: id!, kind: kind as Session["kind"] };
          })
        : [],
    );
  }, [watchKey]);

  const announce = useCallback((sessionId: string, fresh: AlertRecord[]) => {
    const prefs = preferencesRef.current;
    if (prefs.popups) {
      setPopups((current) => [...current, ...fresh.map((record) => ({ sessionId, key: record.key }))]);
    }
    if (prefs.sound) playChime();
    if (prefs.desktop && document.hidden && "Notification" in window && Notification.permission === "granted") {
      const title = sessionsRef.current.find((s) => s.id === sessionId)?.title ?? "Session";
      for (const record of fresh) {
        const note = new Notification(`${ruleLabel(record.rule)} detected · ${title}`, {
          body: record.text,
          tag: `${sessionId}:${record.key}`,
        });
        note.onclick = () => {
          window.focus();
          setSelectedId(sessionId);
          setFocus({ sessionId, key: record.key });
        };
      }
    }
  }, []);

  useEffect(() => {
    const feeds = hub.current;
    const unsubscribe = feeds.subscribe((sessionId) => {
      setFeedVersion((v) => v + 1);
      const fresh = watcher.current.update(
        sessionId,
        alertRecords(feeds.entries(sessionId)),
        feeds.isReplaying(sessionId),
      );
      const unacked = fresh.filter((record) => !ackStore.load(sessionId).has(record.key));
      if (unacked.length > 0) announce(sessionId, unacked);
    });
    return () => {
      unsubscribe();
      feeds.closeAll();
    };
  }, [announce]);

  const recordsBySession = useMemo(() => {
    const map = new Map<string, AlertRecord[]>();
    for (const session of sessions) {
      if (hub.current.watching(session.id)) map.set(session.id, alertRecords(hub.current.entries(session.id)));
    }
    return map;
    // feedVersion: recompute when any feed receives an event.
  }, [sessions, feedVersion]);

  const ackedFor = useCallback(
    (sessionId: string): Set<string> => acks[sessionId] ?? ackStore.load(sessionId),
    [acks],
  );

  const acknowledge = useCallback((sessionId: string, keys: string[]) => {
    if (keys.length === 0) return;
    const next = ackStore.add(sessionId, keys);
    setAcks((current) => ({ ...current, [sessionId]: next }));
    setPopups((current) => current.filter((p) => !(p.sessionId === sessionId && keys.includes(p.key))));
  }, []);

  const openAlerts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const [id, records] of recordsBySession) counts[id] = openAlertCount(records, ackedFor(id));
    return counts;
  }, [recordsBySession, ackedFor]);

  const totalOpen = Object.values(openAlerts).reduce((sum, n) => sum + n, 0);
  useEffect(() => {
    document.title = totalOpen > 0 ? `(${totalOpen}) Drone Automation` : "Drone Automation";
  }, [totalOpen]);

  const popupItems: PopupItem[] = popups.flatMap((ref) => {
    const record = recordsBySession.get(ref.sessionId)?.find((r) => r.key === ref.key);
    if (!record) return [];
    const session = sessions.find((s) => s.id === ref.sessionId);
    const writeUp = session?.llm.detailed_alerts ? alertWriteUp(hub.current.entries(ref.sessionId), ref.key) : "";
    const writeUpPending = Boolean(session?.llm.enabled && session.llm.detailed_alerts && !writeUp && record.clip !== "failed");
    return [{ sessionId: ref.sessionId, sessionTitle: session?.title ?? "Session", record, writeUp, writeUpPending }];
  });

  const updatePreferences = (next: AlertPreferences) => {
    preferenceStore.save(next);
    setPreferences(next);
    if (!next.popups) setPopups([]);
  };

  const connectCamera = async (sessionId: string, stream: MediaStream) => {
    const connection = await LiveConnection.start(api, sessionId, stream);
    registry.current.add(connection);
    setConnectionVersion((v) => v + 1);
  };

  const requestCamera = async (): Promise<MediaStream | null> => {
    try {
      return await navigator.mediaDevices.getUserMedia(CAMERA_CONSTRAINTS);
    } catch (err) {
      showError(err instanceof Error ? `Camera access failed: ${err.message}` : "Camera access failed");
      return null;
    }
  };

  const goLive = async (setup: SessionSetup) => {
    setBusy("live");
    try {
      const stream = await requestCamera();
      if (!stream) return;
      const session = await api.createLiveSession({ setup });
      setSelectedId(session.id);
      try {
        await connectCamera(session.id, stream);
      } catch (err) {
        stream.getTracks().forEach((track) => track.stop());
        throw err;
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : "Could not start live session");
    } finally {
      setBusy(null);
    }
  };

  const startCamera = async (sessionId: string) => {
    const stream = await requestCamera();
    if (!stream) return;
    try {
      await connectCamera(sessionId, stream);
    } catch (err) {
      stream.getTracks().forEach((track) => track.stop());
      showError(err instanceof Error ? err.message : "Could not connect camera");
    }
  };

  const stopLive = async (sessionId: string) => {
    registry.current.close(sessionId);
    setConnectionVersion((v) => v + 1);
    try {
      await api.stopLive(sessionId);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Could not stop live session");
    }
  };

  const upload = async (file: File, setup: SessionSetup) => {
    setBusy("upload");
    try {
      const session = await api.uploadVideo(file, setup);
      setSelectedId(session.id);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(null);
    }
  };

  const remove = async (sessionId: string) => {
    registry.current.close(sessionId);
    try {
      await api.deleteSession(sessionId);
      hub.current.close(sessionId);
      watcher.current.forget(sessionId);
      setPopups((current) => current.filter((p) => p.sessionId !== sessionId));
      if (selectedId === sessionId) setSelectedId(null);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Could not delete session");
    }
  };

  const review = (sessionId: string, key: string) => {
    setSelectedId(sessionId);
    setFocus({ sessionId, key });
    setPopups((current) => current.filter((p) => !(p.sessionId === sessionId && p.key === key)));
  };

  const clearFocus = useCallback(() => setFocus(null), []);
  const selected = sessions.find((s) => s.id === selectedId) ?? null;
  const showSessionOnPopups = new Set(popupItems.map((item) => item.sessionId)).size > 1 || popupItems.some((i) => i.sessionId !== selectedId);

  return (
    <div className="app">
      <Sidebar
        open={navOpen}
        onClose={() => setNavOpen(false)}
        sessions={sessions}
        selectedId={selectedId}
        openAlerts={openAlerts}
        preferences={preferences}
        onPreferences={updatePreferences}
        onSelect={(id) => {
          setSelectedId(id);
          setNavOpen(false);
        }}
        onNew={() => {
          setSelectedId(null);
          setNavOpen(false);
        }}
        onDelete={remove}
      />
      {navOpen ? <div className="nav-backdrop" onClick={() => setNavOpen(false)} aria-hidden /> : null}
      <main className="main">
        <header className="mobile-bar">
          <button type="button" className="icon-btn ghost" aria-label="Open sessions" aria-expanded={navOpen} onClick={() => setNavOpen(true)}>
            <Menu size={20} />
            {totalOpen > 0 ? <span className="menu-dot" /> : null}
          </button>
          <span className="mobile-brand">
            <Radar size={16} /> {selected ? selected.title : "Drone Automation"}
          </span>
          <button type="button" className="icon-btn ghost" aria-label="New session" onClick={() => setSelectedId(null)}>
            <Plus size={20} />
          </button>
        </header>
        {error ? (
          <div className="toast" role="alert">
            <TriangleAlert size={16} />
            <span>{error}</span>
            <button type="button" className="icon-btn ghost sm" aria-label="Dismiss" onClick={() => setError(null)}>
              <X size={15} />
            </button>
          </div>
        ) : null}
        {selected ? (
          <SessionView
            key={selected.id}
            session={selected}
            connection={registry.current.get(selected.id)}
            entries={hub.current.entries(selected.id)}
            liveStats={hub.current.stats(selected.id)}
            records={recordsBySession.get(selected.id) ?? []}
            acked={ackedFor(selected.id)}
            focusKey={focus?.sessionId === selected.id ? focus.key : null}
            onFocusHandled={clearFocus}
            onAcknowledge={(keys) => acknowledge(selected.id, keys)}
            onStartCamera={startCamera}
            onStopLive={stopLive}
            onError={showError}
          />
        ) : (
          <NewSession busy={busy} onGoLive={goLive} onUpload={upload} />
        )}
      </main>
      <AlertPopups
        items={popupItems}
        showSession={showSessionOnPopups}
        onReview={review}
        onAcknowledge={(sessionId, key) => acknowledge(sessionId, [key])}
        onDismiss={(sessionId, key) =>
          setPopups((current) => current.filter((p) => !(p.sessionId === sessionId && p.key === key)))
        }
        onDismissAll={() => setPopups([])}
      />
    </div>
  );
}

function playChime() {
  try {
    const audio = new AudioContext();
    const level = audio.createGain();
    level.connect(audio.destination);
    [880, 1175].forEach((frequency, i) => {
      const tone = audio.createOscillator();
      const start = audio.currentTime + i * 0.14;
      tone.frequency.value = frequency;
      tone.connect(level);
      level.gain.setValueAtTime(0.05, start);
      level.gain.exponentialRampToValueAtTime(0.001, start + 0.13);
      tone.start(start);
      tone.stop(start + 0.14);
      if (i === 1) tone.onended = () => void audio.close();
    });
  } catch {
    // Audio is a courtesy; the on-screen pop-up is the alert.
  }
}
