import logging
import re

import httpx

from app.config import OLLAMA_MODEL, OLLAMA_URL
from app.models import AdvisorChunk, AdvisorDocument

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Always respond in English, even if sources are in another language.
Answer the question using ONLY the provided sources. Never use outside knowledge.
If the sources contain the answer, answer directly.
If not, say "I could not find this in the indexed documents."
Cite sources by name, like: [ecosio_contract] or [Employment Contract].

Sources may come from scanned PDFs where table layouts are garbled. Numbers near field labels
(like "4. withheld income tax" followed by "32.170 00") represent the value for that field.
German number format uses dots for thousands and commas for decimals (e.g. 32.170,00 = €32,170.00).
Extract and present these values clearly."""


def build_context(
    chunks: list[tuple[AdvisorChunk, AdvisorDocument, float]],
) -> str:
    context_parts = []
    for i, (chunk, doc, distance) in enumerate(chunks, start=1):
        section = chunk.section_title or ""
        page = f", p.{chunk.page_number}" if chunk.page_number else ""

        context_parts.append(
            f"--- Source: {doc.title}{f' | {section}' if section else ''}{page} ---\n"
            f"{chunk.content}\n"
        )

    return "\n".join(context_parts)


def generate_answer(
    question: str,
    chunks: list[tuple[AdvisorChunk, AdvisorDocument, float]],
) -> str:
    if not chunks:
        return "I cannot find information about this in the indexed sources."

    context = build_context(chunks)

    prompt = f"""{context}

Question: {question}"""

    response = _call_ollama(prompt)
    return response


def verify_citations(
    answer: str,
    chunks: list[tuple[AdvisorChunk, AdvisorDocument, float]],
) -> tuple[str, list[dict]]:
    """Verify that citations in the answer match retrieved chunks.
    Returns the (possibly cleaned) answer and a list of verified citations."""
    # Find all bracketed citations: [Source: ...], [DocTitle], [DocTitle | Section], etc.
    citation_pattern = re.compile(r"\[(?:Source:\s*)?([^\]]+)\]")
    citations_found = citation_pattern.findall(answer)

    # Collect matched document IDs from citations
    matched_doc_ids = set()

    for citation_text in citations_found:
        for chunk, doc, distance in chunks:
            if doc.title in citation_text or citation_text.strip() in doc.title:
                matched_doc_ids.add(str(doc.id))
                break

    # Fallback: if model didn't cite properly, use all retrieved documents
    if not matched_doc_ids:
        matched_doc_ids = {str(doc.id) for _, doc, _ in chunks}

    # Group all chunks by matched document
    matched_docs: dict[str, list] = {}
    for chunk, doc, distance in chunks:
        doc_id = str(doc.id)
        if doc_id in matched_doc_ids:
            if doc_id not in matched_docs:
                matched_docs[doc_id] = []
            matched_docs[doc_id].append((chunk, doc))

    # Consolidate: one citation entry per document
    verified_citations = []
    for doc_id, chunk_doc_pairs in matched_docs.items():
        doc = chunk_doc_pairs[0][1]
        sections = []
        pages = []
        best_text = ""
        for chunk, _ in chunk_doc_pairs:
            if chunk.section_title and chunk.section_title not in sections:
                sections.append(chunk.section_title)
            if chunk.page_number and chunk.page_number not in pages:
                pages.append(chunk.page_number)
            if len(chunk.content) > len(best_text):
                best_text = chunk.content
        verified_citations.append({
            "document_title": doc.title,
            "document_id": doc_id,
            "section_title": ", ".join(sections) if sections else None,
            "page_number": ", ".join(str(p) for p in sorted(pages)) if pages else None,
            "text": best_text[:300],
            "source_url": doc.source_url,
        })

    # Clean citation markers from the answer text for readability
    cleaned_answer = re.sub(r"\[(?:Source:\s*)?[^\]]+\]", "", answer).strip()
    # Collapse multiple spaces/newlines left by removed citations
    cleaned_answer = re.sub(r"  +", " ", cleaned_answer)
    cleaned_answer = re.sub(r"\n{3,}", "\n\n", cleaned_answer)

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
