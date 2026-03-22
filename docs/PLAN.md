# Aspirant Advisor — Development Plan

*Date: 2026-03-22*

---

## Overview

Build in vertical slices — each milestone produces a working, testable increment. The service is usable (for basic document Q&A) after milestone 3. Later milestones add law support, the source registry UI data, and polish.

---

## Milestone 1: Skeleton + Database

**Goal:** Service boots, health endpoint works, tables exist in PostgreSQL.

1. Replace template placeholders in `app/` files (main.py, config.py, routes.py, schemas.py)
2. Write ORM models for `advisor_documents`, `advisor_chunks`, `advisor_domains`
3. Add pgvector extension setup in `database.py` (`CREATE EXTENSION IF NOT EXISTS vector`)
4. Add advisor-specific config variables (OLLAMA_URL, EMBEDDING_MODEL, ADVISOR_DATA_PATH, etc.)
5. Write Dockerfile-Advisor (python:3.11-slim, install dependencies)
6. Write requirements.txt (fastapi, uvicorn, sqlalchemy, psycopg2-binary, pgvector, pydantic)
7. Health endpoint: check database + pgvector extension
8. Test: `pytest tests/test_import.py` — all imports resolve

**Verify:** `docker compose up advisor` → `/health` returns OK with pgvector connected.

---

## Milestone 2: Document Ingestion

**Goal:** Upload a PDF, get chunks with metadata stored in the database.

1. Create `app/parsers/` directory with `pdf.py`, `docx.py`, `text.py`
2. Implement PDF parser (pdfplumber): extract text per page, preserve page numbers and line ranges
3. Implement section-aware chunking: split on headings/sections, fallback to sliding window with overlap
4. Add sentence-transformers to requirements, load model at startup (lifespan)
5. Implement embedding: chunk text → vector(384) via all-MiniLM-L6-v2
6. Write `POST /documents` endpoint: receive file → parse → chunk → embed → store
7. Write `GET /documents` and `GET /documents/{id}` endpoints
8. Write `DELETE /documents/{id}` endpoint (cascades to chunks)
9. Add file storage to `/data/advisor/uploads/{doc_id}/`
10. Test: upload a sample PDF, verify chunks have page numbers and embeddings

**Verify:** Upload a real contract PDF → `GET /documents/{id}` shows chunks with page/line metadata.

---

## Milestone 3: Query + Generation

**Goal:** Ask a question, get a cited answer from local LLM.

1. Add Ollama container to docker-compose (ollama/ollama, port 11434, 6GB memory limit)
2. Write `app/retrieval.py`: embed question → pgvector cosine search → top-K chunks
3. Write `app/generation.py`: Ollama HTTP client, prompt construction, response parsing
4. Implement system prompt enforcing citation format: `[Source: document, section, page]`
5. Implement citation verification: parse references, match against retrieved chunks, strip unverified
6. Write `POST /query` endpoint: question → retrieve → generate → verify → respond
7. Response includes: answer, citations (with raw chunk text), sources_searched, sources_not_available
8. Test: ingest a sample document, query it, verify citations match real chunks

**Verify:** Ask "What is the cancellation policy?" against an uploaded contract → get a cited answer with raw chunks shown.

---

## Milestone 4: Role-Based Access

**Goal:** Family users can only see and query family-tagged documents.

1. Add role extraction from request headers (JWT payload via aspirant-server proxy)
2. Add access_level filter to retrieval: `WHERE access_level <= user.role`
3. Add access_level filter to `GET /documents` and `GET /sources`
4. Admin can see/query everything; family sees only `access_level = 'family'` documents
5. Test: upload two documents (one admin, one family), query as each role

**Verify:** Family user queries → only family-tagged chunks are retrieved and cited.

---

## Milestone 5: Source Registry

**Goal:** Full source inventory with gap indicators for the UI.

1. Seed `advisor_domains` with initial domains (insurance, employment, tenancy, tax, consumer, immigration)
2. Write `GET /sources` endpoint: aggregate documents per domain, include empty domains
3. Response per domain: document count by tier, coverage summary, last updated, gap flag
4. After each query response, include `sources_searched` and `sources_not_available`
5. Add `confidence` field to query response: full_coverage / partial_coverage / no_coverage
6. Test: verify empty domains appear with gap indicators

**Verify:** `GET /sources` returns all domains, including ones with zero documents flagged as gaps.

---

## Milestone 6: Law Ingestion

**Goal:** Import Swedish and German law sections with proper citation structure.

1. Write `app/parsers/law.py`: parse structured law text preserving §/kap/article boundaries
2. Implement citation metadata: `law_code`, `section_id`, `chapter`, `paragraph`, `effective_date`, `source_url`
3. Write `POST /laws` endpoint: accept structured law input (JSON with sections)
4. Support Tier 1 (full text, embedded) and Tier 2 (metadata + URL only, not embedded)
5. For Tier 2, retrieval returns section metadata + source URL instead of generated text
6. Test: ingest a section of Jordabalken kap. 12, query about tenant rights

**Verify:** Query about rental law → cites "Jordabalken (1970:994) 12 kap. 24 §" with correct source URL.

---

## Milestone 7: DOCX + Plain Text Parsers

**Goal:** Support DOCX and plain text uploads alongside PDF.

1. Implement DOCX parser (python-docx): extract text, headings, structure
2. Implement plain text parser: line-based chunking with section detection
3. Auto-detect file type in `POST /documents` based on extension/MIME type
4. Test: upload a .docx and a .txt, verify chunking works

**Verify:** Upload a DOCX contract → chunks have section metadata.

---

## Milestone 8: Docker Compose + Deploy Integration

**Goal:** Service runs in production on aspirant-cell.

1. Add advisor + ollama to aspirant-deploy `docker-compose.yml` (GHCR images)
2. Add advisor + ollama to `docker-compose.dev.yml` (build from sibling repo)
3. Add server proxy route (ADVISOR_URL env var in aspirant-server)
4. Create CI workflow (`.github/workflows/ci.yml`)
5. Update aspirant-deploy INFRASTRUCTURE.md with advisor service details
6. Create `/data/aspirant/advisor/` and `/data/aspirant/ollama/` bind mounts on cell
7. Pull and test on cell

**Verify:** Full stack runs on cell, query works through the server proxy.

---

## Milestone 9: Client UI

**Goal:** Chat interface in aspirant-client with source registry sidebar.

1. Add advisor chat page in aspirant-client
2. Source registry sidebar: grouped by domain, color-coded by tier, gap indicators
3. Chat input → `POST /query` via server proxy → display answer + citations
4. Citations panel: show raw chunks with document/section/page references
5. After each answer: display sources searched and sources not available
6. Document upload page (admin only): file picker, domain/access-level tagging

**Verify:** End-to-end: upload a document via UI, ask a question, see cited answer with source sidebar.

---

## Post-MVP (tracked in ROADMAP.md)

- OCR support (tesseract for scanned documents)
- Tier 3: on-demand law fetching from riksdagen.se / gesetze-im-internet.de
- Multi-query retrieval (rephrase for exclusions/conditions)
- Document re-chunking review UI (correct/annotate chunks)
- GPU upgrade path (Ollama auto-detects, no code changes)
