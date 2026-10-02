import pytest
from fastapi.testclient import TestClient

from app.ai.base import AIProvider
from app.config import Settings
from app.main import create_app


def _client(provider: AIProvider | None) -> TestClient:
    # provider_factory is always explicit so tests never reach a real API,
    # even when a developer's .env holds a real key.
    app = create_app(
        Settings(database_url="sqlite:///:memory:"), provider_factory=lambda _s: provider
    )
    return TestClient(app)


@pytest.fixture
def client():
    with _client(None) as c:
        yield c


@pytest.fixture
def make_client():
    opened: list[TestClient] = []

    def make(provider: AIProvider | None) -> TestClient:
        c = _client(provider)
        c.__enter__()
        opened.append(c)
        return c

    yield make
    for c in opened:
        c.__exit__(None, None, None)
