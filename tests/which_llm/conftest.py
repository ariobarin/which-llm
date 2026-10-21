import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills" / "which-llm"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never download data into the tracked snapshot."""
    def refuse(*args, **kwargs):
        raise AssertionError("tests must not touch the network; patch urlopen")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
