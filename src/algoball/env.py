"""Tiny .env loader (stdlib only — no python-dotenv dependency)."""
from __future__ import annotations

import os

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_env(path: str = None) -> None:
    """Load KEY=VALUE lines from a .env file into os.environ (does not overwrite existing)."""
    path = path or os.path.join(_PROJECT_ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def get_odds_api_key() -> str:
    load_env()
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ODDS_API_KEY not found. Add it to .env as: ODDS_API_KEY=your_key_here"
        )
    return key
