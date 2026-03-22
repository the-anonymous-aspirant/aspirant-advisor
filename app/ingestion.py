import hashlib
import logging
import os
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import ADVISOR_DATA_PATH, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS
from app.embedding import get_embeddings
from app.models import AdvisorChunk, AdvisorDocument
from app.parsers.docx_parser import parse_docx
from app.parsers.pdf import ParsedSection, parse_pdf
from app.parsers.text import parse_text

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def detect_parser(filename: str):
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return parse_pdf
    elif ext == ".docx":
        return parse_docx
    elif ext in (".txt", ".md"):
        return parse_text
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def save_upload(file_content: bytes, doc_id: uuid.UUID, filename: str) -> str:
    upload_dir = os.path.join(ADVISOR_DATA_PATH, "uploads", str(doc_id))
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path


def chunk_sections(sections: list[ParsedSection], max_tokens: int = CHUNK_MAX_TOKENS, overlap: int = CHUNK_OVERLAP_TOKENS) -> list[ParsedSection]:
    """Split sections that exceed max_tokens into smaller chunks with overlap."""
    chunks = []
    for section in sections:
        words = section.content.split()
        if len(words) <= max_tokens:
            chunks.append(section)
            continue

        # Split large sections with overlap
        start = 0
        sub_index = 0
        while start < len(words):
            end = min(start + max_tokens, len(words))
            chunk_text = " ".join(words[start:end])
            title = section.section_title
            if sub_index > 0 and title:
                title = f"{title} (cont.)"

            chunks.append(ParsedSection(
                content=chunk_text,
                page_number=section.page_number,
                line_start=section.line_start,
                line_end=section.line_end,
                section_title=title,
                chapter=section.chapter,
            ))
            start = end - overlap if end < len(words) else end
            sub_index += 1

    return chunks


def ingest_document(
    db: Session,
    file_content: bytes,
    filename: str,
    title: str,
    domain: str,
    doc_type: str,
    language: str = "en",
    access_level: str = "admin",
    tier: int = 1,
    coverage_note: str | None = None,
    effective_from=None,
    effective_to=None,
    source_url: str | None = None,
) -> AdvisorDocument:
    doc_id = uuid.uuid4()
    fhash = file_hash(file_content)

    # Save file to disk
    file_path = save_upload(file_content, doc_id, filename)

    # Parse
    parser = detect_parser(filename)
    sections = parser(file_path)

    # Chunk
    chunks = chunk_sections(sections)
    logger.info("Document '%s': %d sections -> %d chunks", title, len(sections), len(chunks))

    # Embed
    texts = [c.content for c in chunks]
    embeddings = get_embeddings(texts)

    # Create document record
    doc = AdvisorDocument(
        id=doc_id,
        title=title,
        filename=filename,
        domain=domain,
        doc_type=doc_type,
        language=language,
        access_level=access_level,
        tier=tier,
        coverage_note=coverage_note,
        effective_from=effective_from,
        effective_to=effective_to,
        source_url=source_url,
        file_hash=fhash,
    )
    db.add(doc)

    # Create chunk records
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        db.add(AdvisorChunk(
            document_id=doc_id,
            content=chunk.content,
            embedding=embedding,
            section_id=None,
            section_title=chunk.section_title,
            chapter=chunk.chapter,
            page_number=chunk.page_number,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            chunk_index=i,
        ))

    db.commit()
    db.refresh(doc)
    logger.info("Ingested document '%s' with %d chunks", title, len(chunks))
    return doc
