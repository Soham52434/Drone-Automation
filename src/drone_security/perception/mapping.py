from collections.abc import Mapping

from drone_security.models.perception import SceneObservation

_SUMMARY_KEYS = ("summary", "description", "caption", "text")
_NAME_KEYS = ("name", "label", "action", "type", "category")
_SCORE_KEYS = ("score", "confidence", "conf")
_EMPTY_LABELS = {"", "none", "background", "empty", "no_event"}


def scene_observation_from_vision(
    payload: Mapping[str, object], timestamp_ms: int, frame_index: int
) -> SceneObservation:
    """Turn one vision-model `describe` payload into the timeline record the rest of the app stores."""
    source = _form(payload)
    label = _clean(_text(source.get("label"))) or _best_name(payload)
    summary = _clean(_text(source.get("summary"))) or _event_text(payload) or _scene_text(payload)
    confidence = _explicit_confidence(source)
    if confidence is None:
        confidence = _best_score(payload)
    event_detected = _explicit_event(source)
    if event_detected is None:
        event_detected = bool(label) and label.lower() not in _EMPTY_LABELS and confidence >= 0.35
    if not label:
        label = "activity" if event_detected else "none"
    if not summary:
        summary = _clean(_text(payload.get("reasoning"))) or (label if event_detected else "No notable activity in this frame.")
    return SceneObservation(
        timestamp_ms=timestamp_ms,
        frame_index=frame_index,
        event_detected=event_detected,
        label=label,
        confidence=round(_unit(confidence), 3),
        summary=summary,
        raw=_readable_vision(payload),
    )


def vision_objects(payload: Mapping[str, object]) -> list[tuple[str, float]]:
    """Every named object the vision model reported, with its score."""
    items = payload.get("objects")
    if not isinstance(items, list):
        return []
    return [(_name(item), _score(item) or 0.0) for item in items if _name(item)]


def vision_scene(payload: Mapping[str, object]) -> str:
    """The vision model's own word for the setting, e.g. "porch" or "front yard"."""
    scene = payload.get("scene")
    if isinstance(scene, str):
        return _clean(scene)
    if isinstance(scene, Mapping):
        for key in ("location", "setting", "place", "background", "environment"):
            found = scene.get(key)
            if isinstance(found, str) and found.strip():
                return _clean(found)
    return ""


def _readable_vision(payload: Mapping[str, object]) -> dict[str, object]:
    """The vision model's parsed record without mask polygons, which are large and not for reading."""
    return _json_ready(_without_masks(payload))


def _without_masks(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _without_masks(item) for key, item in value.items() if key != "mask"}
    if isinstance(value, list):
        return [_without_masks(item) for item in value]
    return value


def _json_ready(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    ready: dict[str, object] = {}
    for key, item in value.items():
        ready[str(key)] = _json_value(item)
    return ready


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _form(payload: Mapping[str, object]) -> Mapping[str, object]:
    form = payload.get("form")
    if isinstance(form, Mapping):
        return form
    return payload


def _explicit_event(source: Mapping[str, object]) -> bool | None:
    value = source.get("event_detected")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _explicit_confidence(source: Mapping[str, object]) -> float | None:
    value = source.get("confidence")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _scene_text(payload: Mapping[str, object]) -> str:
    return _text(payload.get("scene")) or _text(payload.get("description")) or _text(payload.get("caption"))


def _event_text(payload: Mapping[str, object]) -> str:
    for key in ("events", "relations"):
        items = payload.get(key)
        if isinstance(items, list):
            for item in items:
                text = _text(item)
                if text:
                    return text
    return ""


def _best_name(payload: Mapping[str, object]) -> str:
    for key in ("events", "objects", "relations"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        named = [(item, _score(item) or 0.0) for item in items if _name(item)]
        if named:
            item, _ = max(named, key=lambda pair: pair[1])
            return _name(item)
    return ""


def _best_score(payload: Mapping[str, object]) -> float:
    scores = [score for key in ("events", "objects", "relations", "text") for score in _scores(payload.get(key))]
    scene_score = _score(payload.get("scene"))
    if scene_score is not None:
        scores.append(scene_score)
    return max(scores, default=0.0)


def _scores(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    return [score for item in value if (score := _score(item)) is not None]


def _score(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, Mapping):
        for key in _SCORE_KEYS:
            found = value.get(key)
            if isinstance(found, (int, float)) and not isinstance(found, bool):
                return float(found)
    return None


def _name(value: object) -> str:
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, Mapping):
        for key in _NAME_KEYS:
            found = value.get(key)
            if isinstance(found, str) and found.strip():
                return _clean(found)
    return ""


def _text(value: object) -> str:
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, Mapping):
        for key in _SUMMARY_KEYS:
            found = value.get(key)
            if isinstance(found, str) and found.strip():
                return _clean(found)
        return _name(value)
    return ""


def _clean(value: str) -> str:
    return " ".join(value.split())


def _unit(value: float) -> float:
    if value > 1.0 and value <= 100.0:
        value = value / 100.0
    return min(1.0, max(0.0, value))
