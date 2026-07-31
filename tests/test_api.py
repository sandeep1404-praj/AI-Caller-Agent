"""API endpoint tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from app import create_app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    app = create_app()

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


class TestAPIEndpoints:
    def test_status_endpoint(self, client):
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert "app_name" in data
        assert data["app_name"] == "Class Call Agent"

    def test_teachers_empty(self, client):
        response = client.get("/api/v1/teachers")
        assert response.status_code == 200
        assert response.json() == []

    def test_calls_empty(self, client):
        response = client.get("/api/v1/calls")
        assert response.status_code == 200
        assert response.json() == []

    def test_retry_empty(self, client):
        response = client.get("/api/v1/retry")
        assert response.status_code == 200
        assert response.json() == []

    def test_logs_empty(self, client):
        response = client.get("/api/v1/logs")
        assert response.status_code == 200
        assert response.json() == []

    def test_today_empty(self, client):
        response = client.get("/api/v1/today")
        assert response.status_code == 200
        assert response.json() == []

    def test_tomorrow_empty(self, client):
        response = client.get("/api/v1/tomorrow")
        assert response.status_code == 200
        assert response.json() == []

    def test_call_teacher_not_found(self, client):
        response = client.post("/api/v1/call/NONEXISTENT")
        assert response.status_code == 404

    def test_retry_teacher_not_found(self, client):
        response = client.post("/api/v1/retry/NONEXISTENT")
        assert response.status_code == 404
