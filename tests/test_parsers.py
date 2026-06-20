from pathlib import Path

from ebooklib import epub

from app.models import ParsedBlock, ParsedBook, ParsedChapter, ParsedWord
from app.parsers import parse_ebook_bytes


def test_parse_txt_preserves_block_order():
    result = parse_ebook_bytes(b"One two\n\nThree four", "sample.txt")

    assert result == ParsedBook(
        title="sample",
        chapters=[
            ParsedChapter(title="Chapter 1", index=0, block_indexes=[0, 1], word_indexes=[0, 1, 2, 3]),
        ],
        blocks=[
            ParsedBlock(index=0, text="One two", word_indexes=[0, 1]),
            ParsedBlock(index=1, text="Three four", word_indexes=[2, 3]),
        ],
        words=[
            ParsedWord(index=0, block_index=0, text="One", normalized="one"),
            ParsedWord(index=1, block_index=0, text="two", normalized="two"),
            ParsedWord(index=2, block_index=1, text="Three", normalized="three"),
            ParsedWord(index=3, block_index=1, text="four", normalized="four"),
        ],
    )


def test_parse_epub_preserves_visible_block_order(tmp_path):
    book = epub.EpubBook()
    book.set_identifier("book-id")
    book.set_title("Sample")
    book.set_language("en")
    chapter = epub.EpubHtml(title="Chapter 1", file_name="chapter1.xhtml", lang="en")
    chapter.content = "<h1>Hello world</h1><p>Three four</p>"
    book.add_item(chapter)
    book.spine = [chapter]
    book.toc = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub_path = tmp_path / "sample.epub"
    epub.write_epub(str(epub_path), book)

    result = parse_ebook_bytes(epub_path.read_bytes(), "sample.epub")

    assert result == ParsedBook(
        title="sample",
        chapters=[
            ParsedChapter(title="Hello world", index=0, block_indexes=[0, 1], word_indexes=[0, 1, 2, 3]),
        ],
        blocks=[
            ParsedBlock(index=0, text="Hello world", word_indexes=[0, 1]),
            ParsedBlock(index=1, text="Three four", word_indexes=[2, 3]),
        ],
        words=[
            ParsedWord(index=0, block_index=0, text="Hello", normalized="hello"),
            ParsedWord(index=1, block_index=0, text="world", normalized="world"),
            ParsedWord(index=2, block_index=1, text="Three", normalized="three"),
            ParsedWord(index=3, block_index=1, text="four", normalized="four"),
        ],
    )


def test_parse_txt_detects_chapters_from_headings():
    content = (
        b"Chapter 1\n"
        b"The boy who lived.\n\n"
        b"Chapter 2\n"
        b"The vanished glass.\n"
    )

    result = parse_ebook_bytes(content, "sample.txt")

    assert result == ParsedBook(
        title="sample",
        chapters=[
            ParsedChapter(title="Chapter 1", index=0, block_indexes=[0], word_indexes=[0, 1, 2, 3]),
            ParsedChapter(title="Chapter 2", index=1, block_indexes=[1], word_indexes=[4, 5, 6]),
        ],
        blocks=[
            ParsedBlock(index=0, text="The boy who lived.", word_indexes=[0, 1, 2, 3]),
            ParsedBlock(index=1, text="The vanished glass.", word_indexes=[4, 5, 6]),
        ],
        words=[
            ParsedWord(index=0, block_index=0, text="The", normalized="the"),
            ParsedWord(index=1, block_index=0, text="boy", normalized="boy"),
            ParsedWord(index=2, block_index=0, text="who", normalized="who"),
            ParsedWord(index=3, block_index=0, text="lived", normalized="lived"),
            ParsedWord(index=4, block_index=1, text="The", normalized="the"),
            ParsedWord(index=5, block_index=1, text="vanished", normalized="vanished"),
            ParsedWord(index=6, block_index=1, text="glass", normalized="glass"),
        ],
    )
