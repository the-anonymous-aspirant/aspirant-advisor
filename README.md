# Aspirant Advisor

RAG-based document assistant for querying personal contracts, insurance policies, benefits, and law. Answers are grounded exclusively in uploaded content with explicit citations — no hallucination.

## Key Features

- **Document ingestion** — Upload PDF, DOCX, or plain text. Section-aware chunking preserves page/line metadata.
- **Law support** — Import Swedish (SFS) and German (BGB) law sections with proper citation structure.
- **Citation-grounded Q&A** — Every claim references the exact document, section, and page. Citations are verified post-generation.
- **Role-based access** — Admin sees all sources; family sees a tagged subset.
- **Source transparency** — Always-visible registry shows what's indexed, what's partial, and what's missing.
- **Fully local** — Embeddings (sentence-transformers) and LLM (Ollama) run on the server. No data leaves your machine.

## Architecture

```
Client → Server (Go proxy) → Advisor (FastAPI :8088)
                                 ├── PostgreSQL + pgvector
                                 └── Ollama (Llama 3.1 8B)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full diagrams and data flow.

## Quick Start

### Development

```bash
# From aspirant-deploy directory
docker compose -f docker-compose.dev.yml up -d postgres advisor ollama
```

### Production

```bash
docker compose pull advisor ollama
docker compose up -d --force-recreate advisor ollama
```

### Health Check

```bash
curl http://localhost:8088/health
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health (DB, pgvector, Ollama) |
| `POST` | `/documents` | Upload and ingest a document |
| `GET` | `/documents` | List documents |
| `GET` | `/documents/{id}` | Document metadata + chunk count |
| `GET` | `/documents/{id}/chunks` | All chunks for a document |
| `DELETE` | `/documents/{id}` | Remove document and chunks |
| `POST` | `/documents/{id}/reprocess` | Re-chunk and re-embed |
| `POST` | `/query` | Ask a question, get cited answer |
| `GET` | `/sources` | Source registry (for UI sidebar) |
| `POST` | `/laws` | Ingest law sections (Tier 1 or 2) |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `postgres` | PostgreSQL host |
| `DB_USER` | `postgres` | Database user |
| `DB_PASSWORD` | `postgres` | Database password |
| `DB_NAME` | `aspirant_online_db` | Database name |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.1:8b-instruct-q4_K_M` | LLM for generation |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model |
| `ADVISOR_DATA_PATH` | `/data/advisor` | File storage path |

## Documentation

- [SPEC.md](docs/SPEC.md) — What and why
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — How it fits together
- [PLAN.md](docs/PLAN.md) — Development milestones
- [DECISIONS.md](docs/DECISIONS.md) — Key choices and rationale
- [OPERATIONS.md](docs/OPERATIONS.md) — Setup, run, test, debug
