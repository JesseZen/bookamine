"""HTML page routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.models import ReaderShell

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> str:
    shell: ReaderShell = request.app.state.shell
    template_path = Path(__file__).resolve().parent.parent / "templates" / "index.html"
    return template_path.read_text(encoding="utf-8").replace("{{ title }}", shell.title)
