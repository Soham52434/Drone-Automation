from collections.abc import Iterator
from pathlib import Path

import av

from drone_security.ingest.frame_normalizer import FrameNormalizer
from drone_security.models import FramePacket, VideoInfo


class VideoFileError(ValueError):
    pass


class VideoFileSource:
    """Reads an uploaded video file as timestamped frames on the media timeline."""

    def __init__(self, path: Path, normalizer: FrameNormalizer) -> None:
        self._path = path
        self._normalizer = normalizer

    def probe(self) -> VideoInfo:
        try:
            with av.open(str(self._path)) as container:
                if not container.streams.video:
                    raise VideoFileError("file has no video stream")
                stream = container.streams.video[0]
                fps = float(stream.average_rate or stream.guessed_rate or 0)
                duration_ms = self._duration_ms(container, stream)
                return VideoInfo(
                    duration_ms=duration_ms,
                    width=stream.codec_context.width,
                    height=stream.codec_context.height,
                    fps=round(fps, 3),
                )
        except av.FFmpegError as exc:
            raise VideoFileError(f"unreadable video: {exc}") from exc

    def frames(self, start_ms: int = 0, end_ms: int | None = None) -> Iterator[FramePacket]:
        with av.open(str(self._path)) as container:
            stream = container.streams.video[0]
            fps = float(stream.average_rate or stream.guessed_rate or 30)
            if start_ms > 0 and stream.time_base:
                container.seek(int(start_ms / 1000 / stream.time_base), stream=stream, backward=True)
            for frame in container.decode(stream):
                if frame.time is None:
                    continue
                timestamp_ms = int(round(frame.time * 1000))
                if timestamp_ms < start_ms:
                    continue
                if end_ms is not None and timestamp_ms > end_ms:
                    return
                frame_index = int(round(frame.time * fps))
                yield self._normalizer.normalize(frame, timestamp_ms, frame_index)

    def frame_at(self, media_ms: int) -> FramePacket | None:
        """The frame on screen at `media_ms`: the latest frame at or before that time."""
        with av.open(str(self._path)) as container:
            stream = container.streams.video[0]
            fps = float(stream.average_rate or stream.guessed_rate or 30)
            if media_ms > 0 and stream.time_base:
                container.seek(int(media_ms / 1000 / stream.time_base), stream=stream, backward=True)
            held: tuple[object, int, int] | None = None
            for frame in container.decode(stream):
                if frame.time is None:
                    continue
                timestamp_ms = int(round(frame.time * 1000))
                if timestamp_ms > media_ms and held is not None:
                    break
                frame_index = int(round(timestamp_ms / 1000 * fps))
                # Copy now. The decoder may reuse this frame's buffer on the next iteration.
                snapshot = av.VideoFrame.from_ndarray(frame.to_ndarray(format="rgb24"), format="rgb24")
                held = (snapshot, timestamp_ms, frame_index)
                if timestamp_ms > media_ms:
                    break
            if held is None:
                return None
            snapshot, timestamp_ms, frame_index = held
            return self._normalizer.normalize(snapshot, timestamp_ms, frame_index)  # type: ignore[arg-type]

    def window_frames(self, start_ms: int, end_ms: int, min_interval_ms: int) -> tuple[FramePacket, ...]:
        """Frames inside a decision window, throttled so the clip is not full source fps."""
        chosen: list[FramePacket] = []
        next_due = start_ms
        for packet in self.frames(start_ms, end_ms):
            if packet.timestamp_ms + 2 < next_due:
                continue
            chosen.append(packet)
            next_due = packet.timestamp_ms + min_interval_ms
        return tuple(chosen)

    @staticmethod
    def _duration_ms(container: av.container.InputContainer, stream: av.VideoStream) -> int:
        if stream.duration is not None and stream.time_base:
            return int(stream.duration * stream.time_base * 1000)
        if container.duration is not None:
            return int(container.duration / 1000)
        return 0
