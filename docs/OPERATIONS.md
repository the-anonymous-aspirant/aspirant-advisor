# Aspirant Advisor — Operations Guide

## Setup

### Prerequisites

- Docker and Docker Compose
- PostgreSQL with pgvector extension
- `.env` file with database credentials
- Ollama container (for LLM generation)

### First-Time Setup

```bash
# 1. Clone
git clone git@github.com:the-anonymous-aspirant/aspirant-advisor.git

# 2. Start via aspirant-deploy
cd ~/aspirant-deploy
docker compose -f docker-compose.dev.yml up -d postgres advisor ollama

# 3. Pull the LLM model (first time only, ~4.7 GB download)
docker compose exec ollama ollama pull llama3.1:8b-instruct-q4_K_M
```

### Production Setup

```bash
# On aspirant-cell
mkdir -p /data/aspirant/advisor/uploads
mkdir -p /data/aspirant/ollama

# Pull and start
cd ~/aspirant-deploy
docker compose pull advisor ollama
docker compose up -d --force-recreate advisor ollama
```

---

## How to Run

### Development

```bash
docker compose -f docker-compose.dev.yml up -d postgres advisor ollama
```

### Production

```bash
docker compose up -d advisor ollama
```

### Access Points

| Endpoint | URL |
|----------|-----|
| API root | http://localhost:8088 |
| Health check | http://localhost:8088/health |
| API docs (Swagger) | http://localhost:8088/docs |

---

## How to Test

### Health Check

```bash
curl http://localhost:8088/health
# Expected: {"status": "ok", "service": "advisor", ...}
```

### Upload a Document

```bash
curl -X POST http://localhost:8088/documents \
  -F "file=@contract.pdf" \
  -F "title=Employment Contract 2025" \
  -F "domain=employment" \
  -F "doc_type=contract" \
  -F "language=en" \
  -F "access_level=admin"
```

### Ask a Question

```bash
curl -X POST http://localhost:8088/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is my notice period?"}'
```

### Check Source Registry

```bash
curl http://localhost:8088/sources | python3 -m json.tool
```

### Automated Tests

```bash
# From the advisor repo directory
pip install -r requirements.txt pytest
pytest tests/ -v
```

---

## How to Debug

### Logs

```bash
docker compose logs -f advisor
docker compose logs -f ollama
```

### Database Inspection

```bash
docker compose exec postgres psql -U $DB_USER -d $DB_NAME

# Check documents
SELECT id, title, domain, doc_type, tier FROM advisor_documents;

# Check chunks for a document
SELECT id, section_title, page_number, chunk_index, length(content)
FROM advisor_chunks WHERE document_id = '<uuid>' ORDER BY chunk_index;

# Check domains
SELECT name, display_name FROM advisor_domains ORDER BY sort_order;

# Check pgvector
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```

### Ollama

```bash
# Check available models
docker compose exec ollama ollama list

# Pull a model
docker compose exec ollama ollama pull llama3.1:8b-instruct-q4_K_M

# Test generation directly
docker compose exec ollama ollama run llama3.1:8b-instruct-q4_K_M "Hello"
```

---

## Gotchas

| Gotcha | Explanation |
|--------|-------------|
| First startup is slow (~30s) | Embedding model (90 MB) loads into memory at startup |
| Ollama model must be pulled first | The advisor doesn't auto-pull models; run `ollama pull` once |
| pgvector extension required | The service creates it at startup, but the DB user needs CREATE EXTENSION privileges |
| LLM responses take 15-25s | CPU-only inference on i7-3770K; expected for 7B model |
| Ollama unloads after 5 min idle | First query after idle has extra latency (~10s model load) |
| `DB_HOST` must be `postgres` in Docker | Docker networking uses service names. `localhost` won't work |
| File uploads stored on disk | Uploaded files go to `/data/advisor/uploads/`; ensure the volume is mounted |
