from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    document_id: str
    title: str
    area: str
    issuer: str | None
    source_url: str | None
    section_count: int
    chunk_count: int


class SectionSummary(BaseModel):
    section: str
    title: str
    citation: str
    chunk_ids: list[str]


class DocumentDetail(BaseModel):
    document: DocumentSummary
    sections: list[SectionSummary]


class ChunkDetail(BaseModel):
    chunk_id: str
    document_id: str
    area: str
    act: str
    chapter: str | None
    section: str
    part: int | None
    title: str
    citation: str
    text: str
    notes: list[str] = Field(default_factory=list)
    source_url: str | None
    page_start: int | None
    page_end: int | None
