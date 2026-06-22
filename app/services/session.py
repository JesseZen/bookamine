"""Session orchestration: persistence, chapter processing, and status tracking."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.alignment import AlignmentFailure, TimedWord, align_words
from app.config import Settings
from app.models import AudioChapter, ParsedBook, SessionSummary
from app.parsers import parse_ebook_bytes
from app.services.audio import (
    SUPPORTED_AUDIO_SUFFIXES,
    discover_m4b_chapters,
    extract_m4b_chapter_clip,
    find_audio_file,
)
from app.services.chapter_matching import suggest_audio_chapter_index
from app.services.transcription import Transcriber

logger = logging.getLogger(__name__)


class SessionNotFoundError(FileNotFoundError):
    pass


def _new_session_id() -> str:
    return f"session-{uuid.uuid4().hex[:12]}"


class SessionService:
    def __init__(
        self,
        data_dir: Path,
        transcriber: Transcriber | None,
        settings: Settings | None = None,
    ):
        self.data_dir = data_dir
        self.sessions_dir = data_dir / "sessions"
        self.transcriber = transcriber
        self.settings = settings
        self._lock = threading.Lock()
        self._listeners: dict[str, list[callable]] = {}

    @property
    def _alignment_kwargs(self) -> dict:
        if self.settings is None:
            return {}
        return {
            "threshold": self.settings.alignment_threshold,
            "window": self.settings.alignment_window,
            "backtrack": self.settings.alignment_backtrack,
            "match_score": self.settings.alignment_match_score,
        }

    # ------------------------------------------------------------------
    # Event subscription for SSE / WebSocket progress streaming
    # ------------------------------------------------------------------
    def subscribe(self, session_id: str, callback: callable) -> callable:
        self._listeners.setdefault(session_id, []).append(callback)

        def unsubscribe() -> None:
            try:
                self._listeners[session_id].remove(callback)
            except (KeyError, ValueError):
                pass

        return unsubscribe

    def _notify(self, session_id: str) -> None:
        for callback in self._listeners.get(session_id, []):
            try:
                callback(session_id)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Legacy single-audio session flow (kept for backwards compatibility)
    # ------------------------------------------------------------------
    def create_session(
        self,
        ebook_name: str,
        ebook_content: bytes,
        audio_name: str,
        audio_content: bytes,
    ) -> SessionSummary:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._validate_upload_names(ebook_name, audio_name)
        session_id = _new_session_id()
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir()
        parsed_book = parse_ebook_bytes(ebook_content, ebook_name)
        (session_dir / ebook_name).write_bytes(ebook_content)
        (session_dir / audio_name).write_bytes(audio_content)
        (session_dir / "book.json").write_text(
            json.dumps(parsed_book.to_dict(), indent=2), encoding="utf-8"
        )
        self._write_session_locked(session_dir, {
            "session_id": session_id,
            "status": "processing",
        })
        return SessionSummary(session_id=session_id, status="processing")

    # ------------------------------------------------------------------
    # Chapter session flow
    # ------------------------------------------------------------------
    def create_chapter_session(
        self,
        ebook_name: str,
        ebook_content: bytes,
        audio_files: list[tuple[str, bytes]],
    ) -> SessionSummary:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._validate_chapter_upload_names(ebook_name, [name for name, _ in audio_files])
        session_id = _new_session_id()
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir()
        parsed_book = parse_ebook_bytes(ebook_content, ebook_name)
        (session_dir / ebook_name).write_bytes(ebook_content)
        for audio_name, audio_content in audio_files:
            (session_dir / audio_name).write_bytes(audio_content)
        audio_chapters = self._build_audio_chapters(session_dir, audio_files)
        ebook_chapters = self._build_ebook_chapters(parsed_book, audio_chapters)
        (session_dir / "book.json").write_text(
            json.dumps(parsed_book.to_dict(), indent=2), encoding="utf-8"
        )
        (session_dir / "audio_chapters.json").write_text(
            json.dumps([chapter.__dict__ for chapter in audio_chapters], indent=2),
            encoding="utf-8",
        )
        self._write_session_locked(session_dir, {
            "session_id": session_id,
            "status": "matching",
            "ebook_chapters": ebook_chapters,
            "audio_chapters": [chapter.__dict__ for chapter in audio_chapters],
        })
        return SessionSummary(session_id=session_id, status="matching")

    def create_session_from_ebook(self, ebook_name: str, ebook_content: bytes) -> dict:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        if Path(ebook_name).suffix.lower() not in {".txt", ".epub"}:
            raise ValueError(f"Unsupported ebook format: {ebook_name}")
        session_id = _new_session_id()
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir()
        parsed_book = parse_ebook_bytes(ebook_content, ebook_name)
        (session_dir / ebook_name).write_bytes(ebook_content)
        (session_dir / "book.json").write_text(
            json.dumps(parsed_book.to_dict(), indent=2), encoding="utf-8"
        )
        ebook_chapters = [
            {
                "title": chapter.title,
                "index": chapter.index,
                "block_indexes": chapter.block_indexes,
                "word_indexes": chapter.word_indexes,
            }
            for chapter in parsed_book.chapters
        ]
        payload = {
            "session_id": session_id,
            "status": "awaiting_audio",
            "ebook_chapters": ebook_chapters,
            "audio_chapters": None,
        }
        self._write_session_locked(session_dir, payload)
        return payload

    def finalize_audio_upload(self, session_id: str, audio_names: list[str]) -> dict:
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            raise SessionNotFoundError(f"Session not found: {session_id}")
        audio_chapters = self._build_audio_chapters_from_names(session_dir, audio_names)
        (session_dir / "audio_chapters.json").write_text(
            json.dumps([chapter.__dict__ for chapter in audio_chapters], indent=2),
            encoding="utf-8",
        )
        book = ParsedBook.from_dict(
            json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
        )
        ebook_chapters = self._build_ebook_chapters(book, audio_chapters)
        payload = self.read_session(session_id)
        payload["status"] = "matching"
        payload["ebook_chapters"] = ebook_chapters
        payload["audio_chapters"] = [chapter.__dict__ for chapter in audio_chapters]
        self._write_session_locked(session_dir, payload)
        self._notify(session_id)
        return payload

    def add_audio_to_session(self, session_id: str, audio_files: list[tuple[str, bytes]]) -> dict:
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            raise SessionNotFoundError(f"Session not found: {session_id}")
        audio_names = [name for name, _ in audio_files]
        suffixes = {Path(name).suffix.lower() for name in audio_names}
        if not (suffixes == {".mp3"} or (suffixes == {".m4b"} and len(audio_names) == 1)):
            raise ValueError("Chapter sessions accept either one .m4b or multiple .mp3 files")
        for audio_name, audio_content in audio_files:
            (session_dir / audio_name).write_bytes(audio_content)
        audio_chapters = self._build_audio_chapters(session_dir, audio_files)
        (session_dir / "audio_chapters.json").write_text(
            json.dumps([chapter.__dict__ for chapter in audio_chapters], indent=2),
            encoding="utf-8",
        )
        book = ParsedBook.from_dict(
            json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
        )
        ebook_chapters = self._build_ebook_chapters(book, audio_chapters)
        payload = self.read_session(session_id)
        payload["status"] = "matching"
        payload["ebook_chapters"] = ebook_chapters
        payload["audio_chapters"] = [chapter.__dict__ for chapter in audio_chapters]
        self._write_session_locked(session_dir, payload)
        self._notify(session_id)
        return payload

    def init_chapter_statuses(self, session_id: str) -> dict:
        session_dir = self.sessions_dir / session_id
        payload = self.read_session(session_id)
        if payload.get("chapter_statuses"):
            return payload
        book = ParsedBook.from_dict(
            json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
        )
        audio_chapters = json.loads(
            (session_dir / "audio_chapters.json").read_text(encoding="utf-8")
        )
        chapter_statuses = []
        for ebook_chapter in payload.get("ebook_chapters", []):
            audio_idx = ebook_chapter.get("suggested_audio_chapter_index")
            chapter_statuses.append(
                {
                    "ebook_chapter_index": ebook_chapter["index"],
                    "audio_chapter_index": audio_idx,
                    "status": "pending" if audio_idx is not None else "skipped",
                    "title": book.chapters[ebook_chapter["index"]].title,
                }
            )
        payload["chapter_statuses"] = chapter_statuses
        payload["chapter_mappings"] = [
            {
                "ebook_chapter_index": ebook_chapter["index"],
                "audio_chapter_index": ebook_chapter.get("suggested_audio_chapter_index"),
            }
            for ebook_chapter in payload.get("ebook_chapters", [])
        ]
        (session_dir / "chapter_mappings.json").write_text(
            json.dumps(payload["chapter_mappings"], indent=2), encoding="utf-8"
        )
        payload["status"] = "processing"
        self._write_session_locked(session_dir, payload)
        self._notify(session_id)
        return payload

    def process_single_chapter(self, session_id: str, ebook_chapter_index: int, audio_chapter_index: int) -> None:
        if self.transcriber is None:
            return
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return
        try:
            payload = self.read_session(session_id)
            book = ParsedBook.from_dict(
                json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
            )
            audio_chapters = json.loads(
                (session_dir / "audio_chapters.json").read_text(encoding="utf-8")
            )
        except (FileNotFoundError, SessionNotFoundError):
            return
        chapter_statuses = payload.setdefault("chapter_statuses", [])
        # Use a reference to the dict that's actually inside payload so
        # mutations below are reflected when we write it back.
        status_entry = next(
            (s for s in chapter_statuses if s["ebook_chapter_index"] == ebook_chapter_index),
            None,
        )
        if status_entry is None:
            status_entry = {"ebook_chapter_index": ebook_chapter_index}
            chapter_statuses.append(status_entry)
        status_entry["audio_chapter_index"] = audio_chapter_index
        status_entry["status"] = "processing"
        status_entry["title"] = book.chapters[ebook_chapter_index].title
        status_entry.pop("reason", None)
        payload["status"] = self._derive_chapter_session_status(payload)
        self._write_session_locked(session_dir, payload)
        self._notify(session_id)
        try:
            result = self._transcribe_and_align(session_dir, session_id, status_entry, book, audio_chapters)
            status_entry["status"] = result["status"]
            if "reason" in result:
                status_entry["reason"] = result["reason"]
            self._upsert_completed_chapter(payload, result["completed_chapter"])
        except (FileNotFoundError, SessionNotFoundError):
            return
        except Exception as error:
            status_entry["status"] = "failed"
            status_entry["reason"] = str(error)
        payload.setdefault("completed_chapters", []).sort(key=lambda chapter: chapter["chapter_index"])
        payload["status"] = self._derive_chapter_session_status(payload)
        self._write_session_locked(session_dir, payload)
        self._notify(session_id)

    def read_session(self, session_id: str) -> dict:
        session_path = self.sessions_dir / session_id / "session.json"
        if not session_path.exists():
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return json.loads(session_path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[dict]:
        if not self.sessions_dir.exists():
            return []
        sessions = []
        for entry in sorted(self.sessions_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not entry.is_dir():
                continue
            session_path = entry / "session.json"
            if not session_path.exists():
                continue
            try:
                payload = json.loads(session_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            ebook_chapters = payload.get("ebook_chapters") or []
            chapter_statuses = payload.get("chapter_statuses") or []
            completed = payload.get("completed_chapters") or []
            sessions.append({
                "session_id": payload.get("session_id", entry.name),
                "status": payload.get("status", "unknown"),
                "title": self._infer_session_title(entry),
                "ebook_chapter_count": len(ebook_chapters),
                "completed_chapter_count": len(completed),
                "total_chapter_count": len(chapter_statuses) or len(ebook_chapters),
                "created_at": entry.stat().st_mtime,
            })
        return sessions

    def delete_session(self, session_id: str) -> None:
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            raise SessionNotFoundError(f"Session not found: {session_id}")
        import shutil
        shutil.rmtree(session_dir)
        self._listeners.pop(session_id, None)

    def recover_stuck_sessions(self) -> int:
        """Reset chapters stuck in 'processing' back to 'pending'.

        Called on startup to recover from crashes where background tasks
        died mid-processing. Returns the count of chapters reset.
        """
        if not self.sessions_dir.exists():
            return 0
        total_reset = 0
        for entry in sorted(self.sessions_dir.iterdir()):
            if not entry.is_dir():
                continue
            session_path = entry / "session.json"
            if not session_path.exists():
                continue
            try:
                payload = json.loads(session_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            reset_count = 0
            for status in payload.get("chapter_statuses", []):
                if status.get("status") == "processing":
                    status["status"] = "pending"
                    status.pop("reason", None)
                    reset_count += 1
            if reset_count:
                payload["status"] = self._derive_chapter_session_status(payload)
                self._write_session_locked(entry, payload)
                logger.info(
                    "[%s] recovered %d stuck chapter(s)",
                    payload.get("session_id", entry.name),
                    reset_count,
                )
                total_reset += reset_count
        return total_reset

    def retry_chapter(self, session_id: str, ebook_chapter_index: int) -> dict:
        session_dir = self.sessions_dir / session_id
        payload = self.read_session(session_id)
        chapter_statuses = payload.get("chapter_statuses", [])
        status = next(
            (s for s in chapter_statuses if s["ebook_chapter_index"] == ebook_chapter_index),
            None,
        )
        if status is None:
            raise ValueError(f"Chapter not found: {ebook_chapter_index}")
        if status["status"] not in {"failed", "transcript-only", "processing"}:
            raise ValueError(f"Chapter is not in a retryable state: {status['status']}")
        audio_idx = status.get("audio_chapter_index")
        if audio_idx is None:
            raise ValueError("Skipped chapters cannot be retried")
        status["status"] = "pending"
        status.pop("reason", None)
        completed = payload.get("completed_chapters", [])
        payload["completed_chapters"] = [
            c for c in completed if c["chapter_index"] != ebook_chapter_index
        ]
        payload["status"] = self._derive_chapter_session_status(payload)
        self._write_session_locked(session_dir, payload)
        self._notify(session_id)
        return payload

    def get_chapter_audio_path(self, session_id: str, audio_name: str) -> Path:
        return self.sessions_dir / session_id / audio_name

    def submit_chapter_mapping(self, session_id: str, matches: list[dict]) -> SessionSummary:
        session_dir = self.sessions_dir / session_id
        book = ParsedBook.from_dict(
            json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
        )
        session_payload = self.read_session(session_id)
        ebook_chapters = session_payload["ebook_chapters"]
        audio_chapters = json.loads((session_dir / "audio_chapters.json").read_text(encoding="utf-8"))
        ebook_indexes = {chapter.index for chapter in book.chapters}
        mapped_ebook_indexes = [match["ebook_chapter_index"] for match in matches]
        missing_indexes = sorted(ebook_indexes - set(mapped_ebook_indexes))
        if missing_indexes:
            raise ValueError(f"Missing matches for ebook chapters: {missing_indexes}")
        if len(set(mapped_ebook_indexes)) != len(mapped_ebook_indexes):
            raise ValueError("Each ebook chapter can only be matched once")
        mapped_audio_indexes = [
            match["audio_chapter_index"]
            for match in matches
            if match["audio_chapter_index"] is not None
        ]
        if len(set(mapped_audio_indexes)) != len(mapped_audio_indexes):
            raise ValueError("Each audio chapter can only be matched once")
        valid_audio_indexes = {chapter["index"] for chapter in audio_chapters}
        invalid_audio_indexes = sorted(set(mapped_audio_indexes) - valid_audio_indexes)
        if invalid_audio_indexes:
            raise ValueError(f"Unknown audio chapters: {invalid_audio_indexes}")
        sorted_matches = sorted(matches, key=lambda match: match["ebook_chapter_index"])
        processing_payload = {
            "session_id": session_id,
            "status": "processing",
            "ebook_chapters": ebook_chapters,
            "audio_chapters": audio_chapters,
            "chapter_mappings": sorted_matches,
            "chapter_statuses": [
                {
                    "ebook_chapter_index": match["ebook_chapter_index"],
                    "audio_chapter_index": match["audio_chapter_index"],
                    "status": "pending" if match["audio_chapter_index"] is not None else "skipped",
                    "title": book.chapters[match["ebook_chapter_index"]].title,
                }
                for match in sorted_matches
            ],
        }
        processing_payload["status"] = self._derive_chapter_session_status(processing_payload)
        (session_dir / "chapter_mappings.json").write_text(
            json.dumps(sorted_matches, indent=2), encoding="utf-8"
        )
        self._write_session_locked(session_dir, processing_payload)
        self._notify(session_id)
        return SessionSummary(session_id=session_id, status="processing")

    def process_session(self, session_id: str) -> None:
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return
        if self.transcriber is None:
            return
        logger.info("[%s] single-audio processing starting", session_id)
        t_total = time.monotonic()
        try:
            book = ParsedBook.from_dict(
                json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
            )
            audio_path = find_audio_file(session_dir)
            timed_words = self.transcriber.transcribe(audio_path)
            alignment = align_words(book.words, timed_words, **self._alignment_kwargs)
            logger.info(
                "[%s] single-audio done in %.1fs (coverage %.0f%%)",
                session_id,
                time.monotonic() - t_total,
                alignment.coverage * 100,
            )
            ready_payload = {
                "session_id": session_id,
                "status": "ready",
                "audio_url": f"/sessions/{session_id}/audio",
                "coverage": alignment.coverage,
                "blocks": json.loads(json.dumps(book.to_dict()["blocks"])),
                "words": alignment.words,
            }
            self._write_session_locked(session_dir, ready_payload)
            self._notify(session_id)
        except (FileNotFoundError, SessionNotFoundError):
            # Session was deleted while the background task was running.
            return
        except Exception as error:
            logger.exception("[%s] single-audio failed: %s", session_id, error)
            failed_payload = {
                "session_id": session_id,
                "status": "failed",
                "reason": str(error),
            }
            self._write_session_locked(session_dir, failed_payload)
            self._notify(session_id)

    def process_chapter_session(self, session_id: str, parallel: bool = False) -> None:
        if parallel:
            self._process_chapter_session_parallel(session_id)
            return
        while self.process_next_pending_chapter(session_id):
            continue

    def process_next_pending_chapter(self, session_id: str) -> bool:
        if self.transcriber is None:
            return False
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return False
        try:
            payload = self.read_session(session_id)
        except SessionNotFoundError:
            return False
        pending_status = next(
            (status for status in payload.get("chapter_statuses", []) if status["status"] == "pending"),
            None,
        )
        if pending_status is None:
            return False
        pending_status["status"] = "processing"
        self._write_session_locked(session_dir, payload)
        self._notify(session_id)
        try:
            book = ParsedBook.from_dict(
                json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
            )
            audio_chapters = json.loads(
                (session_dir / "audio_chapters.json").read_text(encoding="utf-8")
            )
            result = self._transcribe_and_align(session_dir, session_id, pending_status, book, audio_chapters)
            pending_status["status"] = result["status"]
            if "reason" in result:
                pending_status["reason"] = result["reason"]
            self._upsert_completed_chapter(payload, result["completed_chapter"])
        except (FileNotFoundError, SessionNotFoundError):
            # Session was deleted mid-processing.
            return False
        except Exception as error:
            logger.exception(
                "[%s] chapter %d failed: %s",
                session_id,
                pending_status["ebook_chapter_index"] + 1,
                error,
            )
            pending_status["status"] = "failed"
            pending_status["reason"] = str(error)
        payload.setdefault("completed_chapters", []).sort(key=lambda chapter: chapter["chapter_index"])
        payload["status"] = self._derive_chapter_session_status(payload)
        self._write_session_locked(session_dir, payload)
        self._notify(session_id)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _upsert_completed_chapter(self, payload: dict, completed: dict) -> None:
        chapters = payload.setdefault("completed_chapters", [])
        for index, existing in enumerate(chapters):
            if existing["chapter_index"] == completed["chapter_index"]:
                chapters[index] = completed
                return
        chapters.append(completed)

    def _infer_session_title(self, session_dir: Path) -> str:
        book_path = session_dir / "book.json"
        if book_path.exists():
            try:
                return json.loads(book_path.read_text(encoding="utf-8")).get("title", session_dir.name)
            except json.JSONDecodeError:
                pass
        return session_dir.name

    def _transcribe_and_align(
        self,
        session_dir: Path,
        session_id: str,
        pending_status: dict,
        book: ParsedBook,
        audio_chapters: list[dict],
    ) -> dict:
        book_chapter = book.chapters[pending_status["ebook_chapter_index"]]
        audio_chapter = next(
            chapter for chapter in audio_chapters if chapter["index"] == pending_status["audio_chapter_index"]
        )
        audio_path = self._resolve_audio_path_for_processing(session_dir, audio_chapter)
        t_transcribe = time.monotonic()
        logger.info(
            "[%s] chapter %d/%d '%s': transcribing %s",
            session_id,
            pending_status["ebook_chapter_index"] + 1,
            len(book.chapters),
            book_chapter.title,
            audio_path.name,
        )
        timed_words = self.transcriber.transcribe(audio_path)
        logger.info(
            "[%s] chapter %d: transcribe done in %.1fs",
            session_id,
            pending_status["ebook_chapter_index"] + 1,
            time.monotonic() - t_transcribe,
        )
        chapter_word_indexes = set(book_chapter.word_indexes)
        chapter_block_indexes = set(book_chapter.block_indexes)
        chapter_words = [word for word in book.words if word.index in chapter_word_indexes]
        chapter_blocks = [block for block in book.blocks if block.index in chapter_block_indexes]
        t_align = time.monotonic()
        try:
            alignment = align_words(chapter_words, timed_words, **self._alignment_kwargs)
            logger.info(
                "[%s] chapter %d: aligned in %.1fs (coverage %.0f%%, %d words)",
                session_id,
                pending_status["ebook_chapter_index"] + 1,
                time.monotonic() - t_align,
                alignment.coverage * 100,
                len(alignment.words),
            )
            return {
                "status": "ready",
                "completed_chapter": {
                    "chapter_index": book_chapter.index,
                    "title": book_chapter.title,
                    "audio_url": f"/chapter-sessions/{session_id}/audio/{audio_path.name}",
                    "blocks": [
                        {
                            "index": block.index,
                            "text": block.text,
                            "word_indexes": block.word_indexes,
                        }
                        for block in chapter_blocks
                    ],
                    "words": alignment.words,
                    "coverage": alignment.coverage,
                    "text_source": "ebook",
                },
            }
        except AlignmentFailure as error:
            logger.warning(
                "[%s] chapter %d: alignment failed — %s",
                session_id,
                pending_status["ebook_chapter_index"] + 1,
                error,
            )
            return {
                "status": "transcript-only",
                "reason": str(error),
                "completed_chapter": self._build_transcript_chapter_payload(
                    session_id=session_id,
                    chapter_index=book_chapter.index,
                    title=book_chapter.title,
                    audio_name=audio_path.name,
                    timed_words=timed_words,
                ),
            }

    def _process_chapter_session_parallel(self, session_id: str) -> None:
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return
        try:
            payload = self.read_session(session_id)
            book = ParsedBook.from_dict(
                json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
            )
            audio_chapters = json.loads(
                (session_dir / "audio_chapters.json").read_text(encoding="utf-8")
            )
        except (FileNotFoundError, SessionNotFoundError):
            return
        pending_list = [s for s in payload.get("chapter_statuses", []) if s["status"] == "pending"]
        if not pending_list:
            return
        for pending_status in pending_list:
            pending_status["status"] = "processing"
        self._write_session_locked(session_dir, payload)
        self._notify(session_id)
        cpu = os.cpu_count() or 1
        configured = self.settings.max_workers if self.settings else None
        max_workers = min(len(pending_list), configured or cpu)
        logger.info(
            "[%s] parallel processing %d chapters with %d workers",
            session_id,
            len(pending_list),
            max_workers,
        )
        t_batch = time.monotonic()
        completed_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for pending_status in pending_list:
                future = executor.submit(
                    self._transcribe_and_align,
                    session_dir,
                    session_id,
                    pending_status,
                    book,
                    audio_chapters,
                )
                futures[future] = pending_status
            for future in as_completed(futures):
                if not session_dir.exists():
                    # Session deleted mid-processing; cancel remaining futures.
                    for f in futures:
                        f.cancel()
                    logger.info("[%s] session deleted, cancelling remaining work", session_id)
                    return
                pending_status = futures[future]
                try:
                    result = future.result()
                    pending_status["status"] = result["status"]
                    if "reason" in result:
                        pending_status["reason"] = result["reason"]
                    self._upsert_completed_chapter(payload, result["completed_chapter"])
                    completed_count += 1
                    logger.info(
                        "[%s] %d/%d chapters completed (%.1fs elapsed)",
                        session_id,
                        completed_count,
                        len(pending_list),
                        time.monotonic() - t_batch,
                    )
                except (FileNotFoundError, SessionNotFoundError):
                    return
                except Exception as error:
                    pending_status["status"] = "failed"
                    pending_status["reason"] = str(error)
                    logger.exception(
                        "[%s] chapter %d failed: %s",
                        session_id,
                        pending_status["ebook_chapter_index"] + 1,
                        error,
                    )
                payload.setdefault("completed_chapters", []).sort(
                    key=lambda chapter: chapter["chapter_index"]
                )
                payload["status"] = self._derive_chapter_session_status(payload)
                self._write_session_locked(session_dir, payload)
                self._notify(session_id)
        logger.info(
            "[%s] batch complete in %.1fs",
            session_id,
            time.monotonic() - t_batch,
        )

    def _write_session_locked(self, session_dir: Path, payload: dict) -> None:
        """Write session.json atomically. Silently no-ops if the session
        directory was deleted while a background task was running."""
        if not session_dir.exists():
            # Session was deleted out from under a running background task.
            return
        with self._lock:
            (session_dir / "session.json").write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )

    def get_audio_path(self, session_id: str) -> Path:
        return find_audio_path(self.sessions_dir / session_id)

    def _validate_upload_names(self, ebook_name: str, audio_name: str) -> None:
        if Path(ebook_name).suffix.lower() not in {".txt", ".epub"}:
            raise ValueError(f"Unsupported ebook format: {ebook_name}")
        if Path(audio_name).suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
            raise ValueError(f"Unsupported audio format: {audio_name}")

    def _validate_chapter_upload_names(self, ebook_name: str, audio_names: list[str]) -> None:
        if Path(ebook_name).suffix.lower() not in {".txt", ".epub"}:
            raise ValueError(f"Unsupported ebook format: {ebook_name}")
        if not audio_names:
            raise ValueError("At least one audiobook file is required")
        suffixes = {Path(name).suffix.lower() for name in audio_names}
        if suffixes == {".mp3"}:
            return
        if suffixes == {".m4b"} and len(audio_names) == 1:
            return
        raise ValueError("Chapter sessions accept either one .m4b or multiple .mp3 files")

    def _build_audio_chapters(
        self,
        session_dir: Path,
        audio_files: list[tuple[str, bytes]],
    ) -> list[AudioChapter]:
        audio_names = [name for name, _ in audio_files]
        if Path(audio_names[0]).suffix.lower() == ".m4b":
            source_name = audio_names[0]
            chapters = discover_m4b_chapters(session_dir / source_name)
            return [
                AudioChapter(
                    index=index,
                    title=chapter["title"],
                    source_name=source_name,
                    start_ms=chapter["start_ms"],
                    end_ms=chapter["end_ms"],
                )
                for index, chapter in enumerate(chapters)
            ]
        ordered_names = sorted(audio_names)
        return [
            AudioChapter(
                index=index,
                title=Path(name).stem,
                source_name=name,
            )
            for index, name in enumerate(ordered_names)
        ]

    def _build_audio_chapters_from_names(self, session_dir: Path, audio_names: list[str]) -> list[AudioChapter]:
        if Path(audio_names[0]).suffix.lower() == ".m4b":
            source_name = audio_names[0]
            chapters = discover_m4b_chapters(session_dir / source_name)
            return [
                AudioChapter(
                    index=index,
                    title=chapter["title"],
                    source_name=source_name,
                    start_ms=chapter["start_ms"],
                    end_ms=chapter["end_ms"],
                )
                for index, chapter in enumerate(chapters)
            ]
        ordered_names = sorted(audio_names)
        return [
            AudioChapter(index=index, title=Path(name).stem, source_name=name)
            for index, name in enumerate(ordered_names)
        ]

    def _build_ebook_chapters(
        self,
        parsed_book: ParsedBook,
        audio_chapters: list[AudioChapter],
    ) -> list[dict]:
        used_audio_indexes: set[int] = set()
        ebook_chapters: list[dict] = []
        for chapter in parsed_book.chapters:
            suggested_audio_chapter_index = suggest_audio_chapter_index(
                chapter.title,
                audio_chapters,
                used_audio_indexes,
            )
            if suggested_audio_chapter_index is not None:
                used_audio_indexes.add(suggested_audio_chapter_index)
            ebook_chapters.append(
                {
                    "title": chapter.title,
                    "index": chapter.index,
                    "block_indexes": chapter.block_indexes,
                    "word_indexes": chapter.word_indexes,
                    "suggested_audio_chapter_index": suggested_audio_chapter_index,
                }
            )
        return ebook_chapters

    def _resolve_audio_path_for_processing(self, session_dir: Path, audio_chapter: dict) -> Path:
        audio_path = session_dir / audio_chapter["source_name"]
        if audio_path.suffix.lower() != ".m4b":
            return audio_path
        start_ms = audio_chapter["start_ms"]
        end_ms = audio_chapter["end_ms"]
        clip_path = session_dir / f"chapter-{audio_chapter['index'] + 1:03d}.mp3"
        return extract_m4b_chapter_clip(audio_path, start_ms, end_ms, clip_path)

    def _build_transcript_chapter_payload(
        self,
        session_id: str,
        chapter_index: int,
        title: str,
        audio_name: str,
        timed_words: list[TimedWord],
    ) -> dict:
        transcript_words = [
            {
                "index": index,
                "block_index": 0,
                "text": word.text,
                "normalized": word.normalized,
                "start_ms": word.start_ms,
                "end_ms": word.end_ms,
            }
            for index, word in enumerate(timed_words)
        ]
        return {
            "chapter_index": chapter_index,
            "title": title,
            "audio_url": f"/chapter-sessions/{session_id}/audio/{audio_name}",
            "blocks": [
                {
                    "index": 0,
                    "text": " ".join(word["text"] for word in transcript_words),
                    "word_indexes": [word["index"] for word in transcript_words],
                }
            ],
            "words": transcript_words,
            "coverage": None,
            "text_source": "transcript",
        }

    def _derive_chapter_session_status(self, payload: dict) -> str:
        statuses = [status["status"] for status in payload.get("chapter_statuses", [])]
        if not statuses:
            return payload.get("status", "matching")
        if any(status == "processing" for status in statuses):
            return "processing"
        ready_count = sum(status in {"ready", "transcript-only", "skipped"} for status in statuses)
        failed_count = sum(status == "failed" for status in statuses)
        pending_count = sum(status == "pending" for status in statuses)
        if failed_count and ready_count:
            return "failed-partial" if pending_count == 0 else "processing"
        if failed_count:
            return "failed" if pending_count == 0 else "processing"
        if pending_count:
            return "processing"
        return "ready"
