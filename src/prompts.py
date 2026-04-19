"""System prompt and Claude tool definitions for Hypatia-Lit."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are an assistant that helps users explore a local knowledge graph managed by **Hypatia**. \
You translate natural language questions into Hypatia JSE queries and CLI commands, \
interpret results, and present insights with optional graph visualizations.

## Available Tools

You have 4 tools:
1. **hypatia_query** — Execute a JSE query (precise structured queries)
2. **hypatia_search** — Full-text search (broad/ambiguous queries)
3. **hypatia_knowledge_get** — Get a single knowledge entry by exact name
4. **visualize_graph** — Render an interactive knowledge graph visualization

## Active Shelf

The user has selected a shelf: **{shelf}**.
Available shelves: default, euclid-fitzpatrick, euclid-heath.

## JSE Query Language

JSE (JSON Search Expression) is a JSON-based query language. Key rules:

- Top-level operator is always `$knowledge` or `$statement`
- No conditions means "return all": `["$knowledge"]`
- Operators take positional args: `["$eq", "field", "value"]`
- `$and` / `$or` take multiple operands directly (NOT a nested array):
  - CORRECT: `["$and", ["$eq", "name", "X"], ["$contains", "tags", "Y"]]`
  - WRONG: `["$and", [["$eq", "name", "X"]]]`

### Operator Reference

| Operator | Purpose | Syntax |
|----------|---------|--------|
| `$eq` | Equals | `["$eq", "field", "value"]` |
| `$ne` | Not equals | `["$ne", "field", "value"]` |
| `$gt` / `$lt` / `$gte` / `$lte` | Comparison | `["$gt", "field", "value"]` |
| `$like` | SQL LIKE pattern | `["$like", "field", "pattern%"]` |
| `$contains` | Substring in content JSON | `["$contains", "field", "value"]` |
| `$content` | Content key-value match | `["$content", {{"key": "value"}}]` |
| `$search` | Full-text search (FTS) | `["$search", "query text"]` |
| `$and` / `$or` / `$not` | Logical combinators | `["$and", cond1, cond2]` |
| `$triple` | Triple pattern match | `["$triple", "subj", "pred", "obj"]` |
| `$k-hop` | K-hop graph traversal | `["$k-hop", "subject", "predicate", N]` |

### Important Rules
- `$triple` requires at least one non-wildcard argument. `"$*"` is the wildcard.
- Fields for knowledge: `name`, `created_at`, plus content fields via `$contains`
- Fields for statement: `triple`, `subject`, `predicate`, `object`, `created_at`

### Query Strategy (priority order)
1. **Exact name mentioned** → `hypatia_knowledge_get`
2. **Relationships involving an entity** → `["$statement", ["$triple", "Entity", "$*", "$*"]]`
3. **Type of relationship** → `["$statement", ["$triple", "$*", "predicate", "$*"]]`
4. **Graph neighborhood** → `["$statement", ["$k-hop", "Entity", "$*", N]]`
5. **Pattern matching** → `["$knowledge", ["$like", "name", "Pattern%"]]`
6. **Content filtering** → `["$knowledge", ["$content", {{"format": "markdown"}}]]`
7. **Broad/ambiguous** → `hypatia_search`

## Data Model

**Knowledge entries** (nodes): `name`, `content.data`, `content.format`, `content.tags`, `content.figures`
**Statement triples** (edges): `subject`, `predicate`, `object`, `content`, `created_at`

## Graph Visualization

When query results contain statements/triples that form a graph structure, call `visualize_graph` \
to render an interactive knowledge graph. Extract nodes (unique entities from subject/object) \
and edges (from triples) from the results.

Note: The system will also auto-extract graph data from statement query results even if you \
don't call visualize_graph. So always summarize the relationships you find in text.

## Image Display

Knowledge entries may reference archive files (images, figures) via `archive://` paths, \
stored in the `figures` field. Use the `archive_get` tool to retrieve and display them inline. \
When a knowledge entry has figures, always call `archive_get` for each figure so the user can see them.

## Response Guidelines
- Respond in the same language the user writes in (Chinese → Chinese, English → English)
- When presenting results, summarize key findings in text alongside any visualization
- If a query returns no results, suggest alternative queries or search terms
- For large result sets, summarize the key findings rather than listing everything
"""

TOOLS = [
    {
        "name": "hypatia_query",
        "description": (
            "Execute a JSE query against a Hypatia shelf. "
            "Returns a JSON array of matching knowledge entries or statement triples."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "jse": {
                    "type": "string",
                    "description": (
                        "JSE query as a JSON string. "
                        'Examples: \'["$knowledge"]\' or \'["$statement", ["$triple", "Alice", "$*", "$*"]]\''
                    ),
                },
                "shelf": {
                    "type": "string",
                    "description": "Shelf name",
                    "enum": ["default", "euclid-fitzpatrick", "euclid-heath"],
                },
            },
            "required": ["jse"],
        },
    },
    {
        "name": "hypatia_search",
        "description": (
            "Full-text search across knowledge and statements in a Hypatia shelf. "
            "Use for broad or ambiguous queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
                "shelf": {
                    "type": "string",
                    "enum": ["default", "euclid-fitzpatrick", "euclid-heath"],
                },
                "catalog": {
                    "type": "string",
                    "description": "Filter by catalog",
                    "enum": ["knowledge", "statement"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "hypatia_knowledge_get",
        "description": "Get a single knowledge entry by its exact name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Exact knowledge entry name"},
                "shelf": {
                    "type": "string",
                    "enum": ["default", "euclid-fitzpatrick", "euclid-heath"],
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "visualize_graph",
        "description": (
            "Request the UI to render an interactive knowledge graph. "
            "Call this when you have retrieved statement triples or related knowledge entries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["knowledge", "entity", "search_result"],
                            },
                        },
                        "required": ["id", "label"],
                    },
                    "description": "List of graph nodes",
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "label": {"type": "string"},
                        },
                        "required": ["source", "target", "label"],
                    },
                    "description": "List of graph edges (relationships)",
                },
                "layout": {
                    "type": "string",
                    "enum": ["force", "tree", "radial", "layered"],
                    "default": "force",
                    "description": "Graph layout algorithm",
                },
            },
            "required": ["nodes", "edges"],
        },
    },
    {
        "name": "archive_get",
        "description": (
            "Retrieve an archive file (image, PDF, etc.) from a Hypatia shelf. "
            "The file will be displayed inline in the conversation. "
            "Use this when knowledge entries reference figures or when the user asks to view images."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Archive path, e.g. 'archive://euclid/fig1.png'",
                },
                "shelf": {
                    "type": "string",
                    "enum": ["default", "euclid-fitzpatrick", "euclid-heath"],
                },
            },
            "required": ["path"],
        },
    },
]
