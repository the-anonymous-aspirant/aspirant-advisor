"""Tests for generation and citation verification — no database required."""
import uuid
from unittest.mock import MagicMock

import pytest

from app.generation import build_context, verify_citations


pytestmark = pytest.mark.no_db


def _make_chunk(content, title="Test Doc", section="Section 1", page=1):
    chunk = MagicMock()
    chunk.id = uuid.uuid4()
    chunk.content = content
    chunk.section_id = None
    chunk.section_title = section
    chunk.chapter = None
    chunk.page_number = page
    chunk.line_start = 1
    chunk.line_end = 5
    chunk.chunk_index = 0

    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.title = title
    doc.source_url = None

    return chunk, doc, 0.1


def test_build_context_includes_metadata():
    chunks = [_make_chunk("Some content here")]
    context = build_context(chunks)
    assert "Test Doc" in context
    assert "Section 1" in context
    assert "Page: 1" in context
    assert "Some content here" in context


def test_verify_citations_passes_valid():
    chunks = [_make_chunk("Insurance covers delays over 4 hours.")]
    answer = "Coverage applies. [Source: Test Doc | Section 1 | Page 1]"
    cleaned, verified = verify_citations(answer, chunks)
    assert len(verified) == 1
    assert verified[0]["document_title"] == "Test Doc"
    assert "unverified" not in cleaned


def test_verify_citations_removes_invalid():
    chunks = [_make_chunk("Some content.")]
    answer = "Answer here. [Source: Nonexistent Doc | Section 3]"
    cleaned, verified = verify_citations(answer, chunks)
    assert len(verified) == 0
    assert "unverified" in cleaned


def test_verify_citations_handles_no_citations():
    chunks = [_make_chunk("Content.")]
    answer = "Just a plain answer with no citations."
    cleaned, verified = verify_citations(answer, chunks)
    assert cleaned == answer
    assert len(verified) == 0
