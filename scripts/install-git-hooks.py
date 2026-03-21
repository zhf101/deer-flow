#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    hook_path = repo_root / "githooks" / "pre-commit"

    subprocess.run(
        ["git", "-C", str(repo_root), "config", "--local", "core.hooksPath", "githooks"],
        check=True,
    )

    current_mode = hook_path.stat().st_mode
    hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print("Configured Git hooks path to githooks")
    print(f"pre-commit hook is ready at {hook_path}")
    if os.name == "nt":
        print("Git for Windows will use this hook on the next commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
