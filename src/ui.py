"""Streamlit UI layout, session state, and rendering for Hypatia-Lit."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import streamlit as st

from src.models import GraphData, ToolCallRecord


def get_model_config() -> tuple[str, str | None]:
    """Get model name and base_url from env vars or session state."""
    model = st.session_state.get("model", "") or os.getenv("ANTHROPIC_MODEL", "")
    base_url = st.session_state.get("base_url", "") or os.getenv("ANTHROPIC_BASE_URL", "")
    return model, base_url or None


def init_session_state() -> None:
    """Initialize Streamlit session state defaults."""
    defaults = {
        "messages": [],
        "active_shelf": "default",
        "graph_layout": "force",
        "current_graph": None,
        "selected_node": None,
        "model": "",
        "base_url": "",
        "image_store": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_sidebar() -> None:
    """Render the sidebar with configuration controls."""
    with st.sidebar:
        st.title("Hypatia-Lit")
        st.caption("Visual AI conversation for local Hypatia memory")

        st.divider()

        # Shelf selector
        st.subheader("Shelf")
        shelf = st.selectbox(
            "Active Shelf",
            ["default", "euclid-fitzpatrick", "euclid-heath"],
            index=["default", "euclid-fitzpatrick", "euclid-heath"].index(
                st.session_state.active_shelf
            ),
            key="shelf_selector",
        )
        st.session_state.active_shelf = shelf

        st.divider()

        # Model config
        st.subheader("Model")
        st.text_input(
            "Model",
            value=os.getenv("ANTHROPIC_MODEL", ""),
            placeholder="e.g. claude-sonnet-4-5-20250929",
            key="model",
            help="Leave empty to use env var ANTHROPIC_MODEL",
        )
        st.text_input(
            "Base URL",
            value=os.getenv("ANTHROPIC_BASE_URL", ""),
            placeholder="Optional custom API endpoint",
            key="base_url",
            help="Leave empty to use default Anthropic API",
        )

        st.divider()

        # Graph layout
        st.subheader("Graph")
        layout = st.radio(
            "Layout",
            ["force", "circular"],
            index=["force", "circular"].index(
                st.session_state.graph_layout
            ),
            horizontal=True,
        )
        st.session_state.graph_layout = layout

        st.divider()

        # Actions
        if st.button("Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.current_graph = None
            st.session_state.selected_node = None
            st.session_state.image_store = {}
            st.rerun()

        # Selected node info
        if st.session_state.selected_node:
            st.divider()
            st.subheader("Selected Node")
            st.code(st.session_state.selected_node)
            if st.button("Explore this node"):
                st.session_state.selected_node = None
                st.rerun()

        # Export section
        st.divider()
        st.subheader("Export")
        export_format = st.selectbox(
            "Format",
            ["HTML", "Markdown"],
            key="export_format",
        )

        if st.session_state.messages:
            from src.export import export_to_html, export_to_markdown

            if export_format == "HTML":
                content = export_to_html(
                    messages=st.session_state.messages,
                    image_store=st.session_state.image_store,
                    graph=st.session_state.current_graph,
                    graph_layout=st.session_state.graph_layout,
                )
                st.download_button(
                    "Export HTML",
                    data=content.encode("utf-8"),
                    file_name="hypatia-conversation.html",
                    mime="text/html",
                    use_container_width=True,
                )
            else:
                content = export_to_markdown(
                    messages=st.session_state.messages,
                    image_store=st.session_state.image_store,
                    graph=st.session_state.current_graph,
                )
                st.download_button(
                    "Export Markdown",
                    data=content.encode("utf-8"),
                    file_name="hypatia-conversation.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
        else:
            st.caption("No messages to export.")


def _block_attr(block: Any, key: str, default: Any = "") -> Any:
    """Safely get attribute from a block (dict or Pydantic model)."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def render_chat_history() -> None:
    """Render the chat message history."""
    for msg in st.session_state.messages:
        role = msg["role"]
        if role == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        elif role == "assistant":
            with st.chat_message("assistant"):
                content = msg.get("content", "")
                if isinstance(content, str):
                    st.markdown(content)
                elif isinstance(content, list):
                    for block in content:
                        btype = _block_attr(block, "type")
                        if btype == "text":
                            st.markdown(_block_attr(block, "text"))
                        elif btype == "tool_use":
                            with st.expander(f"Tool: {_block_attr(block, 'name', '?')}"):
                                st.json(_block_attr(block, "input", {}))


def stream_and_collect(
    agent_gen: Generator,
    placeholder: st.DeltaGenerator,
) -> tuple[str, list[GraphData], list[ToolCallRecord], list[str]]:
    """Consume the agent generator, streaming text and collecting graphs/images.

    Returns (full_text, graph_data_list, tool_call_records, image_paths).
    """
    full_text_parts: list[str] = []
    graphs: list[GraphData] = []
    tool_records: list[ToolCallRecord] = []
    image_paths: list[str] = []

    for item in agent_gen:
        if isinstance(item, str):
            full_text_parts.append(item)
            placeholder.markdown("".join(full_text_parts) + "▌")
        elif isinstance(item, GraphData):
            graphs.append(item)
        elif isinstance(item, ToolCallRecord):
            tool_records.append(item)
        elif isinstance(item, list):
            # Image paths from archive_get tool
            image_paths.extend(item)

    # Final render without cursor
    if full_text_parts:
        placeholder.markdown("".join(full_text_parts))

    return "".join(full_text_parts), graphs, tool_records, image_paths


def render_tool_calls(records: list[ToolCallRecord]) -> None:
    """Render tool call records as expandable sections."""
    for record in records:
        with st.expander(f"🔧 {record.tool_name} ({record.duration_ms}ms)"):
            st.json(record.tool_input)
            if record.tool_output:
                st.caption("Result:")
                st.text(record.tool_output[:300])


def render_graph_area(graph: GraphData | None) -> None:
    """Render the graph visualization area."""
    st.divider()
    graph_container = st.container()

    with graph_container:
        if graph and graph.nodes:
            st.subheader("Knowledge Graph")
            from src.graph import render_graph as do_render
            do_render(graph, st.session_state.graph_layout)
        else:
            st.subheader("Knowledge Graph")
            st.info(
                "No graph to display. Ask about relationships or connections "
                "to see a knowledge graph visualization."
            )
