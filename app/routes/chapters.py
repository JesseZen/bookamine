"""Chapter session routes: creation, mapping, processing, and retrieval."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.services.session import SessionNotFoundError, SessionService

router = APIRouter()


def _service(request: Request) -> SessionService:
    return request.app.state.session_service


@router.post("/chapter-sessions")
async def create_chapter_session(
    request: Request,
    ebook: UploadFile = File(...),
    audio_files: list[UploadFile] = File(...),
) -> dict:
    service = _service(request)
    try:
        summary = service.create_chapter_session(
            ebook_name=ebook.filename,
            ebook_content=await ebook.read(),
            audio_files=[
                (audio_file.filename, await audio_file.read()) for audio_file in audio_files
            ],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return summary.to_dict()


@router.get("/chapter-sessions/{session_id}")
async def get_chapter_session(request: Request, session_id: str) -> dict:
    service = _service(request)
    try:
        return service.read_session(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/chapter-sessions/{session_id}/audio/{audio_name}")
async def get_chapter_audio(request: Request, session_id: str, audio_name: str) -> FileResponse:
    return FileResponse(_service(request).get_chapter_audio_path(session_id, audio_name))


@router.post("/chapter-sessions/{session_id}/mapping")
async def submit_chapter_mapping(
    request: Request,
    background_tasks: BackgroundTasks,
    session_id: str,
    payload: dict = Body(...),
) -> dict:
    service = _service(request)
    try:
        summary = service.submit_chapter_mapping(
            session_id=session_id,
            matches=payload["matches"],
        )
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if service.transcriber is not None:
        background_tasks.add_task(
            service.process_chapter_session,
            summary.session_id,
            parallel=payload.get("multicore", False),
        )
    return summary.to_dict()


@router.post("/sessions/{session_id}/init-process")
async def init_chapter_processing(request: Request, session_id: str) -> dict:
    service = _service(request)
    try:
        return service.init_chapter_statuses(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/sessions/{session_id}/process-chapter")
async def process_chapter(
    request: Request,
    background_tasks: BackgroundTasks,
    session_id: str,
    payload: dict = Body(...),
) -> dict:
    service = _service(request)
    try:
        ebook_idx = payload["ebook_chapter_index"]
        audio_idx = payload["audio_chapter_index"]
    except KeyError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    background_tasks.add_task(
        service.process_single_chapter,
        session_id,
        ebook_idx,
        audio_idx,
    )
    return {"status": "accepted"}


@router.post("/sessions/{session_id}/retry-chapter/{ebook_chapter_index}")
async def retry_chapter(
    request: Request,
    background_tasks: BackgroundTasks,
    session_id: str,
    ebook_chapter_index: int,
) -> dict:
    service = _service(request)
    try:
        payload = service.retry_chapter(session_id, ebook_chapter_index)
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    status = next(
        s for s in payload["chapter_statuses"]
        if s["ebook_chapter_index"] == ebook_chapter_index
    )
    if status["audio_chapter_index"] is not None:
        background_tasks.add_task(
            service.process_single_chapter,
            session_id,
            ebook_chapter_index,
            status["audio_chapter_index"],
        )
    return {"status": "accepted"}
