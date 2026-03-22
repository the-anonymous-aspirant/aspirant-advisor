import logging
import re

import httpx

from app.config import OLLAMA_MODEL, OLLAMA_URL
from app.models import AdvisorChunk, AdvisorDocument

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a document advisor that answers questions ONLY from the provided context.

Rules:
1. Answer ONLY based on the provided context chunks. Never use outside knowledge.
2. For every claim, cite the source using this exact format: [Source: DOCUMENT_TITLE | SECTION | Page PAGE_NUMBER]
3. If a section or page is not available, use what is available: [Source: DOCUMENT_TITLE | SECTION] or [Source: DOCUMENT_TITLE]
4. If the context does not contain enough information to answer, say: "I cannot find information about this in the indexed sources."
5. If the context partially answers the question, answer what you can and explicitly state what is not covered.
6. Be precise and quote relevant text when helpful.
7. When multiple sources are relevant, cite all of them.
"""


def build_context(
    chunks: list[tuple[AdvisorChunk, AdvisorDocument, float]],
) -> str:
    context_parts = []
    for i, (chunk, doc, distance) in enumerate(chunks, start=1):
        location_parts = []
        if chunk.section_title:
            location_parts.append(f"Section: {chunk.section_title}")
        if chunk.chapter:
            location_parts.append(f"Chapter: {chunk.chapter}")
        if chunk.page_number:
            location_parts.append(f"Page: {chunk.page_number}")
        if chunk.line_start:
            line_info = f"Lines: {chunk.line_start}"
            if chunk.line_end:
                line_info += f"-{chunk.line_end}"
            location_parts.append(line_info)

        location = " | ".join(location_parts) if location_parts else "No location"

        context_parts.append(
            f"[Chunk {i}] Document: {doc.title}\n"
            f"Location: {location}\n"
            f"Content:\n{chunk.content}\n"
        )

    return "\n---\n".join(context_parts)


def generate_answer(
    question: str,
    chunks: list[tuple[AdvisorChunk, AdvisorDocument, float]],
) -> str:
    if not chunks:
        return "I cannot find information about this in the indexed sources."

    context = build_context(chunks)

    prompt = f"""Context:
{context}

Question: {question}

Answer the question using ONLY the context above. Cite every claim."""

    response = _call_ollama(prompt)
    return response


def verify_citations(
    answer: str,
    chunks: list[tuple[AdvisorChunk, AdvisorDocument, float]],
) -> tuple[str, list[dict]]:
    """Verify that citations in the answer match retrieved chunks.
    Returns the (possibly cleaned) answer and a list of verified citations."""
    doc_titles = {doc.title for _, doc, _ in chunks}

    # Find all [Source: ...] citations
    citation_pattern = re.compile(r"\[Source:\s*([^\]]+)\]")
    citations_found = citation_pattern.findall(answer)

    verified_citations = []
    unverified = []

    for citation_text in citations_found:
        # Check if the document title appears in the citation
        matched = False
        for chunk, doc, distance in chunks:
            if doc.title in citation_text:
                citation_info = {
                    "document_title": doc.title,
                    "document_id": str(doc.id),
                    "section_id": chunk.section_id,
                    "section_title": chunk.section_title,
                    "page_number": chunk.page_number,
                    "line_start": chunk.line_start,
                    "line_end": chunk.line_end,
                    "text": chunk.content[:500],
                    "source_url": doc.source_url,
                }
                if citation_info not in verified_citations:
                    verified_citations.append(citation_info)
                matched = True
                break

        if not matched:
            unverified.append(citation_text)

    # Remove unverified citations from the answer
    cleaned_answer = answer
    for uv in unverified:
        cleaned_answer = cleaned_answer.replace(f"[Source: {uv}]", "[Source: unverified — removed]")
        logger.warning("Removed unverified citation: %s", uv)

    return cleaned_answer, verified_citations


def _call_ollama(prompt: str) -> str:
    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 512,
            "num_ctx": 4096,
        },
    }

    try:
        resp = httpx.post(url, json=payload, timeout=300.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
    except httpx.TimeoutException:
        logger.error("Ollama request timed out")
        return "Error: The language model timed out. Please try again."
    except Exception as e:
        logger.error("Ollama request failed: %s", e)
        return f"Error: Could not generate answer — {e}"
