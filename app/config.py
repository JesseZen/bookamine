"""Application settings for Bookamine.

Settings are constructed from environment variables with sensible defaults so
the app can be deployed without editing code. Every value can be overridden:

    BOOKAMINE_DATA_DIR=/var/lib/bookamine \
    BOOKAMINE_ALIGNMENT_THRESHOLD=0.7 \
    BOOKAMINE_MAX_WORKERS=4 \
    uvicorn app.main:app
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path

    # Alignment tuning. Exposed because noisy transcripts or unusual narrators
    # sometimes need a looser threshold or a wider search window.
    alignment_threshold: float = 0.6
    alignment_window: int = 24
    alignment_backtrack: int = 4
    alignment_match_score: float = 0.85

    # WebSocket audio upload chunk size (bytes). 256 KiB matches the client and
    # keeps progress updates frequent without flooding the event loop.
    upload_chunk_size: int = 256 * 1024

    # Maximum parallel chapter workers. None = auto (cpu_count).
    max_workers: int | None = None

    # SSE ping interval (seconds) — keeps proxies from closing idle connections.
    sse_ping_interval: float = 15.0

    # Supported file formats. Stored as tuples so the dataclass stays hashable.
    supported_ebook_suffixes: tuple[str, ...] = (".txt", ".epub")
    supported_audio_suffixes: tuple[str, ...] = (".mp3", ".m4b")


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parent.parent
    data_dir = _env_path("BOOKAMINE_DATA_DIR", project_root / "data")
    max_workers_env = os.environ.get("BOOKAMINE_MAX_WORKERS")
    max_workers = int(max_workers_env) if max_workers_env else None
    return Settings(
        project_root=project_root,
        data_dir=data_dir,
        alignment_threshold=_env_float("BOOKAMINE_ALIGNMENT_THRESHOLD", 0.6),
        alignment_window=_env_int("BOOKAMINE_ALIGNMENT_WINDOW", 24),
        alignment_backtrack=_env_int("BOOKAMINE_ALIGNMENT_BACKTRACK", 4),
        alignment_match_score=_env_float("BOOKAMINE_ALIGNMENT_MATCH_SCORE", 0.85),
        upload_chunk_size=_env_int("BOOKAMINE_UPLOAD_CHUNK_SIZE", 256 * 1024),
        max_workers=max_workers,
        sse_ping_interval=_env_float("BOOKAMINE_SSE_PING_INTERVAL", 15.0),
    )
