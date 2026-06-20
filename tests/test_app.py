from fastapi.testclient import TestClient
import shutil

from app.config import Settings
from app.main import create_app
from app.alignment import TimedWord
import app.services as services


def test_index_route_serves_reader_shell():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Bookamine" in response.text


def test_create_session_returns_processing_state(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    response = client.post(
        "/sessions",
        files={
            "ebook": ("sample.txt", b"One two\n\nThree four", "text/plain"),
            "audio": ("sample.mp3", b"fake-audio", "audio/mpeg"),
        },
    )

    assert response.json() == {
        "session_id": "session-1",
        "status": "processing",
    }


def test_missing_chapter_session_returns_404(tmp_path):
    data_dir = tmp_path / "data"
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=data_dir,
            ),
            transcriber=None,
        )
    )

    client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
        ],
    )
    shutil.rmtree(data_dir / "sessions" / "session-1")

    response = client.get("/chapter-sessions/session-1")

    assert response.status_code == 404
    assert response.json() == {"detail": "Session not found: session-1"}


class FakeTranscriber:
    def transcribe(self, audio_path):
        return [
            TimedWord(text="hello", normalized="hello", start_ms=0, end_ms=300),
            TimedWord(text="world", normalized="world", start_ms=301, end_ms=640),
        ]


class FakeChapterTranscriber:
    def transcribe(self, audio_path):
        if audio_path.name == "chapter-01.mp3":
            return [
                TimedWord(text="one", normalized="one", start_ms=0, end_ms=300),
                TimedWord(text="two", normalized="two", start_ms=301, end_ms=640),
            ]
        if audio_path.name == "chapter-02.mp3":
            return [
                TimedWord(text="three", normalized="three", start_ms=0, end_ms=300),
                TimedWord(text="four", normalized="four", start_ms=301, end_ms=640),
            ]
        raise AssertionError(audio_path.name)


class FakeTranscriptFallbackTranscriber:
    def transcribe(self, audio_path):
        if audio_path.name == "chapter-01.mp3":
            return [
                TimedWord(text="Alpha", normalized="alpha", start_ms=0, end_ms=300),
                TimedWord(text="beta", normalized="beta", start_ms=301, end_ms=640),
            ]
        raise AssertionError(audio_path.name)


def test_session_payload_contains_blocks_and_timed_words(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=FakeTranscriber(),
        )
    )

    create_response = client.post(
        "/sessions",
        files={
            "ebook": ("sample.txt", b"Hello world", "text/plain"),
            "audio": ("sample.mp3", b"fake-audio", "audio/mpeg"),
        },
    )

    payload_response = client.get(f"/sessions/{create_response.json()['session_id']}")

    assert payload_response.json() == {
        "audio_url": "/sessions/session-1/audio",
        "blocks": [
            {"index": 0, "text": "Hello world", "word_indexes": [0, 1]},
        ],
        "coverage": 1.0,
        "session_id": "session-1",
        "status": "ready",
        "words": [
            {
                "block_index": 0,
                "end_ms": 300,
                "index": 0,
                "normalized": "hello",
                "start_ms": 0,
                "text": "Hello",
            },
            {
                "block_index": 0,
                "end_ms": 640,
                "index": 1,
                "normalized": "world",
                "start_ms": 301,
                "text": "world",
            },
        ],
    }


def test_create_session_and_fetch_ready_payload(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=FakeTranscriber(),
        )
    )

    create_response = client.post(
        "/sessions",
        files={
            "ebook": ("sample.txt", b"Hello world", "text/plain"),
            "audio": ("sample.mp3", b"fake-audio", "audio/mpeg"),
        },
    )

    payload_response = client.get(f"/sessions/{create_response.json()['session_id']}")

    assert payload_response.json() == {
        "audio_url": "/sessions/session-1/audio",
        "blocks": [
            {"index": 0, "text": "Hello world", "word_indexes": [0, 1]},
        ],
        "coverage": 1.0,
        "session_id": "session-1",
        "status": "ready",
        "words": [
            {
                "block_index": 0,
                "end_ms": 300,
                "index": 0,
                "normalized": "hello",
                "start_ms": 0,
                "text": "Hello",
            },
            {
                "block_index": 0,
                "end_ms": 640,
                "index": 1,
                "normalized": "world",
                "start_ms": 301,
                "text": "world",
            },
        ],
    }


def test_create_chapter_session_returns_matching_payload_for_sorted_mp3_files(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-02.mp3", b"audio-2", "audio/mpeg")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
        ],
    )

    assert response.json() == {
        "session_id": "session-1",
        "status": "matching",
    }

    payload_response = client.get("/chapter-sessions/session-1")

    assert payload_response.json() == {
        "session_id": "session-1",
        "status": "matching",
        "ebook_chapters": [
            {
                "index": 0,
                "title": "Chapter 1",
                "block_indexes": [0],
                "word_indexes": [0, 1],
                "suggested_audio_chapter_index": 0,
            },
            {
                "index": 1,
                "title": "Chapter 2",
                "block_indexes": [1],
                "word_indexes": [2, 3],
                "suggested_audio_chapter_index": 1,
            },
        ],
        "audio_chapters": [
            {
                "index": 0,
                "title": "chapter-01",
                "source_name": "chapter-01.mp3",
                "start_ms": None,
                "end_ms": None,
            },
            {
                "index": 1,
                "title": "chapter-02",
                "source_name": "chapter-02.mp3",
                "start_ms": None,
                "end_ms": None,
            },
        ],
    }


def test_create_chapter_session_reads_m4b_chapters(tmp_path, monkeypatch):
    def fake_discover_m4b_chapters(audio_path):
        assert audio_path.name == "sample.m4b"
        return [
            {"title": "Chapter One", "start_ms": 0, "end_ms": 120000},
            {"title": "Chapter Two", "start_ms": 120000, "end_ms": 240000},
        ]

    monkeypatch.setattr(services, "discover_m4b_chapters", fake_discover_m4b_chapters)

    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("sample.m4b", b"audio-book", "audio/mp4")),
        ],
    )

    assert response.json() == {
        "session_id": "session-1",
        "status": "matching",
    }

    payload_response = client.get("/chapter-sessions/session-1")

    assert payload_response.json() == {
        "session_id": "session-1",
        "status": "matching",
        "ebook_chapters": [
            {
                "index": 0,
                "title": "Chapter 1",
                "block_indexes": [0],
                "word_indexes": [0, 1],
                "suggested_audio_chapter_index": 0,
            },
            {
                "index": 1,
                "title": "Chapter 2",
                "block_indexes": [1],
                "word_indexes": [2, 3],
                "suggested_audio_chapter_index": 1,
            },
        ],
        "audio_chapters": [
            {
                "index": 0,
                "title": "Chapter One",
                "source_name": "sample.m4b",
                "start_ms": 0,
                "end_ms": 120000,
            },
            {
                "index": 1,
                "title": "Chapter Two",
                "source_name": "sample.m4b",
                "start_ms": 120000,
                "end_ms": 240000,
            },
        ],
    }


def test_create_chapter_session_suggests_fuzzy_chapter_matches(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    client.post(
        "/chapter-sessions",
        files=[
            (
                "ebook",
                (
                    "sample.txt",
                    b"Chapter Twenty-Four\nOne two\n\nChapter Twenty-Five\nThree four\n",
                    "text/plain",
                ),
            ),
            ("audio_files", ("chapter-25.mp3", b"audio-25", "audio/mpeg")),
            ("audio_files", ("chapter-24.mp3", b"audio-24", "audio/mpeg")),
        ],
    )

    payload_response = client.get("/chapter-sessions/session-1")

    assert payload_response.json() == {
        "session_id": "session-1",
        "status": "matching",
        "ebook_chapters": [
            {
                "index": 0,
                "title": "Chapter Twenty-Four",
                "block_indexes": [0],
                "word_indexes": [0, 1],
                "suggested_audio_chapter_index": 0,
            },
            {
                "index": 1,
                "title": "Chapter Twenty-Five",
                "block_indexes": [1],
                "word_indexes": [2, 3],
                "suggested_audio_chapter_index": 1,
            },
        ],
        "audio_chapters": [
            {
                "index": 0,
                "title": "chapter-24",
                "source_name": "chapter-24.mp3",
                "start_ms": None,
                "end_ms": None,
            },
            {
                "index": 1,
                "title": "chapter-25",
                "source_name": "chapter-25.mp3",
                "start_ms": None,
                "end_ms": None,
            },
        ],
    }


def test_submit_incomplete_chapter_mapping_is_rejected(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
            ("audio_files", ("chapter-02.mp3", b"audio-2", "audio/mpeg")),
        ],
    )

    response = client.post(
        "/chapter-sessions/session-1/mapping",
        json={
            "matches": [
                {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            ]
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Missing matches for ebook chapters: [1]"}


def test_submit_complete_chapter_mapping_starts_processing(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
            ("audio_files", ("chapter-02.mp3", b"audio-2", "audio/mpeg")),
        ],
    )

    response = client.post(
        "/chapter-sessions/session-1/mapping",
        json={
            "matches": [
                {"ebook_chapter_index": 0, "audio_chapter_index": 0},
                {"ebook_chapter_index": 1, "audio_chapter_index": 1},
            ]
        },
    )

    assert response.json() == {
        "session_id": "session-1",
        "status": "processing",
    }

    payload_response = client.get("/chapter-sessions/session-1")

    assert payload_response.json() == {
        "session_id": "session-1",
        "status": "processing",
        "ebook_chapters": [
            {
                "index": 0,
                "title": "Chapter 1",
                "block_indexes": [0],
                "word_indexes": [0, 1],
                "suggested_audio_chapter_index": 0,
            },
            {
                "index": 1,
                "title": "Chapter 2",
                "block_indexes": [1],
                "word_indexes": [2, 3],
                "suggested_audio_chapter_index": 1,
            },
        ],
        "audio_chapters": [
            {
                "index": 0,
                "title": "chapter-01",
                "source_name": "chapter-01.mp3",
                "start_ms": None,
                "end_ms": None,
            },
            {
                "index": 1,
                "title": "chapter-02",
                "source_name": "chapter-02.mp3",
                "start_ms": None,
                "end_ms": None,
            },
        ],
        "chapter_mappings": [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": 1},
        ],
        "chapter_statuses": [
            {
                "ebook_chapter_index": 0,
                "audio_chapter_index": 0,
                "status": "pending",
                "title": "Chapter 1",
            },
            {
                "ebook_chapter_index": 1,
                "audio_chapter_index": 1,
                "status": "pending",
                "title": "Chapter 2",
            },
        ],
    }


def test_submit_chapter_mapping_accepts_skipped_chapters(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
        ],
    )

    response = client.post(
        "/chapter-sessions/session-1/mapping",
        json={
            "matches": [
                {"ebook_chapter_index": 0, "audio_chapter_index": 0},
                {"ebook_chapter_index": 1, "audio_chapter_index": None},
            ]
        },
    )

    assert response.json() == {
        "session_id": "session-1",
        "status": "processing",
    }

    payload_response = client.get("/chapter-sessions/session-1")

    assert payload_response.json() == {
        "session_id": "session-1",
        "status": "processing",
        "ebook_chapters": [
            {
                "index": 0,
                "title": "Chapter 1",
                "block_indexes": [0],
                "word_indexes": [0, 1],
                "suggested_audio_chapter_index": 0,
            },
            {
                "index": 1,
                "title": "Chapter 2",
                "block_indexes": [1],
                "word_indexes": [2, 3],
                "suggested_audio_chapter_index": None,
            },
        ],
        "audio_chapters": [
            {
                "index": 0,
                "title": "chapter-01",
                "source_name": "chapter-01.mp3",
                "start_ms": None,
                "end_ms": None,
            },
        ],
        "chapter_mappings": [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": None},
        ],
        "chapter_statuses": [
            {
                "ebook_chapter_index": 0,
                "audio_chapter_index": 0,
                "status": "pending",
                "title": "Chapter 1",
            },
            {
                "ebook_chapter_index": 1,
                "audio_chapter_index": None,
                "status": "skipped",
                "title": "Chapter 2",
            },
        ],
    }


def test_process_next_pending_chapter_updates_completed_chapters_incrementally(tmp_path):
    service = services.SessionService(tmp_path / "data", FakeChapterTranscriber())

    service.create_chapter_session(
        ebook_name="sample.txt",
        ebook_content=b"Chapter 1\nOne two\n\nChapter 2\nThree four\n",
        audio_files=[
            ("chapter-01.mp3", b"audio-1"),
            ("chapter-02.mp3", b"audio-2"),
        ],
    )
    service.submit_chapter_mapping(
        "session-1",
        [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": 1},
        ],
    )

    service.process_next_pending_chapter("session-1")

    after_first = service.read_session("session-1")

    assert after_first == {
        "session_id": "session-1",
        "status": "processing",
        "ebook_chapters": [
            {
                "index": 0,
                "title": "Chapter 1",
                "block_indexes": [0],
                "word_indexes": [0, 1],
                "suggested_audio_chapter_index": 0,
            },
            {
                "index": 1,
                "title": "Chapter 2",
                "block_indexes": [1],
                "word_indexes": [2, 3],
                "suggested_audio_chapter_index": 1,
            },
        ],
        "audio_chapters": [
            {
                "index": 0,
                "title": "chapter-01",
                "source_name": "chapter-01.mp3",
                "start_ms": None,
                "end_ms": None,
            },
            {
                "index": 1,
                "title": "chapter-02",
                "source_name": "chapter-02.mp3",
                "start_ms": None,
                "end_ms": None,
            },
        ],
        "chapter_mappings": [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": 1},
        ],
        "chapter_statuses": [
            {
                "ebook_chapter_index": 0,
                "audio_chapter_index": 0,
                "status": "ready",
                "title": "Chapter 1",
            },
            {
                "ebook_chapter_index": 1,
                "audio_chapter_index": 1,
                "status": "pending",
                "title": "Chapter 2",
            },
        ],
        "completed_chapters": [
            {
                "chapter_index": 0,
                "title": "Chapter 1",
                "audio_url": "/chapter-sessions/session-1/audio/chapter-01.mp3",
                "blocks": [
                    {"index": 0, "text": "One two", "word_indexes": [0, 1]},
                ],
                "words": [
                    {
                        "index": 0,
                        "block_index": 0,
                        "text": "One",
                        "normalized": "one",
                        "start_ms": 0,
                        "end_ms": 300,
                    },
                    {
                        "index": 1,
                        "block_index": 0,
                        "text": "two",
                        "normalized": "two",
                        "start_ms": 301,
                        "end_ms": 640,
                    },
                ],
                "coverage": 1.0,
                "text_source": "ebook",
            }
        ],
    }

    service.process_next_pending_chapter("session-1")

    after_second = service.read_session("session-1")

    assert after_second["status"] == "ready"
    assert after_second["chapter_statuses"] == [
        {"ebook_chapter_index": 0, "audio_chapter_index": 0, "status": "ready", "title": "Chapter 1"},
        {"ebook_chapter_index": 1, "audio_chapter_index": 1, "status": "ready", "title": "Chapter 2"},
    ]
    assert after_second["completed_chapters"] == [
        {
            "chapter_index": 0,
            "title": "Chapter 1",
            "audio_url": "/chapter-sessions/session-1/audio/chapter-01.mp3",
            "blocks": [{"index": 0, "text": "One two", "word_indexes": [0, 1]}],
            "words": [
                {"index": 0, "block_index": 0, "text": "One", "normalized": "one", "start_ms": 0, "end_ms": 300},
                {"index": 1, "block_index": 0, "text": "two", "normalized": "two", "start_ms": 301, "end_ms": 640},
            ],
            "coverage": 1.0,
            "text_source": "ebook",
        },
        {
            "chapter_index": 1,
            "title": "Chapter 2",
            "audio_url": "/chapter-sessions/session-1/audio/chapter-02.mp3",
            "blocks": [{"index": 1, "text": "Three four", "word_indexes": [2, 3]}],
            "words": [
                {"index": 2, "block_index": 1, "text": "Three", "normalized": "three", "start_ms": 0, "end_ms": 300},
                {"index": 3, "block_index": 1, "text": "four", "normalized": "four", "start_ms": 301, "end_ms": 640},
            ],
            "coverage": 1.0,
            "text_source": "ebook",
        },
    ]


def test_process_next_pending_chapter_finishes_when_remaining_chapters_are_skipped(tmp_path):
    service = services.SessionService(tmp_path / "data", FakeChapterTranscriber())

    service.create_chapter_session(
        ebook_name="sample.txt",
        ebook_content=b"Chapter 1\nOne two\n\nChapter 2\nThree four\n",
        audio_files=[
            ("chapter-01.mp3", b"audio-1"),
        ],
    )
    service.submit_chapter_mapping(
        "session-1",
        [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": None},
        ],
    )

    service.process_next_pending_chapter("session-1")

    assert service.read_session("session-1") == {
        "session_id": "session-1",
        "status": "ready",
        "ebook_chapters": [
            {
                "index": 0,
                "title": "Chapter 1",
                "block_indexes": [0],
                "word_indexes": [0, 1],
                "suggested_audio_chapter_index": 0,
            },
            {
                "index": 1,
                "title": "Chapter 2",
                "block_indexes": [1],
                "word_indexes": [2, 3],
                "suggested_audio_chapter_index": None,
            },
        ],
        "audio_chapters": [
            {
                "index": 0,
                "title": "chapter-01",
                "source_name": "chapter-01.mp3",
                "start_ms": None,
                "end_ms": None,
            },
        ],
        "chapter_mappings": [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": None},
        ],
        "chapter_statuses": [
            {
                "ebook_chapter_index": 0,
                "audio_chapter_index": 0,
                "status": "ready",
                "title": "Chapter 1",
            },
            {
                "ebook_chapter_index": 1,
                "audio_chapter_index": None,
                "status": "skipped",
                "title": "Chapter 2",
            },
        ],
        "completed_chapters": [
            {
                "chapter_index": 0,
                "title": "Chapter 1",
                "audio_url": "/chapter-sessions/session-1/audio/chapter-01.mp3",
                "blocks": [{"index": 0, "text": "One two", "word_indexes": [0, 1]}],
                "words": [
                    {
                        "index": 0,
                        "block_index": 0,
                        "text": "One",
                        "normalized": "one",
                        "start_ms": 0,
                        "end_ms": 300,
                    },
                    {
                        "index": 1,
                        "block_index": 0,
                        "text": "two",
                        "normalized": "two",
                        "start_ms": 301,
                        "end_ms": 640,
                    },
                ],
                "coverage": 1.0,
                "text_source": "ebook",
            }
        ],
    }


def test_process_next_pending_chapter_falls_back_to_transcript_text_when_alignment_fails(tmp_path):
    service = services.SessionService(tmp_path / "data", FakeTranscriptFallbackTranscriber())

    service.create_chapter_session(
        ebook_name="sample.txt",
        ebook_content=b"Chapter 1\nOne two\n",
        audio_files=[
            ("chapter-01.mp3", b"audio-1"),
        ],
    )
    service.submit_chapter_mapping(
        "session-1",
        [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
        ],
    )

    service.process_next_pending_chapter("session-1")

    assert service.read_session("session-1") == {
        "session_id": "session-1",
        "status": "ready",
        "ebook_chapters": [
            {
                "index": 0,
                "title": "Chapter 1",
                "block_indexes": [0],
                "word_indexes": [0, 1],
                "suggested_audio_chapter_index": 0,
            },
        ],
        "audio_chapters": [
            {
                "index": 0,
                "title": "chapter-01",
                "source_name": "chapter-01.mp3",
                "start_ms": None,
                "end_ms": None,
            },
        ],
        "chapter_mappings": [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
        ],
        "chapter_statuses": [
            {
                "ebook_chapter_index": 0,
                "audio_chapter_index": 0,
                "status": "transcript-only",
                "title": "Chapter 1",
                "reason": "Alignment coverage 0.00 is below required threshold 0.60",
            },
        ],
        "completed_chapters": [
            {
                "chapter_index": 0,
                "title": "Chapter 1",
                "audio_url": "/chapter-sessions/session-1/audio/chapter-01.mp3",
                "blocks": [{"index": 0, "text": "Alpha beta", "word_indexes": [0, 1]}],
                "words": [
                    {
                        "index": 0,
                        "block_index": 0,
                        "text": "Alpha",
                        "normalized": "alpha",
                        "start_ms": 0,
                        "end_ms": 300,
                    },
                    {
                        "index": 1,
                        "block_index": 0,
                        "text": "beta",
                        "normalized": "beta",
                        "start_ms": 301,
                        "end_ms": 640,
                    },
                ],
                "coverage": None,
                "text_source": "transcript",
            }
        ],
    }


def test_chapter_session_exposes_completed_chapters_and_audio_route(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=FakeChapterTranscriber(),
        )
    )

    client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
            ("audio_files", ("chapter-02.mp3", b"audio-2", "audio/mpeg")),
        ],
    )
    client.post(
        "/chapter-sessions/session-1/mapping",
        json={
            "matches": [
                {"ebook_chapter_index": 0, "audio_chapter_index": 0},
                {"ebook_chapter_index": 1, "audio_chapter_index": 1},
            ]
        },
    )

    session_response = client.get("/chapter-sessions/session-1")
    chapter_audio_response = client.get("/chapter-sessions/session-1/audio/chapter-01.mp3")

    assert session_response.json() == {
        "session_id": "session-1",
        "status": "ready",
        "ebook_chapters": [
            {
                "index": 0,
                "title": "Chapter 1",
                "block_indexes": [0],
                "word_indexes": [0, 1],
                "suggested_audio_chapter_index": 0,
            },
            {
                "index": 1,
                "title": "Chapter 2",
                "block_indexes": [1],
                "word_indexes": [2, 3],
                "suggested_audio_chapter_index": 1,
            },
        ],
        "audio_chapters": [
            {
                "index": 0,
                "title": "chapter-01",
                "source_name": "chapter-01.mp3",
                "start_ms": None,
                "end_ms": None,
            },
            {
                "index": 1,
                "title": "chapter-02",
                "source_name": "chapter-02.mp3",
                "start_ms": None,
                "end_ms": None,
            },
        ],
        "chapter_mappings": [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": 1},
        ],
        "chapter_statuses": [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0, "status": "ready", "title": "Chapter 1"},
            {"ebook_chapter_index": 1, "audio_chapter_index": 1, "status": "ready", "title": "Chapter 2"},
        ],
        "completed_chapters": [
            {
                "chapter_index": 0,
                "title": "Chapter 1",
                "audio_url": "/chapter-sessions/session-1/audio/chapter-01.mp3",
                "blocks": [{"index": 0, "text": "One two", "word_indexes": [0, 1]}],
                "words": [
                    {"index": 0, "block_index": 0, "text": "One", "normalized": "one", "start_ms": 0, "end_ms": 300},
                    {"index": 1, "block_index": 0, "text": "two", "normalized": "two", "start_ms": 301, "end_ms": 640},
                ],
                "coverage": 1.0,
                "text_source": "ebook",
            },
            {
                "chapter_index": 1,
                "title": "Chapter 2",
                "audio_url": "/chapter-sessions/session-1/audio/chapter-02.mp3",
                "blocks": [{"index": 1, "text": "Three four", "word_indexes": [2, 3]}],
                "words": [
                    {"index": 2, "block_index": 1, "text": "Three", "normalized": "three", "start_ms": 0, "end_ms": 300},
                    {"index": 3, "block_index": 1, "text": "four", "normalized": "four", "start_ms": 301, "end_ms": 640},
                ],
                "coverage": 1.0,
                "text_source": "ebook",
            },
        ],
    }
    assert chapter_audio_response.status_code == 200
    assert chapter_audio_response.content == b"audio-1"
