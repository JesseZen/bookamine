from pathlib import Path

from fastapi import BackgroundTasks, Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, load_settings
from app.models import ReaderShell
from app.services import SessionNotFoundError, SessionService, Transcriber, WhisperTranscriber


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
            background_tasks.add_task(session_service.process_chapter_session, summary.session_id)
        return summary.to_dict()

    @app.get("/sessions/{session_id}/audio")
    async def get_audio(session_id: str) -> FileResponse:
        return FileResponse(session_service.get_audio_path(session_id))

    return app


app = create_app()
