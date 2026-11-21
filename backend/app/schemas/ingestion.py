"""Records produced by ingestion. SectionRecord matches the processed JSONL schema
(id, act, chapter, section, title, citation, text, source_url, source_file) plus provenance extras."""

from pydantic import BaseModel, Field

from app.core.constants import Area


class SectionRecord(BaseModel):
    id: str
    document_id: str
    area: Area
    act: str
    chapter: str | None = None
    section: str  # as printed, Bangla digits, e.g. "২", "৩ক"; "প্রস্তাবনা" for a preamble
    title: str
    citation: str
    text: str
    notes: list[str] = Field(default_factory=list)  # amendment footnotes; never dropped
    source_url: str | None = None
    source_file: str
    page_start: int | None = None
    page_end: int | None = None
    text_en: str | None = None
    translation_note: str | None = None


class ChunkRecord(BaseModel):
    id: str  # "<section id>" or "<section id>-p<part>"
    document_id: str
    area: Area
    act: str
    chapter: str | None
    section: str
    title: str
    citation: str  # parent citation; part number is in `part`
    part: int | None  # None when the section was not split
    text: str  # original (repaired) text for display
    normalized_text: str  # search text: normalized, digits ASCII
    token_count: int
    notes: list[str] = Field(default_factory=list)
    source_url: str | None
    page_start: int | None = None
    page_end: int | None = None

    def embedding_text(self) -> str:
        """Text that gets embedded/indexed: heading context + body."""
        return f"{self.citation} — {self.title}\n{self.text}"
