from app.alignment import AlignmentFailure, AlignmentResult, TimedWord, align_words
from app.models import ParsedWord


def test_align_timed_words_to_ebook_words():
    result = align_words(
        ebook_words=[
            ParsedWord(index=0, block_index=0, text="Hello", normalized="hello"),
            ParsedWord(index=1, block_index=0, text="world", normalized="world"),
        ],
        transcript_words=[
            TimedWord(text="hello", normalized="hello", start_ms=0, end_ms=400),
            TimedWord(text="world", normalized="world", start_ms=410, end_ms=800),
        ],
    )

    assert result == AlignmentResult(
        coverage=1.0,
        words=[
            {
                "index": 0,
                "block_index": 0,
                "text": "Hello",
                "normalized": "hello",
                "start_ms": 0,
                "end_ms": 400,
            },
            {
                "index": 1,
                "block_index": 0,
                "text": "world",
                "normalized": "world",
                "start_ms": 410,
                "end_ms": 800,
            },
        ],
    )


def test_align_words_rejects_low_coverage():
    try:
        align_words(
            ebook_words=[
                ParsedWord(index=0, block_index=0, text="alpha", normalized="alpha"),
                ParsedWord(index=1, block_index=0, text="beta", normalized="beta"),
            ],
            transcript_words=[
                TimedWord(text="gamma", normalized="gamma", start_ms=0, end_ms=400),
            ],
        )
    except AlignmentFailure as error:
        assert str(error) == "Alignment coverage 0.00 is below required threshold 0.60"
    else:
        raise AssertionError("Expected AlignmentFailure")


def test_align_chapter_words_preserves_global_indexes():
    result = align_words(
        ebook_words=[
            ParsedWord(index=4, block_index=2, text="Three", normalized="three"),
            ParsedWord(index=5, block_index=2, text="four", normalized="four"),
        ],
        transcript_words=[
            TimedWord(text="three", normalized="three", start_ms=0, end_ms=400),
            TimedWord(text="four", normalized="four", start_ms=410, end_ms=800),
        ],
    )

    assert result == AlignmentResult(
        coverage=1.0,
        words=[
            {
                "index": 4,
                "block_index": 2,
                "text": "Three",
                "normalized": "three",
                "start_ms": 0,
                "end_ms": 400,
            },
            {
                "index": 5,
                "block_index": 2,
                "text": "four",
                "normalized": "four",
                "start_ms": 410,
                "end_ms": 800,
            },
        ],
    )
