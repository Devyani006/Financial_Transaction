"""
app/config.py — Application Configuration
==========================================
Why python-dotenv?
  Keeping passwords in environment variables (not source code) is a fundamental
  security practice. This module loads those variables from a .env file and
  validates that every required variable is present before any code tries to
  use them. Fail fast with a helpful message is much better than cryptic errors
  deep inside SQLAlchemy connection code.
"""

import os
from dotenv import load_dotenv

# Load .env file from the project root (one level up from this file)
load_dotenv()


class ConfigError(Exception):
    """Raised when a required environment variable is missing."""
    pass


def _require(name: str) -> str:
    """Return the value of an env variable or raise ConfigError."""
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"Required environment variable '{name}' is missing or empty.\n"
            f"Copy .env.example to .env and fill in your values."
        )
    return value


class DatabaseConfig:
    """Holds all database connection parameters."""

    def __init__(self):
        self.host = _require("DB_HOST")
        self.port = int(os.getenv("DB_PORT", "3306"))
        self.name = _require("DB_NAME")
        self.user = _require("DB_USER")
        self.password = _require("DB_PASSWORD")

    @property
    def url(self) -> str:
        """
        SQLAlchemy connection URL using PyMySQL driver.
        Format: mysql+pymysql://user:password@host:port/database
        PyMySQL is a pure-Python MySQL driver — no native C extensions needed.
        """
        return (
            f"mysql+pymysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
            f"?charset=utf8mb4"
        )

    def __repr__(self) -> str:
        return (
            f"DatabaseConfig(host={self.host}, port={self.port}, "
            f"name={self.name}, user={self.user})"
        )


class AppConfig:
    """Top-level application configuration."""

    def __init__(self):
        self.db = DatabaseConfig()
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        # Anomaly detection threshold — transactions below this score are flagged
        self.anomaly_contamination = float(
            os.getenv("ANOMALY_CONTAMINATION", "0.02")
        )
        self.anomaly_random_seed = int(
            os.getenv("ANOMALY_RANDOM_SEED", "42")
        )


# Module-level singleton — import this in other modules
settings = AppConfig()
