import pytest

from drone_security.perception import LangGraphPerception, VisionRejectedError
from tests.conftest import make_packet


class FakeVision:
    loaded = True

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls = 0

    def describe(self, packet) -> object:
        self.calls += 1
        return self.payload


def test_describe_then_map_to_an_observation():
    vision = FakeVision(
        {"reasoning": "A man stands by the door.", "objects": [{"name": "man", "score": 0.81}]}
    )
    observation = LangGraphPerception(vision).observe(make_packet(1_500, index=3))
    assert vision.calls == 1
    assert observation.timestamp_ms == 1_500
    assert observation.frame_index == 3
    assert observation.label == "man"
    assert "door" in observation.summary


def test_non_object_payload_is_rejected():
    with pytest.raises(VisionRejectedError, match="non-object"):
        LangGraphPerception(FakeVision(["not", "a", "dict"])).observe(make_packet(0))


def test_loaded_follows_the_wrapped_model():
    assert LangGraphPerception(FakeVision({})).loaded is True
