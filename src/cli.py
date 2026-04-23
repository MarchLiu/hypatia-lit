"""Hypatia CLI subprocess wrapper. Used only for shelf listing."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from src.models import ShelfInfo

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
        from src.models import HypatiaError
        raise HypatiaError(" ".join(args), result.returncode, result.stderr.strip())
    return result


def list_shelves(*, persistent_only: bool = False) -> list[ShelfInfo]:
    """List connected shelves.

    Args:
        persistent_only: If True, only return shelves whose path is under
            the user's home directory (excluding temp directories like
            /var/folders/, /tmp/, etc.).
    """
    result = _run(["list"])
    shelves: list[ShelfInfo] = []
    tmp_dir = tempfile.gettempdir()
    home_dir = os.path.expanduser("~")

    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        path = parts[1]

        if persistent_only:
            if path.startswith(tmp_dir):
                continue
            if not path.startswith(home_dir):
                continue
            if not os.path.isdir(path):
                continue

        shelves.append(ShelfInfo(name=name, path=path))
    return shelves
