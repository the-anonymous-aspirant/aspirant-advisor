# Changelog

### 2026-11-05
- Builds of main's image now run one at a time, and `:latest` and `:main` go
  only on a build of main's current head (`scripts/is-main-head.sh`, unit test
  `sh tests/is_main_head_unit.sh`). Two merges landing seconds apart, or a
  re-run of an older build, can no longer leave `:latest` on an older commit
  for auto-pull to deploy. Test runs are not queued. See system_3 #9984, from
  #9966 (the same guard as aspirant-client #409).

### 2026-03-22
- Initial spec, architecture, and development plan created
- Scaffold from aspirant-deploy template
- Implemented core service: models, config, database with pgvector
- Document ingestion pipeline: PDF, DOCX, plain text parsers with section-aware chunking
- Embedding via sentence-transformers (all-MiniLM-L6-v2, local CPU)
- RAG query pipeline: vector retrieval → Ollama generation → citation verification
- Role-based access filtering (admin/family)
- Source registry endpoint with gap indicators and domain seeding
- Law ingestion endpoint (Tier 1 full text, Tier 2 indexed references)
- Health endpoint checking database, pgvector, and Ollama
- Tests for imports, chunking, and citation verification
- Dockerfile and CI workflow
