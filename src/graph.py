"""Knowledge graph visualization using ECharts via pyecharts."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import streamlit as st
import streamlit.components.v1 as components

if TYPE_CHECKING:
    from src.models import GraphData

_ECHARTS_CDN = "https://assets.pyecharts.org/assets/v6/echarts.min.js"

# Node type → color
_NODE_COLORS: dict[str, str] = {
    "knowledge": "#5470c6",
    "entity": "#91cc75",
    "search_result": "#fac858",
}

_DEFAULT_COLOR = "#5470c6"

_MAX_NODES = 50


def _fetch_echarts_js() -> str | None:
    """Fetch ECharts JS with SSL verification disabled, cache in session state."""
    cached = st.session_state.get("_echarts_js_cache")
    if cached:
        return cached

    try:
        import httpx

        resp = httpx.get(
            _ECHARTS_CDN,
            timeout=15,
            follow_redirects=True,
            verify=False,
        )
        if resp.status_code == 200:
            js = resp.text
            st.session_state["_echarts_js_cache"] = js
            return js
    except Exception:
        pass
    return None


def _inline_echarts_js(html_content: str) -> str:
    """Replace CDN <script src> tags with inline <script> blocks."""
    echarts_js = _fetch_echarts_js()
    if not echarts_js:
        return html_content

    # Replace <script type="text/javascript" src="https://assets.pyecharts.org/assets/v6/echarts.min.js"></script>
    pattern = (
        r'<script\s+type="text/javascript"\s+src="'
        + re.escape(_ECHARTS_CDN)
        + r'"></script>'
    )

    def _replacer(_match: re.Match) -> str:
        return f'<script type="text/javascript">\n{echarts_js}\n</script>'

    return re.sub(pattern, _replacer, html_content)


def build_graph_chart(
    graph_data: GraphData,
    layout: str = "force",
    embed_js: bool = False,
) -> "pyecharts.charts.Graph":
    """Build a pyecharts Graph chart object without rendering.

    Reusable by both the Streamlit renderer and the export module.
    When embed_js=True, the ECharts JS library will be inlined in the HTML output.
    """
    from pyecharts.charts import Graph
    from pyecharts import options as opts
    from pyecharts.options import RenderOpts

    if not graph_data.nodes:
        raise ValueError("Graph has no nodes")

    # Limit nodes for performance
    if len(graph_data.nodes) > _MAX_NODES:
        node_ids = {n.id for n in graph_data.nodes[:_MAX_NODES]}
        display_nodes = graph_data.nodes[:_MAX_NODES]
        display_edges = tuple(
            e for e in graph_data.edges
            if e.source in node_ids and e.target in node_ids
        )
    else:
        display_nodes = graph_data.nodes
        display_edges = graph_data.edges

    # Count connections per node for sizing
    connection_counts: dict[str, int] = {}
    for edge in display_edges:
        connection_counts[edge.source] = connection_counts.get(edge.source, 0) + 1
        connection_counts[edge.target] = connection_counts.get(edge.target, 0) + 1

    # Build pyecharts nodes
    pe_nodes = []
    for node in display_nodes:
        color = _NODE_COLORS.get(node.node_type, _DEFAULT_COLOR)
        connections = connection_counts.get(node.id, 0)
        symbol_size = max(20, min(50, connections * 8 + 15))

        pe_nodes.append(
            opts.GraphNode(
                name=node.id,
                value=node.label,
                symbol_size=symbol_size,
                itemstyle_opts=opts.ItemStyleOpts(color=color),
                label_opts=opts.LabelOpts(
                    is_show=True,
                    position="right",
                    formatter="{b}",
                    font_size=12,
                ),
            )
        )

    # Build pyecharts links
    pe_links = []
    for edge in display_edges:
        pe_links.append(
            opts.GraphLink(
                source=edge.source,
                target=edge.target,
                value=edge.label or None,
                linestyle_opts=opts.LineStyleOpts(
                    curve=0.3,
                    width=1.5,
                    color="#aaa",
                ),
                symbol=["none", "arrow"],
                symbol_size=[4, 10],
            )
        )

    echarts_layout = layout if layout in ("force", "circular") else "force"

    graph = Graph(
        init_opts=opts.InitOpts(
            width="100%",
            height="500px",
            bg_color="transparent",
        ),
        render_opts=RenderOpts(is_embed_js=embed_js),
    )

    graph.add(
        series_name="",
        nodes=pe_nodes,
        links=pe_links,
        layout=echarts_layout,
        is_draggable=True,
        is_roam=True,
        repulsion=500,
        gravity=0.1,
        edge_length=[100, 300],
        is_layout_animation=True,
        friction=0.6,
        edge_symbol=["none", "arrow"],
        edge_symbol_size=[4, 10],
        emphasis_opts=opts.EmphasisOpts(
            focus="adjacency",
            blur_scope="coordinateSystem",
            linestyle_opts=opts.LineStyleOpts(width=3),
        ),
        label_opts=opts.LabelOpts(is_show=True, position="right", formatter="{b}"),
    )

    graph.set_global_opts(
        tooltip_opts=opts.TooltipOpts(trigger="item", is_confine=True),
        legend_opts=opts.LegendOpts(
            type_="scroll",
            pos_bottom="0%",
        ),
    )

    return graph


def render_graph(graph_data: GraphData, layout: str = "force") -> None:
    """Render an interactive knowledge graph in Streamlit using ECharts."""
    if not graph_data.nodes:
        st.info("No graph data to display.")
        return

    try:
        chart = build_graph_chart(graph_data, layout, embed_js=False)
    except Exception as e:
        st.warning(f"Could not build graph: {e}")
        _render_fallback(graph_data)
        return

    try:
        html_content = chart.render_embed()
        # Inline the ECharts JS to avoid CDN SSL failures
        html_content = _inline_echarts_js(html_content)
        components.html(html_content, height=520, scrolling=False)
    except Exception as e:
        st.error(f"Graph rendering error: {e}")
        _render_fallback(graph_data)


def _render_fallback(graph_data: GraphData) -> None:
    """Fallback graph rendering using st.graphviz_chart."""
    try:
        import graphviz

        dot = graphviz.Digraph()
        dot.attr(rankdir="LR")

        for node in graph_data.nodes:
            dot.node(node.id, node.label)
        for edge in graph_data.edges:
            dot.edge(edge.source, edge.target, label=edge.label)

        st.graphviz_chart(dot)
    except Exception:
        st.markdown("### Graph Nodes")
        for node in graph_data.nodes:
            st.markdown(f"- **{node.label}** ({node.node_type})")
        st.markdown("### Graph Edges")
        for edge in graph_data.edges:
            st.markdown(f"- {edge.source} → {edge.target} ({edge.label})")
