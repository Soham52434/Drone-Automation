import base64
import io
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from drone_security.agent import LangGraphSummarizer
from drone_security.agent.keyframes import FRAME_LIMITS, KeyframeSelector
from drone_security.indexing import KeyframeStore
from drone_security.models import ClassHit, FramePacket, Keyframe, SessionKind, SummaryKind, SummaryRequest
from drone_security.models.perception import SceneObservation


def _packet(at_ms: int, width: int = 1280, height: int = 720) -> FramePacket:
    return FramePacket(at_ms, at_ms // 100, np.full((height, width, 3), 120, dtype=np.uint8))


def _obs(at_ms: int, *classes: str, event: bool = True) -> SceneObservation:
    return SceneObservation(
        at_ms, 0, event, classes[0] if classes else "none", 0.8, "a man at the gate",
        classes=tuple(ClassHit(c, 0.8) for c in classes),
    )


def test_store_keeps_notable_frames_downscaled_and_throttled(tmp_path):
    store = KeyframeStore(tmp_path / "kf", max_width=320, min_gap_ms=5_000)
    first = store.offer(_packet(1_000), _obs(1_000, "person"))
    assert first is not None and first.classes == ("person",)
    image = Image.open(store.path(first.file_name))
    assert image.format == "JPEG" and image.size == (320, 180)
    assert store.offer(_packet(3_000), _obs(3_000, "person")) is None  # same classes inside the gap
    assert store.offer(_packet(3_500), _obs(3_500, "vehicle")) is not None  # new class
    assert store.offer(_packet(7_000), _obs(7_000, "person")) is not None  # gap passed
    assert store.offer(_packet(8_000), _obs(8_000, "structure", event=False)) is None  # scene only
    assert base64.b64decode(store.base64(first))[:2] == b"\xff\xd8"


def test_alert_frames_are_always_kept_and_names_are_validated(tmp_path):
    store = KeyframeStore(tmp_path / "kf")
    saved = store.save(_packet(5_000), _obs(5_000, "structure", event=False), alert=True)
    assert saved.alert and saved.file_name == "kf_5000.jpg"
    with pytest.raises(ValueError):
        store.path("../../etc/passwd")


def _kf(at_ms: int, *classes: str, alert: bool = False, confidence: float = 0.5) -> Keyframe:
    return Keyframe(at_ms, f"kf_{at_ms}.jpg", classes, "Main gate", "x", alert, confidence)


def test_selector_prefers_alerts_then_the_watch_brief_and_spreads_over_minutes():
    frames = [
        _kf(1_000, "person", confidence=0.9),
        _kf(2_000, "person", confidence=0.95),  # same minute + classes as 1_000: only the best one
        _kf(65_000, "vehicle", confidence=0.4),
        _kf(130_000, "animal", confidence=0.99),
        _kf(200_000, "structure", alert=True, confidence=0.1),
        _kf(260_000, "package", confidence=0.6),
    ]
    picked = KeyframeSelector().pick(frames, SummaryKind.PERIOD, "Only alert on vehicles in the driveway")
    assert len(picked) == FRAME_LIMITS[SummaryKind.PERIOD] == 4
    assert [f.timestamp_ms for f in picked] == sorted(f.timestamp_ms for f in picked)
    chosen = {f.timestamp_ms for f in picked}
    assert {200_000, 65_000} <= chosen  # the alert, then the class the brief asks for
    assert not {1_000, 2_000} <= chosen  # never two frames of the same minute and classes


def test_brief_maps_to_classes_and_blank_brief_uses_the_default():
    selector = KeyframeSelector()
    assert {"vehicle"} <= selector.brief_classes("a boat near the dock")
    assert {"person", "vehicle", "animal", "package", "hazard"} <= selector.brief_classes("")


class _SummaryLlm:
    def __init__(self) -> None:
        self.messages: list = []

    def invoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content="A man in a red jacket at the gate [frame 1].")


def _request(images: tuple[str, ...]) -> SummaryRequest:
    frame = _kf(4_000, "person", alert=True)
    return SummaryRequest(
        "s1", SessionKind.UPLOAD, SummaryKind.ALERT, 0, 10_000, "Watch the gate.",
        observations=(_obs(4_000, "person"),), alert_key="window-0",
        keyframes=(frame,) if images else (), images=images,
    )


def test_llm_sees_labelled_frames_and_records_which():
    jpeg = io.BytesIO()
    Image.new("RGB", (8, 8)).save(jpeg, format="JPEG")
    image = base64.b64encode(jpeg.getvalue()).decode()
    llm = _SummaryLlm()
    summary = LangGraphSummarizer(llm, "m").summarize(_request((image,)))
    system, human = llm.messages
    assert "key frames" in system.content and "[frame N]" in system.content
    kinds = [block["type"] for block in human.content]
    assert kinds == ["text", "text", "image"]
    assert human.content[1]["text"].startswith("[frame 1] t=0:00:04 at Main gate (raised the alert)")
    assert human.content[2] == {"type": "image", "base64": image, "mime_type": "image/jpeg"}
    assert summary.frames == ("kf_4000.jpg",)


def test_without_frames_the_llm_gets_plain_text():
    llm = _SummaryLlm()
    summary = LangGraphSummarizer(llm, "m").summarize(_request(()))
    assert isinstance(llm.messages[1].content, str) and summary.frames == ()


def test_request_rejects_images_without_matching_frames():
    with pytest.raises(ValueError):
        SummaryRequest("s", SessionKind.LIVE, SummaryKind.PERIOD, 0, 1, "b", images=("x",))
