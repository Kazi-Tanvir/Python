"""
Shared project configuration: root paths, environment loading, and env helpers.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project root (98_PYTHON directory)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env once at import time
load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------
def get_env(key: str, default: str = "") -> str:
    """Get an environment variable, with a default."""
    return os.getenv(key, default).strip()
