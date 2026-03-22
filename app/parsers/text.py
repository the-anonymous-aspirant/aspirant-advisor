import logging
import re

from app.parsers.pdf import ParsedSection

logger = logging.getLogger(__name__)

_HEADING_PATTERN = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)*\.?\s+[A-Z]"
    r"|(?:section|article|chapter|part|§)\s+[\dIVXivx]+"
    r"|[A-Z][A-Z\s]{4,}$"
    r")",
    re.IGNORECASE,
)


def parse_text(file_path: str) -> list[ParsedSection]:
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sections: list[ParsedSection] = []
    current_lines: list[str] = []
    current_title: str | None = None
    current_start: int = 1

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        if _HEADING_PATTERN.match(stripped) and current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(ParsedSection(
                    content=content,
                    line_start=current_start,
                    line_end=i - 1,
                    section_title=current_title,
                ))
            current_lines = [line.rstrip()]
            current_title = stripped
            current_start = i
        else:
            current_lines.append(line.rstrip())

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(ParsedSection(
                content=content,
                line_start=current_start,
                line_end=len(lines),
                section_title=current_title,
            ))

    if not sections and lines:
        full_text = "".join(lines).strip()
        if full_text:
            sections.append(ParsedSection(
                content=full_text,
                line_start=1,
                line_end=len(lines),
            ))

    logger.info("Parsed text: %d sections from %s", len(sections), file_path)
    return sections
