import { LoaderCircle, Scissors } from "lucide-react";
import { useRef, useState } from "react";

import { api } from "../api/client";
import type { Chunk, Session } from "../api/types";
import type { AnalysisEntry } from "../lib/analysisFeed";
import { formatMediaTime } from "../lib/format";
import { StageFrame } from "./StageFrame";

interface UploadStageProps {
  session: Session;
  analyzing: boolean;
  reading: AnalysisEntry | null;
  alerting: boolean;
  onSaved: (chunk: Chunk) => void;
  onError: (message: string) => void;
}

export function UploadStage({ session, analyzing, reading, alerting, onSaved, onError }: UploadStageProps) {
  const video = useRef<HTMLVideoElement>(null);
  const [positionMs, setPositionMs] = useState(0);
  const [saving, setSaving] = useState(false);
  const duration = session.duration_ms ?? 0;

  const saveClip = async () => {
    const position = Math.round((video.current?.currentTime ?? 0) * 1000);
    setSaving(true);
    try {
      onSaved(await api.saveClip(session.id, position));
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not save clip");
    } finally {
      setSaving(false);
    }
  };

  const badges = analyzing ? (
    <span className="badge accent">
      <LoaderCircle size={12} className="spin" /> Analyzing
    </span>
  ) : (
    <span className="badge glass">Review</span>
  );

  return (
    <div className="stage-column">
      <StageFrame badges={badges} reading={analyzing ? reading : null} alerting={alerting}>
        {session.source_url ? (
          <video
            ref={video}
            className="stage-video"
            src={session.source_url}
            controls
            autoPlay
            muted
            playsInline
            preload="metadata"
            onTimeUpdate={(e) => setPositionMs(e.currentTarget.currentTime * 1000)}
          />
        ) : null}
      </StageFrame>
      <div className="control-bar">
        <span className="mono muted">
          {formatMediaTime(positionMs)}
          {duration ? ` / ${formatMediaTime(duration)}` : ""}
        </span>
        <div className="progress" aria-hidden>
          <span style={{ width: duration ? `${Math.min(100, (positionMs / duration) * 100)}%` : "0%" }} />
        </div>
        <button type="button" className="btn btn-ghost" disabled={saving || !session.source_url} onClick={saveClip}>
          {saving ? <LoaderCircle size={15} className="spin" /> : <Scissors size={15} />}
          {saving ? "Saving…" : "Save clip here"}
        </button>
      </div>
    </div>
  );
}
