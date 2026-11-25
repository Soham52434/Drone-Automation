import logging
from pathlib import Path

from drone_security.models import FramePacket
from drone_security.models.perception import SceneObservation
from drone_security.perception.mapping import scene_observation_from_vision

logger = logging.getLogger(__name__)

# Score and box stay. Description, position, scene, and reasoning stay.
# Masks are left out so the record sent to the chat is the readable parse.
_DESCRIBE_FIELDS = ["bbox", "score", "description", "position"]


class VisionModel:
    """The local vision model. Loaded once at startup from its saved weights and reused for every frame."""

    def __init__(self, weights_path: Path) -> None:
        self.weights_path = weights_path
        self._model: object | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        import cactus

        self._model = cactus.Mirage(weights=str(self.weights_path))
        logger.info("The vision model loaded from %s", self.weights_path)

    def describe(self, packet: FramePacket) -> object:
        """Raw vision-model output for one frame; callers validate and map it."""
        if self._model is None:
            raise RuntimeError("The vision model is not loaded")
        return self._model.describe(packet.image, fields=list(_DESCRIBE_FIELDS))  # type: ignore[attr-defined]

    def observe(self, packet: FramePacket) -> SceneObservation:
        payload = self.describe(packet)
        if not isinstance(payload, dict):
            raise RuntimeError("The vision model returned a non-object payload")
        return scene_observation_from_vision(payload, packet.timestamp_ms, packet.frame_index)


def ensure_vision_weights(directory: Path) -> Path:
    """Save the published vision-model weights under `directory` and return that local path."""
    from cactus.agent.fetch import MIRAGE, fetch_weights

    directory.mkdir(parents=True, exist_ok=True)
    return Path(fetch_weights(MIRAGE, dest_dir=str(directory)))


def load_vision_model(directory: Path) -> VisionModel:
    perception = VisionModel(ensure_vision_weights(directory))
    perception.load()
    return perception
