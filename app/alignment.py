"""Word-level alignment between ebook text and transcribed timed words.

The aligner walks the transcript in order, and for each timed word searches a
small forward window of ebook words for the best fuzzy match. A short backtrack
window lets the algorithm recover from transient mismatches (e.g. filler words
the narrator added) without losing sync for the rest of the chapter.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.models import ParsedWord


class AlignmentFailure(ValueError):
    pass


@dataclass(frozen=True)
class TimedWord:
    text: str
    normalized: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class AlignmentResult:
    coverage: float
    words: list[dict]


def align_words(
    ebook_words: list[ParsedWord],
    transcript_words: list[TimedWord],
    threshold: float = 0.6,
    window: int = 24,
    backtrack: int = 4,
    match_score: float = 0.85,
) -> AlignmentResult:
    aligned_words = [
        {
            "index": word.index,
            "block_index": word.block_index,
            "text": word.text,
            "normalized": word.normalized,
            "start_ms": None,
            "end_ms": None,
        }
        for word in ebook_words
    ]
    matches = 0
    cursor = 0
    for timed_word in transcript_words:
        match_index = find_best_forward_match(
            aligned_words=aligned_words,
            normalized=timed_word.normalized,
            cursor=cursor,
            window=window,
            backtrack=backtrack,
            match_score=match_score,
        )
        if match_index is None:
            continue
        aligned_words[match_index]["start_ms"] = timed_word.start_ms
        aligned_words[match_index]["end_ms"] = timed_word.end_ms
        cursor = match_index + 1
        matches += 1
    coverage = 0.0 if not transcript_words else matches / len(transcript_words)
    if coverage < threshold:
        raise AlignmentFailure(
            f"Alignment coverage {coverage:.2f} is below required threshold {threshold:.2f}"
        )
    return AlignmentResult(coverage=coverage, words=aligned_words)


def find_best_forward_match(
    aligned_words: list[dict],
    normalized: str,
    cursor: int,
    window: int,
    backtrack: int = 0,
    match_score: float = 0.85,
) -> int | None:
    """Find the best fuzzy match for ``normalized`` starting near ``cursor``.

    A short backward window is also considered so that the aligner can recover
    when the narrator inserted an extra word that produced no match. Already
    aligned words are skipped so the same ebook word is never matched twice.
    """
    best_index: int | None = None
    best_score = match_score
    start = max(0, cursor - backtrack)
    limit = min(len(aligned_words), cursor + window)
    for index in range(start, limit):
        if aligned_words[index]["start_ms"] is not None:
            continue
        score = fuzz.ratio(aligned_words[index]["normalized"], normalized) / 100
        if score > best_score:
            best_score = score
            best_index = index
    return best_index
