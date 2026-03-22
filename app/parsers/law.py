import logging

from app.parsers.pdf import ParsedSection
from app.schemas import LawSectionInput

logger = logging.getLogger(__name__)


def parse_law_sections(sections: list[LawSectionInput]) -> list[ParsedSection]:
    parsed = []
    for i, section in enumerate(sections):
        if not section.content:
            continue

        parsed.append(ParsedSection(
            content=section.content,
            section_title=section.title,
            chapter=section.chapter,
        ))

    logger.info("Parsed %d law sections", len(parsed))
    return parsed
