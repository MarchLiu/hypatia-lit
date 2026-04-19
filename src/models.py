"""Pydantic data models for Hypatia-Lit. All models are frozen (immutable)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal


class HypatiaError(Exception):
    """Error from the Hypatia CLI."""

    def __init__(self, command: str, exit_code: int, stderr: str) -> None:
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(f"hypatia {command} failed (exit {exit_code}): {stderr}")


# ── Shelf ────────────────────────────────────────────────────────────────────


class ShelfInfo:
    __slots__ = ("name", "path")

    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self.path = path

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShelfInfo):
            return NotImplemented
        return self.name == other.name and self.path == other.path

    def __hash__(self) -> int:
        return hash((self.name, self.path))

    def __repr__(self) -> str:
        return f"ShelfInfo(name={self.name!r}, path={self.path!r})"


# ── Knowledge ────────────────────────────────────────────────────────────────


class KnowledgeContent:
    __slots__ = ("data", "format", "tags", "synonyms", "figures")

    def __init__(
        self,
        data: str,
        format: str = "markdown",
        tags: list[str] | None = None,
        synonyms: list[str] | None = None,
        figures: list[str] | None = None,
    ) -> None:
        self.data = data
        self.format = format
        self.tags = list(tags) if tags else []
        self.synonyms = list(synonyms) if synonyms else None
        self.figures = list(figures) if figures else None


class KnowledgeEntry:
    __slots__ = ("name", "content", "created_at")

    def __init__(self, name: str, content: KnowledgeContent, created_at: str) -> None:
        self.name = name
        self.content = content
        self.created_at = created_at

    @classmethod
    def from_dict(cls, d: dict) -> KnowledgeEntry:
        c = d.get("content", {})
        if isinstance(c, str):
            c = {"data": c}
        return cls(
            name=d["name"],
            content=KnowledgeContent(
                data=c.get("data", ""),
                format=c.get("format", "markdown"),
                tags=c.get("tags", []),
                synonyms=c.get("synonyms"),
                figures=c.get("figures"),
            ),
            created_at=d.get("created_at", ""),
        )


# ── Statement Triple ────────────────────────────────────────────────────────


class StatementTriple:
    __slots__ = ("subject", "predicate", "object", "content", "created_at")

    def __init__(
        self,
        subject: str,
        predicate: str,
        object: str,
        content: KnowledgeContent | None = None,
        created_at: str = "",
    ) -> None:
        self.subject = subject
        self.predicate = predicate
        self.object = object
        self.content = content
        self.created_at = created_at

    @classmethod
    def from_dict(cls, d: dict) -> StatementTriple:
        c = d.get("content", {})
        if isinstance(c, str):
            c = {"data": c}
        content = KnowledgeContent(
            data=c.get("data", ""),
            format=c.get("format", "markdown"),
            tags=c.get("tags", []),
            synonyms=c.get("synonyms"),
            figures=c.get("figures"),
        )
        return cls(
            subject=d.get("subject", ""),
            predicate=d.get("predicate", ""),
            object=d.get("object", ""),
            content=content,
            created_at=d.get("created_at", ""),
        )


# ── Graph Visualization ────────────────────────────────────────────────────


class GraphNode:
    __slots__ = ("id", "label", "node_type", "data")

    def __init__(
        self,
        id: str,
        label: str,
        node_type: Literal["knowledge", "entity", "search_result"] = "knowledge",
        data: dict | None = None,
    ) -> None:
        self.id = id
        self.label = label
        self.node_type = node_type
        self.data = dict(data) if data else {}


class GraphEdge:
    __slots__ = ("id", "source", "target", "label", "animated")

    def __init__(
        self,
        id: str,
        source: str,
        target: str,
        label: str = "",
        animated: bool = False,
    ) -> None:
        self.id = id
        self.source = source
        self.target = target
        self.label = label
        self.animated = animated


class GraphData:
    __slots__ = ("nodes", "edges")

    def __init__(
        self,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
    ) -> None:
        self.nodes = nodes
        self.edges = edges

    def with_node(self, node: GraphNode) -> GraphData:
        existing = {n.id for n in self.nodes}
        if node.id in existing:
            return self
        return GraphData(self.nodes + (node,), self.edges)

    def with_edge(self, edge: GraphEdge) -> GraphData:
        existing = {e.id for e in self.edges}
        if edge.id in existing:
            return self
        return GraphData(self.nodes, self.edges + (edge,))


# ── Tool Call Record ────────────────────────────────────────────────────────


class ToolCallRecord:
    __slots__ = ("tool_name", "tool_input", "tool_output", "duration_ms")

    def __init__(
        self,
        tool_name: str,
        tool_input: dict,
        tool_output: str,
        duration_ms: int,
    ) -> None:
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.tool_output = tool_output
        self.duration_ms = duration_ms
