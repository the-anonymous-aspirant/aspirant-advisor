import logging
import re
from dataclasses import dataclass, field

import pdfplumber

logger = logging.getLogger(__name__)


@dataclass
class ParsedSection:
    content: str
    page_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    section_title: str | None = None
    chapter: str | None = None


def parse_pdf(file_path: str) -> list[ParsedSection]:
    sections: list[ParsedSection] = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # Try table extraction first for structured/tabular PDFs
            tables = page.extract_tables()
            if tables and _is_tabular_page(tables, page):
                page_sections = _parse_tabular_page(tables, page_num)
                sections.extend(page_sections)
                continue

            # Fall back to text extraction for prose-style PDFs
            text = page.extract_text()
            if not text:
                continue

            page_sections = _split_page_into_sections(text, page_num)
            sections.extend(page_sections)

    # If pdfplumber extracted nothing, fall back to OCR
    if not sections:
        logger.info("No text extracted from PDF, falling back to OCR: %s", file_path)
        sections = _ocr_pdf(file_path)

    logger.info("Parsed PDF: %d sections from %s", len(sections), file_path)
    return sections


def _is_tabular_page(tables: list, page) -> bool:
    """Detect if a page is primarily tabular (e.g. tax statements, payslips).

    Heuristic: if the largest table covers most rows relative to page text lines,
    it's a tabular document where table extraction produces better results.
    """
    if not tables:
        return False
    largest_table = max(tables, key=len)
    # Tabular if the main table has 10+ rows (structured form)
    return len(largest_table) >= 10


def _parse_tabular_page(tables: list, page_number: int) -> list[ParsedSection]:
    """Parse a tabular page by extracting field-value pairs from tables.

    Groups related rows into chunks of ~5-8 fields each so the LLM
    gets enough context per chunk without drowning in a giant table.
    """
    lines = []
    for table in tables:
        for row in table:
            if not row:
                continue
            # row is [label, sub_label, euro_value, ct_value] or similar
            cells = [str(c).strip() if c else "" for c in row]
            # Skip empty rows
            if not any(cells):
                continue
            # Build a clean "label: value" line
            label = cells[0].replace("\n", " ").strip()
            # Try to find value in remaining cells
            value_parts = [c.replace("\n", " ").strip() for c in cells[1:] if c.strip() and c.strip() not in ("-------", "--")]
            if label and value_parts:
                value = " ".join(value_parts)
                lines.append(f"{label}: {value}")
            elif label:
                lines.append(label)

    if not lines:
        return []

    # Group into chunks of ~8 lines for reasonable context size
    chunk_size = 8
    sections = []
    for i in range(0, len(lines), chunk_size):
        chunk_lines = lines[i:i + chunk_size]
        content = "\n".join(chunk_lines)
        # Use first line as section title
        title = chunk_lines[0].split(":")[0].strip() if chunk_lines else None
        sections.append(ParsedSection(
            content=content,
            page_number=page_number,
            section_title=title,
        ))

    return sections


def _ocr_pdf(file_path: str) -> list[ParsedSection]:
    """Extract text from scanned/image PDFs using Tesseract OCR."""
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        logger.warning("OCR dependencies not available (pytesseract, pdf2image)")
        return []

    sections = []
    try:
        images = convert_from_path(file_path, dpi=300)
        for page_num, image in enumerate(images, start=1):
            text = pytesseract.image_to_string(image)
            if not text or not text.strip():
                continue

            page_sections = _split_page_into_sections(text, page_num)
            sections.extend(page_sections)
    except Exception as e:
        logger.error("OCR failed for %s: %s", file_path, e)

    return sections


# Matches common section/heading patterns:
# "1. Title", "1.1 Title", "Section 1", "Article 3", "CHAPTER IV", "§ 5"
_HEADING_PATTERN = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)*\.?\s+[A-Z]"  # "1. Title" or "1.1 Title"
    r"|(?:section|article|chapter|part|annex|schedule)\s+[\dIVXivx]+"  # "Section 1"
    r"|§\s*\d+"  # "§ 5"
    r"|[A-Z][A-Z\s]{4,}$"  # ALL CAPS HEADING
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def _split_page_into_sections(text: str, page_number: int) -> list[ParsedSection]:
    lines = text.split("\n")
    sections: list[ParsedSection] = []
    current_lines: list[str] = []
    current_title: str | None = None
    current_start: int = 1

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            current_lines.append(line)
            continue

        if _HEADING_PATTERN.match(stripped) and current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(ParsedSection(
                    content=content,
                    page_number=page_number,
                    line_start=current_start,
                    line_end=i - 1,
                    section_title=current_title,
                ))
            current_lines = [line]
            current_title = stripped
            current_start = i
        else:
            if not current_lines and not current_title:
                current_title = stripped if _HEADING_PATTERN.match(stripped) else None
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(ParsedSection(
                content=content,
                page_number=page_number,
                line_start=current_start,
                line_end=len(lines),
                section_title=current_title,
            ))

    # If no sections were found (no headings detected), return whole page as one section
    if not sections and text.strip():
        sections.append(ParsedSection(
            content=text.strip(),
            page_number=page_number,
            line_start=1,
            line_end=len(lines),
        ))

    return sections
