#!/usr/bin/env python
"""Local web debug launcher for the src-layout project.

This script is intentionally independent from ``uv run`` and avoids importing
``xagent.web`` during argument parsing, so it is easier to use from PyCharm on
Windows.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


def ensure_project_layout() -> Path:
    """Switch to project root and add ``src`` to ``sys.path``."""
    project_root = Path(__file__).resolve().parent.parent
    src_dir = project_root / "src"

    os.chdir(project_root)

    src_str = str(src_dir)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    if src_str not in existing_pythonpath.split(os.pathsep):
        os.environ["PYTHONPATH"] = (
            src_str
            if not existing_pythonpath
            else src_str + os.pathsep + existing_pythonpath
        )

    return project_root


def load_local_env(project_root: Path) -> None:
    """Load local .env so debug launch matches ``python -m xagent.web`` behavior."""
    load_dotenv(project_root / ".env", override=False)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments for local debug usage."""
    parser = argparse.ArgumentParser(description="Run xagent web in local debug mode")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
    )
    return parser.parse_args()


def apply_default_args() -> None:
    """Provide friendly defaults when launched without arguments."""
    if len(sys.argv) > 1:
        return

    sys.argv.extend(["--reload", "--host", "127.0.0.1", "--port", "8000"])


def main() -> None:
    """Run uvicorn directly against the project app entrypoint."""
    project_root = ensure_project_layout()
    load_local_env(project_root)
    apply_default_args()
    args = parse_args()

    log_level = "debug" if args.debug else args.log_level

    uvicorn.run(
        "xagent.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
