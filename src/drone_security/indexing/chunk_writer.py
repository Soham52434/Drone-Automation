import json
import time
from fractions import Fraction
from pathlib import Path

import av

from drone_security.models import ChunkArtifact, ChunkTrigger, ClipPlan, FramePacket

_TIME_BASE = Fraction(1, 1000)


class ChunkWriter:
    """Encodes a clip plan to `chunk_<start_ms>.mp4` plus a paired `chunk_<start_ms>.json`."""

    def __init__(self, codec: str = "libx264") -> None:
        self._codec = codec

    def write(self, plan: ClipPlan, out_dir: Path) -> ChunkArtifact:
        if not plan.frames:
            raise ValueError("clip plan has no frames")
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = self._free_stem(out_dir, plan.start_ms)
        video_path = out_dir / f"{stem}.mp4"
        metadata_path = out_dir / f"{stem}.json"

        fps = self._fps(plan)
        self._encode(plan, video_path, fps)

        artifact = ChunkArtifact(
            session_id=plan.session_id,
            chunk_file=video_path.name,
            metadata_file=metadata_path.name,
            chunk_start_ms=plan.start_ms,
            chunk_end_ms=plan.end_ms,
            detection_ms=plan.detection_ms,
            frame_count=len(plan.frames),
            fps=fps,
            trigger=plan.trigger,
            created_ms=int(time.time() * 1000),
            evidence=plan.evidence,
        )
        metadata_path.write_text(json.dumps(artifact.to_metadata(), indent=2))
        return artifact

    def encode_mp4(self, frames: tuple[FramePacket, ...], path: Path) -> None:
        """Write frames to an mp4 without a metadata sidecar. Used for decision windows."""
        if len(frames) < 2:
            raise ValueError("need at least two frames to encode a window")
        plan = ClipPlan(
            session_id="window",
            trigger=ChunkTrigger.MANUAL,
            detection_ms=frames[0].timestamp_ms,
            frames=frames,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        self._encode(plan, path, self._fps(plan))

    def _encode(self, plan: ClipPlan, path: Path, fps: float) -> None:
        first = plan.frames[0]
        with av.open(str(path), mode="w", options={"movflags": "+faststart"}) as container:
            stream = container.add_stream(self._codec, rate=max(1, round(fps)))
            stream.width = first.width
            stream.height = first.height
            stream.pix_fmt = "yuv420p"
            stream.time_base = _TIME_BASE
            stream.codec_context.time_base = _TIME_BASE
            last_pts = -1
            for packet in plan.frames:
                frame = av.VideoFrame.from_ndarray(packet.image, format="rgb24")
                pts = max(packet.timestamp_ms - plan.start_ms, last_pts + 1)
                frame.pts = pts
                frame.time_base = _TIME_BASE
                last_pts = pts
                for encoded in stream.encode(frame):
                    container.mux(encoded)
            for encoded in stream.encode():
                container.mux(encoded)

    @staticmethod
    def _free_stem(out_dir: Path, start_ms: int) -> str:
        stem = f"chunk_{start_ms}"
        suffix = 2
        while (out_dir / f"{stem}.mp4").exists() or (out_dir / f"{stem}.json").exists():
            stem = f"chunk_{start_ms}_{suffix}"
            suffix += 1
        return stem

    @staticmethod
    def _fps(plan: ClipPlan) -> float:
        span_ms = plan.end_ms - plan.start_ms
        if len(plan.frames) < 2 or span_ms <= 0:
            return 1.0
        return round((len(plan.frames) - 1) * 1000 / span_ms, 3)
