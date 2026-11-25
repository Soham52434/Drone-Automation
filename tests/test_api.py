from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from drone_security.config import AppConfig
from main import create_app


@pytest.fixture
def client(config: AppConfig):
    with TestClient(create_app(config)) as client:
        yield client


def _upload(client: TestClient, video: Path) -> dict:
    with video.open("rb") as data:
        response = client.post("/api/sessions/upload", files={"file": ("yard.mp4", data, "video/mp4")})
    assert response.status_code == 201, response.text
    return response.json()


def test_watch_brief_is_optional_and_stored_on_the_session(client: TestClient, sample_video: Path):
    custom = "Only alert when a boat is near the dock."
    live = client.post("/api/sessions/live", json={"watch_brief": custom}).json()
    assert live["watch_brief"] == custom
    defaulted = client.post("/api/sessions/live", json={}).json()
    assert "Person detection" in defaulted["watch_brief"]
    with sample_video.open("rb") as data:
        uploaded = client.post(
            "/api/sessions/upload",
            files={"file": ("harbor.mp4", data, "video/mp4")},
            data={"watch_brief": custom},
        ).json()
    assert uploaded["watch_brief"] == custom


def test_health(client: TestClient):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["vision_loaded"] is False


def test_create_live_session_and_list(client: TestClient):
    created = client.post("/api/sessions/live", json={"title": "Front gate"}).json()
    assert created["kind"] == "live"
    assert created["status"] == "idle"
    assert created["source_url"] is None
    assert [s["id"] for s in client.get("/api/sessions").json()] == [created["id"]]


def test_upload_save_clip_and_fetch_files(client: TestClient, sample_video: Path):
    session = _upload(client, sample_video)
    assert session["status"] == "ready"
    assert client.get(session["source_url"]).status_code == 200

    chunk = client.post(f"/api/sessions/{session['id']}/chunks", json={"detection_ms": 9_000}).json()
    assert chunk["seek_offset_sec"] == pytest.approx(8.0, abs=0.1)
    assert chunk["trigger"] == "manual"

    video = client.get(chunk["video_url"])
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    assert client.get(chunk["metadata_url"]).json()["chunk_file"] == chunk["chunk_file"]

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert [c["chunk_file"] for c in detail["chunks"]] == [chunk["chunk_file"]]


def test_source_video_supports_range_requests(client: TestClient, sample_video: Path):
    session = _upload(client, sample_video)
    response = client.get(session["source_url"], headers={"Range": "bytes=0-99"})
    assert response.status_code == 206
    assert len(response.content) == 100


def test_invalid_upload_returns_400(client: TestClient):
    response = client.post("/api/sessions/upload", files={"file": ("x.mp4", b"junk", "video/mp4")})
    assert response.status_code == 400


def test_unknown_session_returns_404(client: TestClient):
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.delete("/api/sessions/nope").status_code == 404


def test_live_clip_without_feed_returns_409(client: TestClient):
    session = client.post("/api/sessions/live", json={}).json()
    assert client.post(f"/api/sessions/{session['id']}/chunks", json={}).status_code == 409
    assert client.get(f"/api/sessions/{session['id']}/live/stats").status_code == 409


def test_stop_and_delete_session(client: TestClient):
    session = client.post("/api/sessions/live", json={}).json()
    stopped = client.post(f"/api/sessions/{session['id']}/live/stop").json()
    assert stopped["status"] == "ended"
    assert client.delete(f"/api/sessions/{session['id']}").status_code == 204
    assert client.get("/api/sessions").json() == []


def test_offer_requires_offer_type(client: TestClient):
    session = client.post("/api/sessions/live", json={}).json()
    response = client.post(f"/api/sessions/{session['id']}/webrtc/offer", json={"sdp": "v=0", "type": "answer"})
    assert response.status_code == 422


def test_llm_settings_are_validated_and_returned(client: TestClient):
    created = client.post(
        "/api/sessions/live",
        json={"llm": {"enabled": True, "summary_interval_minutes": 15, "detailed_alerts": False, "advanced_analytics": False}},
    ).json()
    assert created["llm"] == {"enabled": True, "summary_interval_minutes": 15, "detailed_alerts": False, "advanced_analytics": False}
    default = client.post("/api/sessions/live", json={}).json()
    assert default["llm"]["enabled"] is False
    bad = client.post("/api/sessions/live", json={"llm": {"enabled": True, "summary_interval_minutes": 7}})
    assert bad.status_code == 422


def test_upload_rejects_an_interval_off_the_slider(client: TestClient, sample_video: Path):
    with sample_video.open("rb") as data:
        response = client.post(
            "/api/sessions/upload",
            files={"file": ("yard.mp4", data, "video/mp4")},
            data={"llm_enabled": "true", "summary_interval_minutes": "3"},
        )
    assert response.status_code == 422


def test_summaries_endpoint_is_empty_for_a_new_session(client: TestClient):
    created = client.post("/api/sessions/live", json={}).json()
    assert client.get(f"/api/sessions/{created['id']}/summaries").json() == []
    assert client.get("/api/sessions/missing/summaries").status_code == 404
