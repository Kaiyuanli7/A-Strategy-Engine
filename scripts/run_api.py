"""Launch the FastAPI server with uvicorn."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import uvicorn


def main() -> int:
    uvicorn.run(
        "astrategy.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
