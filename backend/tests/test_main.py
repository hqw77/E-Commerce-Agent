
from app.main import app
from fastapi.testclient import TestClient


def test_application_lifespan():
    """Test FastAPI startup and shutdown lifecycle."""
    with TestClient(app) as client:
        assert client.app is app

    # Exiting the context manager triggers application shutdown.
