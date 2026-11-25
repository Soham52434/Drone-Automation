from drone_security.perception import scene_observation_from_vision


def test_maps_scene_objects_and_events():
    observation = scene_observation_from_vision(
        {
            "scene": "Front porch in daylight.",
            "objects": [{"name": "package", "score": 0.91}],
            "events": [
                {
                    "name": "package_dropped",
                    "description": "Delivery driver placed a brown box near the front door.",
                    "score": 0.88,
                }
            ],
        },
        timestamp_ms=1_732_365_012_450,
        frame_index=372,
    )
    assert observation.event_detected is True
    assert observation.label == "package_dropped"
    assert observation.confidence == 0.91
    assert "brown box" in observation.summary
    assert observation.timestamp_ms == 1_732_365_012_450
    assert observation.frame_index == 372


def test_passes_through_prompt_shaped_fields():
    observation = scene_observation_from_vision(
        {
            "event_detected": True,
            "label": "package_dropped",
            "confidence": 0.91,
            "summary": "Delivery driver placed a brown box near the front door.",
        },
        timestamp_ms=10,
        frame_index=1,
    )
    assert observation.to_dict()["label"] == "package_dropped"
    assert observation.event_detected is True
    assert observation.confidence == 0.91


def test_parsed_record_keeps_reasoning_and_drops_masks():
    observation = scene_observation_from_vision(
        {
            "scene": {"background": "porch", "style": "daylight"},
            "objects": [{"name": "package", "score": 0.91, "mask": [1, 2, 3], "description": {"color": "brown"}}],
            "reasoning": "A brown package sits on the porch.",
        },
        timestamp_ms=10,
        frame_index=1,
    )
    assert observation.summary == "A brown package sits on the porch."
    assert observation.raw["reasoning"] == "A brown package sits on the porch."
    assert observation.raw["scene"] == {"background": "porch", "style": "daylight"}
    stored = observation.raw["objects"]
    assert isinstance(stored, list)
    assert "mask" not in stored[0]
    assert "raw" in observation.to_dict()


def test_empty_frame_is_not_an_event():
    observation = scene_observation_from_vision(
        {"scene": "An empty driveway.", "objects": [], "events": []},
        timestamp_ms=0,
        frame_index=0,
    )
    assert observation.event_detected is False
    assert observation.label == "none"
    assert observation.confidence == 0.0
    assert observation.summary == "An empty driveway."


def test_form_block_yes_no_strings():
    observation = scene_observation_from_vision(
        {"form": {"event_detected": "no", "label": "none", "summary": "Still yard."}, "objects": []},
        timestamp_ms=5,
        frame_index=2,
    )
    assert observation.event_detected is False
    assert observation.summary == "Still yard."
