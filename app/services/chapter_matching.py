"""Chapter title fuzzy-matching between ebook chapters and audio chapters."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from app.models import AudioChapter

TITLE_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

ONES = {
    "zero": 0, "one": 1, "first": 1, "two": 2, "second": 2,
    "three": 3, "third": 3, "four": 4, "fourth": 4, "five": 5,
    "fifth": 5, "six": 6, "sixth": 6, "seven": 7, "seventh": 7,
    "eight": 8, "eighth": 8, "nine": 9, "ninth": 9,
}
TEENS = {
    "ten": 10, "tenth": 10, "eleven": 11, "eleventh": 11, "twelve": 12,
    "twelfth": 12, "thirteen": 13, "thirteenth": 13, "fourteen": 14,
    "fourteenth": 14, "fifteen": 15, "fifteenth": 15, "sixteen": 16,
    "sixteenth": 16, "seventeen": 17, "seventeenth": 17, "eighteen": 18,
    "eighteenth": 18, "nineteen": 19, "nineteenth": 19,
}
TENS = {
    "twenty": 20, "twentieth": 20, "thirty": 30, "thirtieth": 30,
    "forty": 40, "fortieth": 40, "fifty": 50, "fiftieth": 50,
    "sixty": 60, "sixtieth": 60, "seventy": 70, "seventieth": 70,
    "eighty": 80, "eightieth": 80, "ninety": 90, "ninetieth": 90,
}


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
        ones_word = token[len(tens_word):]
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
