from drone_security.models.perception import SceneObservation
from drone_security.pipeline.analyzer import StreamAnalyzer


def _observation(timestamp_ms: int) -> SceneObservation:
    return SceneObservation(timestamp_ms, 0, True, "person", 0.5, "A person.")


def test_window_closes_at_ten_seconds_and_carries_observations():
    analyzer = StreamAnalyzer("s1", window_ms=10_000)
    analyzer.record(_observation(500))
    analyzer.record(_observation(9_500))
    assert analyzer.close_ready(0) is None
    assert analyzer.close_ready(9_999) is None
    window = analyzer.close_ready(10_000)
    assert window is not None
    assert (window.start_ms, window.end_ms) == (0, 10_000)
    assert [item.timestamp_ms for item in window.observations] == [500, 9_500]
    assert analyzer.close_ready(19_999) is None


def test_window_cannot_exceed_fifteen_seconds():
    import pytest

    with pytest.raises(ValueError, match="15"):
        StreamAnalyzer("s1", window_ms=15_001)
