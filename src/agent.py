"""Claude SDK streaming agentic loop for Hypatia-Lit."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Generator
from typing import Any

import anthropic

# Retryable error types
_RETRYABLE_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    ConnectionError,
    ConnectionResetError,
)

from src.cli import HypatiaError, knowledge_get, query_jse, search
from src.models import (
    GraphData,
    GraphEdge,
    GraphNode,
    ToolCallRecord,
)

# Pattern to detect archive:// references in text
_ARCHIVE_PATTERN = re.compile(r"archive://[^\s)\"'\]]+")

# Pattern to detect figures field in JSON content
_FIGURES_PATTERN = re.compile(r'"figures"\s*:\s*\[([^\]]*)\]')


def _extract_graph_from_statements(rows: list[dict]) -> GraphData | None:
    """Auto-extract graph data from statement query results."""
    if not rows:
        return None

    nodes_map: dict[str, GraphNode] = {}
    edges_list: list[GraphEdge] = []
    has_statements = False

    for row in rows:
        # Detect statement rows by presence of subject/predicate/object
        subject = row.get("subject", "")
        predicate = row.get("predicate", "")
        obj = row.get("object", "")

        if subject and predicate and obj:
            has_statements = True
            # Add nodes
            if subject not in nodes_map:
                nodes_map[subject] = GraphNode(id=subject, label=subject, node_type="entity")
            if obj not in nodes_map:
                nodes_map[obj] = GraphNode(id=obj, label=obj, node_type="entity")

            edge_id = f"{subject}-{predicate}-{obj}"
            edges_list.append(GraphEdge(
                id=edge_id,
                source=subject,
                target=obj,
                label=predicate,
                animated=True,
            ))

        # Also detect knowledge entries with name field
        name = row.get("name", "")
        if name and not has_statements:
            if name not in nodes_map:
                nodes_map[name] = GraphNode(id=name, label=name, node_type="knowledge")

    if not has_statements or len(nodes_map) < 2:
        return None

    return GraphData(
        nodes=tuple(nodes_map.values()),
        edges=tuple(edges_list),
    )


def _fetch_archive_file(archive_path: str, shelf: str = "default") -> str | None:
    """Fetch an archive file to a temp location. Returns local path or None."""
    try:
        from src.cli import _run

        name = archive_path.replace("archive://", "")
        # Create temp file with inferred extension
        ext = os.path.splitext(name)[1] or ".bin"
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.close()

        result = _run(["archive-get", name, "-o", tmp.name, "-s", shelf])
        if result.returncode == 0 and os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 0:
            return tmp.name
        os.unlink(tmp.name)
        return None
    except Exception:
        return None


def _extract_archive_refs(text: str) -> list[str]:
    """Extract archive:// references from text."""
    return _ARCHIVE_PATTERN.findall(text)


def _execute_tool(
    tool_name: str,
    tool_input: dict,
    shelf: str = "default",
) -> tuple[str, GraphData | None, list[str]]:
    """Execute a Hypatia tool. Returns (result_text, optional_graph_data, image_paths)."""
    graph_data = None
    image_paths: list[str] = []

    try:
        if tool_name == "hypatia_query":
            jse = tool_input["jse"]
            target_shelf = tool_input.get("shelf", shelf)
            rows = query_jse(jse, target_shelf)
            if rows is None:
                return "No results found.", None, []

            # Auto-extract graph from statement results
            graph_data = _extract_graph_from_statements(rows)

            # Check for archive references in the data
            for row in rows:
                content = row.get("content", {})
                if isinstance(content, dict):
                    figures = content.get("figures") or []
                    for fig in figures:
                        path = _fetch_archive_file(fig, target_shelf)
                        if path:
                            image_paths.append(path)

            result = json.dumps(rows, ensure_ascii=False, indent=2)
            return result, graph_data, image_paths

        elif tool_name == "hypatia_search":
            q = tool_input["query"]
            target_shelf = tool_input.get("shelf", shelf)
            catalog = tool_input.get("catalog")
            limit = tool_input.get("limit", 20)
            rows = search(query=q, shelf=target_shelf, catalog=catalog, limit=limit)
            if rows is None:
                return "No results found.", None, []
            result = json.dumps(rows, ensure_ascii=False, indent=2)
            return result, None, []

        elif tool_name == "hypatia_knowledge_get":
            name = tool_input["name"]
            target_shelf = tool_input.get("shelf", shelf)
            entry = knowledge_get(name, target_shelf)
            if entry is None:
                return f"Knowledge entry '{name}' not found.", None, []

            # Check for figures
            content = entry.get("content", {})
            if isinstance(content, dict):
                figures = content.get("figures") or []
                for fig in figures:
                    path = _fetch_archive_file(fig, target_shelf)
                    if path:
                        image_paths.append(path)

            return json.dumps(entry, ensure_ascii=False, indent=2), None, image_paths

        elif tool_name == "archive_get":
            archive_path = tool_input["path"]
            target_shelf = tool_input.get("shelf", shelf)
            local_path = _fetch_archive_file(archive_path, target_shelf)
            if local_path:
                image_paths.append(local_path)
                return f"Image loaded: {archive_path}", None, image_paths
            return f"Failed to retrieve archive: {archive_path}", None, []

        elif tool_name == "visualize_graph":
            nodes_raw = tool_input.get("nodes", [])
            edges_raw = tool_input.get("edges", [])
            layout = tool_input.get("layout", "force")

            nodes = tuple(
                GraphNode(
                    id=n["id"],
                    label=n["label"],
                    node_type=n.get("type", "knowledge"),
                    data={"layout": layout},
                )
                for n in nodes_raw
            )
            edges = tuple(
                GraphEdge(
                    id=f"{e['source']}-{e['target']}-{e.get('label', '')}",
                    source=e["source"],
                    target=e["target"],
                    label=e.get("label", ""),
                    animated=True,
                )
                for e in edges_raw
            )
            graph_data = GraphData(nodes=nodes, edges=edges)
            return (
                f"Graph visualization rendered: {len(nodes)} nodes, {len(edges)} edges (layout: {layout})",
                graph_data,
                [],
            )

        else:
            return f"Unknown tool: {tool_name}", None, []

    except HypatiaError as e:
        return f"Hypatia CLI error: {e}", None, []
    except Exception as e:
        return f"Error executing {tool_name}: {e}", None, []


def run_agent(
    messages: list[dict[str, Any]],
    system_prompt: str,
    tools: list[dict],
    *,
    model: str,
    shelf: str = "default",
    base_url: str | None = None,
    api_key: str = "",
    auth_token: str = "",
    max_tool_rounds: int = 10,
) -> Generator[str | GraphData | ToolCallRecord | list[str], None, None]:
    """Streaming agentic loop.

    Yields:
        - str: text deltas for streaming
        - GraphData: when graph data is extracted from results
        - ToolCallRecord: tool execution record
        - list[str]: image file paths to display
    """
    client_kwargs: dict[str, Any] = {
        "api_key": api_key or None,
        "auth_token": auth_token or None,
    }
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs)

    tool_call_records: list[ToolCallRecord] = []
    _retry_info: dict[str, int] = {"count": 0}

    for _ in range(max_tool_rounds):
        try:
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=tools,
            ) as stream:
                collected_text: list[str] = []

                for event in stream:
                    if event.type == "content_block_delta":
                        if hasattr(event, "delta") and hasattr(event.delta, "text"):
                            collected_text.append(event.delta.text)
                            yield event.delta.text

                final_message = stream.get_final_message()

        except _RETRYABLE_ERRORS as e:
            retried = _retry_info.get("count", 0)
            if retried < 3:
                wait = 2 ** retried
                _retry_info["count"] = retried + 1
                yield f"\n\n连接中断，{wait}秒后重试 ({retried + 1}/3)..."
                time.sleep(wait)
                continue
            yield f"\n\nAPI error after 3 retries: {e}"
            return

        except anthropic.APIError as e:
            yield f"\n\nAPI error: {e}"
            return

        # Append assistant message to history (convert Pydantic blocks to dicts)
        content_dicts = [
            b.model_dump() if hasattr(b, "model_dump") else dict(b)
            for b in final_message.content
        ]
        messages.append({"role": "assistant", "content": content_dicts})

        # Check if we need to execute tools
        tool_uses = [
            block for block in final_message.content if block.type == "tool_use"
        ]

        if not tool_uses or final_message.stop_reason != "tool_use":
            break

        # Execute all tool calls and collect results
        tool_results: list[dict] = []
        for tool_use in tool_uses:
            t0 = time.time()
            result_text, graph_data, image_paths = _execute_tool(
                tool_use.name, tool_use.input, shelf,
            )
            duration_ms = int((time.time() - t0) * 1000)

            record = ToolCallRecord(
                tool_name=tool_use.name,
                tool_input=tool_use.input,
                tool_output=result_text[:500],
                duration_ms=duration_ms,
            )
            tool_call_records.append(record)
            yield record

            if graph_data is not None:
                yield graph_data

            if image_paths:
                yield image_paths

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_text,
            })

        # Append tool results to messages
        messages.append({"role": "user", "content": tool_results})
