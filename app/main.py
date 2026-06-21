from pathlib import Path

from fastapi import BackgroundTasks, Body, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, load_settings
from app.models import AudioChapter, ReaderShell
from app.services import SessionNotFoundError, SessionService, Transcriber, WhisperTranscriber, discover_m4b_chapters


def create_app(
    settings: Settings | None = None,
    transcriber: Transcriber | None = None,
) -> FastAPI:
    app = FastAPI()
    shell = ReaderShell()
    resolved_settings = settings or load_settings()
    static_dir = Path(__file__).resolve().parent / "static"
    template_path = Path(__file__).resolve().parent / "templates" / "index.html"
    session_service = SessionService(
        resolved_settings.data_dir,
        WhisperTranscriber() if transcriber is None and settings is None else transcriber,
    )
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return template_path.read_text(encoding="utf-8").replace("{{ title }}", shell.title)

    @app.post("/sessions")
    async def create_session(
        background_tasks: BackgroundTasks,
        ebook: UploadFile = File(...),
        audio: UploadFile = File(...),
    ) -> dict:
        try:
            summary = session_service.create_session(
                ebook_name=ebook.filename,
                ebook_content=await ebook.read(),
                audio_name=audio.filename,
                audio_content=await audio.read(),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if session_service.transcriber is not None:
            background_tasks.add_task(session_service.process_session, summary.session_id)
        return summary.to_dict()

    @app.post("/chapter-sessions")
    async def create_chapter_session(
        ebook: UploadFile = File(...),
        audio_files: list[UploadFile] = File(...),
    ) -> dict:
        try:
            summary = session_service.create_chapter_session(
                ebook_name=ebook.filename,
                ebook_content=await ebook.read(),
                audio_files=[
                    (audio_file.filename, await audio_file.read()) for audio_file in audio_files
                ],
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return summary.to_dict()

    @app.post("/sessions/ebook")
    async def upload_ebook(ebook: UploadFile = File(...)) -> dict:
        try:
            return session_service.create_session_from_ebook(
                ebook_name=ebook.filename,
                ebook_content=await ebook.read(),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/sessions/{session_id}/audio")
    async def upload_audio(
        session_id: str,
        audio_files: list[UploadFile] = File(...),
    ) -> dict:
        try:
            return session_service.add_audio_to_session(
                session_id=session_id,
                audio_files=[
                    (audio_file.filename, await audio_file.read())
                    for audio_file in audio_files
                ],
            )
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.websocket("/ws/sessions/{session_id}/audio-upload")
    async def audio_upload_ws(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        session_dir = session_service.sessions_dir / session_id
        if not session_dir.exists():
            await websocket.send_json({"type": "error", "detail": "Session not found"})
            await websocket.close()
            return
        try:
            meta = await websocket.receive_json()
        except WebSocketDisconnect:
            return
        filename = meta.get("filename", "")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".mp3", ".m4b"}:
            await websocket.send_json({"type": "error", "detail": f"Unsupported format: {suffix}"})
            await websocket.close()
            return
        filepath = session_dir / filename
        total = 0
        chapters_early: list[AudioChapter] = []
        try:
            with open(filepath, "wb") as f:
                while True:
                    try:
                        data = await websocket.receive()
                    except WebSocketDisconnect:
                        return
                    if "bytes" not in data:
                        continue
                    chunk = data["bytes"]
                    if chunk == b"__EOF__":
                        break
                    f.write(chunk)
                    total += len(chunk)
                    await websocket.send_json({"type": "progress", "received": total})
                    if suffix == ".m4b" and not chapters_early and total >= 5 * 1024 * 1024:
                        try:
                            chapters_raw = discover_m4b_chapters(filepath)
                            if chapters_raw:
                                chapters_early = [
                                    AudioChapter(
                                        index=idx,
                                        title=ch["title"],
                                        source_name=filename,
                                        start_ms=ch["start_ms"],
                                        end_ms=ch["end_ms"],
                                    )
                                    for idx, ch in enumerate(chapters_raw)
                                ]
                                await websocket.send_json({
                                    "type": "chapters_early",
                                    "chapters": [c.__dict__ for c in chapters_early],
                                })
                        except Exception:
                            pass
        except Exception as error:
            await websocket.send_json({"type": "error", "detail": str(error)})
            return
        try:
            payload = session_service.finalize_audio_upload(session_id, [filename])
            await websocket.send_json({"type": "done", "payload": payload})
        except Exception as error:
            await websocket.send_json({"type": "error", "detail": str(error)})

    @app.post("/sessions/{session_id}/init-process")
    async def init_chapter_processing(session_id: str) -> dict:
        try:
            return session_service.init_chapter_statuses(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/sessions/{session_id}/process-chapter")
    async def process_chapter(
        session_id: str,
        background_tasks: BackgroundTasks,
        payload: dict = Body(...),
    ) -> dict:
        try:
            ebook_idx = payload["ebook_chapter_index"]
            audio_idx = payload["audio_chapter_index"]
        except KeyError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        background_tasks.add_task(
            session_service.process_single_chapter,
            session_id,
            ebook_idx,
            audio_idx,
        )
        return {"status": "accepted"}

    @app.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict:
        try:
            return session_service.read_session(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/chapter-sessions/{session_id}")
    async def get_chapter_session(session_id: str) -> dict:
        try:
            return session_service.read_session(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/chapter-sessions/{session_id}/audio/{audio_name}")
    async def get_chapter_audio(session_id: str, audio_name: str) -> FileResponse:
        return FileResponse(session_service.get_chapter_audio_path(session_id, audio_name))

    @app.post("/chapter-sessions/{session_id}/mapping")
    async def submit_chapter_mapping(
        session_id: str,
        background_tasks: BackgroundTasks,
        payload: dict = Body(...),
    ) -> dict:
        try:
            summary = session_service.submit_chapter_mapping(
                session_id=session_id,
                matches=payload["matches"],
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if session_service.transcriber is not None:
            background_tasks.add_task(
                session_service.process_chapter_session,
                summary.session_id,
                parallel=payload.get("multicore", False),
            )
        return summary.to_dict()

    @app.get("/sessions/{session_id}/audio")
    async def get_audio(session_id: str) -> FileResponse:
        return FileResponse(session_service.get_audio_path(session_id))

    return app


app = create_app()
