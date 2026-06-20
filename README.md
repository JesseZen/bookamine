# Bookamine

TikTok destroys your brain. Bookamine destroys it slower.

A Self-hosted audiobook/ebook sync tool for doomscrolling!

## What It Does

- Imports one ebook (`.txt` or `.epub`) plus either one `.m4b` with embedded chapters or multiple chapter `.mp3` files
- Detects ebook chapters and audio chapters before processing starts
- Lets you match ebook chapters to audio chapters once, including skipping ebook-only chapters, then starts sequential chapter processing
- Transcribes completed chapter audio into timed words with a pluggable transcriber
- Aligns timed audiobook words back onto ebook chapter words, with transcript fallback when alignment coverage is too low
- Serves a browser reader where completed chapters support audio playback, word highlight, scrub, and click-to-seek

## Run Locally

1. Install `ffmpeg`
2. Install dependencies:

```bash
uv sync --extra dev --extra transcribe
```

3. Start the server:

```bash
uv run uvicorn app.main:app --reload
```

4. Open `http://127.0.0.1:8000`
5. Upload one ebook and either:
   - one `.m4b` audiobook with chapter metadata, or
   - multiple `.mp3` files where each file is one chapter
6. Match each ebook chapter to one audio chapter, or skip ebook-only chapters such as contents pages
7. Start processing and open completed chapters as they become ready

When a chapter aligns cleanly, the reader shows ebook text. When alignment coverage is too low, that chapter automatically falls back to `Transcript mode` and shows the transcribed audio text instead of failing the whole reading flow.

The default runtime transcriber uses the local `openai-whisper` package with the `base.en` model. Tests use a fake transcriber so the suite stays fast and deterministic.

## Manual Verification

1. Start the server with `uv run uvicorn app.main:app --reload`
2. Open `http://127.0.0.1:8000`
3. Upload one multi-chapter ebook and either one chaptered `.m4b` or multiple chapter `.mp3` files
4. Confirm the matching screen lists detected ebook and audio chapters, plus a `Skip` option for ebook-only chapters
5. Submit the chapter mapping and wait for the progress panel to move chapters from `pending` to `ready`, `transcript-only`, or `skipped`
6. Open the reader panel, switch chapters from the chapter buttons, and confirm each completed chapter shows either aligned ebook text or `Transcript mode` text plus its chapter audio URL

## Test

```bash
uv run pytest -v
```
