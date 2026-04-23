"""Claude Agent SDK streaming agentic loop for Hypatia-Lit."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import queue
import threading
import time
from collections.abc import Generator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk._errors import CLIConnectionError

from src.models import (
    GraphData,
    GraphEdge,
    GraphNode,
    ToolCallRecord,
)


def _build_prompt(system_prompt: str, messages: list[dict]) -> str:
    """Build a complete prompt from system prompt and chat history."""
    parts = [system_prompt, "\n\n---\n"]

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                elif hasattr(block, "text"):
                    text_parts.append(block.text)
            content = "\n".join(text_parts)

        if role == "user":
            parts.append(f"User: {content}\n")
        elif role == "assistant":
            parts.append(f"Assistant: {content}\n")

    parts.append("Assistant: ")
    return "".join(parts)


def _extract_graph_from_statements(rows: list[dict]) -> GraphData | None:
    """Auto-extract graph data from statement query results."""
    if not rows:
        return None

    nodes_map: dict[str, GraphNode] = {}
    edges_list: list[GraphEdge] = []
    has_statements = False

    for row in rows:
        subject = row.get("subject", "")
        predicate = row.get("predicate", "")
        obj = row.get("object", "")

        if subject and predicate and obj:
            has_statements = True
            if subject not in nodes_map:
                nodes_map[subject] = GraphNode(
                    id=subject, label=subject, node_type="entity",
                )
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

        name = row.get("name", "")
        if name and not has_statements:
            if name not in nodes_map:
                nodes_map[name] = GraphNode(
                    id=name, label=name, node_type="knowledge",
                )

    if not has_statements or len(nodes_map) < 2:
        return None

    return GraphData(
        nodes=tuple(nodes_map.values()),
        edges=tuple(edges_list),
    )


def _try_parse_json_results(text: str) -> list[dict] | None:
    """Try to parse JSON array results from tool output text."""
    stripped = text.strip()

    # Try direct parse
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in text
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(stripped[start : end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


def _get_tool_result_text(block: ToolResultBlock) -> str:
    """Extract text content from a ToolResultBlock."""
    content = getattr(block, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        return "".join(parts)
    return str(content) if content else ""


async def _run_agent_async(
    prompt: str,
    options: ClaudeAgentOptions,
    output_queue: queue.Queue[tuple | None],
) -> None:
    """Run the agent in async context, putting results into the queue."""
    client = ClaudeSDKClient(options=options)

    try:
        await client.connect()
        await client.query(prompt)

        tool_start_time: float = 0.0
        current_tool_name = ""
        current_tool_input: dict = {}

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        output_queue.put(("text", block.text))

                    elif isinstance(block, ToolUseBlock):
                        tool_name = getattr(block, "name", "unknown")
                        tool_input = getattr(block, "input", {})
                        command = ""
                        if isinstance(tool_input, dict):
                            command = tool_input.get("command", str(tool_input))
                        else:
                            command = str(tool_input)

                        tool_start_time = time.monotonic()
                        current_tool_name = tool_name
                        current_tool_input = (
                            tool_input if isinstance(tool_input, dict)
                            else {"raw": str(tool_input)}
                        )

                        output_queue.put(("tool_call", {
                            "name": tool_name,
                            "input": current_tool_input,
                            "command": command,
                        }))

            elif isinstance(message, UserMessage):
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        duration_ms = int(
                            (time.monotonic() - tool_start_time) * 1000,
                        )
                        result_text = _get_tool_result_text(block)

                        output_queue.put(("tool_result", {
                            "name": current_tool_name,
                            "input": current_tool_input,
                            "duration_ms": duration_ms,
                            "result": result_text,
                        }))

            elif isinstance(message, ResultMessage):
                break

    except CLIConnectionError as e:
        output_queue.put(("error", f"Claude Code CLI 连接失败: {e}"))
    except Exception as e:
        output_queue.put(("error", f"Agent error: {e}"))
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        output_queue.put(None)  # Sentinel — agent is done


def run_agent(
    messages: list[dict[str, Any]],
    system_prompt: str,
    *,
    model: str,
    shelf: str = "default",
    base_url: str | None = None,
    api_key: str = "",
    auth_token: str = "",
    max_tool_rounds: int = 10,
) -> Generator[str | GraphData | ToolCallRecord | list[str], None, None]:
    """Streaming agentic loop using Claude Agent SDK.

    Runs the claude-agent-sdk client in a background thread and bridges
    async events to a synchronous generator for Streamlit.

    Yields:
        - str: text deltas for streaming
        - GraphData: when graph data is extracted from query results
        - ToolCallRecord: tool execution record
        - list[str]: image file paths to display
    """
    prompt = _build_prompt(system_prompt, messages)

    env: dict[str, str] = {}
    if model:
        env["ANTHROPIC_MODEL"] = model
    if base_url:
        env["ANTHROPIC_BASE_URL"] = base_url
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    if auth_token:
        env["ANTHROPIC_AUTH_TOKEN"] = auth_token

    options = ClaudeAgentOptions(
        permission_mode="acceptEdits",
        max_turns=max_tool_rounds,
        env=env,
        allowed_tools=["Bash", "Read"],
        cwd=str(pathlib.Path.home()),
        setting_sources=["project", "local"],
    )

    output_queue: queue.Queue[tuple | None] = queue.Queue()

    thread = threading.Thread(
        target=lambda: asyncio.run(
            _run_agent_async(prompt, options, output_queue),
        ),
        daemon=True,
    )
    thread.start()

    # State tracking for graph/image extraction
    last_tool_name = ""
    last_tool_command = ""

    while True:
        try:
            item = output_queue.get(timeout=300)
        except queue.Empty:
            yield "\n\nAgent timed out (no response for 5 minutes)."
            break

        if item is None:
            break

        kind, data = item

        if kind == "text":
            yield data

        elif kind == "error":
            yield f"\n\n{data}"

        elif kind == "tool_call":
            last_tool_name = data.get("name", "unknown")
            last_tool_command = data.get("command", "")

        elif kind == "tool_result":
            result_text = data.get("result", "")
            duration_ms = data.get("duration_ms", 0)
            tool_input = data.get("input", {})

            record = ToolCallRecord(
                tool_name=last_tool_name,
                tool_input=tool_input,
                tool_output=result_text[:500],
                duration_ms=duration_ms,
            )
            yield record

            # Extract graph data from hypatia query results
            if "hypatia query" in last_tool_command:
                rows = _try_parse_json_results(result_text)
                if rows:
                    graph = _extract_graph_from_statements(rows)
                    if graph:
                        yield graph

            # Extract image paths from archive-get results
            if "hypatia archive-get" in last_tool_command:
                for line in result_text.strip().splitlines():
                    line = line.strip()
                    if line and os.path.isfile(line):
                        yield [line]
                        break

    # Ensure the background thread finishes
    thread.join(timeout=5)
