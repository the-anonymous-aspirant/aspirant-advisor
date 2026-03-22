import uuid
from datetime import date, datetime

from pydantic import BaseModel


class HealthCheck(BaseModel):
    status: str
    service: str
    version: str
    checks: dict[str, str]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# --- Documents ---


class DocumentResponse(BaseModel):
    id: uuid.UUID
    title: str
    filename: str
    domain: str
    doc_type: str
    language: str
    access_level: str
    tier: int
    coverage_note: str | None
    effective_from: date | None
    effective_to: date | None
    source_url: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int


# --- Chunks ---


class ChunkResponse(BaseModel):
    id: uuid.UUID
    content: str
    section_id: str | None
    section_title: str | None
    chapter: str | None
    page_number: int | None
    line_start: int | None
    line_end: int | None
    chunk_index: int

    model_config = {"from_attributes": True}


# --- Query ---


class QueryRequest(BaseModel):
    question: str
    language: str | None = None
    domains: list[str] | None = None


class Citation(BaseModel):
    document_title: str
    document_id: uuid.UUID
    section_id: str | None
    section_title: str | None
    page_number: int | None
    line_start: int | None
    line_end: int | None
    text: str
    source_url: str | None


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    sources_searched: list[str]
    sources_matched: list[str]
    sources_not_available: list[str]
    confidence: str
    chunks_retrieved: list[ChunkResponse]


# --- Sources Registry ---


class SourceDocumentSummary(BaseModel):
    id: uuid.UUID
    title: str
    doc_type: str
    tier: int
    language: str
    coverage_note: str | None
    effective_from: date | None
    effective_to: date | None
    chunk_count: int
    updated_at: datetime


class DomainSummary(BaseModel):
    name: str
    display_name: str
    description: str | None
    icon: str | None
    document_count: int
    tier1_count: int
    tier2_count: int
    has_content: bool
    last_updated: datetime | None
    documents: list[SourceDocumentSummary]


class SourceRegistryResponse(BaseModel):
    domains: list[DomainSummary]
    total_documents: int
    total_chunks: int


# --- Laws ---


class LawSectionInput(BaseModel):
    law_code: str
    section_id: str
    chapter: str | None = None
    title: str | None = None
    content: str | None = None
    language: str = "en"
    source_url: str | None = None
    effective_date: date | None = None


class LawIngestionRequest(BaseModel):
    domain: str
    tier: int = 1
    access_level: str = "admin"
    sections: list[LawSectionInput]
