from fastapi.testclient import TestClient
import shutil

from app.config import Settings
from app.main import create_app
from app.alignment import TimedWord
import app.services as services
import app.services.session as session_module


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

    payload = response.json()
    assert payload["status"] == "processing"
    assert payload["session_id"].startswith("session-")


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

    create_response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
        ],
    )
    session_id = create_response.json()["session_id"]
    shutil.rmtree(data_dir / "sessions" / session_id)

    response = client.get(f"/chapter-sessions/{session_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Session not found: {session_id}"}


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
    session_id = create_response.json()["session_id"]

    payload_response = client.get(f"/sessions/{session_id}")

    assert payload_response.json() == {
        "audio_url": f"/sessions/{session_id}/audio",
        "blocks": [
            {"index": 0, "text": "Hello world", "word_indexes": [0, 1]},
        ],
        "coverage": 1.0,
        "session_id": session_id,
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

    assert response.json()["status"] == "matching"
    session_id = response.json()["session_id"]

    payload_response = client.get(f"/chapter-sessions/{session_id}")

    assert payload_response.json() == {
        "session_id": session_id,
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

    monkeypatch.setattr(session_module, "discover_m4b_chapters", fake_discover_m4b_chapters)

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

    session_id = response.json()["session_id"]

    payload_response = client.get(f"/chapter-sessions/{session_id}")

    assert payload_response.json() == {
        "session_id": session_id,
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

    response = client.post(
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

    session_id = response.json()["session_id"]

    payload_response = client.get(f"/chapter-sessions/{session_id}")

    assert payload_response.json() == {
        "session_id": session_id,
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

    create_response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
            ("audio_files", ("chapter-02.mp3", b"audio-2", "audio/mpeg")),
        ],
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/chapter-sessions/{session_id}/mapping",
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

    create_response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
            ("audio_files", ("chapter-02.mp3", b"audio-2", "audio/mpeg")),
        ],
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/chapter-sessions/{session_id}/mapping",
        json={
            "matches": [
                {"ebook_chapter_index": 0, "audio_chapter_index": 0},
                {"ebook_chapter_index": 1, "audio_chapter_index": 1},
            ]
        },
    )

    assert response.json() == {
        "session_id": session_id,
        "status": "processing",
    }

    payload_response = client.get(f"/chapter-sessions/{session_id}")

    assert payload_response.json() == {
        "session_id": session_id,
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

    create_response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
        ],
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/chapter-sessions/{session_id}/mapping",
        json={
            "matches": [
                {"ebook_chapter_index": 0, "audio_chapter_index": 0},
                {"ebook_chapter_index": 1, "audio_chapter_index": None},
            ]
        },
    )

    assert response.json() == {
        "session_id": session_id,
        "status": "processing",
    }

    payload_response = client.get(f"/chapter-sessions/{session_id}")

    assert payload_response.json() == {
        "session_id": session_id,
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
    session_id = service.list_sessions()[0]["session_id"]
    service.submit_chapter_mapping(
        session_id,
        [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": 1},
        ],
    )

    service.process_next_pending_chapter(session_id)

    after_first = service.read_session(session_id)

    assert after_first == {
        "session_id": session_id,
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
                "audio_url": f"/chapter-sessions/{session_id}/audio/chapter-01.mp3",
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

    service.process_next_pending_chapter(session_id)

    after_second = service.read_session(session_id)

    assert after_second["status"] == "ready"
    assert after_second["chapter_statuses"] == [
        {"ebook_chapter_index": 0, "audio_chapter_index": 0, "status": "ready", "title": "Chapter 1"},
        {"ebook_chapter_index": 1, "audio_chapter_index": 1, "status": "ready", "title": "Chapter 2"},
    ]
    assert after_second["completed_chapters"] == [
        {
            "chapter_index": 0,
            "title": "Chapter 1",
            "audio_url": f"/chapter-sessions/{session_id}/audio/chapter-01.mp3",
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
            "audio_url": f"/chapter-sessions/{session_id}/audio/chapter-02.mp3",
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
    session_id = service.list_sessions()[0]["session_id"]
    service.submit_chapter_mapping(
        session_id,
        [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": None},
        ],
    )

    service.process_next_pending_chapter(session_id)

    assert service.read_session(session_id) == {
        "session_id": session_id,
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
                "audio_url": f"/chapter-sessions/{session_id}/audio/chapter-01.mp3",
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
    session_id = service.list_sessions()[0]["session_id"]
    service.submit_chapter_mapping(
        session_id,
        [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
        ],
    )

    service.process_next_pending_chapter(session_id)

    assert service.read_session(session_id) == {
        "session_id": session_id,
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
                "audio_url": f"/chapter-sessions/{session_id}/audio/chapter-01.mp3",
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

    create_response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
            ("audio_files", ("chapter-02.mp3", b"audio-2", "audio/mpeg")),
        ],
    )
    session_id = create_response.json()["session_id"]
    client.post(
        f"/chapter-sessions/{session_id}/mapping",
        json={
            "matches": [
                {"ebook_chapter_index": 0, "audio_chapter_index": 0},
                {"ebook_chapter_index": 1, "audio_chapter_index": 1},
            ]
        },
    )

    session_response = client.get(f"/chapter-sessions/{session_id}")
    chapter_audio_response = client.get(f"/chapter-sessions/{session_id}/audio/chapter-01.mp3")

    assert session_response.json() == {
        "session_id": session_id,
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
                "audio_url": f"/chapter-sessions/{session_id}/audio/chapter-01.mp3",
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
                "audio_url": f"/chapter-sessions/{session_id}/audio/chapter-02.mp3",
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


def test_list_sessions_returns_created_sessions(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    response = client.get("/sessions")
    assert response.json() == {"sessions": []}

    client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
        ],
    )

    response = client.get("/sessions")
    sessions = response.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["status"] == "matching"
    assert sessions[0]["ebook_chapter_count"] == 1
    assert sessions[0]["title"] == "sample"


def test_delete_session_removes_it(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    create_response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
        ],
    )
    session_id = create_response.json()["session_id"]

    delete_response = client.delete(f"/sessions/{session_id}")
    assert delete_response.status_code == 200

    list_response = client.get("/sessions")
    assert list_response.json() == {"sessions": []}

    get_response = client.get(f"/chapter-sessions/{session_id}")
    assert get_response.status_code == 404


def test_retry_failed_chapter_resets_status(tmp_path):
    service = services.SessionService(tmp_path / "data", FakeTranscriptFallbackTranscriber())

    service.create_chapter_session(
        ebook_name="sample.txt",
        ebook_content=b"Chapter 1\nOne two\n",
        audio_files=[
            ("chapter-01.mp3", b"audio-1"),
        ],
    )
    session_id = service.list_sessions()[0]["session_id"]
    service.submit_chapter_mapping(
        session_id,
        [{"ebook_chapter_index": 0, "audio_chapter_index": 0}],
    )
    service.process_next_pending_chapter(session_id)

    payload = service.read_session(session_id)
    assert payload["chapter_statuses"][0]["status"] == "transcript-only"

    service.retry_chapter(session_id, 0)

    payload = service.read_session(session_id)
    assert payload["chapter_statuses"][0]["status"] == "pending"
    assert payload["completed_chapters"] == []


def test_retry_endpoint_returns_400_for_skipped_chapters(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    create_response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
        ],
    )
    session_id = create_response.json()["session_id"]
    client.post(
        f"/chapter-sessions/{session_id}/mapping",
        json={
            "matches": [
                {"ebook_chapter_index": 0, "audio_chapter_index": 0},
                {"ebook_chapter_index": 1, "audio_chapter_index": None},
            ]
        },
    )

    # Chapter 1 is skipped (audio_chapter_index is None)
    response = client.post(f"/sessions/{session_id}/retry-chapter/1")
    assert response.status_code == 400


def test_retry_endpoint_returns_404_for_unknown_session(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    response = client.post("/sessions/nonexistent/retry-chapter/0")
    assert response.status_code == 404


def test_recover_stuck_sessions_resets_processing_to_pending(tmp_path):
    service = services.SessionService(tmp_path / "data", FakeChapterTranscriber())

    service.create_chapter_session(
        ebook_name="sample.txt",
        ebook_content=b"Chapter 1\nOne two\n\nChapter 2\nThree four\n",
        audio_files=[
            ("chapter-01.mp3", b"audio-1"),
            ("chapter-02.mp3", b"audio-2"),
        ],
    )
    session_id = service.list_sessions()[0]["session_id"]
    service.submit_chapter_mapping(
        session_id,
        [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": 1},
        ],
    )
    # Simulate a crash: mark a chapter as "processing" mid-flight.
    payload = service.read_session(session_id)
    payload["chapter_statuses"][0]["status"] = "processing"
    service._write_session_locked(service.sessions_dir / session_id, payload)

    reset_count = service.recover_stuck_sessions()

    assert reset_count == 1
    recovered = service.read_session(session_id)
    assert recovered["chapter_statuses"][0]["status"] == "pending"
    assert recovered["status"] == "processing"


def test_recover_stuck_sessions_handles_missing_directory(tmp_path):
    service = services.SessionService(tmp_path / "does-not-exist", None)

    assert service.recover_stuck_sessions() == 0


def test_retry_chapter_accepts_processing_status(tmp_path):
    service = services.SessionService(tmp_path / "data", FakeChapterTranscriber())

    service.create_chapter_session(
        ebook_name="sample.txt",
        ebook_content=b"Chapter 1\nOne two\n",
        audio_files=[
            ("chapter-01.mp3", b"audio-1"),
        ],
    )
    session_id = service.list_sessions()[0]["session_id"]
    service.submit_chapter_mapping(
        session_id,
        [{"ebook_chapter_index": 0, "audio_chapter_index": 0}],
    )
    # Simulate a stuck "processing" chapter.
    payload = service.read_session(session_id)
    payload["chapter_statuses"][0]["status"] = "processing"
    service._write_session_locked(service.sessions_dir / session_id, payload)

    service.retry_chapter(session_id, 0)

    payload = service.read_session(session_id)
    assert payload["chapter_statuses"][0]["status"] == "pending"


def test_delete_endpoint_returns_404_for_unknown_session(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    response = client.delete("/sessions/nonexistent")
    assert response.status_code == 404


def test_get_session_returns_404_for_unknown_session(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    response = client.get("/chapter-sessions/nonexistent")
    assert response.status_code == 404


def test_session_events_sse_stream_returns_404_for_unknown_session(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    response = client.get("/sessions/nonexistent/events")
    assert response.status_code == 404


def test_create_chapter_session_rejects_unsupported_ebook_format(tmp_path):
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
            ("ebook", ("sample.pdf", b"not an ebook", "application/pdf")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
        ],
    )
    assert response.status_code == 400


def test_create_chapter_session_rejects_mixed_audio_formats(tmp_path):
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
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
            ("audio_files", ("chapter-02.m4b", b"audio-2", "audio/mp4")),
        ],
    )
    assert response.status_code == 400


def test_submit_chapter_mapping_rejects_duplicate_audio_matches(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    create_response = client.post(
        "/chapter-sessions",
        files=[
            ("ebook", ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")),
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
            ("audio_files", ("chapter-02.mp3", b"audio-2", "audio/mpeg")),
        ],
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/chapter-sessions/{session_id}/mapping",
        json={
            "matches": [
                {"ebook_chapter_index": 0, "audio_chapter_index": 0},
                {"ebook_chapter_index": 1, "audio_chapter_index": 0},
            ]
        },
    )
    assert response.status_code == 400
    assert "once" in response.json()["detail"]


def test_list_sessions_returns_empty_when_no_sessions(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    response = client.get("/sessions")
    assert response.json() == {"sessions": []}


def test_process_chapter_session_parallel_processes_all_pending(tmp_path):
    service = services.SessionService(tmp_path / "data", FakeChapterTranscriber())

    service.create_chapter_session(
        ebook_name="sample.txt",
        ebook_content=b"Chapter 1\nOne two\n\nChapter 2\nThree four\n",
        audio_files=[
            ("chapter-01.mp3", b"audio-1"),
            ("chapter-02.mp3", b"audio-2"),
        ],
    )
    session_id = service.list_sessions()[0]["session_id"]
    service.submit_chapter_mapping(
        session_id,
        [
            {"ebook_chapter_index": 0, "audio_chapter_index": 0},
            {"ebook_chapter_index": 1, "audio_chapter_index": 1},
        ],
    )

    service.process_chapter_session(session_id, parallel=True)

    payload = service.read_session(session_id)
    assert payload["status"] == "ready"
    assert len(payload["completed_chapters"]) == 2
    assert all(
        status["status"] == "ready" for status in payload["chapter_statuses"]
    )


def test_session_service_subscribe_receives_notifications(tmp_path):
    service = services.SessionService(tmp_path / "data", None)

    notifications = []
    unsubscribe = service.subscribe("test-session", lambda sid: notifications.append(sid))

    service._notify("test-session")
    service._notify("test-session")
    assert len(notifications) == 2

    unsubscribe()
    service._notify("test-session")
    assert len(notifications) == 2  # No new notifications after unsubscribe


def test_session_service_subscribe_swallows_callback_errors(tmp_path):
    service = services.SessionService(tmp_path / "data", None)

    def bad_callback(sid):
        raise RuntimeError("boom")

    service.subscribe("test-session", bad_callback)
    # Should not raise
    service._notify("test-session")


def test_create_session_from_ebook_returns_awaiting_audio_status(tmp_path):
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
        "/sessions/ebook",
        files={"ebook": ("sample.txt", b"Chapter 1\nOne two\n", "text/plain")},
    )

    payload = response.json()
    assert payload["status"] == "awaiting_audio"
    assert payload["session_id"].startswith("session-")
    assert payload["audio_chapters"] is None
    assert len(payload["ebook_chapters"]) == 1


def test_add_audio_to_session_rejects_mixed_formats(tmp_path):
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    # First upload an ebook
    ebook_response = client.post(
        "/sessions/ebook",
        files={"ebook": ("sample.txt", b"Chapter 1\nOne two\n", "text/plain")},
    )
    session_id = ebook_response.json()["session_id"]

    # Try to upload mixed audio formats
    response = client.post(
        f"/sessions/{session_id}/audio",
        files=[
            ("audio_files", ("chapter-01.mp3", b"audio-1", "audio/mpeg")),
            ("audio_files", ("chapter-02.m4b", b"audio-2", "audio/mp4")),
        ],
    )
    assert response.status_code == 400


def test_audio_upload_websocket_accepts_binary_chunks_and_eof(tmp_path):
    """WebSocket audio upload should receive binary chunks and finalize on text EOF."""
    client = TestClient(
        create_app(
            Settings(
                project_root=tmp_path,
                data_dir=tmp_path / "data",
            ),
            transcriber=None,
        )
    )

    ebook_response = client.post(
        "/sessions/ebook",
        files={"ebook": ("sample.txt", b"Chapter 1\nOne two\n\nChapter 2\nThree four\n", "text/plain")},
    )
    session_id = ebook_response.json()["session_id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}/audio-upload") as ws:
        ws.send_json({"type": "start", "filename": "chapter-01.mp3", "size": 12})
        ws.send_bytes(b"fake-audio-1")
        ws.send_text("__EOF__")
        # Drain progress messages until done/error.
        msg = ws.receive_json()
        while msg["type"] == "progress":
            msg = ws.receive_json()
        assert msg["type"] == "done"
        assert "payload" in msg
        assert msg["payload"]["session_id"] == session_id
        assert msg["payload"]["audio_chapters"][0]["source_name"] == "chapter-01.mp3"


def test_settings_env_vars_override_defaults(monkeypatch, tmp_path):
    """Settings should pick up BOOKAMINE_* env vars."""
    monkeypatch.setenv("BOOKAMINE_DATA_DIR", str(tmp_path / "custom-data"))
    monkeypatch.setenv("BOOKAMINE_ALIGNMENT_THRESHOLD", "0.75")
    monkeypatch.setenv("BOOKAMINE_ALIGNMENT_WINDOW", "32")
    monkeypatch.setenv("BOOKAMINE_MAX_WORKERS", "2")
    monkeypatch.setenv("BOOKAMINE_SSE_PING_INTERVAL", "30")

    from app.config import load_settings

    settings = load_settings()
    assert settings.data_dir == (tmp_path / "custom-data").resolve()
    assert settings.alignment_threshold == 0.75
    assert settings.alignment_window == 32
    assert settings.max_workers == 2
    assert settings.sse_ping_interval == 30.0


def test_settings_env_vars_with_invalid_values_fall_back(monkeypatch):
    """Invalid env var values should fall back to defaults rather than crash."""
    monkeypatch.setenv("BOOKAMINE_ALIGNMENT_THRESHOLD", "not-a-number")
    monkeypatch.setenv("BOOKAMINE_ALIGNMENT_WINDOW", "also-not-a-number")

    from app.config import load_settings

    settings = load_settings()
    assert settings.alignment_threshold == 0.6
    assert settings.alignment_window == 24


def test_session_service_uses_alignment_settings(tmp_path):
    """SessionService should pass alignment settings through to align_words."""
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        alignment_threshold=0.42,
        alignment_window=99,
        alignment_backtrack=7,
        alignment_match_score=0.77,
    )
    service = services.SessionService(tmp_path / "data", None, settings=settings)
    kwargs = service._alignment_kwargs
    assert kwargs == {
        "threshold": 0.42,
        "window": 99,
        "backtrack": 7,
        "match_score": 0.77,
    }


def test_session_service_alignment_kwargs_empty_without_settings(tmp_path):
    """Without settings, alignment kwargs should be empty (use defaults)."""
    service = services.SessionService(tmp_path / "data", None)
    assert service._alignment_kwargs == {}


def test_write_session_locked_no_ops_when_session_dir_deleted(tmp_path):
    """_write_session_locked should not raise if the session directory was deleted."""
    service = services.SessionService(tmp_path / "data", None)
    ghost_dir = tmp_path / "data" / "sessions" / "session-ghost"
    # Directory doesn't exist — write should silently no-op.
    service._write_session_locked(ghost_dir, {"status": "ready"})
    assert not ghost_dir.exists()


def test_process_session_silently_aborts_when_session_deleted(tmp_path):
    """process_session should return cleanly if the session directory is gone."""
    service = services.SessionService(tmp_path / "data", None)
    # No session directory exists — should not raise.
    service.process_session("session-nonexistent")
    service.process_next_pending_chapter("session-nonexistent")
    service.process_single_chapter("session-nonexistent", 0, 0)
    service._process_chapter_session_parallel("session-nonexistent")
