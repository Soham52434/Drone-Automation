from drone_security.models.session import WatchBrief
from drone_security.models.summaries import Keyframe, SummaryKind
from drone_security.perception.classes import ObjectClassifier, classes_named_in

#: How many images each LLM job may see. Few frames keep the call cheap; the text log covers the rest.
FRAME_LIMITS: dict[SummaryKind, int] = {SummaryKind.ALERT: 3, SummaryKind.PERIOD: 4, SummaryKind.FINAL: 6}


class KeyframeSelector:
    """Chooses the few frames the LLM should look at, for what this session watches for.

    Order of preference: frames that raised an alert, then frames showing a class the watch brief
    asks about, then other notable frames by the vision model's confidence. At most one frame per minute
    for the same classes, so the picks spread across the period. Returned oldest first.
    """

    def __init__(self, classifier: ObjectClassifier | None = None) -> None:
        self._classifier = classifier or ObjectClassifier()

    def brief_classes(self, watch_brief: str) -> frozenset[str]:
        """Classes the brief names, e.g. 'boats near the dock' → {vehicle, terrain}."""
        return classes_named_in(WatchBrief.resolve(watch_brief).text, self._classifier)

    def pick(self, keyframes: list[Keyframe] | tuple[Keyframe, ...], kind: SummaryKind, watch_brief: str) -> tuple[Keyframe, ...]:
        limit = FRAME_LIMITS[kind]
        wanted = self.brief_classes(watch_brief)

        def score(frame: Keyframe) -> tuple[int, int, float]:
            return (int(frame.alert), int(bool(wanted.intersection(frame.classes))), frame.confidence)

        chosen: list[Keyframe] = []
        seen: set[tuple[int, tuple[str, ...]]] = set()
        for frame in sorted(keyframes, key=score, reverse=True):
            bucket = (frame.timestamp_ms // 60_000, tuple(sorted(frame.classes)))
            if bucket in seen and not frame.alert:
                continue
            seen.add(bucket)
            chosen.append(frame)
            if len(chosen) == limit:
                break
        return tuple(sorted(chosen, key=lambda f: f.timestamp_ms))
