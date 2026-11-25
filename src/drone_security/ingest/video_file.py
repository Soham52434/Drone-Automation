import bisect
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
                    playable_ms=_playable_ms(self._path),
                )
        except av.FFmpegError as exc:
            raise VideoFileError(f"unreadable video: {exc}") from exc

    def frames(
        self, start_ms: int = 0, end_ms: int | None = None, min_interval_ms: int = 0
    ) -> Iterator[FramePacket]:
        """Frames from `start_ms` to `end_ms`. With `min_interval_ms`, frames closer together are
        skipped before they are converted, which is the expensive part on 4K footage."""
        with av.open(str(self._path)) as container:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            fps = float(stream.average_rate or stream.guessed_rate or 30)
            if start_ms > 0 and stream.time_base:
                container.seek(int(start_ms / 1000 / stream.time_base), stream=stream, backward=True)
            next_due = start_ms
            for frame in container.decode(stream):
                if frame.time is None:
                    continue
                timestamp_ms = int(round(frame.time * 1000))
                if timestamp_ms < start_ms:
                    continue
                if end_ms is not None and timestamp_ms > end_ms:
                    return
                if min_interval_ms and timestamp_ms + 2 < next_due:
                    continue
                next_due = timestamp_ms + min_interval_ms
                frame_index = int(round(frame.time * fps))
                yield self._normalizer.normalize(frame, timestamp_ms, frame_index)

    def frame_at(self, media_ms: int) -> FramePacket | None:
        """The frame on screen at `media_ms`: the latest frame at or before that time."""
        with self.playback() as reader:
            return reader.frame_at(media_ms)

    def playback(self) -> "PlaybackReader":
        """A forward reader that keeps the decoder open, for sampling a video as it plays."""
        return PlaybackReader(self._path, self._normalizer)

    def window_frames(self, start_ms: int, end_ms: int, min_interval_ms: int) -> tuple[FramePacket, ...]:
        """Frames inside a decision window, throttled so the clip is not full source fps."""
        return tuple(self.frames(start_ms, end_ms, min_interval_ms))

    @staticmethod
    def _duration_ms(container: av.container.InputContainer, stream: av.VideoStream) -> int:
        if stream.duration is not None and stream.time_base:
            return int(stream.duration * stream.time_base * 1000)
        if container.duration is not None:
            return int(container.duration / 1000)
        return 0


class PlaybackReader:
    """Reads the frame on screen at a moving playhead, the way a video player does.

    The decoder stays open and decodes forward; only the frame that is returned is converted
    to RGB. Keyframe positions are indexed once (packet headers only, no decoding). When the
    playhead moves past a keyframe that is ahead of the decoder, it jumps there instead of
    decoding every frame in between; a jump backwards also seeks.
    """

    def __init__(self, path: Path, normalizer: FrameNormalizer) -> None:
        self._normalizer = normalizer
        self._keyframes_ms = _keyframe_times(path)
        #: True once the decoder has run out of frames (the real end of the data).
        self.exhausted = False
        self._container = av.open(str(path))
        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"
        self._fps = float(self._stream.average_rate or self._stream.guessed_rate or 30)
        self._frames: Iterator[tuple[av.VideoFrame, int]] | None = None
        self._pending: tuple[av.VideoFrame, int] | None = None
        self._current: tuple[av.VideoFrame, int] | None = None
        self._position_ms = -1

    def __enter__(self) -> "PlaybackReader":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._frames = None
        self._pending = None
        self._current = None
        self._container.close()

    def frame_at(self, media_ms: int) -> FramePacket | None:
        """The latest frame at or before `media_ms` (or the first frame after a seek), None at the end."""
        if self._frames is None or media_ms < self._position_ms or self._keyframe_between(self._position_ms, media_ms):
            self._seek(media_ms)
        held = self._current if self._current is not None and self._current[1] <= media_ms else None
        while True:
            item = self._pending or next(self._frames, None)  # type: ignore[arg-type]
            self._pending = None
            if item is None:
                self.exhausted = True
                break
            if item[1] > media_ms:
                if held is None:
                    held = item
                else:
                    self._pending = item
                break
            held = item
        if held is None:
            return None
        self._current = held
        frame, timestamp_ms = held
        self._position_ms = timestamp_ms
        frame_index = int(round(timestamp_ms / 1000 * self._fps))
        return self._normalizer.normalize(frame, timestamp_ms, frame_index)

    def _keyframe_between(self, after_ms: int, until_ms: int) -> bool:
        """A keyframe lies after the decoder's position and at or before the target: seeking is cheaper."""
        index = bisect.bisect_right(self._keyframes_ms, until_ms)
        return index > 0 and self._keyframes_ms[index - 1] > after_ms + 1

    def _seek(self, media_ms: int) -> None:
        if media_ms > 0 and self._stream.time_base:
            self._container.seek(int(media_ms / 1000 / self._stream.time_base), stream=self._stream, backward=True)
        else:
            self._container.seek(0)
        self._frames = self._decode()
        self._pending = None
        self._current = None
        self._position_ms = -1
        self.exhausted = False

    def _decode(self) -> Iterator[tuple[av.VideoFrame, int]]:
        for frame in self._container.decode(self._stream):
            if frame.time is not None:
                yield frame, int(round(frame.time * 1000))


def _keyframe_times(path: Path) -> list[int]:
    """Media times (ms) of the video's keyframes, from packet headers only."""
    times: list[int] = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        for packet in container.demux(stream):
            if packet.is_keyframe and packet.pts is not None and packet.time_base:
                times.append(int(round(float(packet.pts * packet.time_base) * 1000)))
    return sorted(times)


def _playable_ms(path: Path) -> int | None:
    """End time (ms) of the last video packet actually in the file, from packet headers only."""
    end: float | None = None
    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            for packet in container.demux(stream):
                if packet.pts is None or not packet.time_base:
                    continue
                stop = float((packet.pts + (packet.duration or 0)) * packet.time_base)
                end = stop if end is None else max(end, stop)
    except av.FFmpegError:
        pass  # a damaged tail: keep what was read
    return None if end is None else int(round(end * 1000))
