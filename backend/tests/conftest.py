import pytest
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, environment=Environment.TEST)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
