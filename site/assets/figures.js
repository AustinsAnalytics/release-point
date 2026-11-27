/* Release Point: the figures, drawn from data/release.json. */
(async () => {
  "use strict";
  const { el, frame, crosshair, path, table, showTip, hideTip, register, css, fmt, niceTicks } = window.RP;
  const D = await (await fetch("data/release.json", { cache: "no-cache" })).json();
  const S26 = D.seasons["2026"], S25 = D.seasons["2025"];
  const G = D.grid;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const sec = (v) => {
    const a = Math.abs(v), s = Number.isInteger(a) ? String(a) : a.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    return (v > 0 ? "+" : v < 0 ? "−" : "") + s + " s";
  };
  const pct = (v, d = 0) => (100 * v).toFixed(d) + "%";

  /* mark-level tooltip helper: a transparent target bigger than the mark, on hover and keyboard focus */
  function target(parent, attrs, rows, title) {
    const r = el("rect", { ...attrs, fill: "transparent", tabindex: 0, class: "mark-hit" }, parent);
    const show = (e) => {
      const b = r.getBoundingClientRect();
      showTip(e?.clientX ?? b.left + b.width / 2, e?.clientY ?? b.top, rows, title);
    };
    r.addEventListener("pointermove", show);
    r.addEventListener("focus", () => show());
    r.addEventListener("pointerleave", hideTip);
    r.addEventListener("blur", hideTip);
    return r;
  }

  /* ---------------- Fig. 1: one home run, every print ---------------- */
  register(document.getElementById("fig-hero"), (host) => {
    const h = D.hero;
    const prices = h.trades.map((t) => t[1]).concat(h.mid.map((m) => m[1]));
    const lo = Math.floor(Math.min(...prices) / 5) * 5 - 2, hi = Math.ceil(Math.max(...prices) / 5) * 5 + 2;
    const narrow = host.clientWidth < 560;
    const marks = [[0, "Pitch"], [h.half_time, `Halfway, ${sec(+h.half_time.toFixed(2))}`]];
    if (h.feed_delay < 30) marks.push([h.feed_delay, `MLB feed final, ${sec(+h.feed_delay.toFixed(1))}`]);
    // the labels for the three rules sit in their own band above the plot, one row each, clear of the prints
    const band = 16 * marks.length + 8;
    const f = frame(host, { height: Math.min(440, Math.max(320, host.clientWidth * 0.44)) + band, x: [-8, 30], y: [lo, hi],
      xTicks: narrow ? [0, 10, 20, 30] : [-5, 0, 5, 10, 15, 20, 25, 30], xFmt: sec, yFmt: (v) => v + "¢",
      timeBase: true, margin: { top: band }, xLabel: "seconds from the pitch" });
    const blue = css("--blue"), red = css("--red"), ink = css("--ink");
    const clipId = "clip-hero";
    const defs = el("defs", {}, f.svg);
    const clip = el("clipPath", { id: clipId }, defs);
    const cr = el("rect", { x: 0, y: 0, width: f.W, height: f.H }, clip);
    const layer = el("g", { "clip-path": `url(#${clipId})` }, f.svg);
    marks.forEach(([x, label], i) => {
      const ty = 12 + i * 16;
      el("line", { x1: f.X(x), x2: f.X(x), y1: ty + 4, y2: f.H - f.m.bottom, stroke: css("--ink-3"), "stroke-width": 1 }, f.g);
      const right = f.X(x) > f.W - f.m.right - 140;
      el("text", { x: f.X(x) + (right ? -5 : 5), y: ty, class: i ? "note" : "note-strong",
        "text-anchor": right ? "end" : "start" }, f.g).textContent = label;
    });
    // the trading price underneath, then a dot per fill on top, area proportional to contracts
    el("path", { d: path(h.mid, f.X, f.Y), class: "trace" }, layer);
    const rmax = Math.max(...h.trades.map((t) => t[3]));
    const big = Math.max(5, Math.min(10, f.W / 90));
    for (const [t, p, d, s] of h.trades.slice().sort((a, b) => b[3] - a[3])) {
      el("circle", { cx: f.X(t), cy: f.Y(p), r: Math.max(narrow ? 1.6 : 2.2, Math.min(big, big * Math.sqrt(s / rmax))),
        fill: d > 0 ? blue : red, "fill-opacity": 0.8, stroke: css("--paper"), "stroke-width": 1 }, layer);
    }
    crosshair(f, h.mid.map((m) => m[0]), (i) => {
      const [t, m] = h.mid[i];
      const near = h.trades.filter((x) => Math.abs(x[0] - t) <= 0.05);
      const rows = [{ value: m.toFixed(1) + "¢", label: "trading midpoint", color: ink }];
      if (near.length) rows.push({ value: near.reduce((a, x) => a + x[3], 0).toFixed(0), label: `contracts in ${near.length} fill${near.length > 1 ? "s" : ""}` });
      return { title: sec(+t.toFixed(1)), rows, points: [{ y: m, color: ink }] };
    }, "Trades around the home run: move across for the price at each moment");
    // replay: a recording drum turning at 4x real time
    const play = () => {
      if (reduce) return;
      const t0 = performance.now(), dur = (38 / 4) * 1000;
      const step = (now) => {
        const k = Math.min(1, (now - t0) / dur);
        cr.setAttribute("width", f.X(-8 + 38 * k));
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
    if (!host.dataset.played) {
      host.dataset.played = 1;
      const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { play(); io.disconnect(); } }, { threshold: 0.4 });
      io.observe(host);
    }
    document.getElementById("replay").onclick = play;
    table(host, ["Seconds", "Price (¢)", "Taker", "Contracts"],
      h.trades.filter((t) => t[0] >= -1 && t[0] <= 12).slice(0, 60).map((t) => [t[0].toFixed(3), t[1].toFixed(0), t[2] > 0 ? "bought" : "sold", t[3].toFixed(2)]),
      "Fills from one second before the pitch to twelve after (first 60)");
  });

  /* ---------------- response curve: share of the fair move priced, by seconds from the pitch ---------------- */
  const curve = (host, series, { x = [-5, 30], height = 300 } = {}) => {
    const f = frame(host, { height, x, y: [-0.05, 1.15], yTicks: [0, 0.25, 0.5, 0.75, 1], yFmt: (v) => pct(v), xFmt: sec,
      timeBase: true, xLabel: "seconds from the pitch", yLabel: "share of the fair move priced" });
    const idx = G.map((g, i) => i).filter((i) => G[i] >= x[0] && G[i] <= x[1]);
    el("line", { x1: f.X(x[0]), x2: f.X(x[1]), y1: f.Y(1), y2: f.Y(1), stroke: css("--ink-3"), "stroke-width": 1 }, f.g);
    for (const s of series) {
      const band = idx.map((i) => [G[i], s.data.hi[i]]).concat(idx.slice().reverse().map((i) => [G[i], s.data.lo[i]]));
      el("path", { d: path(band, f.X, f.Y) + "Z", fill: s.color, "fill-opacity": 0.13, stroke: "none" }, f.g);
      el("path", { d: path(idx.map((i) => [G[i], s.data.est[i]]), f.X, f.Y), fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round" }, f.g);
    }
    crosshair(f, idx.map((i) => G[i]), (k) => {
      const i = idx[k];
      return { title: sec(G[i]), rows: series.map((s) => ({ value: pct(s.data.est[i]), label: `${s.name} (95%: ${pct(s.data.lo[i])}–${pct(s.data.hi[i])})`, color: s.color })),
        points: series.map((s) => ({ y: s.data.est[i], color: s.color })) };
    });
    table(host, ["Seconds from pitch"].concat(series.map((s) => s.name)), idx.map((i) => [sec(G[i])].concat(series.map((s) => `${pct(s.data.est[i])} (${pct(s.data.lo[i])}–${pct(s.data.hi[i])})`))));
    return f;
  };

  register(document.getElementById("fig-response"), (host) => {
    const f = curve(host, [{ name: "2026, every pitch", data: S26.beta_all, color: css("--blue") }]);
    for (const [k, frac] of [["t50", 0.5], ["t90", 0.9]]) {
      const t = +host.dataset[k];
      el("circle", { cx: f.X(t), cy: f.Y(frac), r: 4.5, fill: css("--blue"), class: "dot" }, f.g);
      el("text", { x: f.X(t) + 9, y: f.Y(frac) + 4, class: "note-strong" }, f.g).textContent = `${pct(frac)} by ${sec(+t.toFixed(1))}`;
    }
  });

  /* ---------------- first trade past halfway: histogram for big pitches ---------------- */
  register(document.getElementById("fig-half"), (host) => {
    const hist = S26.half_hist.slice(0, 40), n = S26.half_hist.reduce((a, b) => a + b, 0);
    const share = hist.map((c) => c / n);
    const top = Math.max(...share) * 100;
    const f = frame(host, { height: 260, x: [0, 20], y: [0, top * 1.12 / 100], xFmt: sec, timeBase: true,
      yTicks: niceTicks(0, top, 4).map((v) => v / 100), yFmt: (v) => +(v * 100).toFixed(1) + "%",
      xLabel: "seconds from the pitch to the first trade past halfway", yLabel: "share of big pitches" });
    const bw = f.X(0.5) - f.X(0) - 2;
    share.forEach((v, i) => {
      const x = f.X(i * 0.5) + 1, y = f.Y(v), h0 = f.Y(0) - y;
      const r = Math.min(4, bw / 2, h0);
      el("path", { d: `M${x},${f.Y(0)}V${y + r}Q${x},${y} ${x + r},${y}H${x + bw - r}Q${x + bw},${y} ${x + bw},${y + r}V${f.Y(0)}Z`, fill: css("--blue") }, f.g);
      target(f.svg, { x: x - 1, y: f.m.top, width: bw + 2, height: f.Y(0) - f.m.top }, [{ value: pct(v, 1), label: "of big pitches" }], `${(i * 0.5).toFixed(1)}–${(i * 0.5 + 0.5).toFixed(1)} s`);
    });
    const med = +host.dataset.median;
    el("line", { x1: f.X(med), x2: f.X(med), y1: f.m.top, y2: f.Y(0), stroke: css("--ink"), "stroke-width": 1 }, f.g);
    el("text", { x: f.X(med) + 6, y: f.m.top + 12, class: "note-strong" }, f.g).textContent = `median ${sec(+med.toFixed(1))}`;
    table(host, ["Seconds", "Share of big pitches"], hist.map((c, i) => [`${(i * 0.5).toFixed(1)}–${(i * 0.5 + 0.5).toFixed(1)}`, pct(c / n, 1)]));
  });

  /* ---------------- by kind of pitch: market vs MLB's feed ---------------- */
  register(document.getElementById("fig-kinds"), (host) => {
    const ks = S26.kinds.slice().sort((a, b) => a.half_median - b.half_median);
    const rowH = 46, height = ks.length * rowH + 62;
    const left = Math.min(150, host.clientWidth * 0.3);
    const f = frame(host, { height, x: [0, 30], y: [0, ks.length], yTicks: [], xFmt: sec, timeBase: true, margin: { left },
      xLabel: "seconds from the pitch" });
    const blue = css("--blue"), red = css("--red");
    ks.forEach((k, i) => {
      const yy = f.m.top + i * rowH + rowH / 2;
      el("line", { x1: f.m.left, x2: f.W - f.m.right, y1: yy, y2: yy, class: "grid" }, f.g);
      el("text", { x: f.m.left - 12, y: yy - 2, class: "note-strong", "text-anchor": "end" }, f.g).textContent = k.kind;
      el("text", { x: f.m.left - 12, y: yy + 13, class: "tick", "text-anchor": "end" }, f.g).textContent = `${k.n.toLocaleString()} pitches`;
      el("line", { x1: f.X(k.half_q25), x2: f.X(Math.min(30, k.half_q75)), y1: yy, y2: yy, stroke: blue, "stroke-width": 2, "stroke-linecap": "round" }, f.g);
      el("circle", { cx: f.X(Math.min(30, k.feed_median)), cy: yy, r: 5, fill: red, class: "dot" }, f.g);
      el("circle", { cx: f.X(k.half_median), cy: yy, r: 5, fill: blue, class: "dot" }, f.g);
      target(f.svg, { x: f.m.left, y: yy - rowH / 2, width: f.W - f.m.left - f.m.right, height: rowH },
        [{ value: sec(+k.half_median.toFixed(1)), label: `market halfway (middle half ${k.half_q25.toFixed(1)}–${k.half_q75.toFixed(1)} s)`, color: blue },
         { value: sec(+k.feed_median.toFixed(1)), label: "MLB feed marks it final", color: red },
         { value: pct(k.ahead_of_feed), label: "priced before the feed" }], k.kind);
    });
    table(host, ["Pitch", "Pitches", "Market halfway (median)", "Middle half", "Feed final (median)", "Priced before feed"],
      ks.map((k) => [k.kind, k.n.toLocaleString(), k.half_median.toFixed(2) + " s", `${k.half_q25.toFixed(1)}–${k.half_q75.toFixed(1)} s`, k.feed_median.toFixed(1) + " s", pct(k.ahead_of_feed)]));
  });

  /* ---------------- calibration ---------------- */
  register(document.getElementById("fig-cal"), (host) => {
    const c = S26.calibration;
    const f = frame(host, { height: Math.min(340, host.clientWidth * 0.8), x: [0, 100], y: [0, 100], xTicks: [0, 25, 50, 75, 100], yTicks: [0, 25, 50, 75, 100],
      xFmt: (v) => v + "¢", yFmt: (v) => v + "%", xLabel: "price before the pitch", yLabel: "how often that team won" });
    el("line", { x1: f.X(0), x2: f.X(100), y1: f.Y(0), y2: f.Y(100), stroke: css("--ink-3"), "stroke-width": 1 }, f.g);
    const blue = css("--blue");
    for (const b of c) {
      el("line", { x1: f.X(b.price), x2: f.X(b.price), y1: f.Y(100 * b.ci[0]), y2: f.Y(100 * b.ci[1]), stroke: blue, "stroke-width": 2, "stroke-linecap": "round" }, f.g);
      el("circle", { cx: f.X(b.price), cy: f.Y(100 * b.won), r: 4.5, fill: blue, class: "dot" }, f.g);
      target(f.svg, { x: f.X(b.price) - 12, y: f.Y(100 * b.ci[1]) - 12, width: 24, height: f.Y(100 * b.ci[0]) - f.Y(100 * b.ci[1]) + 24 },
        [{ value: pct(b.won, 1), label: `won (95%: ${pct(b.ci[0], 1)}–${pct(b.ci[1], 1)})`, color: blue }, { value: b.price.toFixed(1) + "¢", label: "average price" }, { value: b.n.toLocaleString(), label: "pitches" }],
        `Priced ${b.lo}–${b.hi}¢`);
    }
    table(host, ["Price before the pitch", "Average price", "Won", "95% interval", "Pitches"],
      c.map((b) => [`${b.lo}–${b.hi}¢`, b.price.toFixed(1) + "¢", pct(b.won, 1), `${pct(b.ci[0], 1)}–${pct(b.ci[1], 1)}`, b.n.toLocaleString()]));
  });

  /* ---------------- maker markouts by seconds since the pitch (diverging) ---------------- */
  register(document.getElementById("fig-markouts"), (host) => {
    const m = S26.markouts.filter((b) => b.lo < 60);
    const lab = (b) => `${b.lo}–${b.hi}`;
    const vals = m.map((b) => b.maker_c);
    const lo = Math.min(-1, Math.floor(Math.min(...vals))), hi = Math.max(1, Math.ceil(Math.max(...vals)));
    const f = frame(host, { height: 300, x: [0, m.length], y: [lo, hi], xTicks: [], yFmt: (v) => (v > 0 ? "+" : "") + fmt(v, 0) + "¢",
      yLabel: "makers' profit per contract, one minute later", margin: { bottom: 62 } });
    const step = (f.W - f.m.left - f.m.right) / m.length, bw = Math.min(24, step - 2);
    el("line", { x1: f.m.left, x2: f.W - f.m.right, y1: f.Y(0), y2: f.Y(0), stroke: css("--ink-2"), "stroke-width": 1 }, f.g);
    m.forEach((b, i) => {
      const x = f.m.left + i * step + (step - bw) / 2, v = b.maker_c, y0 = f.Y(0), y = f.Y(v);
      const up = v >= 0, r = Math.min(4, Math.abs(y - y0));
      const d = up ? `M${x},${y0}V${y + r}Q${x},${y} ${x + r},${y}H${x + bw - r}Q${x + bw},${y} ${x + bw},${y + r}V${y0}Z`
        : `M${x},${y0}V${y - r}Q${x},${y} ${x + r},${y}H${x + bw - r}Q${x + bw},${y} ${x + bw},${y - r}V${y0}Z`;
      el("path", { d, fill: up ? css("--blue") : css("--red") }, f.g);
      if (i % (step < 34 ? 2 : 1) === 0 || i === m.length - 1)
        el("text", { x: x + bw / 2, y: f.H - f.m.bottom + 17, class: "tick", "text-anchor": "middle" }, f.g).textContent = lab(b);
      target(f.svg, { x: f.m.left + i * step, y: f.m.top, width: step, height: f.H - f.m.top - f.m.bottom },
        [{ value: (v > 0 ? "+" : "") + fmt(v, 2) + "¢", label: "per contract to the maker" }, { value: pct(b.share, 1), label: "of all contracts" }], `${lab(b)} s after the pitch`);
    });
    el("text", { x: f.W - f.m.right, y: f.H - 8, class: "axis-label", "text-anchor": "end" }, f.g).textContent = "seconds since the last pitch";
    table(host, ["Seconds since the pitch", "Makers' profit per contract", "Share of contracts"], m.map((b) => [lab(b), (b.maker_c > 0 ? "+" : "") + b.maker_c.toFixed(2) + "¢", pct(b.share, 1)]));
  });

  /* ---------------- the pulse: orders per second around the pitch ---------------- */
  register(document.getElementById("fig-pulse"), (host) => {
    const p = S26.pulse_big;
    const win = p.lo.map((lo, i) => [lo + 0.125, p.rate[i]]).filter((q) => q[0] >= -10 && q[0] <= 20);
    const top = Math.ceil(Math.max(...win.map((q) => q[1])) * 2) / 2 + 0.5;
    const f = frame(host, { height: 280, x: [-10, 20], y: [0, top], xFmt: sec, timeBase: true, yFmt: (v) => v.toFixed(1),
      xTicks: [-10, -5, 0, 5, 10, 15, 20], xLabel: "seconds from the pitch", yLabel: "orders per second, per game" });
    el("line", { x1: f.X(0), x2: f.X(0), y1: f.m.top, y2: f.H - f.m.bottom, stroke: css("--ink-3"), "stroke-width": 1 }, f.g);
    el("text", { x: f.X(0) + 5, y: f.m.top + 12, class: "note-strong" }, f.g).textContent = "Pitch";
    const blue = css("--blue");
    el("path", { d: path(win, f.X, f.Y), fill: "none", stroke: blue, "stroke-width": 2, "stroke-linejoin": "round" }, f.g);
    el("circle", { cx: f.X(p.peak_t), cy: f.Y(p.peak), r: 4.5, fill: blue, class: "dot" }, f.g);
    el("text", { x: f.X(p.peak_t) + 9, y: f.Y(p.peak) + 4, class: "note-strong" }, f.g).textContent =
      `${p.peak.toFixed(1)} a second, ${sec(+p.peak_t.toFixed(2))}`;
    crosshair(f, win.map((q) => q[0]), (i) => ({ title: sec(+win[i][0].toFixed(3)), rows: [{ value: win[i][1].toFixed(2), label: "orders per second, per game", color: blue }], points: [{ y: win[i][1], color: blue }] }));
    table(host, ["Seconds from the pitch", "Orders per second"], win.filter((_, i) => i % 2 === 0).map((q) => [q[0].toFixed(2), q[1].toFixed(2)]));
  });

  /* ---------------- 2025 vs 2026 ---------------- */
  register(document.getElementById("fig-seasons"), (host) => {
    if (!S25) { host.textContent = "2025 is still downloading."; return; }
    curve(host, [{ name: "2025", data: S25.beta_all, color: css("--red") }, { name: "2026", data: S26.beta_all, color: css("--blue") }], { height: 290, x: [-5, 60] });
  });

  register(document.getElementById("fig-monthly"), (host) => {
    // one time axis across both seasons; the off-season is a gap, not a line
    const rows = [].concat(S25 ? S25.monthly.map((r) => ({ ...r, season: "2025" })) : [], S26.monthly.map((r) => ({ ...r, season: "2026" })));
    const n = rows.length;
    const ys = rows.flatMap((r) => [r.half_median, r.band_half_median]).filter((v) => v != null);
    const narrow = host.clientWidth < 560;
    const f = frame(host, { height: 270, x: [-0.5, n - 0.5], y: [0, Math.ceil(Math.max(...ys) + 0.5)], xTicks: [], yFmt: (v) => v + " s",
      yLabel: "median seconds to the first trade past halfway", margin: { bottom: 58 } });
    const series = [{ key: "half_median", color: css("--blue"), name: "every big pitch" },
                    { key: "band_half_median", color: css("--red"), name: "equally busy markets" }];
    for (const season of ["2025", "2026"]) {
      const idx = rows.map((r, i) => [i, r]).filter(([, r]) => r.season === season);
      if (!idx.length) continue;
      for (const s of series) {
        const pts = idx.filter(([, r]) => r[s.key] != null).map(([i, r]) => [i, r[s.key]]);
        el("path", { d: path(pts, f.X, f.Y), fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round" }, f.g);
        for (const [i, v] of pts) el("circle", { cx: f.X(i), cy: f.Y(v), r: 4.5, fill: s.color, class: "dot" }, f.g);
      }
      idx.forEach(([i, r]) => {
        if (!narrow || i % 2 === 0)        // on a phone, every other month across both seasons
          el("text", { x: f.X(i), y: f.H - f.m.bottom + 17, class: "tick", "text-anchor": "middle" }, f.g).textContent =
            new Date(r.month + "-15").toLocaleString("en-US", { month: "short" });
        target(f.svg, { x: f.X(i) - 14, y: f.m.top, width: 28, height: f.H - f.m.top - f.m.bottom },
          [{ value: r.half_median.toFixed(2) + " s", label: `every big pitch (${r.n.toLocaleString()})`, color: series[0].color },
           ...(r.band_half_median != null ? [{ value: r.band_half_median.toFixed(2) + " s", label: `equally busy (${r.band_n.toLocaleString()})`, color: series[1].color }] : []),
           { value: r.activity.toFixed(2), label: "orders a second before the pitch (median)" }],
          new Date(r.month + "-15").toLocaleString("en-US", { month: "long", year: "numeric" }));
      });
      const mid = idx[Math.floor((idx.length - 1) / 2)][0];
      el("text", { x: f.X(mid), y: f.H - 12, class: "axis-label", "text-anchor": "middle" }, f.g).textContent = season;
    }
    table(host, ["Month", "Every big pitch", "Equally busy markets", "Orders a second before (median)", "Big pitches"],
      rows.map((r) => [r.month, r.half_median.toFixed(2) + " s", r.band_half_median != null ? r.band_half_median.toFixed(2) + " s" : "too few", r.activity.toFixed(2), r.n.toLocaleString()]));
  });

  /* ---------------- the simulation check ---------------- */
  register(document.getElementById("fig-sim"), (host) => {
    const g = D.sim.curve_grid;
    const f = frame(host, { height: 250, x: [-2, 12], y: [-0.05, 1.1], yTicks: [0, 0.5, 1], yFmt: (v) => pct(v), xFmt: sec, timeBase: true,
      xLabel: "seconds from the pitch", yLabel: "share of the move priced" });
    const idx = g.map((v, i) => i).filter((i) => g[i] >= -2 && g[i] <= 12);
    const ser = [{ name: "true quotes (known in the simulation)", arr: D.sim.beta_true, color: css("--red") }, { name: "read off the trades", arr: D.sim.beta_est, color: css("--blue") }];
    for (const s of ser) el("path", { d: path(idx.map((i) => [g[i], s.arr[i]]), f.X, f.Y), fill: "none", stroke: s.color, "stroke-width": 2 }, f.g);
    crosshair(f, idx.map((i) => g[i]), (k) => {
      const i = idx[k];
      return { title: sec(g[i]), rows: ser.map((s) => ({ value: pct(s.arr[i]), label: s.name, color: s.color })), points: ser.map((s) => ({ y: s.arr[i], color: s.color })) };
    });
    table(host, ["Seconds", ...ser.map((s) => s.name)], idx.map((i) => [sec(g[i]), ...ser.map((s) => pct(s.arr[i]))]));
  });
})();
