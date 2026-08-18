"""Environment-based configuration. Real secrets belong in backend/.env."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    # Flask can still run with environment variables. python-dotenv is listed
    # in requirements.txt for normal local development.
    pass


class Config:
    APP_ROOT = Path(__file__).resolve().parent

    # The source must be selected explicitly. Missing or unknown values fail
    # closed instead of silently serving the development fixture.
    TOP10_DATA_SOURCE = os.getenv("TOP10_DATA_SOURCE")
    TOP10_FIXTURE_STATE = os.getenv("TOP10_FIXTURE_STATE", "success")

    MYSQL_HOST = os.getenv("MYSQL_HOST")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
    MYSQL_CONNECT_TIMEOUT = int(os.getenv("MYSQL_CONNECT_TIMEOUT", "3"))

    JSON_SORT_KEYS = False
