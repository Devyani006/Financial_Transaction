import os
import pytest
from unittest.mock import patch


# Markers

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: tests that require a running MySQL instance"
    )
    config.addinivalue_line(
        "markers", "unit: pure unit tests with no external dependencies"
    )


# Environment fixtures

@pytest.fixture
def mock_env():
    """
    Patch environment variables for config tests.
    This ensures tests don't depend on a real .env file.
    """
    env_vars = {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "3306",
        "DB_NAME": "financial_transaction_test",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_password",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def incomplete_env():
    env_vars = {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "3306",
        "DB_NAME": "financial_transaction_test",
    }
    keys_to_remove = ["DB_USER", "DB_PASSWORD"]
    original = {k: os.environ.get(k) for k in keys_to_remove}

    with patch.dict(os.environ, env_vars, clear=False):
        for k in keys_to_remove:
            os.environ.pop(k, None)
        yield env_vars

    for k, v in original.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


# Integration DB fixture

@pytest.fixture(scope="session")
def integration_engine():
    pytest.importorskip("sqlalchemy")

    test_db_url = (
        f"mysql+pymysql://{os.getenv('DB_USER', 'fti_app')}"
        f":{os.getenv('DB_PASSWORD', '')}"
        f"@{os.getenv('DB_HOST', '127.0.0.1')}"
        f":{os.getenv('DB_PORT', '3306')}"
        f"/financial_transaction_test"
        f"?charset=utf8mb4"
    )

    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(test_db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        yield engine
        engine.dispose()
    except Exception as e:
        pytest.skip(f"MySQL integration test DB not available: {e}")
