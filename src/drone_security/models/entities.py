import re
from dataclasses import dataclass, field

_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class EntitySighting:
    """One person/vehicle/animal/package the LLM described in a key frame, with its attributes."""

    timestamp_ms: int
    class_name: str
    description: str
    color: str = ""
    make: str = ""
    model: str = ""
    kind: str = ""  # e.g. "pickup", "sedan", "delivery van", "man", "dog"
    clothing: str = ""
    observation_id: str = ""

    @property
    def signature(self) -> str:
        """Stable fingerprint for "is this the same thing again?": class + colour + make + model + kind."""
        parts = [self.class_name, self.color, self.make, self.model, self.kind]
        return "|".join(" ".join(_WORD.findall(p.lower())) for p in parts)

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "class": self.class_name,
            "description": self.description,
            "color": self.color,
            "make": self.make,
            "model": self.model,
            "kind": self.kind,
            "clothing": self.clothing,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class Visit:
    """A run of sightings of the same entity with no gap longer than the visit gap."""

    start_ms: int
    end_ms: int
    sightings: int


@dataclass(frozen=True)
class EntityMatch:
    """Every visit of one entity (by signature) that matched a question."""

    signature: str
    description: str
    class_name: str
    visits: tuple[Visit, ...]
    observation_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def sightings(self) -> int:
        return sum(v.sightings for v in self.visits)


def group_visits(timestamps: list[int] | tuple[int, ...], gap_ms: int = 120_000) -> tuple[Visit, ...]:
    """Sightings more than `gap_ms` apart are separate visits ("entered twice today")."""
    visits: list[Visit] = []
    for ts in sorted(timestamps):
        last = visits[-1] if visits else None
        if last and ts - last.end_ms <= gap_ms:
            visits[-1] = Visit(last.start_ms, ts, last.sightings + 1)
        else:
            visits.append(Visit(ts, ts, 1))
    return tuple(visits)
