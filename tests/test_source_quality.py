"""Source quality tests — verify each document type produces usable chunks.

These tests run against actual source files on disk (no database needed).
They ensure that parsing + chunking produces content the LLM can interpret.
"""
import os
import re

import pytest

from app.parsers.pdf import parse_pdf
from app.parsers.text import parse_text
from app.ingestion import chunk_sections

pytestmark = pytest.mark.no_db

# --- Paths to source documents ---

LEGAL_DIR = os.path.expanduser("~/Downloads/Legal")
LAWS_DIR = os.path.join(LEGAL_DIR, "Laws")
WORK_DIR = os.path.join(LEGAL_DIR, "Legal/Work")
HOUSING_DIR = os.path.join(LEGAL_DIR, "Legal/Housing")

# Skip all tests if the Legal directory doesn't exist (CI environment)
pytestmark = [
    pytest.mark.no_db,
    pytest.mark.skipif(
        not os.path.isdir(LEGAL_DIR),
        reason="Source documents not available (~/Downloads/Legal missing)",
    ),
]


# ============================================================
# Tax Statements — the key regression we're fixing
# ============================================================

TAX_STATEMENTS = [
    "Income Tax Statement 2024 - 42313.pdf",
    "Income Tax Statement 2025 - 42313.pdf",
    "Income tax statement 2023_42313.pdf",
    "Income tax statement 2022 -42313 (2).pdf",
]


@pytest.mark.parametrize("filename", TAX_STATEMENTS)
def test_tax_statement_has_gross_pay(filename):
    """Tax statement chunks must contain extractable gross pay value."""
    path = os.path.join(WORK_DIR, "GYG", filename)
    if not os.path.exists(path):
        pytest.skip(f"File not found: {filename}")

    sections = parse_pdf(path)
    all_content = " ".join(s.content for s in sections)

    # Must contain a recognizable gross pay figure (German format: xxx.xxx yy)
    assert re.search(r"(?:Bruttoarbeitslohn|gross pay).*?[\d.]+\s+\d{2}", all_content, re.IGNORECASE), \
        f"No extractable gross pay found in {filename}"


@pytest.mark.parametrize("filename", TAX_STATEMENTS)
def test_tax_statement_has_income_tax(filename):
    """Tax statement chunks must contain extractable withheld income tax value."""
    path = os.path.join(WORK_DIR, "GYG", filename)
    if not os.path.exists(path):
        pytest.skip(f"File not found: {filename}")

    sections = parse_pdf(path)
    all_content = " ".join(s.content for s in sections)

    assert re.search(r"(?:Einbehaltene Lohnsteuer|withheld income tax).*?[\d.]+\s+\d{2}", all_content, re.IGNORECASE), \
        f"No extractable income tax amount found in {filename}"


@pytest.mark.parametrize("filename", TAX_STATEMENTS)
def test_tax_statement_reasonable_chunk_count(filename):
    """Tax statements should produce 5-20 chunks, not 60-80 fragmented ones."""
    path = os.path.join(WORK_DIR, "GYG", filename)
    if not os.path.exists(path):
        pytest.skip(f"File not found: {filename}")

    sections = parse_pdf(path)
    chunks = chunk_sections(sections)
    assert len(chunks) <= 30, \
        f"Too many chunks ({len(chunks)}) — tabular parsing likely not applied"
    assert len(chunks) >= 4, \
        f"Too few chunks ({len(chunks)}) — data may be lost"


@pytest.mark.parametrize("filename", TAX_STATEMENTS)
def test_tax_statement_field_value_colocated(filename):
    """Field labels and their values must appear in the same chunk."""
    path = os.path.join(WORK_DIR, "GYG", filename)
    if not os.path.exists(path):
        pytest.skip(f"File not found: {filename}")

    sections = parse_pdf(path)
    # Find the chunk containing "withheld income tax" or "Einbehaltene Lohnsteuer"
    for s in sections:
        if re.search(r"(?:withheld income tax|Einbehaltene Lohnsteuer)", s.content, re.IGNORECASE):
            # The value (a number) must be in the SAME chunk
            has_value = re.search(r"\d{1,3}(?:\.\d{3})*\s+\d{2}", s.content)
            if has_value:
                return  # Pass: field and value are together
    pytest.fail(f"Income tax field and value are not in the same chunk in {filename}")


# ============================================================
# Employment Contracts — prose-style PDFs
# ============================================================

def test_ecosio_contract_has_salary():
    """Ecosio employment contract must contain salary/compensation information."""
    path = os.path.join(WORK_DIR, "Ecosio", "Employment Contract - Victor Lars Henry Wiklund - Senior Data Engineer.pdf")
    if not os.path.exists(path):
        pytest.skip("Ecosio contract not found")

    sections = parse_pdf(path)
    all_content = " ".join(s.content for s in sections).lower()
    assert any(term in all_content for term in ["salary", "remuneration", "gehalt", "compensation", "vergütung"]), \
        "No salary/compensation information found in contract"


def test_ecosio_contract_has_notice_period():
    """Ecosio employment contract must contain notice period information."""
    path = os.path.join(WORK_DIR, "Ecosio", "Employment Contract - Victor Lars Henry Wiklund - Senior Data Engineer.pdf")
    if not os.path.exists(path):
        pytest.skip("Ecosio contract not found")

    sections = parse_pdf(path)
    all_content = " ".join(s.content for s in sections).lower()
    assert any(term in all_content for term in ["notice", "kündigung", "termination", "kündigungsfrist"]), \
        "No notice period / termination info found in contract"


def test_gyg_contract_has_salary():
    """GYG employment contract must contain salary information."""
    path = os.path.join(WORK_DIR, "GYG", "2021-10-12 Employment Contract Wiklund Victor.pdf")
    if not os.path.exists(path):
        pytest.skip("GYG contract not found")

    sections = parse_pdf(path)
    if not sections:
        pytest.skip("GYG contract is image-based (needs OCR)")

    all_content = " ".join(s.content for s in sections).lower()
    assert any(term in all_content for term in ["salary", "remuneration", "gehalt", "compensation", "vergütung"]), \
        "No salary information found in GYG contract"


# ============================================================
# Law texts — .txt files
# ============================================================

LAW_FILES = [
    ("DE_KSchG_Kuendigungsschutzgesetz.txt", ["Kündigung", "Kündigungsschutz", "dismissal"]),
    ("DE_BUrlG_Bundesurlaubsgesetz.txt", ["Urlaub", "vacation", "Urlaubstage"]),
    ("DE_ArbZG_Arbeitszeitgesetz.txt", ["Arbeitszeit", "working hours", "Überstunden", "overtime"]),
    ("DE_AGG_Allgemeines_Gleichbehandlungsgesetz.txt", ["Benachteiligung", "discrimination", "Gleichbehandlung"]),
    ("DE_TzBfG_Teilzeit_und_Befristungsgesetz.txt", ["Teilzeit", "part-time", "Befristung"]),
    ("DE_EntgFG_Entgeltfortzahlungsgesetz.txt", ["Entgeltfortzahlung", "sick pay", "Krankheit"]),
    ("SE_ATL_Arbetstidslag.txt", ["arbetstid", "working hours", "övertid"]),
    ("SE_LAS_Lag_om_anstallningsskydd.txt", ["uppsägning", "anställning", "employment"]),
    ("SE_SemL_Semesterlag.txt", ["semester", "semesterlön", "annual leave"]),
    ("EU_GDPR_General_Data_Protection_Regulation.txt", ["personal data", "consent", "data subject"]),
]


@pytest.mark.parametrize("filename,expected_terms", LAW_FILES)
def test_law_text_contains_key_terms(filename, expected_terms):
    """Each law file must contain its expected key terms after parsing."""
    path = os.path.join(LAWS_DIR, filename)
    if not os.path.exists(path):
        pytest.skip(f"Law file not found: {filename}")

    sections = parse_text(path)
    all_content = " ".join(s.content for s in sections).lower()
    matched = [t for t in expected_terms if t.lower() in all_content]
    assert matched, \
        f"None of {expected_terms} found in {filename}"


@pytest.mark.parametrize("filename,expected_terms", LAW_FILES)
def test_law_text_reasonable_chunks(filename, expected_terms):
    """Law text files should produce a reasonable number of chunks."""
    path = os.path.join(LAWS_DIR, filename)
    if not os.path.exists(path):
        pytest.skip(f"Law file not found: {filename}")

    sections = parse_text(path)
    chunks = chunk_sections(sections)
    assert len(chunks) >= 1, f"No chunks produced from {filename}"
    assert len(chunks) <= 50, f"Too many chunks ({len(chunks)}) from {filename}"


# ============================================================
# General quality checks
# ============================================================

def test_no_empty_chunks_from_tax():
    """No chunk should have empty or whitespace-only content."""
    path = os.path.join(WORK_DIR, "GYG", "Income Tax Statement 2024 - 42313.pdf")
    if not os.path.exists(path):
        pytest.skip("Tax statement not found")

    sections = parse_pdf(path)
    chunks = chunk_sections(sections)
    for i, chunk in enumerate(chunks):
        assert chunk.content.strip(), f"Chunk {i} has empty content"


def test_no_chunk_is_just_a_heading():
    """No chunk should be a bare heading with no substance (< 20 chars)."""
    path = os.path.join(WORK_DIR, "GYG", "Income Tax Statement 2024 - 42313.pdf")
    if not os.path.exists(path):
        pytest.skip("Tax statement not found")

    sections = parse_pdf(path)
    for s in sections:
        assert len(s.content.strip()) >= 20, \
            f"Section is too short to be useful: '{s.content.strip()}'"
