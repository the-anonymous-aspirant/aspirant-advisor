"""Tests for document parsing and chunking — no database required."""
import os
import tempfile

import pytest

from app.parsers.pdf import ParsedSection, _split_page_into_sections
from app.parsers.text import parse_text
from app.ingestion import chunk_sections


pytestmark = pytest.mark.no_db


def test_chunk_sections_no_split():
    sections = [ParsedSection(content="Short text", page_number=1)]
    result = chunk_sections(sections, max_tokens=100)
    assert len(result) == 1
    assert result[0].content == "Short text"


def test_chunk_sections_splits_long():
    long_text = " ".join(["word"] * 200)
    sections = [ParsedSection(content=long_text, page_number=1)]
    result = chunk_sections(sections, max_tokens=100, overlap=20)
    assert len(result) >= 2
    assert len(result[0].content.split()) <= 100


def test_chunk_sections_preserves_metadata():
    sections = [ParsedSection(
        content=" ".join(["word"] * 200),
        page_number=3,
        section_title="Important Section",
    )]
    result = chunk_sections(sections, max_tokens=100, overlap=20)
    assert result[0].page_number == 3
    assert result[0].section_title == "Important Section"
    assert "cont." in result[1].section_title


def test_split_page_detects_headings():
    text = "1. Introduction\nThis is the intro.\n2. Details\nThis is the detail."
    sections = _split_page_into_sections(text, page_number=1)
    assert len(sections) >= 2


def test_parse_text_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("1. First Section\nContent of first section.\n2. Second Section\nContent of second.")
        f.flush()
        try:
            sections = parse_text(f.name)
            assert len(sections) >= 1
            assert any("Content" in s.content for s in sections)
        finally:
            os.unlink(f.name)
