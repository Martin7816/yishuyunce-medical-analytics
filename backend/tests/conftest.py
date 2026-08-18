from __future__ import annotations

import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app  # noqa: E402


@pytest.fixture
def make_client():
    def _make(repository):
        app = create_app({"TESTING": True}, repository=repository)
        return app.test_client()

    return _make
