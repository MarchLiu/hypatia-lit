"""Hypatia-Lit — Streamlit entry point."""

from __future__ import annotations

import base64
import mimetypes
import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from src.agent import run_agent
from src.models import GraphData, ToolCallRecord
from src.prompts import SYSTEM_PROMPT
from src.ui import (
    get_model_config,
    init_session_state,
    render_chat_history,
    render_graph_area,
    render_sidebar,
    render_tool_calls,
)

# Load .env from the project directory only (not from parent dirs)
_project_dir = os.path.dirname(os.path.abspath(__file__))
_env_file = os.path.join(_project_dir, ".env")
load_dotenv(_env_file, override=False)


def _get_persistent_shelves_from_session() -> list[str]:
    """Get cached persistent shelf names from session state."""
    return st.session_state.get("_cached_shelves", ["default"])


# ── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Hypatia-Lit",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()

# ── Sidebar ──────────────────────────────────────────────────────────────────

render_sidebar()

# ── API Key Check ────────────────────────────────────────────────────────────

_api_key = os.getenv("ANTHROPIC_API_KEY", "")
_auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN", "")

if not _api_key and not _auth_token:
    st.error(
        "Neither ANTHROPIC_API_KEY nor ANTHROPIC_AUTH_TOKEN is set. "
        "Please configure at least one in your environment or .env file."
    )
    st.stop()

# ── Main Area ────────────────────────────────────────────────────────────────

render_chat_history()

# Chat input
if prompt := st.chat_input("Ask about your Hypatia knowledge graph..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # Prepare model config
    model, base_url = get_model_config()
    if not model:
        st.error("Model not configured. Set ANTHROPIC_MODEL env var or in sidebar.")
        st.stop()

    # Debug: show effective API config (redact keys)
    _key_hint = (_api_key[:8] + "...") if _api_key else "(none)"
    _token_hint = (_auth_token[:8] + "...") if _auth_token else "(none)"
    st.caption(f"API: `{base_url or 'default'}` | Model: `{model}` | key: `{_key_hint}` | token: `{_token_hint}`")

    # Build system prompt with dynamic shelf list
    shelf_names = _get_persistent_shelves_from_session()
    shelves_str = ", ".join(shelf_names)
    system_prompt = SYSTEM_PROMPT.format(shelf=st.session_state.active_shelf, shelves=shelves_str)

    # Run agent in a chat message block
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        tool_container = st.container()
        image_container = st.container()

        agent_gen = run_agent(
            messages=st.session_state.messages,
            system_prompt=system_prompt,
            model=model,
            shelf=st.session_state.active_shelf,
            base_url=base_url,
            api_key=_api_key,
            auth_token=_auth_token,
        )

        full_text = []
        graphs: list[GraphData] = []
        tool_records = []
        all_image_paths: list[str] = []

        for item in agent_gen:
            if isinstance(item, str):
                full_text.append(item)
                response_placeholder.markdown("".join(full_text) + "▌")
            elif isinstance(item, GraphData):
                graphs.append(item)
            elif isinstance(item, ToolCallRecord):
                tool_records.append(item)
            elif isinstance(item, list):
                # Image paths from archive_get
                all_image_paths.extend(item)

        # Final text render
        if full_text:
            response_placeholder.markdown("".join(full_text))

        # Show tool calls
        if tool_records:
            with tool_container:
                render_tool_calls(tool_records)

        # Show images inline
        if all_image_paths:
            with image_container:
                for j, img_path in enumerate(all_image_paths):
                    if os.path.exists(img_path):
                        st.image(img_path, use_container_width=True)
                        # Capture base64 for export
                        mime = mimetypes.guess_type(img_path)[0] or "image/png"
                        with open(img_path, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode()
                        msg_idx = len(st.session_state.messages)
                        st.session_state.image_store[f"msg_{msg_idx}_img_{j}"] = (
                            f"data:{mime};base64,{b64}"
                        )

    # Store assistant response
    st.session_state.messages.append({
        "role": "assistant",
        "content": "".join(full_text),
    })

    # Update graph if new one was generated
    if graphs:
        st.session_state.current_graph = graphs[-1]

    st.rerun()
    st.stop()  # prevent render_graph_area from running in the same pass

# ── Graph Area ───────────────────────────────────────────────────────────────

render_graph_area(st.session_state.current_graph)


def main() -> None:
    """Entry point for `uv run hypatia-lit`."""
    import subprocess
    import sys

    subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])


if __name__ == "__main__":
    main()
