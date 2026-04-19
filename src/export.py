"""Conversation export to HTML and Markdown."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from src.models import GraphData

_ECHARTS_CDN = "https://assets.pyecharts.org/assets/v6/echarts.min.js"

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hypatia-Lit Conversation Export</title>
<style>
:root {{ --bg: #fafafa; --user-bg: #e3f2fd; --assistant-bg: #fff; --border: #e0e0e0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: var(--bg); color: #333; line-height: 1.6; padding: 1rem; }}
header {{ max-width: 800px; margin: 0 auto 1rem; padding: 1rem;
          border-bottom: 2px solid var(--border); }}
header h1 {{ font-size: 1.4rem; }}
header p {{ font-size: 0.85rem; color: #666; }}
main {{ max-width: 800px; margin: 0 auto; }}
.msg {{ margin-bottom: 1rem; padding: 0.75rem 1rem; border-radius: 8px; }}
.msg.user {{ background: var(--user-bg); }}
.msg.assistant {{ background: var(--assistant-bg); border: 1px solid var(--border); }}
.msg .role {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
             color: #888; margin-bottom: 0.25rem; }}
.msg .content {{ white-space: pre-wrap; word-break: break-word; }}
.msg img {{ max-width: 100%; border-radius: 6px; margin-top: 0.5rem; }}
details {{ margin-top: 0.5rem; }}
details summary {{ cursor: pointer; font-size: 0.85rem; color: #666; }}
details pre {{ background: #f5f5f5; padding: 0.5rem; border-radius: 4px;
              font-size: 0.8rem; overflow-x: auto; }}
.graph-section {{ margin: 1.5rem 0; border-top: 2px solid var(--border);
                  padding-top: 1rem; }}
.graph-section h2 {{ font-size: 1.1rem; margin-bottom: 0.5rem; }}
hr {{ border: none; border-top: 1px solid var(--border); margin: 1rem 0; }}
</style>
</head>
<body>
<header>
<h1>Hypatia-Lit Conversation Export</h1>
<p>Exported at {timestamp} &mdash; Shelf: {shelf}</p>
</header>
<main>
{body}
</main>
</body>
</html>"""

_MSG_BUBBLE = """\
<div class="msg {role}">
<div class="role">{role_label}</div>
<div class="content">{content_html}</div>
{images}
</div>
"""

_TOOL_DETAILS = """\
<details>
<summary>Tool: {name}</summary>
<pre><code>{input_json}</code></pre>
</details>
"""


def export_to_html(
    messages: list[dict],
    image_store: dict[str, str],
    graph: GraphData | None,
    graph_layout: str,
) -> str:
    """Generate a self-contained HTML document from the conversation."""
    parts: list[str] = []

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")

        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = _render_content_blocks_html(content)
        else:
            text = html.escape(str(content))

        # Collect images for this message
        images_html = _collect_images_html(image_store, i)

        role_label = "User" if role == "user" else "Assistant"
        parts.append(
            _MSG_BUBBLE.format(
                role=role,
                role_label=role_label,
                content_html=html.escape(text) if isinstance(msg.get("content"), str) else text,
                images=images_html,
            )
        )

    # Graph section
    if graph and graph.nodes:
        graph_html = _build_graph_html(graph, graph_layout)
        parts.append(
            f'<div class="graph-section"><h2>Knowledge Graph</h2>'
            f"{graph_html}</div>"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    shelf = st.session_state.get("active_shelf", "default")
    body = "<hr>".join(parts)
    return _HTML_TEMPLATE.format(timestamp=timestamp, shelf=shelf, body=body)


def export_to_markdown(
    messages: list[dict],
    image_store: dict[str, str],
    graph: GraphData | None,
) -> str:
    """Generate a Markdown document from the conversation."""
    lines: list[str] = []

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    shelf = st.session_state.get("active_shelf", "default")
    lines.append("# Hypatia-Lit Conversation Export\n")
    lines.append(f"> Exported at {timestamp} | Shelf: {shelf}\n")
    lines.append("---\n")

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")

        role_label = "User" if role == "user" else "Assistant"

        if isinstance(content, str):
            lines.append(f"## {role_label}\n\n{content}\n")
        elif isinstance(content, list):
            text = _render_content_blocks_md(content)
            lines.append(f"## {role_label}\n\n{text}\n")

        # Images for this message
        for key, data_uri in sorted(image_store.items()):
            if key.startswith(f"msg_{i}_img_"):
                lines.append(f"\n![image]({data_uri})\n")

        lines.append("---\n")

    # Graph as Mermaid
    if graph and graph.nodes:
        lines.append("## Knowledge Graph\n")
        mermaid = _build_mermaid(graph)
        lines.append(f"```mermaid\n{mermaid}\n```\n")

    return "\n".join(lines)


def _render_content_blocks_html(blocks: list[dict]) -> str:
    """Render content blocks (text/tool_use) to HTML."""
    parts: list[str] = []
    for block in blocks:
        btype = block.get("type", "")
        if btype == "text":
            parts.append(html.escape(block.get("text", "")))
        elif btype == "tool_use":
            name = block.get("name", "?")
            input_json = json.dumps(block.get("input", {}), ensure_ascii=False, indent=2)
            parts.append(
                _TOOL_DETAILS.format(
                    name=html.escape(name),
                    input_json=html.escape(input_json),
                )
            )
        elif btype == "tool_result":
            # Skip internal tool results in export
            pass
    return "\n".join(parts)


def _render_content_blocks_md(blocks: list[dict]) -> str:
    """Render content blocks to Markdown."""
    parts: list[str] = []
    for block in blocks:
        btype = block.get("type", "")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "tool_use":
            name = block.get("name", "?")
            input_json = json.dumps(block.get("input", {}), ensure_ascii=False, indent=2)
            parts.append(
                f"<details><summary>Tool: {html.escape(name)}</summary>\n\n"
                f"```json\n{input_json}\n```\n\n</details>"
            )
        elif btype == "tool_result":
            pass
    return "\n\n".join(parts)


def _collect_images_html(image_store: dict[str, str], msg_idx: int) -> str:
    """Collect base64 images for a given message index as HTML img tags."""
    imgs: list[str] = []
    for key, data_uri in sorted(image_store.items()):
        if key.startswith(f"msg_{msg_idx}_img_"):
            imgs.append(f'<img src="{data_uri}" alt="image">')
    return "\n".join(imgs)


def _build_graph_html(graph: GraphData, layout: str) -> str:
    """Build the ECharts graph HTML for embedding in the export."""
    try:
        from src.graph import build_graph_chart, _inline_echarts_js

        chart = build_graph_chart(graph, layout, embed_js=False)
        html_content = chart.render_embed()
        # Inline the ECharts JS to make the export self-contained
        return _inline_echarts_js(html_content)
    except Exception:
        return _build_graph_html_fallback(graph, layout)


def _build_graph_html_fallback(graph: GraphData, layout: str) -> str:
    """Build graph HTML with CDN script tag when embed_js fails."""
    try:
        from src.graph import build_graph_chart

        chart = build_graph_chart(graph, layout, embed_js=False)
        return chart.render_embed()
    except Exception:
        # Last resort: text description
        lines = ["<p><strong>Graph Nodes:</strong></p><ul>"]
        for node in graph.nodes[:20]:
            lines.append(f"<li>{html.escape(node.label)} ({node.node_type})</li>")
        lines.append("</ul>")
        return "\n".join(lines)


def _build_mermaid(graph: GraphData) -> str:
    """Convert GraphData to a Mermaid flowchart definition."""
    lines = ["graph LR"]
    seen_ids: set[str] = set()

    for edge in graph.edges:
        # Mermaid-safe IDs (replace spaces and special chars)
        src = _mermaid_id(edge.source)
        tgt = _mermaid_id(edge.target)
        label = edge.label.replace('"', "'") if edge.label else ""
        if label:
            lines.append(f"    {src}[\"{edge.source}\"] -->|\"{label}\"| {tgt}[\"{edge.target}\"]")
        else:
            lines.append(f"    {src}[\"{edge.source}\"] --> {tgt}[\"{edge.target}\"]")
        seen_ids.add(edge.source)
        seen_ids.add(edge.target)

    # Add isolated nodes
    for node in graph.nodes:
        if node.id not in seen_ids:
            mid = _mermaid_id(node.id)
            lines.append(f"    {mid}[\"{node.id}\"]")

    return "\n".join(lines)


def _mermaid_id(raw: str) -> str:
    """Convert a raw string to a Mermaid-safe node ID."""
    return raw.replace(" ", "_").replace("-", "_").replace(".", "_").replace("/", "_")[:40]
