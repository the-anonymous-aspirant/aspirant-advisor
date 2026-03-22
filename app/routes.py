import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import ADVISOR_DATA_PATH, MAX_UPLOAD_SIZE_MB, OLLAMA_URL
from app.database import get_db
from app.generation import generate_answer, verify_citations
from app.ingestion import ingest_document
from app.models import AdvisorChunk, AdvisorDocument, AdvisorDomain
from app.retrieval import retrieve_chunks
from app.schemas import (
    ChunkResponse,
    Citation,
    DocumentListResponse,
    DocumentResponse,
    DomainSummary,
    HealthCheck,
    LawIngestionRequest,
    QueryRequest,
    QueryResponse,
    SourceDocumentSummary,
    SourceRegistryResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

SERVICE_NAME = "advisor"
SERVICE_VERSION = "1.0.0"


# --- Health ---


@router.get("/health", response_model=HealthCheck)
def health_check(db: Session = Depends(get_db)):
    checks = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception:
        checks["database"] = "disconnected"

    try:
        result = db.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        checks["pgvector"] = "available" if result.fetchone() else "not installed"
    except Exception:
        checks["pgvector"] = "check failed"

    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        checks["ollama"] = "connected" if resp.status_code == 200 else "error"
    except Exception:
        checks["ollama"] = "disconnected"

    all_ok = all(v in ("connected", "available") for v in checks.values())

    return HealthCheck(
        status="ok" if all_ok else "degraded",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        checks=checks,
    )


# --- Documents ---


@router.post("/documents", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    domain: str = Form(...),
    doc_type: str = Form("contract"),
    language: str = Form("en"),
    access_level: str = Form("admin"),
    tier: int = Form(1),
    coverage_note: str | None = Form(None),
    effective_from: str | None = Form(None),
    effective_to: str | None = Form(None),
    source_url: str | None = Form(None),
    db: Session = Depends(get_db),
):
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_SIZE_MB} MB limit")

    # Validate domain exists
    domain_obj = db.execute(
        select(AdvisorDomain).where(AdvisorDomain.name == domain)
    ).scalar_one_or_none()
    if not domain_obj:
        raise HTTPException(status_code=400, detail=f"Domain '{domain}' not found. Create it first via GET /sources.")

    from datetime import date

    eff_from = date.fromisoformat(effective_from) if effective_from else None
    eff_to = date.fromisoformat(effective_to) if effective_to else None

    doc = ingest_document(
        db=db,
        file_content=content,
        filename=file.filename,
        title=title,
        domain=domain,
        doc_type=doc_type,
        language=language,
        access_level=access_level,
        tier=tier,
        coverage_note=coverage_note,
        effective_from=eff_from,
        effective_to=eff_to,
        source_url=source_url,
    )

    chunk_count = db.execute(
        select(func.count(AdvisorChunk.id)).where(AdvisorChunk.document_id == doc.id)
    ).scalar()

    return _doc_to_response(doc, chunk_count)


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    domain: str | None = None,
    access_level: str = "admin",
    db: Session = Depends(get_db),
):
    stmt = select(AdvisorDocument)
    if domain:
        stmt = stmt.where(AdvisorDocument.domain == domain)

    # Role filtering
    if access_level != "admin":
        stmt = stmt.where(AdvisorDocument.access_level == "family")

    docs = db.execute(stmt.order_by(AdvisorDocument.created_at.desc())).scalars().all()

    items = []
    for doc in docs:
        chunk_count = db.execute(
            select(func.count(AdvisorChunk.id)).where(AdvisorChunk.document_id == doc.id)
        ).scalar()
        items.append(_doc_to_response(doc, chunk_count))

    return DocumentListResponse(items=items, total=len(items))


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = db.get(AdvisorDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunk_count = db.execute(
        select(func.count(AdvisorChunk.id)).where(AdvisorChunk.document_id == doc.id)
    ).scalar()

    return _doc_to_response(doc, chunk_count)


@router.get("/documents/{doc_id}/chunks", response_model=list[ChunkResponse])
def get_document_chunks(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = db.get(AdvisorDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = (
        db.execute(
            select(AdvisorChunk)
            .where(AdvisorChunk.document_id == doc_id)
            .order_by(AdvisorChunk.chunk_index)
        )
        .scalars()
        .all()
    )

    return [
        ChunkResponse(
            id=c.id,
            content=c.content,
            section_id=c.section_id,
            section_title=c.section_title,
            chapter=c.chapter,
            page_number=c.page_number,
            line_start=c.line_start,
            line_end=c.line_end,
            chunk_index=c.chunk_index,
        )
        for c in chunks
    ]


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = db.get(AdvisorDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    db.delete(doc)
    db.commit()
    return {"status": "deleted", "id": str(doc_id)}


@router.post("/documents/{doc_id}/reprocess", response_model=DocumentResponse)
def reprocess_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    doc = db.get(AdvisorDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    import os

    file_path = os.path.join(ADVISOR_DATA_PATH, "uploads", str(doc_id), doc.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Original file not found on disk")

    with open(file_path, "rb") as f:
        content = f.read()

    # Delete old chunks
    db.execute(
        AdvisorChunk.__table__.delete().where(AdvisorChunk.document_id == doc_id)
    )

    # Re-parse, re-chunk, re-embed
    from app.embedding import get_embeddings
    from app.ingestion import chunk_sections, detect_parser

    parser = detect_parser(doc.filename)
    sections = parser(file_path)
    chunks = chunk_sections(sections)
    texts = [c.content for c in chunks]
    embeddings = get_embeddings(texts)

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        db.add(AdvisorChunk(
            document_id=doc_id,
            content=chunk.content,
            embedding=embedding,
            section_title=chunk.section_title,
            chapter=chunk.chapter,
            page_number=chunk.page_number,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            chunk_index=i,
        ))

    db.commit()
    db.refresh(doc)

    chunk_count = db.execute(
        select(func.count(AdvisorChunk.id)).where(AdvisorChunk.document_id == doc.id)
    ).scalar()

    return _doc_to_response(doc, chunk_count)


# --- Query ---


@router.post("/query", response_model=QueryResponse)
def query_advisor(req: QueryRequest, db: Session = Depends(get_db)):
    # Determine which domains exist and which have content
    all_domains = db.execute(select(AdvisorDomain)).scalars().all()
    domains_with_content = set()
    for d in all_domains:
        count = db.execute(
            select(func.count(AdvisorDocument.id)).where(
                AdvisorDocument.domain == d.name, AdvisorDocument.tier == 1
            )
        ).scalar()
        if count > 0:
            domains_with_content.add(d.name)

    # Determine searched domains
    if req.domains:
        searched = req.domains
    else:
        searched = [d.name for d in all_domains]

    sources_not_available = [d for d in searched if d not in domains_with_content]

    # Retrieve
    results = retrieve_chunks(
        db=db,
        question=req.question,
        access_level="admin",  # TODO: extract from auth headers
        domains=req.domains,
    )

    if not results:
        return QueryResponse(
            answer="I cannot find information about this in the indexed sources.",
            citations=[],
            sources_searched=searched,
            sources_matched=[],
            sources_not_available=sources_not_available,
            confidence="no_coverage",
            chunks_retrieved=[],
        )

    # Generate
    raw_answer = generate_answer(req.question, results)

    # Verify citations
    answer, verified = verify_citations(raw_answer, results)

    # Determine matched sources
    sources_matched = list({doc.domain for _, doc, _ in results})

    # Confidence
    if not sources_not_available:
        confidence = "full_coverage"
    elif sources_matched:
        confidence = "partial_coverage"
    else:
        confidence = "no_coverage"

    # Build response
    citations = [
        Citation(
            document_title=c["document_title"],
            document_id=c["document_id"],
            section_id=c.get("section_id"),
            section_title=c.get("section_title"),
            page_number=c.get("page_number"),
            line_start=c.get("line_start"),
            line_end=c.get("line_end"),
            text=c["text"],
            source_url=c.get("source_url"),
        )
        for c in verified
    ]

    chunks_retrieved = [
        ChunkResponse(
            id=chunk.id,
            content=chunk.content,
            section_id=chunk.section_id,
            section_title=chunk.section_title,
            chapter=chunk.chapter,
            page_number=chunk.page_number,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            chunk_index=chunk.chunk_index,
        )
        for chunk, _, _ in results
    ]

    return QueryResponse(
        answer=answer,
        citations=citations,
        sources_searched=searched,
        sources_matched=sources_matched,
        sources_not_available=sources_not_available,
        confidence=confidence,
        chunks_retrieved=chunks_retrieved,
    )


# --- Sources Registry ---


@router.get("/sources", response_model=SourceRegistryResponse)
def get_sources(access_level: str = "admin", db: Session = Depends(get_db)):
    domains = db.execute(
        select(AdvisorDomain).order_by(AdvisorDomain.sort_order)
    ).scalars().all()

    domain_summaries = []
    total_documents = 0
    total_chunks = 0

    for domain in domains:
        # Get documents for this domain
        doc_stmt = select(AdvisorDocument).where(AdvisorDocument.domain == domain.name)
        if access_level != "admin":
            doc_stmt = doc_stmt.where(AdvisorDocument.access_level == "family")
        docs = db.execute(doc_stmt.order_by(AdvisorDocument.updated_at.desc())).scalars().all()

        doc_summaries = []
        tier1 = 0
        tier2 = 0
        last_updated = None

        for doc in docs:
            chunk_count = db.execute(
                select(func.count(AdvisorChunk.id)).where(AdvisorChunk.document_id == doc.id)
            ).scalar()
            total_chunks += chunk_count

            doc_summaries.append(SourceDocumentSummary(
                id=doc.id,
                title=doc.title,
                doc_type=doc.doc_type,
                tier=doc.tier,
                language=doc.language,
                coverage_note=doc.coverage_note,
                effective_from=doc.effective_from,
                effective_to=doc.effective_to,
                chunk_count=chunk_count,
                updated_at=doc.updated_at,
            ))

            if doc.tier == 1:
                tier1 += 1
            elif doc.tier == 2:
                tier2 += 1

            if last_updated is None or doc.updated_at > last_updated:
                last_updated = doc.updated_at

        total_documents += len(docs)

        domain_summaries.append(DomainSummary(
            name=domain.name,
            display_name=domain.display_name,
            description=domain.description,
            icon=domain.icon,
            document_count=len(docs),
            tier1_count=tier1,
            tier2_count=tier2,
            has_content=len(docs) > 0,
            last_updated=last_updated,
            documents=doc_summaries,
        ))

    return SourceRegistryResponse(
        domains=domain_summaries,
        total_documents=total_documents,
        total_chunks=total_chunks,
    )


# --- Laws ---


@router.post("/laws")
def ingest_laws(req: LawIngestionRequest, db: Session = Depends(get_db)):
    from app.embedding import get_embeddings
    from app.ingestion import file_hash
    from app.parsers.law import parse_law_sections

    # Validate domain
    domain_obj = db.execute(
        select(AdvisorDomain).where(AdvisorDomain.name == req.domain)
    ).scalar_one_or_none()
    if not domain_obj:
        raise HTTPException(status_code=400, detail=f"Domain '{req.domain}' not found")

    created_docs = []

    # Group sections by law_code
    by_code: dict[str, list] = {}
    for section in req.sections:
        by_code.setdefault(section.law_code, []).append(section)

    for law_code, sections in by_code.items():
        # Create a document per law code
        all_content = "\n".join(s.content or s.title or "" for s in sections)
        fhash = file_hash(all_content.encode("utf-8"))

        doc = AdvisorDocument(
            title=law_code,
            filename=f"{law_code}.law",
            domain=req.domain,
            doc_type="law-full" if req.tier == 1 else "law-index",
            language=sections[0].language,
            access_level=req.access_level,
            tier=req.tier,
            source_url=sections[0].source_url,
            effective_from=sections[0].effective_date,
            file_hash=fhash,
        )
        db.add(doc)
        db.flush()

        if req.tier == 1:
            # Tier 1: embed full text
            parsed = parse_law_sections(sections)
            texts = [p.content for p in parsed]
            embeddings = get_embeddings(texts) if texts else []

            for i, (section, parsed_s, embedding) in enumerate(
                zip(sections, parsed, embeddings)
            ):
                db.add(AdvisorChunk(
                    document_id=doc.id,
                    content=parsed_s.content,
                    embedding=embedding,
                    section_id=section.section_id,
                    section_title=section.title,
                    chapter=section.chapter,
                    chunk_index=i,
                ))
        else:
            # Tier 2: store metadata only, use a zero vector as placeholder
            zero_vec = [0.0] * 384
            for i, section in enumerate(sections):
                content = section.content or section.title or section.section_id
                db.add(AdvisorChunk(
                    document_id=doc.id,
                    content=content,
                    embedding=zero_vec,
                    section_id=section.section_id,
                    section_title=section.title,
                    chapter=section.chapter,
                    chunk_index=i,
                ))

        created_docs.append({"law_code": law_code, "document_id": str(doc.id), "sections": len(sections)})

    db.commit()

    return {"status": "ingested", "documents": created_docs}


# --- Helpers ---


def _doc_to_response(doc: AdvisorDocument, chunk_count: int) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        title=doc.title,
        filename=doc.filename,
        domain=doc.domain,
        doc_type=doc.doc_type,
        language=doc.language,
        access_level=doc.access_level,
        tier=doc.tier,
        coverage_note=doc.coverage_note,
        effective_from=doc.effective_from,
        effective_to=doc.effective_to,
        source_url=doc.source_url,
        chunk_count=chunk_count,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )
