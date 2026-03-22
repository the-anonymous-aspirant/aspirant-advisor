import logging

from docx import Document

from app.parsers.pdf import ParsedSection

logger = logging.getLogger(__name__)


def parse_docx(file_path: str) -> list[ParsedSection]:
    doc = Document(file_path)
    sections: list[ParsedSection] = []
    current_lines: list[str] = []
    current_title: str | None = None
    current_start: int = 1
    line_num = 0

    for para in doc.paragraphs:
        line_num += 1
        text = para.text.strip()
        if not text:
            current_lines.append("")
            continue

        is_heading = para.style.name.startswith("Heading")

        if is_heading and current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(ParsedSection(
                    content=content,
                    line_start=current_start,
                    line_end=line_num - 1,
                    section_title=current_title,
                ))
            current_lines = [text]
            current_title = text
            current_start = line_num
        else:
            current_lines.append(text)
            if is_heading and current_title is None:
                current_title = text

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(ParsedSection(
                content=content,
                line_start=current_start,
                line_end=line_num,
                section_title=current_title,
            ))

    logger.info("Parsed DOCX: %d sections from %s", len(sections), file_path)
    return sections
