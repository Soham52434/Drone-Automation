import re
from collections.abc import Iterable

from drone_security.models.perception import ClassHit

# Class → words the vision model uses for things of that class. Order matters: the first class whose
# words match an object name wins, so "police car" is a vehicle, not a person.
CLASS_WORDS: dict[str, tuple[str, ...]] = {
    "hazard": ("fire", "flame", "flames", "smoke", "explosion", "spark"),
    "weapon": ("gun", "rifle", "pistol", "knife", "weapon", "bat"),
    "vehicle": (
        "car", "truck", "van", "bus", "suv", "pickup", "vehicle", "motorcycle", "motorbike", "scooter",
        "bicycle", "bike", "boat", "ship", "trailer", "tractor", "ambulance", "taxi", "jeep", "f150", "sedan", "airplane", "plane", "aircraft", "helicopter", "drone",
    ),
    "person": (
        "person", "man", "woman", "men", "women", "people", "boy", "girl", "child", "kid", "baby", "human",
        "pedestrian", "worker", "driver", "guard", "officer", "face", "hand", "head", "intruder",
    ),
    "animal": ("dog", "cat", "bird", "animal", "cow", "horse", "deer", "squirrel", "goat", "sheep", "monkey", "rat"),
    "package": ("package", "box", "parcel", "bag", "backpack", "suitcase", "luggage", "carton", "delivery"),
    "electronics": ("tv", "television", "laptop", "phone", "monitor", "screen", "computer", "camera", "keyboard"),
    "furniture": ("chair", "table", "sofa", "couch", "bed", "desk", "shelf", "bench", "cabinet", "stool"),
    "lighting": ("light", "lamp", "lights", "fixture", "chandelier", "bulb"),
    "vegetation": ("tree", "trees", "grass", "bush", "plant", "plants", "flower", "hedge", "lawn", "leaves"),
    "structure": (
        "wall", "door", "window", "ceiling", "roof", "gate", "fence", "house", "building", "floor", "stairs",
        "porch", "garage", "pillar", "column", "railing", "curtain", "blinds", "conditioner",
    ),
    "terrain": ("sky", "road", "driveway", "street", "sidewalk", "ground", "water", "dock", "path", "parking"),
}

OTHER = "other"
ALL_CLASSES: tuple[str, ...] = (*CLASS_WORDS, OTHER)
_WORD = re.compile(r"[a-z0-9]+")


class ObjectClassifier:
    """Rolls the vision model's exact object names (\"man in a black shirt\") up to classes (\"person\")."""

    def __init__(self, class_words: dict[str, tuple[str, ...]] = CLASS_WORDS) -> None:
        self._lookup = {word: name for name, words in class_words.items() for word in words}
        self._order = list(class_words)

    def class_of(self, object_name: str) -> str:
        words = [_singular(word) for word in _WORD.findall(object_name.lower())]
        matches = {self._lookup[word] for word in words if word in self._lookup}
        for name in self._order:
            if name in matches:
                return name
        return OTHER

    def classify(self, objects: Iterable[tuple[str, float]]) -> tuple[ClassHit, ...]:
        """Best score and count per class, strongest first."""
        best: dict[str, ClassHit] = {}
        for name, score in objects:
            if not name.strip():
                continue
            cls = self.class_of(name)
            current = best.get(cls)
            if current is None:
                best[cls] = ClassHit(cls, score, 1)
            else:
                best[cls] = ClassHit(cls, max(current.score, score), current.count + 1)
        return tuple(sorted(best.values(), key=lambda hit: (-hit.score, hit.name)))


def _singular(word: str) -> str:
    if word in {"glasses", "bus", "grass"}:
        return word
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def classes_named_in(text: str, classifier: ObjectClassifier | None = None) -> frozenset[str]:
    """Classes a piece of text names, e.g. 'boats near the dock' → {vehicle, terrain}."""
    classifier = classifier or ObjectClassifier()
    return frozenset({classifier.class_of(word) for word in text.split()} - {OTHER})
