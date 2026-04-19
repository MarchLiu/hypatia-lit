"""Hypatia-Lit desktop launcher.

Opens Streamlit in a browser app window (Chrome/Safari/Edge app mode).
No URL bar, no tabs — looks and feels like a native desktop application.

Fallback order:
  1. Google Chrome  (--app flag, removes chrome)
  2. Microsoft Edge  (--app flag)
  3. Safari          (opens in new window, minimal chrome)
  4. Default browser
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

# Browsers that support --app mode (removes URL bar/tabs)
_APP_BROWSERS: list[tuple[str, list[str]]] = [
    ("Google Chrome", [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "chrome",
        "google-chrome",
    ]),
    ("Microsoft Edge", [
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "microsoft-edge",
        "msedge",
    ]),
    ("Chromium", [
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "chromium",
        "chromium-browser",
    ]),
]

# Browsers without --app mode (fallback)
_FALLBACK_BROWSERS: list[tuple[str, list[str]]] = [
    ("Safari", ["/Applications/Safari.app/Contents/MacOS/Safari", "safari"]),
]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _find_browser(candidates: list[str]) -> str | None:
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
        if name.startswith("/") and __import__("os").path.isfile(name):
            return name
    return None


def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            if resp.status == 200:
                return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def _get_user_data_dir() -> str:
    """Return a dedicated Chrome user-data-dir for the app (separate from regular Chrome)."""
    import os
    base = os.path.expanduser("~/.cache/hypatia-lit")
    os.makedirs(base, exist_ok=True)
    return base


def _open_in_app_mode(url: str, proc: subprocess.Popen) -> None:
    """Try to open URL in browser app mode. Falls back through browser list."""
    import os

    user_data_dir = _get_user_data_dir()

    # Try app-mode browsers first
    for browser_name, candidates in _APP_BROWSERS:
        exe = _find_browser(candidates)
        if exe:
            try:
                subprocess.Popen(
                    [
                        exe,
                        f"--app={url}",
                        f"--user-data-dir={user_data_dir}",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"Opened in {browser_name} app mode.", file=sys.stderr)
                _wait_and_cleanup(proc)
                return
            except OSError:
                continue

    # Fallback browsers (no --app flag)
    for browser_name, candidates in _FALLBACK_BROWSERS:
        exe = _find_browser(candidates)
        if exe:
            try:
                subprocess.Popen(
                    [exe, url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"Opened in {browser_name}.", file=sys.stderr)
                _wait_and_cleanup(proc)
                return
            except OSError:
                continue

    # Last resort: default browser
    import webbrowser
    webbrowser.open(url)
    print("Opened in default browser.", file=sys.stderr)
    _wait_and_cleanup(proc)


def _wait_and_cleanup(proc: subprocess.Popen) -> None:
    """Wait for the Streamlit process to exit, then clean up."""
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()


def main() -> None:
    import os

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    # Log file for Streamlit output
    log = tempfile.NamedTemporaryFile(
        mode="w", prefix="hypatia-lit-", suffix=".log", delete=False
    )
    log_path = log.name
    log.close()

    # Start Streamlit with file watcher disabled to prevent rerun-induced page opens
    env = {**os.environ, "STREAMLIT_SERVER_HEADLESS": "true"}
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run",
            "app.py",
            "--server.port", str(port),
            "--server.address", "127.0.0.1",
            "--server.headless=true",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
        ],
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT,
        env=env,
    )

    if not _wait_for_server(url):
        proc.terminate()
        proc.wait()
        with open(log_path) as f:
            err_output = f.read()
        print(f"Streamlit failed to start.\nLog: {log_path}\n{err_output}", file=sys.stderr)
        sys.exit(1)

    print(f"Hypatia-Lit running at {url} (log: {log_path})", file=sys.stderr)
    print("Press Ctrl+C to stop.", file=sys.stderr)

    _open_in_app_mode(url, proc)

    # Cleanup
    try:
        os.unlink(log_path)
    except OSError:
        pass


if __name__ == "__main__":
    main()
