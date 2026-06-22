"""Transcriber protocol and the default Whisper-backed implementation."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Protocol

from app.alignment import TimedWord

logger = logging.getLogger(__name__)


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> list[TimedWord]: ...


class WhisperTranscriber:
    """Lazy-loading wrapper around the local openai-whisper package."""

    def __init__(self, model_name: str = "base.en"):
        self.model_name = model_name
        self._model = None

    def transcribe(self, audio_path: Path) -> list[TimedWord]:
        if self._model is None:
            logger.info("Loading Whisper model %r…", self.model_name)
            t0 = time.monotonic()
            import whisper

            self._model = whisper.load_model(self.model_name)
            logger.info(
                "Whisper model %r loaded in %.1fs",
                self.model_name,
                time.monotonic() - t0,
            )
        size_mb = audio_path.stat().st_size / (1024 * 1024)
        logger.info(
            "Transcribing %s (%.1f MB) with Whisper…",
            audio_path.name,
            size_mb,
        )
        t0 = time.monotonic()
        result = self._model.transcribe(
            str(audio_path),
            language="en",
            word_timestamps=True,
            condition_on_previous_text=False,
            verbose=True,
        )
        elapsed = time.monotonic() - t0
        timed_words: list[TimedWord] = []
        for segment in result["segments"]:
            for word in segment["words"]:
                text = word["word"].strip()
                if not text:
                    continue
                timed_words.append(
                    TimedWord(
                        text=text,
                        normalized=text.casefold(),
                        start_ms=round(word["start"] * 1000),
                        end_ms=round(word["end"] * 1000),
                    )
                )
        logger.info(
            "Transcribed %s in %.1fs → %d words",
            audio_path.name,
            elapsed,
            len(timed_words),
        )
        return timed_words
