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

    # Fixture use must be explicit so an incomplete production environment
    # cannot silently present demo aggregates as real analytics.
    ANALYTICS_DATA_SOURCE = os.getenv("ANALYTICS_DATA_SOURCE")
    # The aggregate fact is internal-only and has no fixture fallback.
    AGGREGATE_DATA_SOURCE = os.getenv("AGGREGATE_DATA_SOURCE")
    # Deliberately unset until the privacy policy owner chooses a threshold.
    ANALYTICS_MIN_COHORT_SIZE = os.getenv("ANALYTICS_MIN_COHORT_SIZE") or None
    HIGH_COST_MODEL_PATH = os.getenv("HIGH_COST_MODEL_PATH")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_TIMEOUT_SECONDS = int(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "20"))
    # Thinking is enabled only on the one-shot structured planner/answer
    # requests.  Legacy tool-call turns keep their original payload because
    # DeepSeek requires reasoning_content to be replayed on tool follow-ups.
    DEEPSEEK_THINKING_MODE = os.getenv("DEEPSEEK_THINKING_MODE", "enabled")
    DEEPSEEK_REASONING_EFFORT = os.getenv("DEEPSEEK_REASONING_EFFORT", "high")
    DEEPSEEK_STRUCTURED_MAX_TOKENS = int(
        os.getenv("DEEPSEEK_STRUCTURED_MAX_TOKENS", "4096")
    )

    MYSQL_HOST = os.getenv("MYSQL_HOST")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
    MYSQL_CONNECT_TIMEOUT = int(os.getenv("MYSQL_CONNECT_TIMEOUT", "3"))
    # Aggregate reads can scan the active fact through an SSH tunnel.  Keep
    # connection failure detection short without aborting a valid grouped
    # read after the connection has already been established.
    MYSQL_READ_TIMEOUT = int(os.getenv("MYSQL_READ_TIMEOUT", "30"))

    JSON_SORT_KEYS = False
