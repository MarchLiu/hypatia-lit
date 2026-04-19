# Hypatia-Lit

Visual AI conversation interface for local [Hypatia](https://github.com/MarchLiu/hypatia) knowledge graphs.

Built with Streamlit + Claude API + ECharts.

## Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) package manager
- [Hypatia](https://github.com/MarchLiu/hypatia) CLI installed and available on `$PATH`
- Anthropic API key (or compatible endpoint)

## Install

```bash
git clone https://github.com/MarchLiu/hypatia-lit.git
cd hypatia-lit
uv sync
```

## Configure

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

`.env` contents:

```bash
# Required — at least one
ANTHROPIC_API_KEY=sk-ant-xxx
# or for compatible endpoints (OpenRouter, etc.):
# ANTHROPIC_AUTH_TOKEN=sk-or-v1-xxx

# Optional — custom API endpoint
# ANTHROPIC_BASE_URL=https://openrouter.ai/api
# ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
```

You can also configure the model and base URL at runtime from the sidebar.

## Run

### Web mode

```bash
uv run streamlit run app.py
```

Opens in your default browser at `http://localhost:8501`.

### Desktop mode

```bash
uv run hypatia-lit-desktop
```

Opens the app in a Chrome/Edge app window — no URL bar, no tabs, looks like a native desktop application. Uses a separate browser profile (`~/.cache/hypatia-lit`) so closing the app won't affect your regular browser session.

## Features

### Conversation with your knowledge graph

Ask questions in natural language. The AI agent translates them into Hypatia JSE queries and CLI commands, then presents the results with context.

### Interactive knowledge graph

Query results that contain relationships (subject-predicate-object triples) are automatically visualized as an interactive force-directed graph powered by ECharts. Drag nodes, zoom, and click to explore connections.

### Image display

Knowledge entries with `archive://` figure references are automatically fetched and displayed inline in the conversation.

### Export

Export the current conversation (including images and graph) as:

- **HTML** — self-contained file with inline ECharts JS, viewable offline in any browser
- **Markdown** — with base64-embedded images and Mermaid diagram blocks

## Project structure

```
hypatia-lit/
├── app.py              Streamlit entry point
├── run_desktop.py      Desktop launcher (Chrome app mode)
├── main.py             CLI entry point
├── pyproject.toml      Project config & dependencies
├── .env.example        Environment variable template
└── src/
    ├── agent.py        Claude SDK streaming agentic loop
    ├── cli.py          Hypatia CLI subprocess wrapper
    ├── export.py       HTML/Markdown export
    ├── graph.py        ECharts graph visualization
    ├── models.py       Data models (GraphNode, GraphEdge, etc.)
    ├── prompts.py      System prompt & tool definitions
    └── ui.py           Streamlit layout & session state
```

## Shelves

Hypatia organizes knowledge into shelves. The sidebar lets you switch between:

- `default` — your default shelf
- `euclid-fitzpatrick` — Euclid's Elements (Fitzpatrick translation)
- `euclid-heath` — Euclid's Elements (Heath translation)

## License

MIT
