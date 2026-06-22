"""FastAPI application factory for Bookamine."""

from __future__ import annotations

import fcntl
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Settings, load_settings
from app.models import ReaderShell
from app.routes import audio, chapters, pages, sessions
from app.services.session import SessionService
from app.services.transcription import Transcriber, WhisperTranscriber

# Configure logging so background processing output is visible.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def create_app(
    settings: Settings | None = None,
    transcriber: Transcriber | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Enforce single instance per data_dir: two processes writing to the
        # same session.json would corrupt data and duplicate transcription
        # work. The lock is released automatically when the process exits.
        data_dir = app.state.settings.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(str(data_dir / ".bookamine.lock"), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(lock_fd)
            print(
                f"ERROR: Another Bookamine instance is already using {data_dir}.\n"
                f"Stop it first or set BOOKAMINE_DATA_DIR to a different path.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        app.state._lock_fd = lock_fd

        recovered = app.state.session_service.recover_stuck_sessions()
        if recovered:
            logging.info("Recovered %d stuck chapter(s) on startup", recovered)
        try:
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    app = FastAPI(title="Bookamine", lifespan=lifespan)
    app.state.shell = ReaderShell()
    resolved_settings = settings or load_settings()
    static_dir = Path(__file__).resolve().parent / "static"
    app.state.session_service = SessionService(
        resolved_settings.data_dir,
        WhisperTranscriber() if transcriber is None and settings is None else transcriber,
        settings=resolved_settings,
    )
    app.state.settings = resolved_settings
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(pages.router)
    app.include_router(sessions.router)
    app.include_router(chapters.router)
    app.include_router(audio.router)
    return app


app = create_app()
