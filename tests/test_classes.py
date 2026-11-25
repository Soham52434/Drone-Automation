import pytest

from drone_security.models import ClassHit
from drone_security.perception import LangGraphPerception
from drone_security.perception.classes import ObjectClassifier
from tests.conftest import make_packet


@pytest.mark.parametrize(
    ("name", "cls"),
    [
        ("man in a dark shirt", "person"),
        ("police car", "vehicle"),
        ("blue Ford F150", "vehicle"),
        ("brown package", "package"),
        ("dogs", "animal"),
        ("smoke plume", "hazard"),
        ("ceiling light", "lighting"),
        ("rectangular windows", "structure"),
        ("mysterious blob", "other"),
    ],
)
def test_objects_roll_up_to_classes(name, cls):
    assert ObjectClassifier().class_of(name) == cls


def test_classify_keeps_best_score_and_count_per_class():
    hits = ObjectClassifier().classify([("man", 0.5), ("woman", 0.8), ("door", 0.6), ("", 0.9)])
    assert [(h.name, h.score, h.count) for h in hits] == [("person", 0.8, 2), ("structure", 0.6, 1)]


class _Vision:
    loaded = True

    def __init__(self, payload):
        self.payload = payload

    def describe(self, packet):
        return self.payload


def test_perception_graph_adds_classes_and_scene():
    payload = {
        "reasoning": "A man stands by the gate.",
        "scene": {"background": "front yard"},
        "objects": [{"name": "man", "score": 0.8}, {"name": "gate", "score": 0.4}],
    }
    observation = LangGraphPerception(_Vision(payload)).observe(make_packet(0))
    assert observation.class_names == ("person", "structure")
    assert observation.scene == "front yard"
    assert observation.to_dict()["classes"][0] == {"name": "person", "score": 0.8, "count": 1}


def test_quiet_frame_without_objects_has_no_classes():
    observation = LangGraphPerception(_Vision({"reasoning": "Empty."})).observe(make_packet(0))
    assert observation.classes == ()


def test_location_is_the_scene():
    from drone_security.models.perception import SceneObservation

    observation = SceneObservation(0, 0, True, "man", 0.8, "a man indoors", scene="indoor room")
    assert observation.location == "indoor room" and observation.to_dict()["location"] == "indoor room"


def test_decision_evidence_carries_scene_and_classes_only():
    from drone_security.decisions.graph import _evidence_text
    from drone_security.models.perception import DecisionWindow, SceneObservation

    observation = SceneObservation(0, 0, True, "man", 0.8, "a man", classes=(ClassHit("person", 0.8),), scene="indoor")
    text = _evidence_text(DecisionWindow("s", 0, 1_000, (observation,)), video_attached=False)
    assert "scene=indoor" in text and "classes=person" in text
    assert "altitude" not in text and "zone" not in text
