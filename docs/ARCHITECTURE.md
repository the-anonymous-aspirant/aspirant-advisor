# Aspirant Advisor — Architecture

*Date: 2026-03-22*

---

## System Context

```
┌──────────────────┐       ┌──────────────────┐
│  aspirant-client │       │  aspirant-server  │
│  Vue.js + Nginx  │──────▶│  Go/Gin gateway   │
│  :80             │       │  :8081            │
└──────────────────┘       └────────┬─────────┘
                                    │ HTTP proxy
                                    ▼
                           ┌──────────────────┐
                           │ aspirant-advisor  │
                           │ FastAPI           │
                           │ :8088 → 8000      │
                           │                   │
                           │ ┌───────────────┐ │
                           │ │ Ingestion     │ │  upload → parse → chunk → embed → store
                           │ │ Retrieval     │ │  query → embed → search → rank
                           │ │ Generation    │ │  chunks → Ollama → cited answer
                           │ │ Registry      │ │  source inventory for UI
                           │ └───────────────┘ │
                           └──┬──────────┬─────┘
                              │          │
                    ┌─────────▼──┐  ┌────▼──────────┐
                    │ PostgreSQL │  │    Ollama      │
                    │ + pgvector │  │ llama3.1:8b    │
                    │ :5432      │  │ :11434         │
                    └────────────┘  └───────────────┘
                                          │
                                    ┌─────▼──────┐
                                    │ /data/     │
                                    │ advisor/   │
                                    │ models/    │
                                    └────────────┘
```

---

## Internal Structure

```
aspirant-advisor/
├── app/
│   ├── main.py              # FastAPI app, lifespan (load embedding model)
│   ├── config.py            # Environment variable settings
│   ├── database.py          # SQLAlchemy engine, pgvector setup
│   ├── models.py            # ORM: documents, chunks, domains
│   ├── schemas.py           # Pydantic: request/response models
│   ├── routes.py            # API endpoint definitions
│   ├── ingestion.py         # Document parsing, chunking, embedding
│   ├── retrieval.py         # Vector search, chunk ranking, role filtering
│   ├── generation.py        # Ollama client, prompt construction, citation verification
│   └── parsers/
│       ├── pdf.py           # PDF parsing (pdfplumber/pymupdf)
│       ├── docx.py          # DOCX parsing (python-docx)
│       ├── text.py          # Plain text parsing
│       └── law.py           # Law-specific parsing (SFS, BGB section structure)
├── docs/
│   ├── SPEC.md
│   ├── ARCHITECTURE.md      # This file
│   ├── CHANGELOG.md
│   ├── DECISIONS.md
│   └── OPERATIONS.md
├── tests/
│   ├── test_import.py       # All imports resolve
│   ├── test_ingestion.py    # Parsing and chunking
│   ├── test_retrieval.py    # Vector search
│   └── test_generation.py   # Citation verification
├── Dockerfile-Advisor
└── requirements.txt
```

---

## Data Flow

### Document Ingestion

```
1. Admin uploads file via POST /documents
         │
         ▼
2. File saved to /data/advisor/uploads/{id}/{filename}
         │
         ▼
3. Parser selected by file type (PDF/DOCX/TXT)
         │
         ▼
4. Section-aware chunking
   - PDFs: split on headings, preserve page numbers and line ranges
   - Law texts: split on §/kap/article boundaries
   - Fallback: sliding window with overlap
         │
         ▼
5. Each chunk embedded via sentence-transformers (local, CPU)
   Model: all-MiniLM-L6-v2 (384 dimensions)
         │
         ▼
6. Chunks + embeddings + metadata stored in PostgreSQL
   - advisor_documents row (metadata)
   - advisor_chunks rows (content + embedding + position)
         │
         ▼
7. Domain registry updated (advisor_domains)
```

### Query Pipeline

```
1. User submits question via POST /query
         │
         ▼
2. Question embedded with same sentence-transformer model
         │
         ▼
3. pgvector similarity search (cosine distance)
   - Filter: access_level <= user.role
   - Filter: domain (if specified)
   - Return top-K chunks with metadata
         │
         ▼
4. Prompt construction
   - System prompt: "Answer ONLY from the provided context.
     Cite every claim with [Source: document, section, page].
     If the context doesn't contain the answer, say so."
   - Context: retrieved chunks with citation identifiers
   - Question: user's original query
         │
         ▼
5. Ollama generates answer (llama3.1:8b, local, CPU)
         │
         ▼
6. Citation verification (post-processing)
   - Parse all [Source: ...] references in the answer
   - Verify each reference exists in the retrieved chunks
   - Strip or flag any citation that doesn't match
         │
         ▼
7. Response assembled
   - answer: verified text
   - citations: matched chunk details (document, section, page, raw text)
   - sources_searched: which domains were queried
   - sources_not_available: domains the question touches but have no content
   - confidence: full_coverage | partial_coverage | no_coverage
```

### Source Registry

```
1. Client requests GET /sources
         │
         ▼
2. Query advisor_domains (all domains, including empty ones)
         │
         ▼
3. For each domain, aggregate from advisor_documents:
   - Count of documents by tier
   - Coverage summary
   - Last updated timestamp
   - Access level distribution
         │
         ▼
4. Return structured registry with gap indicators
   (domains with zero documents are included and flagged)
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector DB | pgvector (PostgreSQL extension) | Already running PostgreSQL; avoid a new service. Sufficient for <1M chunks |
| Embedding model | all-MiniLM-L6-v2 (local) | 90 MB, runs on CPU, 384-dim. Privacy: no data leaves the server |
| LLM | Ollama + Llama 3.1 8B Q4 (local) | Privacy-first. CPU-only viable on i7-3770K. Swappable for larger models after GPU upgrade |
| LLM deployment | Separate Ollama container | Decoupled from advisor. Shared by future services. Model management via Ollama CLI |
| Chunking strategy | Section-aware with fallback | Legal/contract documents have clear structure. Fallback handles unstructured text |
| Citation verification | Post-processing (not prompt-only) | Prompting reduces but doesn't eliminate hallucination. Verification catches the rest |
| Source transparency | Explicit domain registry with gaps | Prevents false confidence. User always knows what the system can and can't answer about |
| Access control | Document-level tagging | Simple, auditable. Filter at retrieval time, before LLM sees anything |

---

## Resource Requirements

| Resource | Requirement | Notes |
|----------|------------|-------|
| RAM (advisor) | 2 GB | Embedding model (~90 MB) + FastAPI + parsing |
| RAM (Ollama) | 6 GB | Model weights (~5 GB) + context window |
| Disk | 1 GB+ on /data | Uploaded documents + Ollama models on RAID |
| CPU | Moderate | Embedding is fast; LLM inference is the bottleneck (~8-12 tok/s) |
| Port | 8088:8000 | FastAPI |
| Ollama port | 11434 | Internal Docker network only |

### Memory Budget (total cell impact)

```
Current Docker usage:     ~1.9 GB
Advisor service:          ~2.0 GB
Ollama (when loaded):     ~6.0 GB
                          --------
Peak total:               ~9.9 GB (of 16 GB)
Available headroom:       ~6 GB (for OS, buffers, other services)
```

Ollama unloads the model after idle timeout (default 5 min), freeing ~5 GB when not in use.

---

## Security Considerations

- **Authentication:** Via aspirant-server JWT proxy (same as other services)
- **Network access:** Internal Docker network only; exposed via server proxy
- **Data sensitivity:** High — contracts, insurance policies, legal documents
- **Privacy model:** All processing is local (embeddings, LLM). No data leaves the server
- **Role enforcement:** Chunks from admin-only documents are never retrieved for family users
- **File storage:** Uploaded files stored on RAID volume, not in database
