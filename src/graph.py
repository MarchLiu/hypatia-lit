"""Knowledge graph visualization using HTML Canvas 2D — zero dependencies."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import streamlit as st
import streamlit.components.v1 as components

if TYPE_CHECKING:
    from src.models import GraphData

_MAX_NODES = 50

_NODE_COLORS: dict[str, str] = {
    "knowledge": "#5470c6",
    "entity": "#91cc75",
    "search_result": "#fac858",
}
_DEFAULT_COLOR = "#5470c6"


def build_graph_html(graph_data: GraphData, layout: str = "force") -> str:
    """Build a self-contained HTML string with Canvas 2D force-directed graph."""
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
    conn_count: dict[str, int] = {}
    for edge in display_edges:
        conn_count[edge.source] = conn_count.get(edge.source, 0) + 1
        conn_count[edge.target] = conn_count.get(edge.target, 0) + 1

    # Serialize nodes: id, label, type, color, radius
    nodes_data = [
        {
            "id": n.id,
            "label": n.label,
            "type": n.node_type,
            "color": _NODE_COLORS.get(n.node_type, _DEFAULT_COLOR),
            "r": max(14, min(30, (conn_count.get(n.id, 0)) * 5 + 10)),
            "desc": n.data.get("desc", "") or n.data.get("data", "") if n.data else "",
        }
        for n in display_nodes
    ]

    # Serialize edges
    edges_data = [
        {"source": e.source, "target": e.target, "label": e.label or ""}
        for e in display_edges
    ]

    nodes_json = json.dumps(nodes_data, ensure_ascii=False)
    edges_json = json.dumps(edges_data, ensure_ascii=False)
    safe_layout = "circular" if layout == "circular" else "force"

    html = _CANVAS_TEMPLATE
    html = html.replace("%%NODES%%", nodes_json)
    html = html.replace("%%EDGES%%", edges_json)
    html = html.replace("%%LAYOUT%%", safe_layout)
    return html


def render_graph(graph_data: GraphData, layout: str = "force") -> None:
    """Render an interactive knowledge graph in Streamlit using Canvas 2D."""
    if not graph_data.nodes:
        st.info("No graph data to display.")
        return

    try:
        html_content = build_graph_html(graph_data, layout)
        components.html(html_content, height=540, scrolling=False)
    except Exception as e:
        st.warning(f"Could not build graph: {e}")
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


# ---------------------------------------------------------------------------
# Canvas 2D HTML Template
# ---------------------------------------------------------------------------

_CANVAS_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
canvas{display:block;cursor:grab}
canvas.dragging{cursor:grabbing}
canvas.pointing{cursor:pointer}
#tip{position:absolute;display:none;background:rgba(15,23,42,.95);color:#e2e8f0;border:1px solid #334155;border-radius:8px;padding:10px 14px;font-size:13px;max-width:280px;pointer-events:none;z-index:100;backdrop-filter:blur(8px);box-shadow:0 4px 12px rgba(0,0,0,.4);line-height:1.5}
#tip .t{font-weight:600;font-size:14px;margin-bottom:4px}
#tip .d{color:#94a3b8}
#tip .m{color:#64748b;font-size:11px;margin-top:6px}
#ctl{position:absolute;top:10px;right:10px;display:flex;gap:6px}
#ctl button{background:rgba(30,41,59,.9);color:#94a3b8;border:1px solid #334155;border-radius:6px;padding:5px 10px;font-size:12px;cursor:pointer;backdrop-filter:blur(8px);transition:all .2s}
#ctl button:hover{background:rgba(51,65,85,.9);color:#e2e8f0}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="tip"><div class="t"></div><div class="d"></div><div class="m"></div></div>
<div id="ctl">
<button id="resetBtn">Reset</button>
<button id="pngBtn">PNG</button>
</div>
<script>
(function(){
// ── Data ──────────────────────────────────────────────────────────────
var nodes=%%NODES%%;
var edges=%%EDGES%%;
var LAYOUT="%%LAYOUT%%";

// ── Constants ─────────────────────────────────────────────────────────
var REPULSION=1500,ATTRACT=.004,GRAVITY=.004,EDGE_LEN=280;
var ALPHA_DECAY=.003,VEL_DECAY=.55;

// ── Canvas setup ──────────────────────────────────────────────────────
var cv=document.getElementById("c"),cx=cv.getContext("2d");
var tip=document.getElementById("tip");
var tipT=tip.querySelector(".t"),tipD=tip.querySelector(".d"),tipM=tip.querySelector(".m");
var W,H;

function resize(){W=cv.width=window.innerWidth;H=cv.height=window.innerHeight}
window.addEventListener("resize",resize);resize();

// ── Node / edge processing ────────────────────────────────────────────
var nMap={};
nodes.forEach(function(n){n.x=0;n.y=0;n.vx=0;n.vy=0;nMap[n.id]=n});
edges=edges.filter(function(e){return nMap[e.source]&&nMap[e.target]});

// Detect parallel edge groups for curve offset
var eGroups={};
edges.forEach(function(e,i){
  var k=e.source<e.target?e.source+"||"+e.target:e.target+"||"+e.source;
  if(!eGroups[k])eGroups[k]=[];
  eGroups[k].push(i);
});

function edgeOffset(idx){
  var e=edges[idx];
  var k=e.source<e.target?e.source+"||"+e.target:e.target+"||"+e.source;
  var g=eGroups[k]||[idx];
  if(g.length<=1)return 18;
  var my=g.indexOf(idx),t=g.length;
  return(my-(t-1)/2)*28;
}

// ── Initial positions ─────────────────────────────────────────────────
function initPositions(){
  if(LAYOUT==="circular"){
    var r=Math.min(W,H)*.36;
    nodes.forEach(function(n,i){
      var a=2*Math.PI*i/nodes.length-Math.PI/2;
      n.x=W/2+Math.cos(a)*r;n.y=H/2+Math.sin(a)*r;n.vx=0;n.vy=0;
    });
  }else{
    nodes.forEach(function(n){
      n.x=W*.1+Math.random()*W*.8;n.y=H*.1+Math.random()*H*.8;n.vx=0;n.vy=0;
    });
  }
}

// ── Camera ────────────────────────────────────────────────────────────
var camX=0,camY=0,camS=1;
function w2s(wx,wy){return{x:(wx+camX)*camS,y:(wy+camY)*camS}}
function s2w(sx,sy){return{x:sx/camS-camX,y:sy/camS-camY}}

// ── Force simulation ──────────────────────────────────────────────────
var alpha=1;
var dragN=null,dragOff={x:0,y:0};
var panning=false,panS={x:0,y:0};

function simulate(){
  if(alpha<.001||LAYOUT==="circular")return;
  var i,j,n,a,b,dx,dy,d2,d,f,fx,fy;
  // Repulsion
  for(i=0;i<nodes.length;i++){
    for(j=i+1;j<nodes.length;j++){
      a=nodes[i];b=nodes[j];
      dx=a.x-b.x;dy=a.y-b.y;d2=dx*dx+dy*dy;
      d=Math.max(Math.sqrt(d2),1);f=REPULSION/d2;
      fx=dx/d*f*alpha;fy=dy/d*f*alpha;
      if(a!==dragN){a.vx+=fx;a.vy+=fy}
      if(b!==dragN){b.vx-=fx;b.vy-=fy}
    }
  }
  // Attraction along edges
  edges.forEach(function(e){
    var s=nMap[e.source],t=nMap[e.target];if(!s||!t)return;
    dx=t.x-s.x;dy=t.y-s.y;d=Math.max(Math.sqrt(dx*dx+dy*dy),1);
    f=ATTRACT*(d-EDGE_LEN)*alpha;fx=dx/d*f;fy=dy/d*f;
    if(s!==dragN){s.vx+=fx;s.vy+=fy}
    if(t!==dragN){t.vx-=fx;t.vy-=fy}
  });
  // Center gravity
  nodes.forEach(function(n){
    if(n===dragN)return;
    n.vx+=(W/2-n.x)*GRAVITY*alpha;n.vy+=(H/2-n.y)*GRAVITY*alpha;
  });
  // Apply
  nodes.forEach(function(n){
    if(n===dragN)return;
    n.vx*=VEL_DECAY;n.vy*=VEL_DECAY;n.x+=n.vx;n.y+=n.vy;
    var m=n.r+5;n.x=Math.max(m,Math.min(W-m,n.x));n.y=Math.max(m,Math.min(H-m,n.y));
  });
  alpha*=(1-ALPHA_DECAY);
}

// ── Rendering helpers ─────────────────────────────────────────────────
function hexShift(hex,amt){
  var r=Math.max(0,Math.min(255,parseInt(hex.slice(1,3),16)+amt));
  var g=Math.max(0,Math.min(255,parseInt(hex.slice(3,5),16)+amt));
  var b=Math.max(0,Math.min(255,parseInt(hex.slice(5,7),16)+amt));
  return"#"+((1<<24)+(r<<16)+(g<<8)+b).toString(16).slice(1);
}

// Find t on bezier where point is at distance r from target center
function arrowT(sx,sy,cpx,cpy,tx,ty,tr){
  var lo=0,hi=1,mid,mt,px,py,dx,dy;
  for(var i=0;i<12;i++){
    mid=(lo+hi)/2;mt=1-mid;
    px=mt*mt*sx+2*mt*mid*cpx+mid*mid*tx;
    py=mt*mt*sy+2*mt*mid*cpy+mid*mid*ty;
    dx=px-tx;dy=py-ty;
    if(Math.sqrt(dx*dx+dy*dy)>tr)lo=mid;else hi=mid;
  }
  return hi;
}

// ── Rendering ─────────────────────────────────────────────────────────
var hovered=null;

function render(){
  cx.clearRect(0,0,W,H);
  cx.fillStyle="#0f172a";cx.fillRect(0,0,W,H);

  // Highlighted set
  var hlNodes={},hlEdges={};
  if(hovered){
    hlNodes[hovered.id]=true;
    edges.forEach(function(e,i){
      if(e.source===hovered.id||e.target===hovered.id){
        hlEdges[i]=true;hlNodes[e.source]=true;hlNodes[e.target]=true;
      }
    });
  }

  // Draw edges
  edges.forEach(function(e,idx){
    var s=nMap[e.source],t=nMap[e.target];if(!s||!t)return;
    var sp=w2s(s.x,s.y),tp=w2s(t.x,t.y);
    var sr=s.r*camS,tr=t.r*camS;
    var mx=(sp.x+tp.x)/2,my=(sp.y+tp.y)/2;
    var dx=tp.x-sp.x,dy=tp.y-sp.y;
    var len=Math.max(Math.sqrt(dx*dx+dy*dy),1);
    var off=edgeOffset(idx)*camS;
    var nx=-dy/len,ny=dx/len;
    var cpx=mx+nx*off,cpy=my+ny*off;

    var isHL=!!hlEdges[idx];
    var isDim=hovered&&!isHL;

    cx.beginPath();cx.moveTo(sp.x,sp.y);cx.quadraticCurveTo(cpx,cpy,tp.x,tp.y);
    if(isDim){cx.strokeStyle="rgba(100,116,139,.12)";cx.lineWidth=1}
    else if(isHL){cx.strokeStyle="rgba(148,163,184,.7)";cx.lineWidth=2.2*camS}
    else{cx.strokeStyle="rgba(100,116,139,.35)";cx.lineWidth=1.5*camS}
    cx.stroke();

    // Arrowhead
    if(!isDim){
      var at=arrowT(sp.x,sp.y,cpx,cpy,tp.x,tp.y,tr+2);
      var amt=1-at;
      var ax=amt*amt*sp.x+2*amt*at*cpx+at*at*tp.x;
      var ay=amt*amt*sp.y+2*amt*at*cpy+at*at*tp.y;
      var tdx=2*amt*(cpx-sp.x)+2*at*(tp.x-cpx);
      var tdy=2*amt*(cpy-sp.y)+2*at*(tp.y-cpy);
      var tl=Math.max(Math.sqrt(tdx*tdx+tdy*tdy),.001);
      var tnx=tdx/tl,tny=tdy/tl;
      var as=7*camS;
      cx.beginPath();
      cx.moveTo(ax,ay);
      cx.lineTo(ax-as*tnx+as*.4*tny,ay-as*tny-as*.4*tnx);
      cx.moveTo(ax,ay);
      cx.lineTo(ax-as*tnx-as*.4*tny,ay-as*tny+as*.4*tnx);
      cx.strokeStyle=isHL?"rgba(148,163,184,.8)":"rgba(148,163,184,.5)";
      cx.lineWidth=isHL?2*camS:1.5*camS;
      cx.stroke();
    }

    // Edge label (show on highlight or when no hover)
    if(e.label&&(isHL||!hovered)&&!isDim){
      var fs=Math.max(10,11*camS);
      cx.font=fs+"px -apple-system,sans-serif";
      cx.fillStyle=isHL?"rgba(226,232,240,.9)":"rgba(148,163,184,.55)";
      cx.textAlign="center";cx.textBaseline="middle";
      // Place at control point
      cx.fillText(e.label,cpx,cpy-6*camS);
    }
  });

  // Draw nodes
  nodes.forEach(function(n){
    var p=w2s(n.x,n.y),r=n.r*camS;
    var isHL=n===hovered||hlNodes[n.id];
    var isDim=hovered&&!hlNodes[n.id];

    // Glow
    if(isHL&&!isDim){
      var glow=cx.createRadialGradient(p.x,p.y,r*.4,p.x,p.y,r*2.5);
      glow.addColorStop(0,n.color+"50");glow.addColorStop(1,n.color+"00");
      cx.beginPath();cx.arc(p.x,p.y,r*2.5,0,Math.PI*2);cx.fillStyle=glow;cx.fill();
    }

    // Circle
    cx.beginPath();cx.arc(p.x,p.y,r,0,Math.PI*2);
    if(isDim){
      cx.fillStyle="rgba(30,41,59,.6)";cx.strokeStyle="rgba(71,85,105,.25)";
    }else{
      var g=cx.createRadialGradient(p.x-r*.3,p.y-r*.3,0,p.x,p.y,r);
      g.addColorStop(0,n.color);g.addColorStop(1,hexShift(n.color,-35));
      cx.fillStyle=g;cx.strokeStyle=isHL?"#e2e8f0":"rgba(71,85,105,.45)";
    }
    cx.lineWidth=isHL?2.2:1;cx.fill();cx.stroke();

    // Label
    if(!isDim||isHL){
      var fs2=Math.max(10,12*camS);
      cx.font="500 "+fs2+"px -apple-system,sans-serif";
      cx.fillStyle=isDim?"rgba(148,163,184,.2)":"#e2e8f0";
      cx.textAlign="center";cx.textBaseline="middle";
      var lbl=n.label;
      if(lbl.length>10)lbl=lbl.substring(0,9)+"\u2026";
      cx.fillText(lbl,p.x,p.y);
    }
  });
}

// ── Hit testing ───────────────────────────────────────────────────────
function nodeAt(sx,sy){
  var w=s2w(sx,sy);
  for(var i=nodes.length-1;i>=0;i--){
    var n=nodes[i],dx=w.x-n.x,dy=w.y-n.y;
    if(dx*dx+dy*dy<n.r*n.r)return n;
  }
  return null;
}

// ── Mouse events ──────────────────────────────────────────────────────
cv.addEventListener("mousemove",function(e){
  var r=cv.getBoundingClientRect(),sx=e.clientX-r.left,sy=e.clientY-r.top;
  if(dragN){
    var w=s2w(sx,sy);dragN.x=w.x-dragOff.x;dragN.y=w.y-dragOff.y;
    alpha=Math.max(alpha,.3);return;
  }
  if(panning){
    camX+=(sx-panS.x)/camS;camY+=(sy-panS.y)/camS;
    panS.x=sx;panS.y=sy;return;
  }
  var nd=nodeAt(sx,sy);
  if(nd!==hovered){
    hovered=nd;
    cv.className=nd?"pointing":"";
    if(nd){
      tipT.textContent=nd.label;
      tipD.textContent=nd.desc||"";
      tipM.textContent=nd.type;
      tip.style.display="block";
    }else{tip.style.display="none"}
  }
  if(hovered){
    var tx=sx+15,ty=sy-10;
    if(tx+280>W)tx=sx-290;
    if(ty+100>H)ty=sy-100;
    tip.style.left=tx+"px";tip.style.top=ty+"px";
  }
});

cv.addEventListener("mousedown",function(e){
  var r=cv.getBoundingClientRect(),sx=e.clientX-r.left,sy=e.clientY-r.top;
  var nd=nodeAt(sx,sy);
  if(nd){
    dragN=nd;var w=s2w(sx,sy);dragOff.x=w.x-nd.x;dragOff.y=w.y-nd.y;
    cv.className="dragging";
  }else{
    panning=true;panS.x=sx;panS.y=sy;cv.className="dragging";
  }
});

cv.addEventListener("mouseup",function(){
  dragN=null;panning=false;cv.className=hovered?"pointing":"";
});

cv.addEventListener("mouseleave",function(){
  dragN=null;panning=false;hovered=null;tip.style.display="none";cv.className="";
});

cv.addEventListener("wheel",function(e){
  e.preventDefault();
  var r=cv.getBoundingClientRect(),sx=e.clientX-r.left,sy=e.clientY-r.top;
  var f=e.deltaY>0?.92:1.08;
  var ns=Math.max(.15,Math.min(6,camS*f));
  var w=s2w(sx,sy);camS=ns;camX=sx/camS-w.x;camY=sy/camS-w.y;
},{passive:false});

// ── Controls ──────────────────────────────────────────────────────────
document.getElementById("resetBtn").addEventListener("click",function(){
  camX=0;camY=0;camS=1;alpha=1;initPositions();
});
document.getElementById("pngBtn").addEventListener("click",function(){
  var a=document.createElement("a");a.download="knowledge-graph.png";
  a.href=cv.toDataURL("image/png");a.click();
});

// ── Main loop ─────────────────────────────────────────────────────────
function tick(){simulate();render();requestAnimationFrame(tick)}
initPositions();tick();
})();
</script>
</body>
</html>"""
