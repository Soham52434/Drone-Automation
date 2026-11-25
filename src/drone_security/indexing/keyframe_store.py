import base64
import re
import threading
from pathlib import Path

from drone_security.models import FramePacket
from drone_security.models.perception import SceneObservation
from drone_security.models.summaries import Keyframe

# Classes worth a picture even when the vision model did not flag an event.
NOTABLE_CLASSES = frozenset({"person", "vehicle", "animal", "package", "hazard", "weapon"})
_FILE = re.compile(r"^kf_\d+(_\d+)?\.jpg$")


class KeyframeStore:
    """Keeps a small JPEG of frames that matter, so the LLM can look at them later.

    Live frames leave the ring buffer within 15 s; summaries run minutes later. Only readings
    with an event or a notable class are kept, at most one per `min_gap_ms` for the same classes,
    downscaled to `max_width`. Alert frames are always kept.
    """

    def __init__(self, directory: Path, max_width: int = 512, quality: int = 70, min_gap_ms: int = 5_000) -> None:
        if max_width <= 0 or not 1 <= quality <= 95 or min_gap_ms < 0:
            raise ValueError("max_width must be positive, quality 1–95, and min_gap_ms non-negative")
        self._directory = directory
        self._max_width = max_width
        self._quality = quality
        self._min_gap = min_gap_ms
        self._last_by_classes: dict[tuple[str, ...], int] = {}
        self._lock = threading.Lock()

    @property
    def directory(self) -> Path:
        return self._directory

    def worth_keeping(self, observation: SceneObservation) -> bool:
        notable = NOTABLE_CLASSES.intersection(observation.class_names)
        if not observation.event_detected and not notable:
            return False
        key = tuple(sorted(notable)) or (observation.label,)
        last = self._last_by_classes.get(key)
        return last is None or observation.timestamp_ms - last >= self._min_gap

    def offer(self, packet: FramePacket, observation: SceneObservation) -> Keyframe | None:
        """Save the frame if it is worth keeping; returns the keyframe or None."""
        if not self.worth_keeping(observation):
            return None
        notable = tuple(sorted(NOTABLE_CLASSES.intersection(observation.class_names))) or (observation.label,)
        self._last_by_classes[notable] = observation.timestamp_ms
        return self.save(packet, observation)

    def save(self, packet: FramePacket, observation: SceneObservation | None = None, alert: bool = False) -> Keyframe:
        from PIL import Image

        image = Image.fromarray(packet.image)
        if image.width > self._max_width:
            image = image.resize((self._max_width, round(image.height * self._max_width / image.width)))
        with self._lock:
            self._directory.mkdir(parents=True, exist_ok=True)
            path = self._directory / f"kf_{packet.timestamp_ms}.jpg"
            suffix = 2
            while path.exists() and not alert:
                path = self._directory / f"kf_{packet.timestamp_ms}_{suffix}.jpg"
                suffix += 1
            image.save(path, format="JPEG", quality=self._quality, optimize=True)
        return Keyframe(
            timestamp_ms=packet.timestamp_ms,
            file_name=path.name,
            classes=observation.class_names if observation else (),
            location=observation.location if observation else "",
            summary=observation.summary if observation else "",
            alert=alert,
            confidence=float(observation.confidence) if observation else 0.0,
        )

    def path(self, file_name: str) -> Path:
        if not _FILE.match(file_name):
            raise ValueError(f"not a keyframe file name: {file_name}")
        return self._directory / file_name

    def base64(self, keyframe: Keyframe) -> str:
        return base64.b64encode(self.path(keyframe.file_name).read_bytes()).decode("ascii")

