from pathlib import Path

from drone_security.perception import VisionModel
from tests.conftest import make_packet


class FakeVision:
    def __init__(self) -> None:
        self.image = None
        self.kwargs: dict = {}

    def describe(self, image, **kwargs):
        self.image = image
        self.kwargs = kwargs
        return {
            "scene": {"background": "yard"},
            "objects": [],
            "reasoning": "An empty yard with nothing moving.",
        }


def test_observe_sends_the_frame_and_keeps_the_parsed_record(tmp_path: Path):
    perception = VisionModel(tmp_path / "weights.cact")
    model = FakeVision()
    perception._model = model
    packet = make_packet(20, index=3)
    observation = perception.observe(packet)
    assert observation.summary == "An empty yard with nothing moving."
    assert observation.raw["reasoning"] == "An empty yard with nothing moving."
    assert observation.raw["scene"] == {"background": "yard"}
    assert model.image is packet.image
    assert "mask" not in model.kwargs["fields"]
    assert "sections" not in model.kwargs


def test_observe_before_load_fails(tmp_path: Path):
    import pytest

    perception = VisionModel(tmp_path / "weights.cact")
    with pytest.raises(RuntimeError, match="not loaded"):
        perception.observe(make_packet(0))
