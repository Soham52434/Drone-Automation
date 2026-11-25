import { Camera, CloudUpload, Radar } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import type { SessionSetup } from "../lib/sessionSetup";
import { SessionSetupDialog, type SetupMode } from "./SessionSetupDialog";

interface NewSessionProps {
  busy: "live" | "upload" | null;
  onGoLive: (setup: SessionSetup) => void;
  onUpload: (file: File, setup: SessionSetup) => void;
}

/** Start screen: two choices. Each opens the setup form before anything runs. */
export function NewSession({ busy, onGoLive, onUpload }: NewSessionProps) {
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [setup, setSetup] = useState<{ mode: SetupMode; file: File | null } | null>(null);

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    depth.current = 0;
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file && !busy) setSetup({ mode: "upload", file });
  };

  return (
    <div
      className="new-session-view"
      onDragEnter={(e) => {
        e.preventDefault();
        depth.current += 1;
        setDragging(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        depth.current -= 1;
        if (depth.current <= 0) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <div className="new-session-inner">
        <span className="hero-mark" aria-hidden>
          <Radar size={28} strokeWidth={1.8} />
        </span>
        <h1>Start a session</h1>
        <p className="lede">Watch a live camera or review a recorded video. You choose what to watch for next.</p>

        <div className="choice-grid">
          <button type="button" className="choice-card live" disabled={busy !== null} onClick={() => setSetup({ mode: "live", file: null })}>
            <span className="choice-icon">
              <Camera size={24} />
            </span>
            <span className="choice-copy">
              <strong>Go live</strong>
              <span>Stream this device's camera to the analyst in real time.</span>
            </span>
          </button>
          <button
            type="button"
            className="choice-card upload"
            disabled={busy !== null}
            onClick={() => setSetup({ mode: "upload", file: null })}
          >
            <span className="choice-icon">
              <CloudUpload size={24} />
            </span>
            <span className="choice-copy">
              <strong>Upload a video</strong>
              <span>Pick a file, or drop it anywhere on this page.</span>
            </span>
          </button>
        </div>
      </div>

      {setup ? (
        <SessionSetupDialog
          mode={setup.mode}
          initialFile={setup.file}
          busy={busy !== null}
          onCancel={() => setSetup(null)}
          onStart={(choice, file) => {
            if (setup.mode === "live") onGoLive(choice);
            else if (file) onUpload(file, choice);
          }}
        />
      ) : null}

      {dragging ? (
        <div className="drop-overlay" aria-hidden>
          <CloudUpload size={40} strokeWidth={1.6} />
          <strong>Drop the video to set up a review</strong>
        </div>
      ) : null}
    </div>
  );
}
