from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from drone_security.agent.llm import ChatModel, parse_json_object, response_text
from drone_security.models.entities import EntitySighting

DESCRIBED_CLASSES = ("person", "vehicle", "animal", "package")

_SYSTEM = (
    "You catalogue what a security camera frame shows, for later questions such as "
    "'how many times did the blue Ford F150 come by?'. Describe only what you can see. "
    "Use empty strings for anything you cannot tell. Never guess a make or model you cannot read or recognise."
)

_ASK = (
    "A small local vision model said: {vision}\n"
    "Classes in the frame: {classes}\n\n"
    "List every person, vehicle, animal, and package you can see. Return JSON only:\n"
    '{{"entities": [{{"class": "person|vehicle|animal|package", "description": "short phrase, e.g. blue Ford F150 pickup", '
    '"color": "", "make": "", "model": "", "kind": "e.g. pickup, sedan, delivery van, man, woman, dog", '
    '"clothing": "people only"}}]}}'
)


class EntityState(TypedDict):
    image: str
    vision: str
    classes: list[str]
    timestamp_ms: int
    observation_id: str
    raw: dict
    sightings: list[EntitySighting]
    error: str


class LangGraphEntityDescriber:
    """Advanced analytics as a LangGraph: describe_entities (LLM reads the key frame) → normalize.

    The vision model names "car"; this names "blue Ford F150 pickup", so repeat visits can be counted.
    """

    def __init__(self, llm: ChatModel | None) -> None:
        self._llm = llm
        graph = StateGraph(EntityState)
        graph.add_node("describe_entities", self._describe)
        graph.add_node("normalize", self._normalize)
        graph.add_edge(START, "describe_entities")
        graph.add_conditional_edges("describe_entities", lambda s: "end" if s["error"] else "normalize", {"normalize": "normalize", "end": END})
        graph.add_edge("normalize", END)
        self.graph = graph.compile()

    @property
    def available(self) -> bool:
        return self._llm is not None

    def describe(
        self, image_b64: str, vision_summary: str, classes: tuple[str, ...], timestamp_ms: int, observation_id: str
    ) -> tuple[EntitySighting, ...]:
        if self._llm is None:
            return ()
        state = self.graph.invoke(
            {
                "image": image_b64,
                "vision": vision_summary,
                "classes": list(classes),
                "timestamp_ms": timestamp_ms,
                "observation_id": observation_id,
                "raw": {},
                "sightings": [],
                "error": "",
            }
        )
        return tuple(state["sightings"])

    def _describe(self, state: EntityState) -> dict[str, object]:
        try:
            reply = self._llm.invoke(  # type: ignore[union-attr]
                [
                    SystemMessage(content=_SYSTEM),
                    HumanMessage(
                        content=[
                            {"type": "text", "text": _ASK.format(vision=state["vision"] or "nothing", classes=", ".join(state["classes"]) or "none")},
                            {"type": "image", "base64": state["image"], "mime_type": "image/jpeg"},
                        ]
                    ),
                ]
            )
            return {"raw": parse_json_object(response_text(reply))}
        except Exception as exc:  # busy, quota, or unparseable: skip this frame
            return {"error": str(exc) or exc.__class__.__name__}

    def _normalize(self, state: EntityState) -> dict[str, object]:
        items = state["raw"].get("entities") if isinstance(state["raw"], dict) else None
        sightings: list[EntitySighting] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            cls = str(item.get("class", "")).strip().lower()
            description = str(item.get("description", "")).strip()
            if cls not in DESCRIBED_CLASSES or not description:
                continue
            sightings.append(
                EntitySighting(
                    timestamp_ms=state["timestamp_ms"],
                    class_name=cls,
                    description=description[:160],
                    color=_field(item, "color"),
                    make=_field(item, "make"),
                    model=_field(item, "model"),
                    kind=_field(item, "kind"),
                    clothing=_field(item, "clothing") if cls == "person" else "",
                    observation_id=state["observation_id"],
                )
            )
        return {"sightings": sightings}


def _field(item: dict, key: str) -> str:
    value = item.get(key)
    text = str(value).strip() if isinstance(value, (str, int, float)) else ""
    return "" if text.lower() in {"unknown", "n/a", "none", "null", "-"} else text[:60]
