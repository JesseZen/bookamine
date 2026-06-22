"""Session lifecycle routes: creation, listing, deletion, and SSE progress."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.models import AudioChapter
from app.services.audio import discover_m4b_chapters
from app.services.session import SessionNotFoundError, SessionService

router = APIRouter()


def _service(request: Request) -> SessionService:
    return request.app.state.session_service


@router.post("/sessions")
async def create_session(
    request: Request,
    background_tasks: BackgroundTasks,
    ebook: UploadFile = File(...),
    audio: UploadFile = File(...),
) -> dict:
    service = _service(request)
    try:
        summary = service.create_session(
            ebook_name=ebook.filename,
            ebook_content=await ebook.read(),
            audio_name=audio.filename,
            audio_content=await audio.read(),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if service.transcriber is not None:
        background_tasks.add_task(service.process_session, summary.session_id)
    return summary.to_dict()


@router.post("/sessions/ebook")
async def upload_ebook(request: Request, ebook: UploadFile = File(...)) -> dict:
    service = _service(request)
    try:
        return service.create_session_from_ebook(
            ebook_name=ebook.filename,
            ebook_content=await ebook.read(),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/sessions/{session_id}/audio")
async def upload_audio(
    request: Request,
    session_id: str,
    audio_files: list[UploadFile] = File(...),
) -> dict:
    service = _service(request)
    try:
        return service.add_audio_to_session(
            session_id=session_id,
            audio_files=[
                (audio_file.filename, await audio_file.read()) for audio_file in audio_files
            ],
        )
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.websocket("/ws/sessions/{session_id}/audio-upload")
async def audio_upload_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    service: SessionService = websocket.app.state.session_service
    session_dir = service.sessions_dir / session_id
    if not session_dir.exists():
        await _safe_send_json(websocket, {"type": "error", "detail": "Session not found"})
        await _safe_close(websocket)
        return
    try:
        meta = await websocket.receive_json()
    except (WebSocketDisconnect, RuntimeError):
        return
    filename = meta.get("filename", "")
    suffix = _suffix(filename)
    if suffix not in {".mp3", ".m4b"}:
        await _safe_send_json(websocket, {"type": "error", "detail": f"Unsupported format: {suffix}"})
        await _safe_close(websocket)
        return
    filepath = session_dir / filename
    total = 0
    chapters_early: list[AudioChapter] = []
    try:
        with open(filepath, "wb") as f:
            while True:
                try:
                    data = await websocket.receive()
                except (WebSocketDisconnect, RuntimeError):
                    # Client went away — keep the partial file so they can resume
                    # later, but stop trying to talk to the dead socket.
                    return
                if data.get("text") == "__EOF__":
                    break
                if "bytes" not in data:
                    continue
                chunk = data["bytes"]
                f.write(chunk)
                total += len(chunk)
                await _safe_send_json(websocket, {"type": "progress", "received": total})
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
                            await _safe_send_json(websocket, {
                                "type": "chapters_early",
                                "chapters": [c.__dict__ for c in chapters_early],
                            })
                    except Exception:
                        pass
    except Exception as error:
        await _safe_send_json(websocket, {"type": "error", "detail": str(error)})
        return
    try:
        payload = service.finalize_audio_upload(session_id, [filename])
        await _safe_send_json(websocket, {"type": "done", "payload": payload})
    except Exception as error:
        await _safe_send_json(websocket, {"type": "error", "detail": str(error)})


async def _safe_send_json(websocket: WebSocket, message: dict) -> None:
    """Send a JSON message, ignoring errors if the client already disconnected."""
    try:
        await websocket.send_json(message)
    except (RuntimeError, WebSocketDisconnect):
        pass


async def _safe_close(websocket: WebSocket) -> None:
    """Close the websocket, ignoring errors if it's already gone."""
    try:
        await websocket.close()
    except (RuntimeError, WebSocketDisconnect):
        pass


@router.get("/sessions")
async def list_sessions(request: Request) -> dict:
    return {"sessions": _service(request).list_sessions()}


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str) -> dict:
    service = _service(request)
    try:
        service.delete_session(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}")
async def get_session(request: Request, session_id: str) -> dict:
    service = _service(request)
    try:
        return service.read_session(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/sessions/{session_id}/audio")
async def get_audio(request: Request, session_id: str) -> FileResponse:
    return FileResponse(_service(request).get_audio_path(session_id))


@router.get("/sessions/{session_id}/events")
async def session_events(request: Request, session_id: str):
    """Server-Sent Events stream that notifies clients whenever the session
    payload changes (chapter completed, status transitioned, etc.)."""
    service = _service(request)
    try:
        service.read_session(session_id)
    except SessionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    settings = getattr(request.app.state, "settings", None)
    ping_interval = settings.sse_ping_interval if settings else 15.0

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[None] = asyncio.Queue()

    def _push(_session_id: str) -> None:
        # Called from background processing threads — must bridge into
        # the asyncio event loop thread-safely.
        try:
            loop.call_soon_threadsafe(queue.put_nowait, None)
        except (RuntimeError, AttributeError):
            pass

    unsubscribe = service.subscribe(session_id, _push)

    async def event_generator():
        try:
            yield "event: hello\ndata: {}\n\n"
            # Send current state immediately so late subscribers don't miss
            # updates that happened between page load and SSE connect.
            try:
                initial = service.read_session(session_id)
                yield f"event: update\ndata: {json.dumps(initial)}\n\n"
                if initial.get("status") in {"ready", "failed", "failed-partial"}:
                    return
            except SessionNotFoundError:
                yield "event: deleted\ndata: {}\n\n"
                return
            while True:
                try:
                    await asyncio.wait_for(queue.get(), timeout=ping_interval)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                try:
                    payload = service.read_session(session_id)
                except SessionNotFoundError:
                    yield "event: deleted\ndata: {}\n\n"
                    break
                yield f"event: update\ndata: {json.dumps(payload)}\n\n"
                if payload.get("status") in {"ready", "failed", "failed-partial"}:
                    break
        finally:
            unsubscribe()

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _suffix(filename: str) -> str:
    from pathlib import Path
    return Path(filename).suffix.lower()
