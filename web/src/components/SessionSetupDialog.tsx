import { Camera, CloudUpload, FileVideo, Info, ScanEye, Sparkles, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import {
  DEFAULT_LLM,
  type LlmSettings,
  SUMMARY_INTERVALS,
  type SessionSetup,
  WATCH_EXAMPLES,
  formatInterval,
  intervalAt,
  intervalIndex,
  VIDEO_ACCEPT,
} from "../lib/sessionSetup";

export type SetupMode = "live" | "upload";

interface SessionSetupDialogProps {
  mode: SetupMode;
  initialFile: File | null;
  busy: boolean;
  onCancel: () => void;
  onStart: (setup: SessionSetup, file: File | null) => void;
}

/** The form between "Go live / Upload" and the session: what to watch for and how LLM is used. */
export function SessionSetupDialog({ mode, initialFile, busy, onCancel, onStart }: SessionSetupDialogProps) {
  const [watchBrief, setWatchBrief] = useState("");
  const [llm, setLlm] = useState<LlmSettings>(DEFAULT_LLM);
  const [file, setFile] = useState<File | null>(initialFile);
  const fileInput = useRef<HTMLInputElement>(null);
  const briefId = useId();
  const sliderId = useId();
  const needsFile = mode === "upload" && !file;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && !busy && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  const submit = () => {
    if (needsFile || busy) return;
    onStart({ watchBrief, llm }, file);
  };

  const index = intervalIndex(llm.summaryIntervalMinutes);
  const fill = (index / (SUMMARY_INTERVALS.length - 1)) * 100;

  return (
    <div className="modal-backdrop" onClick={() => !busy && onCancel()}>
      <form
        className="setup"
        role="dialog"
        aria-modal="true"
        aria-label={mode === "live" ? "Set up a live session" : "Set up a video review"}
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <header className="setup-head">
          <span className={`setup-mark ${mode}`}>{mode === "live" ? <Camera size={20} /> : <CloudUpload size={20} />}</span>
          <div>
            <h2>{mode === "live" ? "Set up live session" : "Set up video review"}</h2>
            <p>{mode === "live" ? "Your camera streams to the analyst once you start." : "The video is analyzed as it plays."}</p>
          </div>
          <button type="button" className="icon-btn ghost" aria-label="Close" onClick={onCancel} disabled={busy}>
            <X size={18} />
          </button>
        </header>

        <div className="setup-body">
          {mode === "upload" ? (
            <section className="setup-section">
              <h3>Video</h3>
              <button type="button" className={`file-pick${file ? " has-file" : ""}`} onClick={() => fileInput.current?.click()}>
                <FileVideo size={20} />
                <span className="file-copy">
                  <strong>{file ? file.name : "Choose a video file"}</strong>
                  <span>{file ? `${(file.size / 1_048_576).toFixed(1)} MB · click to change` : "MP4, MOV, WebM…"}</span>
                </span>
              </button>
              <input
                ref={fileInput}
                type="file"
                accept={VIDEO_ACCEPT}
                hidden
                onChange={(event) => {
                  const picked = event.target.files?.[0];
                  if (picked) setFile(picked);
                  event.target.value = "";
                }}
              />
            </section>
          ) : null}

          <section className="setup-section">
            <h3>
              <label htmlFor={briefId}>
                <ScanEye size={15} /> What should we watch for?
              </label>
              <span className="optional">Optional</span>
            </h3>
            <textarea
              id={briefId}
              className="setup-brief"
              rows={3}
              maxLength={2000}
              value={watchBrief}
              placeholder="e.g. Only alert when a boat comes near the dock. Ignore people walking past."
              onChange={(event) => setWatchBrief(event.target.value)}
            />
            <p className="hint">Leave blank to watch for people, vehicles, packages, animals, and hazards.</p>
            <div className="examples">
              <Sparkles size={13} aria-hidden />
              {WATCH_EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  className={`suggestion${watchBrief === example ? " picked" : ""}`}
                  onClick={() => setWatchBrief(example)}
                >
                  {example}
                </button>
              ))}
            </div>
          </section>

          <section className="setup-section">
            <h3>
              <Sparkles size={15} /> LLM usage
            </h3>
            <div className="yes-no" role="radiogroup" aria-label="Use LLM summaries">
              <button
                type="button"
                role="radio"
                aria-checked={!llm.enabled}
                className={!llm.enabled ? "active" : ""}
                onClick={() => setLlm({ ...llm, enabled: false })}
              >
                <strong>No</strong>
                <span>Local vision model and alerts only</span>
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={llm.enabled}
                className={llm.enabled ? "active" : ""}
                onClick={() => setLlm({ ...llm, enabled: true })}
              >
                <strong>Yes</strong>
                <span>The LLM writes summaries</span>
              </button>
            </div>

            {llm.enabled ? (
              <div className="llm-options">
                <div className="slider-head">
                  <label htmlFor={sliderId}>Summary every</label>
                  <output htmlFor={sliderId}>{formatInterval(llm.summaryIntervalMinutes)}</output>
                </div>
                <div className="stop-slider" style={{ ["--fill" as string]: `${fill}%` }}>
                  <input
                    id={sliderId}
                    type="range"
                    min={0}
                    max={SUMMARY_INTERVALS.length - 1}
                    step={1}
                    value={index}
                    aria-valuetext={formatInterval(llm.summaryIntervalMinutes)}
                    onChange={(event) => setLlm({ ...llm, summaryIntervalMinutes: intervalAt(Number(event.target.value)) })}
                  />
                  <div className="stops" aria-hidden>
                    {SUMMARY_INTERVALS.map((minutes, i) => (
                      <button
                        key={minutes}
                        type="button"
                        tabIndex={-1}
                        className={`stop${i <= index ? " on" : ""}${i === index ? " current" : ""}`}
                        style={{ left: `${(i / (SUMMARY_INTERVALS.length - 1)) * 100}%` }}
                        onClick={() => setLlm({ ...llm, summaryIntervalMinutes: minutes })}
                      >
                        <span className="dot" />
                        {minutes === 1 || minutes % 15 === 0 ? <span className="stop-label">{minutes}m</span> : null}
                      </button>
                    ))}
                  </div>
                </div>

                <label className="toggle-row boxed">
                  <span className="toggle-copy">
                    <strong>Advanced analytics</strong>
                    <span>
                      The LLM describes people and vehicles in key frames (colour, make, clothing), so you can ask
                      things like “how many times did the blue F150 come by?”. Uses more LLM requests.
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    role="switch"
                    checked={llm.advancedAnalytics}
                    onChange={(event) => setLlm({ ...llm, advancedAnalytics: event.target.checked })}
                  />
                  <span className="switch" aria-hidden />
                </label>

                <label className="toggle-row boxed">
                  <span className="toggle-copy">
                    <strong>Detailed alert write-ups</strong>
                    <span>The LLM adds a richer description after each alert. The pop-up still shows at once.</span>
                  </span>
                  <input
                    type="checkbox"
                    role="switch"
                    checked={llm.detailedAlerts}
                    onChange={(event) => setLlm({ ...llm, detailedAlerts: event.target.checked })}
                  />
                  <span className="switch" aria-hidden />
                </label>
              </div>
            ) : null}

            <p className="hint with-icon">
              <Info size={13} />
              {llm.enabled
                ? `A summary with evidence timestamps every ${formatInterval(llm.summaryIntervalMinutes)}, and a final one when the session ends. The LLM reads the text log and a few key frames, never video.`
                : "No LLM calls. The alert classifier still decides which windows raise an alert."}
            </p>
          </section>
        </div>

        <footer className="setup-foot">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className={`btn ${mode === "live" ? "btn-danger" : "btn-primary"}`} disabled={busy || needsFile}>
            {mode === "live" ? <Camera size={16} /> : <CloudUpload size={16} />}
            {busy ? (mode === "live" ? "Connecting…" : "Uploading…") : mode === "live" ? "Start live session" : "Start review"}
          </button>
        </footer>
      </form>
    </div>
  );
}
