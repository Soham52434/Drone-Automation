import { MapPin, Maximize2, Minimize2 } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { AnalysisEntry } from "../lib/analysisFeed";
import { ClassChips } from "./ClassChips";

interface StageFrameProps {
  children: ReactNode;
  badges?: ReactNode;
  reading?: AnalysisEntry | null;
  alerting?: boolean;
}

/** Video surface: badges top-left, fullscreen top-right, the vision model's latest reading along the bottom. */
export function StageFrame({ children, badges, reading = null, alerting = false }: StageFrameProps) {
  const frame = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);

  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === frame.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggle = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void frame.current?.requestFullscreen();
  };

  return (
    <div className={`stage${alerting ? " alerting" : ""}`} ref={frame}>
      {children}
      <div className="stage-badges">{badges}</div>
      <div className="stage-tools">
        <button
          type="button"
          className="icon-btn glass"
          aria-label={full ? "Exit full screen" : "Full screen"}
          title={full ? "Exit full screen" : "Full screen"}
          onClick={toggle}
        >
          {full ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>
      </div>
      {reading ? (
        <div className="stage-reading" key={reading.id}>
          <span className="reading-kicker">
            Vision · {reading.meta.split(" · ").slice(-1)[0]}
            {reading.location ? (
              <span className="kicker-place">
                <MapPin size={11} /> {reading.location}
              </span>
            ) : null}
          </span>
          <p>{reading.text}</p>
          <ClassChips classes={reading.classes} glass max={5} />
        </div>
      ) : null}
    </div>
  );
}
