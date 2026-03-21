#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


TEXT_CHECK_LABELS = {
    "bom": "contains a UTF-8 BOM",
    "trailing-whitespace": "has trailing whitespace",
    "missing-final-newline": "is missing a trailing newline",
}


def run_git(args: list[str], cwd: Path) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def get_repo_root() -> Path:
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    return Path(root)


def get_staged_paths(repo_root: Path) -> list[str]:
    output = run_git(
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=repo_root,
    )
    return [path.decode("utf-8") for path in output.split(b"\x00") if path]


def get_repo_paths(repo_root: Path) -> list[str]:
    output = run_git(["ls-files", "-z"], cwd=repo_root)
    return [path.decode("utf-8") for path in output.split(b"\x00") if path]


def get_staged_blob(repo_root: Path, path: str) -> bytes:
    return run_git(["show", "--no-textconv", f":{path}"], cwd=repo_root)


def get_worktree_blob(repo_root: Path, path: str) -> bytes:
    return (repo_root / path).read_bytes()


def is_binary(data: bytes) -> bool:
    return b"\x00" in data


def strip_line_ending(line: bytes) -> bytes:
    if line.endswith(b"\r\n"):
        return line[:-2]
    if line.endswith(b"\n") or line.endswith(b"\r"):
        return line[:-1]
    return line


def check_file(data: bytes) -> list[tuple[int | None, str]]:
    issues: list[tuple[int | None, str]] = []

    if data.startswith(b"\xef\xbb\xbf"):
        issues.append((1, "bom"))

    for line_number, line in enumerate(data.splitlines(keepends=True), start=1):
        if strip_line_ending(line).endswith((b" ", b"\t")):
            issues.append((line_number, "trailing-whitespace"))

    if data and not data.endswith((b"\n", b"\r")):
        issues.append((None, "missing-final-newline"))

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check text files for UTF-8 BOM, trailing whitespace, and missing final newlines."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all tracked files in the current worktree.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Check specific worktree paths instead of staged files.",
    )
    args = parser.parse_args()

    repo_root = get_repo_root()

    if args.paths:
        candidate_paths = args.paths
        read_blob = get_worktree_blob
    elif args.all:
        candidate_paths = get_repo_paths(repo_root)
        read_blob = get_worktree_blob
    else:
        candidate_paths = get_staged_paths(repo_root)
        read_blob = get_staged_blob

    if not candidate_paths:
        return 0

    failures: dict[str, list[tuple[int | None, str]]] = defaultdict(list)

    for relative_path in candidate_paths:
        data = read_blob(repo_root, relative_path)
        if is_binary(data):
            continue
        issues = check_file(data)
        if issues:
            failures[relative_path].extend(issues)

    if not failures:
        print("Staged text checks passed.")
        return 0

    print("Staged text checks failed:")
    for path in sorted(failures):
        print(f"- {path}")
        for line_number, issue_code in failures[path]:
            label = TEXT_CHECK_LABELS[issue_code]
            if line_number is None:
                print(f"  {label}")
            else:
                print(f"  line {line_number}: {label}")
    print("")
    print("Fix the files above and restage them before committing.")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            sys.stderr.buffer.write(exc.stderr)
        raise
