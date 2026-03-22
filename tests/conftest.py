import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def db():
    """Provide a database session — only for tests that need it."""
    from app.database import Base, SessionLocal, engine, ensure_pgvector

    try:
        ensure_pgvector()
    except Exception:
        pass
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    session.begin_nested()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db):
    """Provide a FastAPI test client with the test DB session injected."""
    from app.database import get_db
    from app.main import app

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
