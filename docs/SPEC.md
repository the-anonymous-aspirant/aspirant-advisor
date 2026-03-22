# Aspirant Advisor — Specification

*Status: Draft*
*Author: Victor Wiklund*
*Date: 2026-03-22*

---

## Motivation

Personal documents (contracts, insurance policies, benefits, legal codes) are scattered across PDFs, emails, and bookmarks. When a question arises — "Am I covered for this flight delay?" — finding the answer requires manually searching through multiple documents, cross-referencing clauses, and hoping you haven't missed an exclusion buried in a different section.

Aspirant Advisor is a RAG-based document assistant that ingests these sources, indexes them with full citation metadata, and answers questions grounded exclusively in the uploaded content. It never fabricates — every claim links back to the exact document, section, and line.

---

## Scope

### In Scope

- **Document ingestion** — Upload and parse PDF, DOCX, and plain text files
- **Law ingestion** — Import legal sections with proper citation structure (Swedish SFS, German BGB/etc.)
- **Section-aware chunking** — Split documents by logical sections, preserving page/line/paragraph metadata
- **Semantic search** — Embed chunks with a local model, store in pgvector, retrieve by similarity
- **Grounded Q&A** — Answer questions using only retrieved chunks, with explicit citations
- **Citation verification** — Post-process LLM output to confirm every reference exists in the retrieved context
- **Role-based access** — Admin sees all sources; family role sees a tagged subset
- **Knowledge base transparency** — UI clearly displays all indexed sources, their type, coverage, and last update
- **Source display** — Show raw retrieved chunks alongside the generated answer

### Out of Scope

- **Legal advice** — The system retrieves and cites; it does not interpret or advise
- **Real-time law updates** — Laws are ingested manually; no auto-sync from government sources (future Tier 3)
- **Multi-language query translation** — Queries must match the language of the source document (Swedish query for Swedish law, etc.)
- **OCR for scanned documents** — Deferred to a future iteration (tesseract integration)
- **Email/Gmail integration** — Handled by aspirant-assistant harness, not this service

---

## Knowledge Base Transparency

A core design principle: **the user must always know what the system can and cannot answer about.**

### Source Registry

The UI displays a persistent, always-visible source registry listing every indexed domain. Each entry shows:

| Field | Purpose |
|-------|---------|
| **Domain** | Category (e.g., "Insurance", "Employment Law", "Tenancy") |
| **Source name** | Specific document or law (e.g., "Allianz Travel Policy #12345", "Jordabalken kap. 12") |
| **Type** | `contract`, `policy`, `benefit`, `law-full`, `law-index`, `other` |
| **Coverage** | What's included (e.g., "Full text", "Chapters 1-5 only", "Index with links") |
| **Tier** | `1` (full text, searchable), `2` (indexed reference, links out), `3` (not yet ingested) |
| **Language** | `sv`, `de`, `en` |
| **Effective dates** | When the document/law version is valid |
| **Last updated** | When this source was last ingested or refreshed |
| **Access level** | `admin`, `family` |

### Source Registry UI Behavior

- **Always visible** in a sidebar or collapsible panel on the chat page
- **Grouped by domain** (Insurance, Employment, Tenancy, Tax, etc.)
- **Color-coded by tier**: Tier 1 (full text) = solid, Tier 2 (indexed) = outlined, gaps = greyed placeholder
- **Gap indicators**: Empty domains or known-missing documents are shown explicitly (e.g., "Health Insurance: not yet uploaded") so the user sees what's missing
- **Clickable**: Each source expands to show section inventory and metadata
- **Query context**: After each answer, the system states which sources were searched and which were not available

### Answer Attribution

Every response includes:

1. **Sources searched** — Which domains/documents were queried
2. **Sources matched** — Which documents contributed to the answer
3. **Sources not available** — Explicit disclaimer if the question touches a domain with no indexed content
4. **Confidence indicator** — "Answered from full text" vs. "Partial coverage — some relevant documents may not be indexed"

---

## Source Tiers

### Tier 1: Full Text (in database, searchable)

Documents uploaded in their entirety. Chunks are embedded and retrievable. Citations reference exact page/section/line.

**Suitable for:**
- Personal contracts (employment, rental, insurance policies)
- Benefits documentation
- Specific law sections directly referenced by contracts
- Any document where exact wording matters

### Tier 2: Indexed Reference (metadata + links)

Section-level metadata stored without full text. When matched, the system displays the section title, a brief summary, and a link to the official source.

**Suitable for:**
- Broader legal codes (sections you might need but haven't uploaded yet)
- Government publications with stable URLs
- Swedish law via riksdagen.se, German law via gesetze-im-internet.de

**Schema:**
```
law_code, section_id, chapter, title, summary, language, source_url, effective_date
```

### Tier 3: On-Demand Fetch (future)

Fetch specific sections from public sources on demand, cache locally, promote to Tier 1 after retrieval.

**Not in initial scope.** Tracked in ROADMAP.md.

---

## API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/health` | Health check | No |
| `POST` | `/documents` | Upload and ingest a document | Admin |
| `GET` | `/documents` | List all documents (filtered by role) | Yes |
| `GET` | `/documents/{id}` | Get document metadata and chunk inventory | Yes |
| `DELETE` | `/documents/{id}` | Remove document and its chunks | Admin |
| `POST` | `/documents/{id}/reprocess` | Re-chunk and re-embed a document | Admin |
| `POST` | `/query` | Ask a question, get a cited answer | Yes |
| `GET` | `/sources` | Get the full source registry (for UI sidebar) | Yes |
| `POST` | `/laws` | Ingest law sections (Tier 1 or Tier 2) | Admin |
| `GET` | `/laws` | List indexed law codes | Yes |

### Request/Response Examples

```bash
# Health check
curl http://localhost:8088/health

# Upload a document
curl -X POST http://localhost:8088/documents \
  -F "file=@insurance-policy.pdf" \
  -F "domain=insurance" \
  -F "access_level=admin" \
  -F "effective_from=2025-01-01" \
  -F "effective_to=2026-12-31"

# Ask a question
curl -X POST http://localhost:8088/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Am I covered for a 2-hour flight delay?",
    "language": "en"
  }'

# Response includes:
{
  "answer": "Based on your Allianz travel insurance policy...",
  "citations": [
    {
      "document": "Allianz Travel Policy #12345",
      "section": "Section 4.2 — Travel Delay",
      "page": 7,
      "lines": "34-41",
      "text": "Coverage applies for delays exceeding 4 hours..."
    }
  ],
  "sources_searched": ["insurance"],
  "sources_not_available": ["consumer-law"],
  "confidence": "full_coverage"
}

# Get source registry
curl http://localhost:8088/sources
```

---

## Data Model

### Table: `advisor_documents`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | UUID | No | Primary key |
| title | TEXT | No | Document display name |
| filename | TEXT | No | Original filename |
| domain | TEXT | No | Category (insurance, employment, tenancy, tax, etc.) |
| doc_type | TEXT | No | contract, policy, benefit, law-full, law-index, other |
| language | VARCHAR(5) | No | ISO language code (sv, de, en) |
| access_level | TEXT | No | admin, family |
| tier | INT | No | 1 (full text), 2 (indexed reference) |
| coverage_note | TEXT | Yes | Human description of what's included |
| effective_from | DATE | Yes | Start of validity period |
| effective_to | DATE | Yes | End of validity period |
| source_url | TEXT | Yes | Link to official source (for Tier 2, laws) |
| file_hash | TEXT | No | SHA-256 of uploaded file (dedup) |
| created_at | TIMESTAMPTZ | No | Upload timestamp |
| updated_at | TIMESTAMPTZ | No | Last reprocessing |

### Table: `advisor_chunks`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | UUID | No | Primary key |
| document_id | UUID (FK) | No | Parent document |
| content | TEXT | No | Chunk text |
| embedding | VECTOR(384) | No | Sentence-transformer embedding |
| section_id | TEXT | Yes | Section/paragraph identifier (e.g., "kap. 12 § 24") |
| section_title | TEXT | Yes | Section heading |
| chapter | TEXT | Yes | Chapter identifier |
| page_number | INT | Yes | Source page (for PDFs) |
| line_start | INT | Yes | Start line in source |
| line_end | INT | Yes | End line in source |
| chunk_index | INT | No | Order within document |
| created_at | TIMESTAMPTZ | No | Creation timestamp |

### Table: `advisor_domains`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| id | UUID | No | Primary key |
| name | TEXT | No | Domain identifier (insurance, employment, etc.) |
| display_name | TEXT | No | Human-readable name |
| description | TEXT | Yes | What this domain covers |
| icon | TEXT | Yes | UI icon identifier |
| sort_order | INT | No | Display ordering |

### Indexes

- `advisor_chunks.embedding` — IVFFlat or HNSW index for vector similarity search
- `advisor_chunks.document_id` — Foreign key lookups
- `advisor_documents.domain` — Filter by category
- `advisor_documents.access_level` — Role-based filtering
- `advisor_documents.doc_type` — Filter by type

---

## Configuration

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DB_HOST` | `postgres` | Yes | PostgreSQL hostname |
| `DB_USER` | — | Yes | Database username |
| `DB_PASSWORD` | — | Yes | Database password |
| `DB_NAME` | `aspirant_online_db` | Yes | Database name |
| `OLLAMA_URL` | `http://ollama:11434` | Yes | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.1:8b-instruct-q4_K_M` | No | LLM model for generation |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | No | Sentence-transformer model name |
| `CHUNK_MAX_TOKENS` | `512` | No | Maximum chunk size |
| `RETRIEVAL_TOP_K` | `10` | No | Number of chunks to retrieve per query |
| `ADVISOR_DATA_PATH` | `/data/advisor` | No | Volume path for uploaded files |

---

## Constraints

- **Memory budget:** 2 GB for the advisor service itself (excluding Ollama)
- **Ollama container:** 6 GB memory limit (model weights + context)
- **Max upload size:** 50 MB per document
- **Embedding model:** ~90 MB (all-MiniLM-L6-v2), loaded once at startup
- **Dependencies:** PostgreSQL (with pgvector extension), Ollama
- **Response time target:** < 30 seconds for a grounded answer (CPU-only inference)

---

## Acceptance Criteria

- [ ] Health endpoint returns service status including Ollama and pgvector connectivity
- [ ] PDF upload produces section-aware chunks with page/line metadata
- [ ] Plain text and DOCX uploads produce chunks with preserved structure
- [ ] Law ingestion stores sections with proper citation identifiers (SFS format, BGB format)
- [ ] Vector search retrieves relevant chunks for a given question
- [ ] Generated answers cite only retrieved chunks — no hallucinated references
- [ ] Citation verification rejects LLM outputs that reference non-existent chunks
- [ ] Role-based filtering: family role cannot see admin-only documents
- [ ] Source registry endpoint returns complete inventory grouped by domain
- [ ] Source registry shows gaps (domains with no content)
- [ ] Each answer includes sources-searched, sources-matched, and sources-not-available
- [ ] Tier 2 sources return section metadata + URL instead of generated text
- [ ] Docker image builds and runs via docker-compose
- [ ] Service integrates with existing PostgreSQL instance
