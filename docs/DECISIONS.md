# Decision Log

### 2026-03-22 — pgvector over dedicated vector database

**Context:** Need vector similarity search for RAG retrieval. Options: pgvector extension, Qdrant, ChromaDB, Weaviate.

**Options considered:**
1. pgvector — PostgreSQL extension, no new service, simple
2. Qdrant — Dedicated vector DB, better features, another container to manage
3. ChromaDB — Lightweight, Python-native, but less mature

**Decision:** pgvector

**Rationale:** Already running PostgreSQL. Collection will be well under 1M chunks. Adding a dedicated vector DB introduces operational complexity without benefit at this scale. Simple over complicated.

---

### 2026-03-22 — Local embedding model over API

**Context:** Choosing how to generate embeddings for document chunks.

**Options considered:**
1. Local sentence-transformers (all-MiniLM-L6-v2) — Free, private, ~90 MB, 384 dimensions
2. OpenAI text-embedding-3-small — Better quality, but data leaves the server
3. Cohere embed-english-v3 — Good quality, same privacy concern

**Decision:** Local sentence-transformers

**Rationale:** Documents contain contracts, insurance policies, and legal text — highly sensitive. Privacy is non-negotiable. The model is small enough to run on CPU with negligible latency for batch embedding. Quality is sufficient for retrieval when combined with section-aware chunking.

---

### 2026-03-22 — Ollama as separate container over embedded LLM

**Context:** How to deploy the local LLM for answer generation.

**Options considered:**
1. Ollama in a separate container — Model management, shared across services, clear resource boundaries
2. llama-cpp-python embedded in the advisor process — Simpler deployment, but couples model lifecycle to the service

**Decision:** Separate Ollama container

**Rationale:** Ollama handles model downloads, GPU detection (future), and idle unloading. A separate container means the advisor service stays at 2 GB while Ollama manages its own 6 GB budget. Other services (e.g., transcriber) could share Ollama in the future.

---

### 2026-03-22 — Three-tier source model for law content

**Context:** How to handle large legal codes (Swedish SFS, German BGB) without degrading retrieval quality.

**Options considered:**
1. Upload everything as Tier 1 (full text) — Complete but dilutes relevance for personal queries
2. Curated Tier 1 subset + Tier 2 index — Focused retrieval with pointers to broader content
3. API-based on-demand fetch — Fetches from government sites as needed

**Decision:** Tier 1 (curated full text) + Tier 2 (indexed references with URLs) now; Tier 3 (on-demand) later

**Rationale:** Personal assistant queries are focused — a few dozen relevant law sections, not entire legal codes. Tier 1 gives grounded citations for what matters. Tier 2 provides discoverability without polluting the vector space. Matches "minimal and focused" principle.

---

### 2026-03-22 — Citation verification as post-processing over prompt-only

**Context:** Ensuring the LLM doesn't hallucinate citations.

**Options considered:**
1. Prompt-only ("cite only from context") — Simple, but models still occasionally fabricate references
2. Post-processing verification — Parse citations, match against retrieved chunks, strip unverified

**Decision:** Both — strict system prompt + post-processing verification

**Rationale:** Robust over fast. The post-processing step catches the cases where the prompt alone fails. Cost is trivial (regex + set lookup). For a system handling legal and financial documents, false citations are worse than no citation.
