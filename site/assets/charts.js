/* Release Point: the figures. Plain SVG, no libraries.
   Every chart reads its colors from CSS variables, redraws on resize and on theme change, has a crosshair or
   per-mark tooltip (also on keyboard focus), and a data table under it. */
(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const el = (tag, attrs = {}, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  };
  const fmt = (v, d = 1) => (v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
  const lin = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  const niceTicks = (lo, hi, n = 5) => {
    const span = hi - lo, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n + 0.5);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  };

  /* ---------- tooltip (one per page) ---------- */
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.setAttribute("role", "status");
  document.body.appendChild(tip);
  function showTip(x, y, rows, title) {
    tip.replaceChildren();
    if (title) {
      const t = document.createElement("div");
      t.className = "tip-title";
      t.textContent = title;
      tip.appendChild(t);
    }
    for (const r of rows) {
      const row = document.createElement("div");
      row.className = "tip-row";
      if (r.color) {
        const k = document.createElement("span");
        k.className = "tip-key";
        k.style.background = r.color;
        row.appendChild(k);
      }
      const v = document.createElement("strong");
      v.textContent = r.value;
      const l = document.createElement("span");
      l.className = "tip-label";
      l.textContent = r.label;
      row.append(v, l);
      tip.appendChild(row);
    }
    tip.style.opacity = 1;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    const px = Math.min(window.innerWidth - w - 12, x + 14), py = Math.max(8, y - h - 14);
    tip.style.transform = `translate(${px}px, ${py + window.scrollY}px)`;
  }
  const hideTip = () => (tip.style.opacity = 0);

  /* ---------- data table under each figure ---------- */
  function table(host, head, rows, caption) {
    let det = host.parentElement.querySelector(":scope > details.data");
    if (!det) {
      det = document.createElement("details");
      det.className = "data";
      const s = document.createElement("summary");
      s.textContent = "Data";
      det.appendChild(s);
      host.after(det);
    }
    det.querySelector("table")?.remove();
    const t = document.createElement("table");
    if (caption) {
      const c = document.createElement("caption");
      c.textContent = caption;
      t.appendChild(c);
    }
    const tr = document.createElement("tr");
    for (const h of head) {
      const th = document.createElement("th");
      th.textContent = h;
      tr.appendChild(th);
    }
    t.appendChild(tr);
    for (const r of rows) {
      const row = document.createElement("tr");
      for (const c of r) {
        const td = document.createElement("td");
        td.textContent = c;
        row.appendChild(td);
      }
      t.appendChild(row);
    }
    det.appendChild(t);
  }

  /* ---------- frame: svg, margins, axes, grid ---------- */
  function frame(host, { height = 300, margin = {}, x, y, xTicks, yTicks, xLabel, yLabel, xFmt = (v) => v,
                         yFmt = (v) => v, timeBase = false }) {
    host.replaceChildren();
    const W = Math.max(280, host.clientWidth);
    const m = { top: yLabel ? 32 : 18, right: 18, bottom: timeBase ? 58 : 44, left: 52, ...margin };
    const svg = el("svg", { width: W, height, viewBox: `0 0 ${W} ${height}`, role: "img" }, host);
    const name = host.closest("figure")?.querySelector(".fig-title")?.textContent;
    if (name) svg.setAttribute("aria-label", `${name}. The values are in the data table below the chart.`);
    const X = lin(x[0], x[1], m.left, W - m.right), Y = lin(y[0], y[1], height - m.bottom, m.top);
    const g = el("g", {}, svg);
    for (const t of yTicks ?? niceTicks(y[0], y[1])) {
      el("line", { x1: m.left, x2: W - m.right, y1: Y(t), y2: Y(t), class: "grid" }, g);
      el("text", { x: m.left - 8, y: Y(t) + 4, class: "tick", "text-anchor": "end" }, g).textContent = yFmt(t);
    }
    el("line", { x1: m.left, x2: W - m.right, y1: height - m.bottom, y2: height - m.bottom, class: "axis" }, g);
    const xt = xTicks ?? niceTicks(x[0], x[1], Math.max(3, Math.floor((W - m.left - m.right) / 70)));
    for (const t of xt) {
      el("line", { x1: X(t), x2: X(t), y1: height - m.bottom, y2: height - m.bottom + 4, class: "axis" }, g);
      el("text", { x: X(t), y: height - m.bottom + 17, class: "tick", "text-anchor": "middle" }, g).textContent =
        xFmt(t);
    }
    if (timeBase) {   // the chronograph: a fine tick every quarter second, a longer one every second
      const tb = el("g", { class: "timebase" }, g);
      const y0 = height - m.bottom + 26;
      el("line", { x1: X(x[0]), x2: X(x[1]), y1: y0, y2: y0 }, tb);
      const span = x[1] - x[0], step = span > 70 ? 5 : span > 25 ? 1 : 0.25;
      for (let v = Math.ceil(x[0] / step) * step; v <= x[1] + 1e-9; v += step) {
        const major = Math.abs(v - Math.round(v)) < 1e-9 && (step < 1 || Math.round(v) % 5 === 0);
        el("line", { x1: X(v), x2: X(v), y1: y0, y2: y0 + (major ? 7 : 3.5) }, tb);
      }
    }
    if (xLabel) el("text", { x: W - m.right, y: height - 6, class: "axis-label", "text-anchor": "end" }, g)
      .textContent = xLabel;
    if (yLabel) el("text", { x: 0, y: 12, class: "axis-label" }, g).textContent = yLabel;
    return { svg, g, X, Y, W, H: height, m };
  }

  /* crosshair: a hairline that snaps to the nearest x in `xs`, and a readout of every series there */
  function crosshair(f, xs, readout, label) {
    const line = el("line", { y1: f.m.top, y2: f.H - f.m.bottom, class: "cross", opacity: 0 }, f.svg);
    const dots = el("g", {}, f.svg);
    const hit = el("rect", { x: f.m.left, y: f.m.top, width: f.W - f.m.left - f.m.right,
      height: f.H - f.m.top - f.m.bottom, fill: "transparent", tabindex: 0, class: "hit",
      "aria-label": label || "Chart: move across it, or use the arrow keys, for values" }, f.svg);
    let idx = Math.floor(xs.length / 2);
    const show = (i, cx, cy) => {
      idx = Math.max(0, Math.min(xs.length - 1, i));
      const x = f.X(xs[idx]);
      line.setAttribute("x1", x); line.setAttribute("x2", x); line.setAttribute("opacity", 1);
      dots.replaceChildren();
      const { rows, title, points = [] } = readout(idx);
      for (const p of points) el("circle", { cx: x, cy: f.Y(p.y), r: 4.5, fill: p.color, class: "dot" }, dots);
      const box = f.svg.getBoundingClientRect();
      showTip(cx ?? box.left + x, cy ?? box.top + f.m.top + 20, rows, title);
    };
    const nearest = (px) => {
      let best = 0, bd = Infinity;
      xs.forEach((v, i) => { const d = Math.abs(f.X(v) - px); if (d < bd) { bd = d; best = i; } });
      return best;
    };
    hit.addEventListener("pointermove", (e) => {
      const r = f.svg.getBoundingClientRect();
      show(nearest(e.clientX - r.left), e.clientX, e.clientY);
    });
    const clear = () => { line.setAttribute("opacity", 0); dots.replaceChildren(); hideTip(); };
    hit.addEventListener("pointerleave", clear);
    hit.addEventListener("blur", clear);
    hit.addEventListener("focus", () => show(idx));
    hit.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") { show(idx + 1); e.preventDefault(); }
      if (e.key === "ArrowLeft") { show(idx - 1); e.preventDefault(); }
    });
  }

  const path = (pts, X, Y) => pts.filter((p) => p && isFinite(p[1]))
    .map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");

  /* ---------- registry: draw on load, redraw on resize/theme ---------- */
  const charts = [];
  const register = (host, draw) => {
    if (!host) return;
    charts.push([host, draw]);
    draw(host);
  };
  let pending;
  const redrawAll = () => { cancelAnimationFrame(pending); pending = requestAnimationFrame(() => charts.forEach(([h, d]) => d(h))); };
  new ResizeObserver(redrawAll).observe(document.querySelector("main"));
  window.addEventListener("themechange", redrawAll);
  window.RP = { el, frame, crosshair, path, table, showTip, hideTip, register, css, fmt, niceTicks, lin };
})();
