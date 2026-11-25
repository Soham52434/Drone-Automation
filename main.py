import argparse
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from pydantic import ValidationError
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from drone_security.api.schemas import (
    ChatAskIn,
    ChatTurnOut,
    ChatVerifyIn,
    ChunkOut,
    ClassCountOut,
    CreateLiveSessionIn,
    DayLogOut,
    SessionCostOut,
    SessionTelemetryOut,
    LiveStatsOut,
    LlmSettingsIO,
    SaveClipIn,
    SdpIn,
    SdpOut,
    SessionDetailOut,
    SessionOut,
    SummaryOut,
)
from drone_security.agent import LangGraphSummarizer, build_summarizer
from drone_security.agent.entity_graph import LangGraphEntityDescriber
from drone_security.agent.llm import ChatModel, build_llm, model_chain
from drone_security.agent.metering import UsageMeter, metered
from drone_security.indexing.usage_ledger import UsageLedger
from drone_security.config import AppConfig
from drone_security.indexing import ChunkWriter, SessionNotFoundError, SessionStore
from drone_security.ingest import SdpMessage, VideoFileError
from drone_security.decisions import build_decision_gate
from drone_security.perception import LangGraphPerception, load_vision_model
from drone_security.pipeline import (
    ClipDebouncedError,
    ClipUnavailableError,
    InvalidSessionStateError,
    SessionManager,
)

WEB_DIST = Path(__file__).resolve().parent / "web" / "dist"

_ERROR_STATUS: dict[type[Exception], int] = {
    SessionNotFoundError: 404,
    InvalidSessionStateError: 409,
    ClipUnavailableError: 409,
    ClipDebouncedError: 429,
    VideoFileError: 400,
}

router = APIRouter(prefix="/api")


def _manager(request: Request) -> SessionManager:
    return request.app.state.manager


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    return {"status": "ok", "vision_loaded": _manager(request).vision_loaded}


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/sessions/stream")
async def sessions_stream(request: Request) -> StreamingResponse:
    """The session list, pushed: once on connect, then whenever a session is created, changes, or is deleted."""
    manager = _manager(request)

    async def events() -> AsyncIterator[str]:
        async for tick in manager.session_changes():
            if tick == "ping":
                yield ": ping\n\n"
                continue
            body = [SessionOut.from_model(s).model_dump(mode="json") for s in manager.list_sessions()]
            yield f"event: sessions\ndata: {json.dumps(body)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(request: Request) -> list[SessionOut]:
    return [SessionOut.from_model(s) for s in _manager(request).list_sessions()]


@router.post("/sessions/live", response_model=SessionOut, status_code=201)
def create_live(request: Request, body: CreateLiveSessionIn) -> SessionOut:
    llm = body.llm.to_model() if body.llm else None
    return SessionOut.from_model(_manager(request).create_live(body.title, body.watch_brief, llm))


@router.post("/sessions/upload", response_model=SessionOut, status_code=201)
def create_upload(
    request: Request,
    file: UploadFile = File(...),
    watch_brief: str = Form(""),
    llm_enabled: bool = Form(False),
    summary_interval_minutes: int = Form(60),
    detailed_alerts: bool = Form(False),
    advanced_analytics: bool = Form(False),
) -> SessionOut:
    try:
        llm = LlmSettingsIO(
            enabled=llm_enabled,
            summary_interval_minutes=summary_interval_minutes,
            detailed_alerts=detailed_alerts,
            advanced_analytics=advanced_analytics,
        ).to_model()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()[0]["msg"]) from exc
    session = _manager(request).create_upload(file.filename or "video.mp4", file.file, watch_brief, llm)
    return SessionOut.from_model(session)


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
def get_session(request: Request, session_id: str) -> SessionDetailOut:
    manager = _manager(request)
    session = SessionOut.from_model(manager.get_session(session_id))
    chunks = [ChunkOut.from_model(c) for c in manager.list_chunks(session_id)]
    return SessionDetailOut(**session.model_dump(), chunks=chunks)


@router.get("/sessions/{session_id}/summaries", response_model=list[SummaryOut])
def list_summaries(request: Request, session_id: str) -> list[SummaryOut]:
    return [SummaryOut.from_model(s) for s in _manager(request).list_summaries(session_id)]


@router.get("/sessions/{session_id}/index/classes", response_model=list[ClassCountOut])
def index_classes(request: Request, session_id: str) -> list[ClassCountOut]:
    return [ClassCountOut.from_model(c) for c in _manager(request).index_classes(session_id)]


@router.get("/sessions/{session_id}/cost", response_model=SessionCostOut)
def cost(request: Request, session_id: str) -> SessionCostOut:
    return SessionCostOut.from_model(_manager(request).cost(session_id))


@router.get("/sessions/{session_id}/telemetry", response_model=SessionTelemetryOut)
def telemetry(request: Request, session_id: str) -> SessionTelemetryOut:
    return SessionTelemetryOut.from_model(_manager(request).telemetry(session_id))


@router.get("/sessions/{session_id}/index/daylog", response_model=DayLogOut)
def day_log(request: Request, session_id: str) -> DayLogOut:
    return DayLogOut.from_model(_manager(request).day_log(session_id))


@router.post("/sessions/{session_id}/chat", response_model=ChatTurnOut)
async def chat(request: Request, session_id: str, body: ChatAskIn) -> ChatTurnOut:
    return ChatTurnOut.from_model(session_id, await _manager(request).ask(session_id, body.question))


@router.post("/sessions/{session_id}/chat/{thread_id}/verify", response_model=ChatTurnOut)
async def chat_verify(request: Request, session_id: str, thread_id: str, body: ChatVerifyIn) -> ChatTurnOut:
    turn = await _manager(request).verify_classes(session_id, thread_id, body.classes)
    return ChatTurnOut.from_model(session_id, turn)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(request: Request, session_id: str) -> None:
    await _manager(request).delete_session(session_id)


@router.post("/sessions/{session_id}/webrtc/offer", response_model=SdpOut)
async def webrtc_offer(request: Request, session_id: str, body: SdpIn) -> SdpOut:
    answer = await _manager(request).start_live(session_id, SdpMessage(sdp=body.sdp, type=body.type))
    return SdpOut(sdp=answer.sdp, type=answer.type)


@router.post("/sessions/{session_id}/live/stop", response_model=SessionOut)
async def stop_live(request: Request, session_id: str) -> SessionOut:
    return SessionOut.from_model(await _manager(request).stop_live(session_id))


@router.get("/sessions/{session_id}/live/stats", response_model=LiveStatsOut)
def live_stats(request: Request, session_id: str) -> LiveStatsOut:
    return LiveStatsOut.from_model(_manager(request).live_stats(session_id))


@router.post("/sessions/{session_id}/chunks", response_model=ChunkOut, status_code=201)
async def save_clip(request: Request, session_id: str, body: SaveClipIn) -> ChunkOut:
    artifact = await _manager(request).save_clip(session_id, detection_ms=body.detection_ms)
    return ChunkOut.from_model(artifact)


@router.get("/sessions/{session_id}/events")
async def session_events(request: Request, session_id: str) -> StreamingResponse:
    manager = _manager(request)
    manager.get_session(session_id)
    return StreamingResponse(
        manager.iter_events(session_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/sessions/{session_id}/source")
def source_video(request: Request, session_id: str) -> FileResponse:
    return FileResponse(_manager(request).source_path(session_id))


@router.get("/sessions/{session_id}/keyframes/{file_name}")
def keyframe_file(request: Request, session_id: str, file_name: str) -> FileResponse:
    return FileResponse(_manager(request).keyframe_path(session_id, file_name), media_type="image/jpeg")


@router.get("/sessions/{session_id}/chunks/{file_name}")
def chunk_file(request: Request, session_id: str, file_name: str) -> FileResponse:
    return FileResponse(_manager(request).chunk_path(session_id, file_name))


def _error_handler(status: int):
    async def handle(_: Request, exc: Exception) -> JSONResponse:
        detail = exc.args[0] if exc.args else exc.__class__.__name__
        return JSONResponse(status_code=status, content={"detail": str(detail)})

    return handle


def create_app(
    config: AppConfig | None = None,
    web_dist: Path | None = None,
    *,
    load_models: bool = False,
    perception: object | None = None,
    gate: object | None = None,
    playback_pace: bool = True,
    summarizer: LangGraphSummarizer | None = None,
    chat_llm: ChatModel | None = None,
    describer: LangGraphEntityDescriber | None = None,
    usage: UsageLedger | None = None,
) -> FastAPI:
    config = config or AppConfig.from_env()
    usage = usage or UsageLedger(config.usage_path)
    meter = UsageMeter(usage)
    if load_models:
        perception = LangGraphPerception(load_vision_model(config.resolved_vision_dir))
        gate = build_decision_gate(
            config.llm_api_key, config.decision_model, config.alert_noul_threshold, config.time_rules(), meter
        )
        summarizer = build_summarizer(config.llm_api_key, config.summary_model, meter)
        chat_llm = metered(build_llm(config.llm_api_key, config.chat_model), meter, "chat", model_chain(config.chat_model)[0])
        describer = LangGraphEntityDescriber(
            metered(build_llm(config.llm_api_key, config.summary_model), meter, "analytics", model_chain(config.summary_model)[0])
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = SessionStore(config.db_path)
        app.state.manager = SessionManager(
            config,
            store,
            ChunkWriter(),
            perception=perception,
            gate=gate,
            playback_pace=playback_pace,
            summarizer=summarizer,
            chat_llm=chat_llm,
            describer=describer,
            usage=usage,
        )
        try:
            yield
        finally:
            await app.state.manager.shutdown()
            store.close()

    app = FastAPI(title="Drone Automation", lifespan=lifespan)

    for error_type, status in _ERROR_STATUS.items():
        app.add_exception_handler(error_type, _error_handler(status))

    app.include_router(router)

    if web_dist is not None and (web_dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> None:
    _load_dotenv(Path(__file__).resolve().parent / ".env")
    parser = argparse.ArgumentParser(description="Drone Automation server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(web_dist=WEB_DIST, load_models=True), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
