import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from langchain_core.messages import SystemMessage

from drone_security.config import AppConfig
from drone_security.decisions import LangGraphDecisionGate
from drone_security.models.perception import SceneObservation
from drone_security.models.session import DEFAULT_WATCH_BRIEF
from main import create_app
from tests.conftest import write_test_video


class ScriptedPerception:
    def __init__(self, event: bool, label: str, summary: str, confidence: float = 0.9) -> None:
        self.event = event
        self.label = label
        self.summary = summary
        self.confidence = confidence
        self.calls = 0

    def observe(self, packet) -> SceneObservation:
        self.calls += 1
        return SceneObservation(
            timestamp_ms=packet.timestamp_ms,
            frame_index=packet.frame_index,
            event_detected=self.event,
            label=self.label,
            confidence=self.confidence,
            summary=self.summary,
        )


class ScriptedClassifier:
    def __init__(self, noul: float, rule: str, brief: str = DEFAULT_WATCH_BRIEF) -> None:
        self.noul = noul
        self.rule = rule
        self.brief = brief
        self.calls = 0

    def invoke(self, payload: dict) -> object:
        self.calls += 1
        message = payload["state"][0]
        assert isinstance(message, SystemMessage)
        assert self.brief in message.content
        assert self.brief in payload["questions"]["alert"].instructions
        assert any(isinstance(block, dict) and block.get("type") == "video" for block in payload["state"])
        return SimpleNamespace(
            nouls={"alert": SimpleNamespace(noul=self.noul)},
            choices={
                "rule": SimpleNamespace(choice=self.rule, confidence=0.8),
                "severity": SimpleNamespace(choice="warn", confidence=0.7),
            },
        )


def _events(client: TestClient, session_id: str) -> list[tuple[str, dict]]:
    found: list[tuple[str, dict]] = []
    with client.stream("GET", f"/api/sessions/{session_id}/events") as response:
        assert response.status_code == 200
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                name = "message"
                data = ""
                for line in block.splitlines():
                    if line.startswith("event: "):
                        name = line.removeprefix("event: ")
                    elif line.startswith("data: "):
                        data = line.removeprefix("data: ")
                if data:
                    found.append((name, json.loads(data)))
            if any(event == "status" and body.get("status") == "ended" for event, body in found):
                break
    return found


def test_upload_stream_emits_observations_and_saves_one_alert(tmp_path, config: AppConfig):
    video = write_test_video(tmp_path / "yard.mp4", seconds=12)
    perception = ScriptedPerception(True, "person", "A person is at the gate.")
    gate = LangGraphDecisionGate(ScriptedClassifier(0.92, "person_on_property"), threshold=0.6)
    with TestClient(create_app(config, perception=perception, gate=gate, playback_pace=False)) as client:
        with video.open("rb") as data:
            session = client.post("/api/sessions/upload", files={"file": ("yard.mp4", data, "video/mp4")}).json()
        events = _events(client, session["id"])
        detail = client.get(f"/api/sessions/{session['id']}").json()

    names = [name for name, _ in events]
    assert "observation" in names
    assert "decision" in names
    assert "alert" in names
    decision = next(body["decision"] for name, body in events if name == "decision")
    assert decision["alert"] is True
    assert detail["chunks"][0]["trigger"] == "alert"
    metadata = client_metadata(config, session["id"], detail["chunks"][0]["chunk_file"])
    assert metadata["vision_output"]["label"] == "person"
    assert metadata["decision"]["alert"] is True
    assert metadata["seek_offset_sec"] >= 0
    assert perception.calls > 0
    hour_logs = list((config.session_dir(session["id"]) / "logs" / "observations").glob("*.json"))
    assert hour_logs and json.loads(hour_logs[0].read_text())


def test_quiet_window_does_not_save_a_chunk(tmp_path, config: AppConfig):
    video = write_test_video(tmp_path / "quiet.mp4", seconds=12)
    perception = ScriptedPerception(False, "none", "An empty yard.", confidence=0.0)
    gate = LangGraphDecisionGate(ScriptedClassifier(0.1, "none"), threshold=0.6)
    with TestClient(create_app(config, perception=perception, gate=gate, playback_pace=False)) as client:
        with video.open("rb") as data:
            session = client.post("/api/sessions/upload", files={"file": ("quiet.mp4", data, "video/mp4")}).json()
        events = _events(client, session["id"])
        detail = client.get(f"/api/sessions/{session['id']}").json()
    assert any(name == "observation" for name, _ in events)
    decision = next(body["decision"] for name, body in events if name == "decision")
    assert decision["alert"] is False
    assert detail["chunks"] == []
    assert "alert" not in [name for name, _ in events]


def test_slow_playback_samples_the_current_moment_not_every_interval(tmp_path, config: AppConfig):
    video = write_test_video(tmp_path / "slow.mp4", seconds=2, fps=15)
    perception = _SlowPerception()
    gate = LangGraphDecisionGate(ScriptedClassifier(0.1, "none"), threshold=0.6)
    with TestClient(create_app(config, perception=perception, gate=gate, playback_pace=True)) as client:
        with video.open("rb") as data:
            session = client.post("/api/sessions/upload", files={"file": ("slow.mp4", data, "video/mp4")}).json()
        events = _events(client, session["id"])
    times = [body["timestamp_ms"] for name, body in events if name == "observation"]
    assert times
    assert len(times) <= 6
    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    assert gaps and min(gaps) >= 300


class _SlowPerception(ScriptedPerception):
    def __init__(self) -> None:
        super().__init__(False, "none", "Quiet.", confidence=0.0)

    def observe(self, packet) -> SceneObservation:
        import time

        time.sleep(0.45)
        return super().observe(packet)


def test_fast_clock_jumps_to_the_next_step_instead_of_every_frame(tmp_path):
    video = write_test_video(tmp_path / "steps.mp4", seconds=12)
    config = AppConfig(data_dir=tmp_path / "data", vision_sample_ms=5_000)
    perception = ScriptedPerception(False, "none", "Quiet.", confidence=0.0)
    gate = LangGraphDecisionGate(ScriptedClassifier(0.1, "none"), threshold=0.6)
    with TestClient(create_app(config, perception=perception, gate=gate, playback_pace=False)) as client:
        with video.open("rb") as data:
            session = client.post("/api/sessions/upload", files={"file": ("steps.mp4", data, "video/mp4")}).json()
        events = _events(client, session["id"])
    times = [body["timestamp_ms"] for name, body in events if name == "observation"]
    assert len(times) <= 4
    assert times[0] < 200
    assert times[-1] >= 9_000


def test_custom_watch_brief_reaches_the_alert_classifier(tmp_path, config: AppConfig):
    video = write_test_video(tmp_path / "harbor.mp4", seconds=12)
    brief = "Only alert when a boat is near the dock."
    perception = ScriptedPerception(True, "boat", "A boat is alongside the dock.")
    gate = LangGraphDecisionGate(ScriptedClassifier(0.9, "brief_match", brief=brief), threshold=0.6)
    with TestClient(create_app(config, perception=perception, gate=gate, playback_pace=False)) as client:
        with video.open("rb") as data:
            response = client.post(
                "/api/sessions/upload",
                files={"file": ("harbor.mp4", data, "video/mp4")},
                data={"watch_brief": brief},
            )
        assert response.status_code == 201, response.text
        events = _events(client, response.json()["id"])
    assert any(name == "decision" and body["decision"]["alert"] is True for name, body in events)


def test_second_alert_inside_cooldown_does_not_save_another_clip(tmp_path):
    video = write_test_video(tmp_path / "busy.mp4", seconds=12)
    config = AppConfig(data_dir=tmp_path / "data", decision_window_seconds=4)
    perception = ScriptedPerception(True, "person", "A person stays at the gate.")
    gate = LangGraphDecisionGate(ScriptedClassifier(0.9, "person_on_property"), threshold=0.6)
    with TestClient(create_app(config, perception=perception, gate=gate, playback_pace=False)) as client:
        with video.open("rb") as data:
            session = client.post("/api/sessions/upload", files={"file": ("busy.mp4", data, "video/mp4")}).json()
        events = _events(client, session["id"])
        detail = client.get(f"/api/sessions/{session['id']}").json()
    alerts = [body for name, body in events if name == "alert"]
    assert len(detail["chunks"]) == 1
    assert any(body["debounced"] for body in alerts)
    saved = next(body for body in alerts if not body["debounced"])
    assert saved["video_url"].endswith(".mp4")
    assert saved["chunk_end_ms"] > saved["chunk_start_ms"]


def client_metadata(config: AppConfig, session_id: str, chunk_file: str) -> dict:
    path = config.chunk_dir(session_id) / chunk_file.replace(".mp4", ".json")
    return json.loads(path.read_text())


class _RecordingSummaryLlm:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.images: list[int] = []

    def invoke(self, messages: list) -> object:
        self.prompts.append(messages[0].content)
        content = messages[1].content
        self.images.append(sum(1 for b in content if isinstance(b, dict) and b.get("type") == "image") if isinstance(content, list) else 0)
        return SimpleNamespace(content=f"summary #{len(self.prompts)}")


def _upload_with_llm(client: TestClient, video, **llm) -> dict:
    with video.open("rb") as data:
        response = client.post(
            "/api/sessions/upload",
            files={"file": ("yard.mp4", data, "video/mp4")},
            data={key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in llm.items()},
        )
    assert response.status_code == 201, response.text
    return response.json()


def test_llm_session_writes_period_alert_and_final_summaries_through_langgraph(tmp_path, config: AppConfig):
    from drone_security.agent import LangGraphSummarizer

    video = write_test_video(tmp_path / "long.mp4", seconds=65, fps=4)
    perception = ScriptedPerception(True, "person", "A person is at the gate.")
    gate = LangGraphDecisionGate(ScriptedClassifier(0.92, "person_on_property"), threshold=0.6)
    llm = _RecordingSummaryLlm()
    app = create_app(
        config, perception=perception, gate=gate, playback_pace=False, summarizer=LangGraphSummarizer(llm, "fake")
    )
    with TestClient(app) as client:
        session = _upload_with_llm(
            client, video, llm_enabled=True, summary_interval_minutes=1, detailed_alerts=True
        )
        assert session["llm"] == {"enabled": True, "summary_interval_minutes": 1, "detailed_alerts": True, "advanced_analytics": False}
        events = _events(client, session["id"])
        stored = client.get(f"/api/sessions/{session['id']}/summaries").json()
        keyframe_type = client.get(stored[-1]["frames"][0]).headers["content-type"]
        assert client.get(f"/api/sessions/{session['id']}/keyframes/..%2Fdrone.db").status_code in (404, 409)

    summaries = [body for name, body in events if name == "summary"]
    kinds = [body["kind"] for body in summaries]
    assert "period" in kinds and "alert" in kinds and kinds[-1] == "final"
    period = next(body for body in summaries if body["kind"] == "period")
    assert (period["start_ms"], period["end_ms"]) == (0, 60_000)
    alert_summary = next(body for body in summaries if body["kind"] == "alert")
    assert alert_summary["alert_key"].startswith("window-")
    assert any(ref["chunk_file"] for ref in alert_summary["evidence"])

    names = [(name, body.get("status")) for name, body in events]
    final_at = max(i for i, (name, _) in enumerate(names) if name == "summary")
    summarizing_at = names.index(("status", "summarizing"))
    ended_at = names.index(("status", "ended"))
    assert summarizing_at < final_at < ended_at, "dead hand runs last, before the session ends"
    assert [s["kind"] for s in stored][-1] == "final"
    assert stored[-1]["text"].startswith("summary #")
    assert all("final summary" in p or "period" in p or "single alert" in p for p in llm.prompts)
    assert llm.images and all(0 < n <= 6 for n in llm.images), "every LLM job sees a few key frames, never video"
    assert alert_summary["frames"] and stored[-1]["frames"]
    assert keyframe_type == "image/jpeg"


def test_llm_off_makes_no_llm_calls(tmp_path, config: AppConfig):
    from drone_security.agent import LangGraphSummarizer

    video = write_test_video(tmp_path / "short.mp4", seconds=12)
    llm = _RecordingSummaryLlm()
    app = create_app(
        config,
        perception=ScriptedPerception(True, "person", "A person is at the gate."),
        gate=LangGraphDecisionGate(ScriptedClassifier(0.92, "person_on_property"), threshold=0.6),
        playback_pace=False,
        summarizer=LangGraphSummarizer(llm, "fake"),
    )
    with TestClient(app) as client:
        session = _upload_with_llm(client, video, llm_enabled=False)
        events = _events(client, session["id"])
        stored = client.get(f"/api/sessions/{session['id']}/summaries").json()
    assert "summary" not in [name for name, _ in events]
    assert stored == []
    assert llm.prompts == []


class _DescribingVision:
    loaded = True

    def describe(self, packet) -> dict:
        return {
            "reasoning": "A man in a dark jacket walks to the gate.",
            "scene": {"background": "driveway"},
            "objects": [{"name": "man in dark jacket", "score": 0.82}, {"name": "gate", "score": 0.5}],
        }


def test_upload_indexes_readings_with_classes_scene_and_alerts(tmp_path, config: AppConfig):
    from drone_security.models.index import FrameQuery
    from drone_security.perception import LangGraphPerception

    video = write_test_video(tmp_path / "gate.mp4", seconds=12)
    gate = LangGraphDecisionGate(ScriptedClassifier(0.92, "person_on_property"), threshold=0.6)
    app = create_app(config, perception=LangGraphPerception(_DescribingVision()), gate=gate, playback_pace=False)
    with TestClient(app) as client:
        with video.open("rb") as data:
            session = client.post("/api/sessions/upload", files={"file": ("gate.mp4", data, "video/mp4")}).json()
        events = _events(client, session["id"])
        index = app.state.manager.index
        frames = index.find_frames(session["id"], FrameQuery(classes=("person",)))
        alerts = index.find_frames(session["id"], FrameQuery(alerts_only=True))
        classes = {c.name: c for c in index.classes(session["id"])}

    observation = next(body for name, body in events if name == "observation")
    assert [c["name"] for c in observation["classes"]] == ["person", "structure"]
    assert "telemetry" not in observation and observation["location"] == "driveway"
    assert frames.total > 0 and frames.frames[0].scene == "driveway" and frames.frames[0].minute_label == "00:00"
    assert alerts.total == 1 and alerts.frames[0].alert_rule == "person_on_property"
    assert classes["person"].alerts == 1
