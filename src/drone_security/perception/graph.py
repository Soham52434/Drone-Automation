from dataclasses import replace
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from drone_security.models import FramePacket
from drone_security.models.perception import SceneObservation
from drone_security.perception.classes import ObjectClassifier
from drone_security.perception.mapping import vision_objects, vision_scene, scene_observation_from_vision


class FrameDescriber(Protocol):
    @property
    def loaded(self) -> bool: ...

    def describe(self, packet: FramePacket) -> object: ...


class VisionRejectedError(RuntimeError):
    pass


class PerceptionState(TypedDict):
    packet: FramePacket
    payload: object
    observation: SceneObservation | None
    error: str


class LangGraphPerception:
    """The local vision model as a LangGraph: describe → map_observation → classify_objects, or reject a malformed payload.

    Same `observe(packet)` interface as `VisionModel`, so the pipeline does not change.
    """

    def __init__(self, vision: FrameDescriber, classifier: ObjectClassifier | None = None) -> None:
        self._vision = vision
        self._classifier = classifier or ObjectClassifier()
        graph = StateGraph(PerceptionState)
        graph.add_node("describe", self._describe)
        graph.add_node("map_observation", self._map)
        graph.add_node("classify_objects", self._classify)
        graph.add_node("reject", self._reject)
        graph.add_edge(START, "describe")
        graph.add_conditional_edges("describe", _route, {"map": "map_observation", "reject": "reject"})
        graph.add_edge("map_observation", "classify_objects")
        graph.add_edge("classify_objects", END)
        graph.add_edge("reject", END)
        self.graph = graph.compile()

    @property
    def loaded(self) -> bool:
        return self._vision.loaded

    def observe(self, packet: FramePacket) -> SceneObservation:
        state = self.graph.invoke({"packet": packet, "payload": None, "observation": None, "error": ""})
        if state["observation"] is None:
            raise VisionRejectedError(state["error"] or "The vision model produced no observation")
        return state["observation"]

    def _describe(self, state: PerceptionState) -> dict[str, object]:
        return {"payload": self._vision.describe(state["packet"])}

    def _map(self, state: PerceptionState) -> dict[str, object]:
        packet = state["packet"]
        payload = state["payload"]
        assert isinstance(payload, dict)
        return {"observation": scene_observation_from_vision(payload, packet.timestamp_ms, packet.frame_index)}

    def _classify(self, state: PerceptionState) -> dict[str, object]:
        """Exact vision objects → classes (person, vehicle, …) and the scene where they were seen."""
        observation = state["observation"]
        payload = state["payload"]
        assert observation is not None and isinstance(payload, dict)
        objects = vision_objects(payload)
        if not objects and observation.event_detected:
            objects = [(observation.label, observation.confidence)]
        classes = self._classifier.classify(objects)
        return {"observation": replace(observation, classes=classes, scene=vision_scene(payload))}

    def _reject(self, state: PerceptionState) -> dict[str, object]:
        kind = type(state["payload"]).__name__
        return {"observation": None, "error": f"The vision model returned a non-object payload ({kind})"}


def _route(state: PerceptionState) -> str:
    return "map" if isinstance(state["payload"], dict) else "reject"
