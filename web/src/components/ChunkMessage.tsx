import { FileJson, Scissors } from "lucide-react";

import type { Chunk, SessionKind } from "../api/types";
import { chunkPlaybackUrl, describeChunk } from "../lib/format";

interface ChunkMessageProps {
  kind: SessionKind;
  chunk: Chunk;
}

/** A clip the operator saved by hand. */
export function ChunkMessage({ kind, chunk }: ChunkMessageProps) {
  return (
    <article className="saved-clip">
      <video src={chunkPlaybackUrl(chunk)} controls preload="metadata" />
      <div className="saved-clip-copy">
        <p>
          <Scissors size={13} /> {describeChunk(kind, chunk)}
        </p>
        <p className="muted small">
          seek {chunk.seek_offset_sec.toFixed(2)} s · {chunk.fps.toFixed(1)} fps ·{" "}
          <a href={chunk.metadata_url} target="_blank" rel="noreferrer">
            <FileJson size={12} /> metadata
          </a>
        </p>
      </div>
    </article>
  );
}
