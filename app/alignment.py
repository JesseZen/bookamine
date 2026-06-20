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
) -> int | None:
    best_index: int | None = None
    best_score = 0.0
    limit = min(len(aligned_words), cursor + window)
    for index in range(cursor, limit):
        score = fuzz.ratio(aligned_words[index]["normalized"], normalized) / 100
        if score > best_score:
            best_score = score
            best_index = index
    if best_score < 0.85:
        return None
    return best_index
