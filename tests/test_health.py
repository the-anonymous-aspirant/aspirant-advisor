def test_app_imports():
    from app.main import app

    assert app is not None


def test_models_import():
    from app.models import AdvisorChunk, AdvisorDocument, AdvisorDomain

    assert AdvisorDocument.__tablename__ == "advisor_documents"
    assert AdvisorChunk.__tablename__ == "advisor_chunks"
    assert AdvisorDomain.__tablename__ == "advisor_domains"


def test_schemas_import():
    from app.schemas import (
        Citation,
        DocumentResponse,
        DomainSummary,
        QueryRequest,
        QueryResponse,
        SourceRegistryResponse,
    )

    req = QueryRequest(question="test")
    assert req.question == "test"


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_shape(client):
    data = client.get("/health").json()
    assert "status" in data
    assert "service" in data
    assert data["service"] == "advisor"
    assert "version" in data
    assert "checks" in data
    assert "database" in data["checks"]
    assert "pgvector" in data["checks"]
    assert "ollama" in data["checks"]
