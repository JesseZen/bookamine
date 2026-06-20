import json
import re
import subprocess
from pathlib import Path
from typing import Protocol

from rapidfuzz import fuzz

from app.alignment import AlignmentFailure, TimedWord, align_words
from app.models import AudioChapter, ParsedBook, SessionSummary
from app.parsers import parse_ebook_bytes

SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".m4b"}
TITLE_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
ONES = {
    "zero": 0,
    "one": 1,
    "first": 1,
    "two": 2,
    "second": 2,
    "three": 3,
    "third": 3,
    "four": 4,
    "fourth": 4,
    "five": 5,
    "fifth": 5,
    "six": 6,
    "sixth": 6,
    "seven": 7,
    "seventh": 7,
    "eight": 8,
    "eighth": 8,
    "nine": 9,
    "ninth": 9,
}
TEENS = {
    "ten": 10,
    "tenth": 10,
    "eleven": 11,
    "eleventh": 11,
    "twelve": 12,
    "twelfth": 12,
    "thirteen": 13,
    "thirteenth": 13,
    "fourteen": 14,
    "fourteenth": 14,
    "fifteen": 15,
    "fifteenth": 15,
    "sixteen": 16,
    "sixteenth": 16,
    "seventeen": 17,
    "seventeenth": 17,
    "eighteen": 18,
    "eighteenth": 18,
    "nineteen": 19,
    "nineteenth": 19,
}
TENS = {
    "twenty": 20,
    "twentieth": 20,
    "thirty": 30,
    "thirtieth": 30,
    "forty": 40,
    "fortieth": 40,
    "fifty": 50,
    "fiftieth": 50,
    "sixty": 60,
    "sixtieth": 60,
    "seventy": 70,
    "seventieth": 70,
    "eighty": 80,
    "eightieth": 80,
    "ninety": 90,
    "ninetieth": 90,
}


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> list[TimedWord]: ...


class SessionNotFoundError(FileNotFoundError):
    pass


class WhisperTranscriber:
    def __init__(self, model_name: str = "base.en"):
        self.model_name = model_name
        self._model = None

    def transcribe(self, audio_path: Path) -> list[TimedWord]:
        if self._model is None:
            import whisper

            self._model = whisper.load_model(self.model_name)
        result = self._model.transcribe(
            str(audio_path),
            language="en",
            word_timestamps=True,
            condition_on_previous_text=False,
        )
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
        return timed_words


def discover_m4b_chapters(audio_path: Path) -> list[dict]:
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
    return chapters


def extract_chapter_number(title: str) -> int | None:
    digit_match = re.search(r"\d+", title)
    if digit_match is not None:
        return int(digit_match.group(0))
    raw_tokens = TITLE_TOKEN_PATTERN.findall(title.casefold().replace("-", " "))
    tokens: list[str] = []
    for token in raw_tokens:
        expanded_tokens = expand_compound_number_token(token)
        if expanded_tokens:
            tokens.extend(expanded_tokens)
            continue
        tokens.append(token)
    for index, token in enumerate(tokens):
        if token in ONES:
            return ONES[token]
        if token in TEENS:
            return TEENS[token]
        if token in TENS:
            if index + 1 < len(tokens) and tokens[index + 1] in ONES:
                return TENS[token] + ONES[tokens[index + 1]]
            return TENS[token]
    return None


def expand_compound_number_token(token: str) -> list[str]:
    if token in ONES or token in TEENS or token in TENS:
        return [token]
    for tens_word in TENS:
        if not token.startswith(tens_word) or token == tens_word:
            continue
        ones_word = token[len(tens_word) :]
        if ones_word in ONES:
            return [tens_word, ones_word]
    return []


def normalize_chapter_title(title: str) -> str:
    tokens = TITLE_TOKEN_PATTERN.findall(title.casefold().replace("-", " "))
    normalized_tokens: list[str] = []
    chapter_number = extract_chapter_number(title)
    if chapter_number is not None:
        normalized_tokens.append(str(chapter_number))
    for token in tokens:
        if token.isdigit() or expand_compound_number_token(token):
            continue
        normalized_tokens.append(token)
    return " ".join(normalized_tokens)


def score_chapter_title_match(ebook_title: str, audio_title: str) -> float:
    ebook_number = extract_chapter_number(ebook_title)
    audio_number = extract_chapter_number(audio_title)
    if ebook_number is not None and audio_number is not None:
        return 1.0 if ebook_number == audio_number else 0.0
    return fuzz.token_sort_ratio(
        normalize_chapter_title(ebook_title),
        normalize_chapter_title(audio_title),
    ) / 100


def suggest_audio_chapter_index(
    ebook_title: str,
    audio_chapters: list[AudioChapter],
    used_audio_indexes: set[int],
    threshold: float = 0.55,
) -> int | None:
    best_index: int | None = None
    best_score = 0.0
    for chapter in audio_chapters:
        if chapter.index in used_audio_indexes:
            continue
        score = score_chapter_title_match(ebook_title, chapter.title)
        if score > best_score:
            best_score = score
            best_index = chapter.index
    if best_score < threshold:
        return None
    return best_index


class SessionService:
    def __init__(self, data_dir: Path, transcriber: Transcriber | None):
        self.data_dir = data_dir
        self.sessions_dir = data_dir / "sessions"
        self.transcriber = transcriber

    def create_session(
        self,
        ebook_name: str,
        ebook_content: bytes,
        audio_name: str,
        audio_content: bytes,
    ) -> SessionSummary:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._validate_upload_names(ebook_name, audio_name)
        session_id = f"session-{len(list(self.sessions_dir.iterdir())) + 1}"
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir()
        parsed_book = parse_ebook_bytes(ebook_content, ebook_name)
        (session_dir / ebook_name).write_bytes(ebook_content)
        (session_dir / audio_name).write_bytes(audio_content)
        (session_dir / "book.json").write_text(
            json.dumps(parsed_book.to_dict(), indent=2),
            encoding="utf-8",
        )
        (session_dir / "session.json").write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "status": "processing",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return SessionSummary(session_id=session_id, status="processing")

    def create_chapter_session(
        self,
        ebook_name: str,
        ebook_content: bytes,
        audio_files: list[tuple[str, bytes]],
    ) -> SessionSummary:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._validate_chapter_upload_names(ebook_name, [name for name, _ in audio_files])
        session_id = f"session-{len(list(self.sessions_dir.iterdir())) + 1}"
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir()
        parsed_book = parse_ebook_bytes(ebook_content, ebook_name)
        (session_dir / ebook_name).write_bytes(ebook_content)
        for audio_name, audio_content in audio_files:
            (session_dir / audio_name).write_bytes(audio_content)
        audio_chapters = self._build_audio_chapters(session_dir, audio_files)
        ebook_chapters = self._build_ebook_chapters(parsed_book, audio_chapters)
        (session_dir / "book.json").write_text(
            json.dumps(parsed_book.to_dict(), indent=2),
            encoding="utf-8",
        )
        (session_dir / "audio_chapters.json").write_text(
            json.dumps([chapter.__dict__ for chapter in audio_chapters], indent=2),
            encoding="utf-8",
        )
        matching_payload = {
            "session_id": session_id,
            "status": "matching",
            "ebook_chapters": ebook_chapters,
            "audio_chapters": [chapter.__dict__ for chapter in audio_chapters],
        }
        (session_dir / "session.json").write_text(
            json.dumps(matching_payload, indent=2),
            encoding="utf-8",
        )
        return SessionSummary(session_id=session_id, status="matching")

    def process_session(self, session_id: str) -> None:
        session_dir = self.sessions_dir / session_id
        if self.transcriber is None:
            return
        try:
            book = ParsedBook.from_dict(
                json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
            )
            audio_path = self._find_audio_path(session_dir)
            timed_words = self.transcriber.transcribe(audio_path)
            alignment = align_words(book.words, timed_words)
            ready_payload = {
                "session_id": session_id,
                "status": "ready",
                "audio_url": f"/sessions/{session_id}/audio",
                "coverage": alignment.coverage,
                "blocks": json.loads(json.dumps(book.to_dict()["blocks"])),
                "words": alignment.words,
            }
            (session_dir / "session.json").write_text(
                json.dumps(ready_payload, indent=2),
                encoding="utf-8",
            )
        except Exception as error:
            failed_payload = {
                "session_id": session_id,
                "status": "failed",
                "reason": str(error),
            }
            (session_dir / "session.json").write_text(
                json.dumps(failed_payload, indent=2),
                encoding="utf-8",
            )

    def process_chapter_session(self, session_id: str) -> None:
        while self.process_next_pending_chapter(session_id):
            continue

    def read_session(self, session_id: str) -> dict:
        session_path = self.sessions_dir / session_id / "session.json"
        if not session_path.exists():
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return json.loads(session_path.read_text(encoding="utf-8"))

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
            json.dumps(sorted_matches, indent=2),
            encoding="utf-8",
        )
        (session_dir / "session.json").write_text(
            json.dumps(processing_payload, indent=2),
            encoding="utf-8",
        )
        return SessionSummary(session_id=session_id, status="processing")

    def process_next_pending_chapter(self, session_id: str) -> bool:
        if self.transcriber is None:
            return False
        session_dir = self.sessions_dir / session_id
        payload = self.read_session(session_id)
        pending_status = next(
            (status for status in payload.get("chapter_statuses", []) if status["status"] == "pending"),
            None,
        )
        if pending_status is None:
            return False
        pending_status["status"] = "processing"
        (session_dir / "session.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        try:
            book = ParsedBook.from_dict(
                json.loads((session_dir / "book.json").read_text(encoding="utf-8"))
            )
            audio_chapters = json.loads(
                (session_dir / "audio_chapters.json").read_text(encoding="utf-8")
            )
            ebook_chapter_index = pending_status["ebook_chapter_index"]
            audio_chapter_index = pending_status["audio_chapter_index"]
            book_chapter = book.chapters[ebook_chapter_index]
            audio_chapter = next(
                chapter for chapter in audio_chapters if chapter["index"] == audio_chapter_index
            )
            audio_path = self._resolve_audio_path_for_processing(session_dir, audio_chapter)
            timed_words = self.transcriber.transcribe(audio_path)
            chapter_word_indexes = set(book_chapter.word_indexes)
            chapter_block_indexes = set(book_chapter.block_indexes)
            chapter_words = [word for word in book.words if word.index in chapter_word_indexes]
            chapter_blocks = [block for block in book.blocks if block.index in chapter_block_indexes]
            completed_chapters = payload.setdefault("completed_chapters", [])
            try:
                alignment = align_words(chapter_words, timed_words)
                pending_status["status"] = "ready"
                completed_chapters.append(
                    {
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
                    }
                )
            except AlignmentFailure as error:
                pending_status["status"] = "transcript-only"
                pending_status["reason"] = str(error)
                completed_chapters.append(
                    self._build_transcript_chapter_payload(
                        session_id=session_id,
                        chapter_index=book_chapter.index,
                        title=book_chapter.title,
                        audio_name=audio_path.name,
                        timed_words=timed_words,
                    )
                )
            completed_chapters.sort(key=lambda chapter: chapter["chapter_index"])
        except Exception as error:
            pending_status["status"] = "failed"
            pending_status["reason"] = str(error)
        payload["status"] = self._derive_chapter_session_status(payload)
        (session_dir / "session.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        return True

    def get_audio_path(self, session_id: str) -> Path:
        return self._find_audio_path(self.sessions_dir / session_id)

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

    def _find_audio_path(self, session_dir: Path) -> Path:
        for file_path in session_dir.iterdir():
            if file_path.suffix.lower() in SUPPORTED_AUDIO_SUFFIXES:
                return file_path
        raise FileNotFoundError(f"Audio file not found in {session_dir}")

    def _resolve_audio_path_for_processing(self, session_dir: Path, audio_chapter: dict) -> Path:
        audio_path = session_dir / audio_chapter["source_name"]
        if audio_path.suffix.lower() != ".m4b":
            return audio_path
        start_ms = audio_chapter["start_ms"]
        end_ms = audio_chapter["end_ms"]
        clip_path = session_dir / f"chapter-{audio_chapter['index'] + 1:03d}.mp3"
        if clip_path.exists():
            return clip_path
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start_ms / 1000:.3f}",
                "-to",
                f"{end_ms / 1000:.3f}",
                "-i",
                str(audio_path),
                str(clip_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return clip_path

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
