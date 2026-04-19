"""Hypatia CLI subprocess wrapper. All Hypatia interactions go through this module."""

from __future__ import annotations

import json
import shutil
import subprocess

from src.models import HypatiaError, ShelfInfo

# Locate hypatia binary
_HYPATIA_BIN = shutil.which("hypatia") or ""
_DEFAULT_TIMEOUT = 30


def _run(args: list[str], timeout: int = _DEFAULT_TIMEOUT) -> subprocess.CompletedProcess:
    """Execute a hypatia CLI command and return the result."""
    cmd = [_HYPATIA_BIN] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise HypatiaError(" ".join(args), result.returncode, result.stderr.strip())
    return result


def list_shelves() -> list[ShelfInfo]:
    """List connected shelves. Returns list of ShelfInfo."""
    result = _run(["list"])
    shelves: list[ShelfInfo] = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("name"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            shelves.append(ShelfInfo(name=parts[0], path=parts[1]))
    return shelves


def query_jse(jse: str, shelf: str = "default") -> list[dict] | None:
    """Execute a JSE query. Returns parsed JSON list, or None if no results."""
    result = _run(["query", jse, "-s", shelf])
    stdout = result.stdout.strip()
    if stdout == "No results found.":
        return None
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    except json.JSONDecodeError as e:
        raise HypatiaError(f"query {jse[:50]}...", 0, f"Invalid JSON output: {e}") from e


def search(
    query: str,
    *,
    shelf: str = "default",
    catalog: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict] | None:
    """Full-text search across knowledge and statements."""
    args = ["search", query, "-s", shelf, "--limit", str(limit), "--offset", str(offset)]
    if catalog:
        args.extend(["-c", catalog])
    result = _run(args)
    stdout = result.stdout.strip()
    if stdout == "No results found.":
        return None
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    except json.JSONDecodeError as e:
        raise HypatiaError(f"search {query[:30]}...", 0, f"Invalid JSON output: {e}") from e


def knowledge_get(name: str, shelf: str = "default") -> dict | None:
    """Get a single knowledge entry by exact name. Returns dict or None."""
    try:
        result = _run(["knowledge-get", name, "-s", shelf])
    except HypatiaError:
        return None
    stdout = result.stdout.strip()
    if not stdout or "not found" in stdout.lower():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def knowledge_create(
    name: str,
    data: str = "",
    tags: str = "",
    figures: str = "",
    shelf: str = "default",
) -> str:
    """Create a knowledge entry. Returns confirmation message."""
    args = ["knowledge-create", name, "-s", shelf]
    if data:
        args.extend(["-d", data])
    if tags:
        args.extend(["-t", tags])
    if figures:
        args.extend(["--figures", figures])
    result = _run(args)
    return result.stdout.strip()


def statement_create(
    subject: str,
    predicate: str,
    object: str,
    data: str = "",
    shelf: str = "default",
) -> str:
    """Create a statement triple. Returns confirmation message."""
    args = ["statement-create", subject, predicate, object, "-s", shelf]
    if data:
        args.extend(["-d", data])
    result = _run(args)
    return result.stdout.strip()
