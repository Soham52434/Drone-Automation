import json
import threading
import time
from pathlib import Path

from drone_security.models.perception import SceneObservation


class HourlyObservationLog:
    """Appends every vision observation to an hour-keyed JSON file. Alerts are not required."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._lock = threading.Lock()

    def append(self, observation: SceneObservation, recorded_ms: int | None = None) -> Path:
        recorded = int(time.time() * 1000) if recorded_ms is None else recorded_ms
        hour = time.strftime("%Y-%m-%dT%H", time.gmtime(recorded / 1000))
        path = self._directory / f"{hour}.json"
        record = observation.to_dict()
        with self._lock:
            self._directory.mkdir(parents=True, exist_ok=True)
            rows = json.loads(path.read_text()) if path.is_file() else []
            rows.append(record)
            path.write_text(json.dumps(rows, indent=2))
        return path
