import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from bs4 import BeautifulSoup
from ebooklib import epub

from app.models import ParsedBlock, ParsedBook, ParsedChapter, ParsedWord

WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
CHAPTER_HEADING_PATTERN = re.compile(r"^(chapter|book|part)\s+\w+", re.IGNORECASE)


class UnsupportedFormatError(ValueError):
    pass


def normalize_word(text: str) -> str:
    return text.casefold()


def build_parsed_book(chapter_blocks: list[tuple[str, list[str]]], title: str) -> ParsedBook:
    parsed_chapters: list[ParsedChapter] = []
    parsed_blocks: list[ParsedBlock] = []
    parsed_words: list[ParsedWord] = []
    word_index = 0
    block_index = 0
    for chapter_index, (chapter_title, blocks) in enumerate(chapter_blocks):
        chapter_block_indexes: list[int] = []
        chapter_word_indexes: list[int] = []
        for block in blocks:
            block_word_indexes: list[int] = []
            for match in WORD_PATTERN.finditer(block):
                parsed_words.append(
                    ParsedWord(
                        index=word_index,
                        block_index=block_index,
                        text=match.group(0),
                        normalized=normalize_word(match.group(0)),
                    )
                )
                block_word_indexes.append(word_index)
                chapter_word_indexes.append(word_index)
                word_index += 1
            parsed_blocks.append(
                ParsedBlock(
                    index=block_index,
                    text=block,
                    word_indexes=block_word_indexes,
                )
            )
            chapter_block_indexes.append(block_index)
            block_index += 1
        parsed_chapters.append(
            ParsedChapter(
                title=chapter_title,
                index=chapter_index,
                block_indexes=chapter_block_indexes,
                word_indexes=chapter_word_indexes,
            )
        )
    return ParsedBook(title=title, chapters=parsed_chapters, blocks=parsed_blocks, words=parsed_words)


def extract_epub_chapters(content: bytes) -> list[tuple[str, list[str]]]:
    with NamedTemporaryFile(suffix=".epub") as temp_file:
        temp_file.write(content)
        temp_file.flush()
        book = epub.read_epub(temp_file.name)

    chapters: list[tuple[str, list[str]]] = []
    untitled_index = 1
    for spine_entry in book.spine:
        item_id = spine_entry[0] if isinstance(spine_entry, tuple) else spine_entry
        item = book.get_item_with_id(item_id)
        if item is None:
            continue
        soup = BeautifulSoup(item.get_body_content(), "html.parser")
        chapter_title = item.title
        if not chapter_title:
            heading = soup.find(["h1", "h2", "h3"])
            if heading is not None:
                chapter_title = " ".join(heading.get_text(" ", strip=True).split())
        if not chapter_title:
            chapter_title = f"Chapter {untitled_index}"
            untitled_index += 1
        blocks: list[str] = []
        for element in soup.find_all(["p", "li", "h1", "h2", "h3", "h4"]):
            text = " ".join(element.get_text(" ", strip=True).split())
            if text:
                blocks.append(text)
        if blocks:
            chapters.append((chapter_title, blocks))
    return chapters


def extract_txt_chapters(text: str) -> list[tuple[str, list[str]]]:
    raw_blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    if not raw_blocks:
        return [("Chapter 1", [])]
    chapters: list[tuple[str, list[str]]] = []
    current_title = "Chapter 1"
    current_blocks: list[str] = []
    chapter_counter = 1
    for block in raw_blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) >= 2 and CHAPTER_HEADING_PATTERN.match(lines[0]):
            if current_blocks:
                chapters.append((current_title, current_blocks))
            current_title = lines[0]
            current_blocks = [" ".join(lines[1:])]
            chapter_counter += 1
            continue
        if CHAPTER_HEADING_PATTERN.match(block):
            if current_blocks:
                chapters.append((current_title, current_blocks))
            current_title = block
            current_blocks = []
            chapter_counter += 1
            continue
        current_blocks.append(" ".join(lines))
    if current_blocks:
        chapters.append((current_title, current_blocks))
    if not chapters:
        return [("Chapter 1", [" ".join(raw_blocks)])]
    return chapters


def parse_ebook_bytes(content: bytes, filename: str) -> ParsedBook:
    suffix = Path(filename).suffix.lower()
    title = Path(filename).stem
    if suffix == ".txt":
        text = content.decode("utf-8")
        return build_parsed_book(extract_txt_chapters(text), title)
    if suffix == ".epub":
        return build_parsed_book(extract_epub_chapters(content), title)
    raise UnsupportedFormatError(filename)
