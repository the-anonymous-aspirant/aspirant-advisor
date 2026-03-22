import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import RETRIEVAL_TOP_K
from app.embedding import get_embedding
from app.models import AdvisorChunk, AdvisorDocument

logger = logging.getLogger(__name__)


def retrieve_chunks(
    db: Session,
    question: str,
    access_level: str = "admin",
    domains: list[str] | None = None,
    top_k: int = RETRIEVAL_TOP_K,
) -> list[tuple[AdvisorChunk, AdvisorDocument, float]]:
    query_embedding = get_embedding(question)

    # Build the query with cosine distance
    distance = AdvisorChunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(AdvisorChunk, AdvisorDocument, distance.label("distance"))
        .join(AdvisorDocument, AdvisorChunk.document_id == AdvisorDocument.id)
        .where(AdvisorDocument.tier == 1)
    )

    # Role-based filtering
    access_levels = _expand_access(access_level)
    stmt = stmt.where(AdvisorDocument.access_level.in_(access_levels))

    # Domain filtering
    if domains:
        stmt = stmt.where(AdvisorDocument.domain.in_(domains))

    stmt = stmt.order_by(distance).limit(top_k)

    results = db.execute(stmt).all()
    logger.info(
        "Retrieved %d chunks for question (access=%s, domains=%s)",
        len(results), access_level, domains,
    )
    return [(row[0], row[1], row[2]) for row in results]


def _expand_access(access_level: str) -> list[str]:
    """Return the access levels visible to the given role."""
    if access_level == "admin":
        return ["admin", "family"]
    elif access_level == "family":
        return ["family"]
    else:
        return ["family"]
