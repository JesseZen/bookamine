# Repository Guidelines

## Project Structure & Module Organization

Bookamine is a FastAPI application packaged from `app/`. Core modules include `main.py` for app creation, `models.py` for shared data shapes, `parsers.py` for ebook parsing, and `alignment.py` for word alignment. Route handlers are in `app/routes/`, services are in `app/services/`, browser assets are in `app/static/`, and Jinja templates are in `app/templates/`.

Tests live in `tests/`. Python tests use `test_*.py`; JavaScript module tests use `test_*.mjs`. Runtime uploads and generated session data belong under `data/`, which is ignored by git.

## Build, Test, and Development Commands

- `uv sync --extra dev --extra transcribe`: install Python dependencies, test tools, and optional local Whisper transcription support.
- `uv run uvicorn app.main:app --reload`: run the development server at `http://127.0.0.1:8000`.
- `uv run pytest -v`: run the Python test suite.
- `node --test tests/*.mjs`: run JavaScript unit tests for browser helper modules.
- `uv build`: build package artifacts with Hatchling.

Install `ffmpeg` locally before testing real audio imports or running manual end-to-end flows.

## Coding Style & Naming Conventions

Use Python 3.14+ syntax and keep modules typed where practical. Follow the existing style: 4-space indentation, small functions, dataclasses for immutable value objects, and explicit names such as `FakeChapterTranscriber`. Prefer `snake_case` for Python functions, variables, and modules.

For browser code, use ES modules in `app/static/*.mjs` when logic is testable outside the DOM. Keep DOM-heavy wiring in `reader.js`. Do not commit `.bak`, `__pycache__`, or generated `data/` contents.

## Testing Guidelines

Add Python tests beside related coverage in `tests/test_*.py` and use `tmp_path` for filesystem isolation. FastAPI endpoints should be exercised through `fastapi.testclient.TestClient`; transcription should use fake transcribers so tests stay deterministic and fast.

Add JavaScript tests in `tests/test_*.mjs` with `node:test` and `node:assert/strict`. Cover parsing, alignment, session state, and reader helper behavior when changing those areas.

## Commit & Pull Request Guidelines

Recent commits use short conventional-style subjects such as `init: bookamine 1.0.0.dev1` and `merge(app): sync local workspace`. Keep subjects imperative and scoped when useful, for example `fix(alignment): handle repeated transcript words`.

Pull requests should describe the behavior change, list test commands run, and note any manual verification for upload, matching, transcription, or reader playback flows. Include screenshots or short recordings for visible UI changes.

## Security & Configuration Tips

Treat uploaded books and audio as untrusted input. Keep secrets out of the repository, avoid committing runtime data from `data/`, and prefer dependency changes through `pyproject.toml` plus `uv.lock` updates.
