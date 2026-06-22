"""Audio chapter discovery and extraction helpers built on ffmpeg/ffprobe."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".m4b"}


def discover_m4b_chapters(audio_path: Path) -> list[dict]:
    """Return chapter metadata for an .m4b file using ffprobe."""
    t0 = time.monotonic()
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_chapters",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout or "{}")
    chapters: list[dict] = []
    for index, chapter in enumerate(payload.get("chapters", [])):
        tags = chapter.get("tags", {})
        chapters.append(
            {
                "index": index,
                "title": tags.get("title") or f"Chapter {index + 1}",
                "start_ms": round(float(chapter["start_time"]) * 1000),
                "end_ms": round(float(chapter["end_time"]) * 1000),
            }
        )
    logger.info(
        "ffprobe found %d chapters in %s (%.1fs)",
        len(chapters),
        audio_path.name,
        time.monotonic() - t0,
    )
    return chapters


def extract_m4b_chapter_clip(
    source: Path,
    start_ms: int,
    end_ms: int,
    output_path: Path,
) -> Path:
    """Extract a chapter range from an .m4b into a standalone .mp3 clip."""
    if output_path.exists():
        logger.info("Reusing cached clip %s", output_path.name)
        return output_path
    duration_s = (end_ms - start_ms) / 1000
    logger.info(
        "Extracting %s (%.1fs) from %s…",
        output_path.name,
        duration_s,
        source.name,
    )
    t0 = time.monotonic()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_ms / 1000:.3f}",
            "-to",
            f"{end_ms / 1000:.3f}",
            "-i",
            str(source),
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    logger.info(
        "Extracted %s in %.1fs",
        output_path.name,
        time.monotonic() - t0,
    )
    return output_path


def find_audio_file(session_dir: Path) -> Path:
    """Return the first supported audio file inside a session directory."""
    for file_path in session_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES:
            return file_path
    raise FileNotFoundError(f"Audio file not found in {session_dir}")
