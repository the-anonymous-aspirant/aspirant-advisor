import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine, ensure_pgvector
from app.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)


def seed_domains():
    from sqlalchemy.orm import Session

    from app.models import AdvisorDomain

    default_domains = [
        ("insurance", "Insurance", "Travel, health, liability, home insurance policies", "shield", 1),
        ("employment", "Employment", "Employment contracts, benefits, work regulations", "briefcase", 2),
        ("tenancy", "Tenancy", "Rental agreements, tenant rights, landlord obligations", "home", 3),
        ("tax", "Tax", "Tax regulations, declarations, deductions", "receipt", 4),
        ("consumer", "Consumer Rights", "Consumer protection, warranties, returns", "scale", 5),
        ("immigration", "Immigration", "Residence permits, visa, work permits", "globe", 6),
        ("finance", "Finance", "Banking, investments, loans, pension", "piggy-bank", 7),
        ("health", "Health", "Health insurance, medical benefits, prescriptions", "heart", 8),
        ("other", "Other", "Documents that don't fit other categories", "file", 99),
    ]

    with Session(engine) as db:
        for name, display, desc, icon, order in default_domains:
            existing = db.query(AdvisorDomain).filter_by(name=name).first()
            if not existing:
                db.add(AdvisorDomain(
                    name=name,
                    display_name=display,
                    description=desc,
                    icon=icon,
                    sort_order=order,
                ))
        db.commit()
    logger.info("Default domains seeded.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ensuring pgvector extension...")
    ensure_pgvector()

    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready.")

    seed_domains()

    logger.info("Loading embedding model...")
    from app.embedding import load_model
    load_model()
    logger.info("Embedding model ready.")

    yield

    logger.info("Shutting down.")


app = FastAPI(
    title="Aspirant Advisor",
    description="RAG-based document assistant with citation-grounded answers",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)
