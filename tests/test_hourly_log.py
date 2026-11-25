import json

from drone_security.indexing import HourlyObservationLog
from drone_security.models.perception import SceneObservation


def test_appends_observations_into_the_utc_hour_file(tmp_path):
    log = HourlyObservationLog(tmp_path)
    observation = SceneObservation(50, 1, False, "none", 0.0, "Quiet.")
    path = log.append(observation, recorded_ms=1_700_000_000_000)
    log.append(observation, recorded_ms=1_700_000_000_000)
    rows = json.loads(path.read_text())
    assert path.name.endswith(".json")
    assert len(rows) == 2
    assert rows[0]["summary"] == "Quiet."
    assert rows[0]["timestamp_ms"] == 50
