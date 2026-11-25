import { Camera, CameraOff, LoaderCircle, Scissors, Square } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "../api/client";
import type { Chunk, LiveStats, Session } from "../api/types";
import type { AnalysisEntry } from "../lib/analysisFeed";
import type { LiveConnection, LiveState } from "../live/liveConnection";
import { StageFrame } from "./StageFrame";

interface LiveStageProps {
  session: Session;
  connection: LiveConnection | undefined;
  reading: AnalysisEntry | null;
  /** Pushed once a second by the server while streaming; no polling. */
  stats: LiveStats | null;
  alerting: boolean;
  /** After the feed ends: the incident clip chosen for replay, if any. */
  playback: { url: string; label: string } | null;
  /** Shown in place of the video once the feed has ended and nothing is chosen for replay. */
  endedView: ReactNode;
  onStartCamera: () => void;
  onStop: () => void;
  onSaved: (chunk: Chunk) => void;
  onError: (message: string) => void;
}

export function LiveStage({
  session,
  connection,
  reading,
  stats,
  alerting,
  playback,
  endedView,
  onStartCamera,
  onStop,
  onSaved,
  onError,
}: LiveStageProps) {
  const video = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<LiveState | undefined>(connection?.state);
  const [saving, setSaving] = useState(false);
  const [stopping, setStopping] = useState(false);
  const ended = session.status === "ended";
  const streaming = session.status === "streaming" && connection !== undefined;

  useEffect(() => {
    setState(connection?.state);
    if (video.current) video.current.srcObject = connection?.stream ?? null;
    return connection?.subscribe(setState);
  }, [connection]);

  const saveClip = async () => {
    setSaving(true);
    try {
      onSaved(await api.saveClip(session.id));
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not save clip");
    } finally {
      setSaving(false);
    }
  };

  if (ended && !playback) return <>{endedView}</>;

  const badges = ended ? (
    <span className="badge glass">Replay · {playback?.label}</span>
  ) : streaming ? (
    <>
      <span className="badge live">
        <span className="rec-dot" /> LIVE
      </span>
      {stats ? (
        <span className="badge glass mono" title={`${stats.frames_received} frames received`}>
          {stats.buffered_seconds.toFixed(1)} s buffered
        </span>
      ) : null}
    </>
  ) : null;

  return (
    <div className="stage-column">
      <StageFrame badges={badges} reading={ended ? null : reading} alerting={alerting && !ended}>
        {ended && playback ? (
          <video key={playback.url} className="stage-video" src={playback.url} controls autoPlay muted playsInline />
        ) : (
          <video ref={video} className="stage-video" autoPlay muted playsInline />
        )}
        {!ended && !connection ? (
          <div className="stage-empty">
            <CameraOff size={30} strokeWidth={1.6} />
            <strong>Camera is off</strong>
            <span>Start the camera to stream it to the analyst.</span>
            <button type="button" className="btn btn-primary" onClick={onStartCamera}>
              <Camera size={16} /> Start camera
            </button>
          </div>
        ) : null}
      </StageFrame>

      {!ended && connection ? (
        <div className="control-bar">
          <span className={`conn ${state ?? ""}`}>
            <span className="conn-dot" />
            {state === "connected" ? "Streaming to the analyst" : `Connection ${state ?? "pending"}…`}
          </span>
          <button type="button" className="btn btn-ghost" disabled={!streaming || saving} onClick={saveClip}>
            {saving ? <LoaderCircle size={15} className="spin" /> : <Scissors size={15} />}
            {saving ? "Saving…" : "Save clip"}
          </button>
          <button
            type="button"
            className="btn btn-danger"
            disabled={stopping}
            onClick={() => {
              setStopping(true);
              onStop();
            }}
          >
            <Square size={13} fill="currentColor" /> {stopping ? "Stopping…" : "Stop"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
