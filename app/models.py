from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReaderShell:
    title: str = "Bookamine"


@dataclass(frozen=True)
class ParsedWord:
    index: int
    block_index: int
    text: str
    normalized: str


@dataclass(frozen=True)
class ParsedBlock:
    index: int
    text: str
    word_indexes: list[int]


@dataclass(frozen=True)
class ParsedChapter:
    title: str
    index: int
    block_indexes: list[int]
    word_indexes: list[int]


@dataclass(frozen=True)
class AudioChapter:
    index: int
    title: str
    source_name: str
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True)
class ParsedBook:
    title: str
    chapters: list[ParsedChapter]
    blocks: list[ParsedBlock]
    words: list[ParsedWord]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "chapters": [asdict(chapter) for chapter in self.chapters],
            "blocks": [asdict(block) for block in self.blocks],
            "words": [asdict(word) for word in self.words],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ParsedBook":
        return cls(
            title=payload["title"],
            chapters=[ParsedChapter(**chapter) for chapter in payload["chapters"]],
            blocks=[ParsedBlock(**block) for block in payload["blocks"]],
            words=[ParsedWord(**word) for word in payload["words"]],
        )


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    status: str

    def to_dict(self) -> dict:
        return asdict(self)
