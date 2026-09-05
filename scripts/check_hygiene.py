"""Fail if the repository carries anything that is not code or documentation.

Runs over tracked files only (``git ls-files``), so a local cache never
trips it. Checks:

1. No file under a data directory (``cache/``, ``data/``).
2. No data-file extension anywhere (csv, json, parquet, jsonl, archives, and
   ``.txt`` price files), checked case-insensitively.
3. No ``.env`` or key-looking file.
4. Every notebook has empty outputs and no execution counts.
5. Test fixtures are declared synthetic: every file under ``tests/`` is Python
   and mentions the word "synthetic".
6. No URL other than the Distill API in any Python file (package, examples,
   scripts, research, tests): a URL in code is a downloader.

Usage: python scripts/check_hygiene.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

DATA_DIRS = ("cache/", "data/")
DATA_EXT = {
    ".csv", ".tsv", ".parquet", ".json", ".jsonl", ".feather", ".arrow", ".pkl", ".pickle",
    ".zip", ".gz", ".bz2", ".xz", ".7z", ".xlsx", ".xls", ".dat", ".h5", ".hdf5", ".db", ".sqlite",
}
TXT_ALLOWLIST = {"requirements.txt"}
KEY_PATTERN = re.compile(r"\bdmk_[A-Za-z0-9]{8,}\b")
# Any URL in code that is not the Distill API is a downloader for something the
# project does not ship. Docs may name hosts; code may not fetch from them.
DOWNLOADER_PATTERN = re.compile(
    r"https?://(?!(?:[\w-]+\.)*distillmarkets\.com\b|[\w.-]*\.invalid\b|localhost\b|127\.0\.0\.1)[^\s'\")]+",
    re.I,
)
CODE_DIRS = ("distill_toolkit/", "examples/", "scripts/", "research/", "tests/")


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True).stdout
    return [Path(p) for p in out.decode().split("\0") if p]


def check_notebook(path: Path) -> list[str]:
    problems = []
    try:
        nb = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return [f"{path}: unreadable notebook ({e})"]
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        if cell.get("outputs"):
            problems.append(f"{path}: cell {i} has saved outputs")
        if cell.get("execution_count") is not None:
            problems.append(f"{path}: cell {i} has an execution count")
    return problems


def main() -> int:
    problems: list[str] = []
    for path in tracked_files():
        s = path.as_posix()
        if any(s.startswith(d) or f"/{d}" in s for d in DATA_DIRS):
            problems.append(f"{s}: tracked file under a data directory")
        suffix = path.suffix.lower()
        if suffix in DATA_EXT:
            problems.append(f"{s}: data-file extension")
        if suffix == ".txt" and path.name not in TXT_ALLOWLIST:
            problems.append(f"{s}: .txt file outside the allowlist (price files are .txt)")
        if s.startswith("tests/") and suffix != ".py":
            problems.append(f"{s}: only Python files belong under tests/ (fixtures are synthetic code)")
        if path.name == ".env" or path.name.startswith(".env.") and path.name != ".env.example":
            problems.append(f"{s}: environment file")
        if path.suffix == ".ipynb":
            problems.extend(check_notebook(path))
        if path.suffix in {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".ipynb"}:
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            if KEY_PATTERN.search(text):
                problems.append(f"{s}: contains something that looks like an API key")
            if s.startswith("tests/") and path.suffix == ".py" and "synthetic" not in text.lower():
                problems.append(f"{s}: test file does not declare its fixtures synthetic")
            if path.suffix == ".py" and s.startswith(CODE_DIRS) and DOWNLOADER_PATTERN.search(text):
                problems.append(f"{s}: URL to a third-party data host in code (no downloaders)")

    if problems:
        print("hygiene check FAILED:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("hygiene check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
