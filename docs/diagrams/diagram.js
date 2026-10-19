// Draws arrows between boxes after layout, so boxes can move without redrawing by hand.
// connect(fromId, toId, { from: "bottom"|"top"|"left"|"right", to: ..., label, dashed, color, via })
const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("wires");
const stage = document.getElementById("stage");

function anchor(el, side) {
  const r = el.getBoundingClientRect(), s = stage.getBoundingClientRect();
  const x = r.left - s.left, y = r.top - s.top;
  return {
    top: [x + r.width / 2, y], bottom: [x + r.width / 2, y + r.height],
    left: [x, y + r.height / 2], right: [x + r.width, y + r.height / 2],
  }[side];
}

function marker(color) {
  const id = "m" + color.replace("#", "");
  if (!document.getElementById(id)) {
    const m = document.createElementNS(NS, "marker");
    Object.entries({ id, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" })
      .forEach(([k, v]) => m.setAttribute(k, v));
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", "M0,0 L10,5 L0,10 z");
    p.setAttribute("fill", color);
    m.append(p);
    svg.querySelector("defs").append(m);
  }
  return `url(#${id})`;
}

function connect(a, b, o = {}) {
  const A = document.getElementById(a), B = document.getElementById(b);
  if (!A || !B) throw new Error(`missing box ${!A ? a : b}`);
  const from = o.from || "bottom", to = o.to || "top";
  const [x1, y1] = anchor(A, from), [x2, y2] = anchor(B, to);
  let d;
  const vert = (s) => s === "top" || s === "bottom";
  if (o.via) {
    // null in a via point = keep the previous point's x (or y), giving straight segments
    let px = x1, py = y1;
    d = `M${x1},${y1} ` + o.via.map(([vx, vy]) => { px = vx ?? px; py = vy ?? py; return `L${px},${py}`; }).join(" ") + ` L${x2},${y2}`;
  } else if (vert(from) && vert(to)) {
    const my = o.midY ?? (y1 + y2) / 2;
    d = Math.abs(x1 - x2) < 1 ? `M${x1},${y1} L${x2},${y2}` : `M${x1},${y1} L${x1},${my} L${x2},${my} L${x2},${y2}`;
  } else if (!vert(from) && !vert(to)) {
    const mx = o.midX ?? (x1 + x2) / 2;
    d = Math.abs(y1 - y2) < 1 ? `M${x1},${y1} L${x2},${y2}` : `M${x1},${y1} L${mx},${y1} L${mx},${y2} L${x2},${y2}`;
  } else if (vert(from)) {
    d = `M${x1},${y1} L${x1},${y2} L${x2},${y2}`;
  } else {
    d = `M${x1},${y1} L${x2},${y1} L${x2},${y2}`;
  }
  const color = o.color || "#17302a";
  const p = document.createElementNS(NS, "path");
  p.setAttribute("d", d);
  p.setAttribute("fill", "none");
  p.setAttribute("stroke", color);
  p.setAttribute("stroke-width", o.width || 2.2);
  if (o.dashed) p.setAttribute("stroke-dasharray", "7 5");
  p.setAttribute("marker-end", marker(color));
  if (o.both) p.setAttribute("marker-start", marker(color));
  svg.append(p);
  if (o.label) {
    const len = p.getTotalLength();
    const pt = p.getPointAtLength(len * (o.at ?? 0.5));
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", pt.x + (o.dx || 0));
    t.setAttribute("y", pt.y + (o.dy ?? -6));
    t.setAttribute("text-anchor", o.anchor || "middle");
    t.setAttribute("class", "wire-label");
    t.textContent = o.label;
    const bg = document.createElementNS(NS, "rect");
    svg.append(bg, t);
    const bb = t.getBBox();
    Object.entries({ x: bb.x - 4, y: bb.y - 1, width: bb.width + 8, height: bb.height + 2, rx: 4, fill: "#ffffff" })
      .forEach(([k, v]) => bg.setAttribute(k, v));
  }
}

window.connect = connect;
window.diagramReady = () => {
  const s = stage.getBoundingClientRect();
  svg.setAttribute("width", s.width);
  svg.setAttribute("height", s.height);
  svg.setAttribute("viewBox", `0 0 ${s.width} ${s.height}`);
};
