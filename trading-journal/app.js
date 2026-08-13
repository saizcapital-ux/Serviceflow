/* ============================================================
   Trading Journal — app logic (vanilla JS + inline SVG)
   Consumes window.JOURNAL_DATA = { meta, trades, prices, intraday }
   ============================================================ */
(function () {
  "use strict";
  const D = window.JOURNAL_DATA;
  if (!D) { document.body.innerHTML = "<p style='padding:40px'>No data loaded.</p>"; return; }

  const $ = (s, r = document) => r.querySelector(s);
  const el = (t, a = {}, kids = []) => {
    const n = document.createElement(t);
    for (const k in a) {
      if (k === "class") n.className = a[k];
      else if (k === "html") n.innerHTML = a[k];
      else n.setAttribute(k, a[k]);
    }
    (Array.isArray(kids) ? kids : [kids]).forEach(c => c && n.append(c.nodeType ? c : document.createTextNode(c)));
    return n;
  };
  const SVGNS = "http://www.w3.org/2000/svg";
  const svgEl = (t, a = {}) => { const n = document.createElementNS(SVGNS, t); for (const k in a) n.setAttribute(k, a[k]); return n; };

  const money = v => (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const moneyS = v => (v > 0 ? "+" : v < 0 ? "-" : "") + "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pct = v => (v * 100).toFixed(1) + "%";
  const fmtDate = iso => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const fmtDateY = iso => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const fmtTime = iso => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const cls = v => v > 0 ? "pos" : v < 0 ? "neg" : "";

  const trades = D.trades.slice();               // chronological
  const meta = D.meta;

  /* ---------------- tooltip ---------------- */
  const tt = el("div", { class: "tt" });
  document.body.append(tt);
  function showTT(html, x, y) {
    tt.innerHTML = html; tt.style.opacity = "1";
    const w = tt.offsetWidth, h = tt.offsetHeight;
    let left = x + 14, top = y - h - 10;
    if (left + w > window.innerWidth - 8) left = x - w - 14;
    if (top < 8) top = y + 16;
    tt.style.left = left + "px"; tt.style.top = top + "px";
  }
  const hideTT = () => { tt.style.opacity = "0"; };

  /* ---------------- stats ---------------- */
  function computeStats(list) {
    const wins = list.filter(t => t.pnl > 0), losses = list.filter(t => t.pnl < 0);
    const gross = list.reduce((s, t) => s + t.pnl, 0);
    const winSum = wins.reduce((s, t) => s + t.pnl, 0);
    const lossSum = losses.reduce((s, t) => s + t.pnl, 0);
    return {
      n: list.length, gross,
      wins: wins.length, losses: losses.length,
      winRate: list.length ? wins.length / list.length : 0,
      avgWin: wins.length ? winSum / wins.length : 0,
      avgLoss: losses.length ? lossSum / losses.length : 0,
      profitFactor: lossSum ? winSum / Math.abs(lossSum) : (winSum ? Infinity : 0),
      best: list.reduce((m, t) => t.pnl > m.pnl ? t : m, list[0]),
      worst: list.reduce((m, t) => t.pnl < m.pnl ? t : m, list[0]),
    };
  }

  // per-day P&L
  function dailyPnl(list) {
    const m = new Map();
    list.forEach(t => m.set(t.date, (m.get(t.date) || 0) + t.pnl));
    return [...m.entries()].map(([date, pnl]) => ({ date, pnl })).sort((a, b) => a.date < b.date ? -1 : 1);
  }

  /* ---------------- KPIs ---------------- */
  function renderKPIs() {
    const s = computeStats(trades);
    const days = dailyPnl(trades);
    const bestDay = days.reduce((m, d) => d.pnl > m.pnl ? d : m, days[0]);
    const greenDays = days.filter(d => d.pnl > 0).length;
    const pf = s.profitFactor === Infinity ? "∞" : s.profitFactor.toFixed(2);
    const tiles = [
      { label: "Net realized P&L", value: moneyS(s.gross), vcls: cls(s.gross), foot: `${s.n} trades · ${meta.rangeStart} → ${meta.rangeEnd}` },
      { label: "Win rate", value: pct(s.winRate), foot: `${s.wins}W / ${s.losses}L` },
      { label: "Profit factor", value: pf, foot: "gross win ÷ gross loss" },
      { label: "Avg win", value: moneyS(s.avgWin), vcls: "pos", foot: "per winning trade" },
      { label: "Avg loss", value: moneyS(s.avgLoss), vcls: "neg", foot: "per losing trade" },
      { label: "Best day", value: moneyS(bestDay.pnl), vcls: cls(bestDay.pnl), foot: `${fmtDateY(bestDay.date)} · ${greenDays}/${days.length} green days` },
      { label: "Best trade", value: moneyS(s.best.pnl), vcls: "pos", foot: `${s.best.symbol} · ${fmtDate(s.best.t)}` },
      { label: "Worst trade", value: moneyS(s.worst.pnl), vcls: "neg", foot: `${s.worst.symbol} · ${fmtDate(s.worst.t)}` },
    ];
    const root = $("#kpis"); root.innerHTML = "";
    tiles.forEach(t => root.append(el("div", { class: "kpi" }, [
      el("div", { class: "label" }, t.label),
      el("div", { class: "value " + (t.vcls || "") }, t.value),
      el("div", { class: "foot" }, t.foot),
    ])));
  }

  /* ---------------- Equity curve ---------------- */
  function renderEquity() {
    const W = 920, H = 300, P = { t: 16, r: 16, b: 26, l: 54 };
    let cum = 0;
    const pts = trades.map((t, i) => { cum += t.pnl; return { i, cum, t }; });
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const maxC = Math.max(0, ...pts.map(p => p.cum));
    const minC = Math.min(0, ...pts.map(p => p.cum));
    const pad = (maxC - minC) * 0.08 || 1;
    const yhi = maxC + pad, ylo = minC - pad;
    const X = i => P.l + (pts.length <= 1 ? 0 : i / (pts.length - 1) * iw);
    const Y = v => P.t + (yhi - v) / (yhi - ylo) * ih;

    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", role: "img" });
    svg.style.height = "300px";
    // gridlines + y labels
    const ticks = 5;
    for (let k = 0; k <= ticks; k++) {
      const v = ylo + (yhi - ylo) * k / ticks, y = Y(v);
      svg.append(svgEl("line", { class: "grid-line", x1: P.l, x2: W - P.r, y1: y, y2: y }));
      const lab = svgEl("text", { class: "axis-txt", x: P.l - 8, y: y + 3, "text-anchor": "end" });
      lab.textContent = moneyS(Math.round(v)); svg.append(lab);
    }
    // zero line
    if (ylo < 0 && yhi > 0) svg.append(svgEl("line", { class: "zero-line", x1: P.l, x2: W - P.r, y1: Y(0), y2: Y(0) }));
    // area
    const areaColor = cum >= 0 ? "var(--win)" : "var(--loss)";
    const dLine = pts.map((p, i) => (i ? "L" : "M") + X(p.i).toFixed(1) + " " + Y(p.cum).toFixed(1)).join(" ");
    const area = svgEl("path", { d: `${dLine} L ${X(pts.length - 1)} ${Y(Math.max(ylo, 0))} L ${X(0)} ${Y(Math.max(ylo, 0))} Z`, fill: areaColor, opacity: "0.10" });
    svg.append(area);
    svg.append(svgEl("path", { class: "price-line", d: dLine, stroke: areaColor }));
    // x labels (5 dates)
    for (let k = 0; k <= 4; k++) {
      const idx = Math.round(k / 4 * (pts.length - 1)), x = X(idx);
      const lab = svgEl("text", { class: "axis-txt", x, y: H - 8, "text-anchor": "middle" });
      lab.textContent = fmtDate(pts[idx].t.t); svg.append(lab);
    }
    // crosshair
    const cross = svgEl("line", { class: "zero-line", y1: P.t, y2: H - P.b, opacity: "0", stroke: "var(--muted)" });
    const dot = svgEl("circle", { r: 4, fill: areaColor, stroke: "var(--surface-1)", "stroke-width": 2, opacity: "0" });
    svg.append(cross, dot);
    const hit = svgEl("rect", { x: P.l, y: P.t, width: iw, height: ih, fill: "transparent" });
    svg.append(hit);
    hit.addEventListener("pointermove", e => {
      const r = svg.getBoundingClientRect();
      const sx = (e.clientX - r.left) / r.width * W;
      let idx = Math.round((sx - P.l) / iw * (pts.length - 1));
      idx = Math.max(0, Math.min(pts.length - 1, idx));
      const p = pts[idx];
      cross.setAttribute("x1", X(idx)); cross.setAttribute("x2", X(idx)); cross.setAttribute("opacity", "0.6");
      dot.setAttribute("cx", X(idx)); dot.setAttribute("cy", Y(p.cum)); dot.setAttribute("opacity", "1");
      showTT(`<div class="h">${fmtDateY(p.t.t)} · ${fmtTime(p.t.t)}</div>
        <div class="r">Equity <b class="${cls(p.cum)}">${moneyS(p.cum)}</b></div>
        <div class="r">${p.t.symbol} trade <b class="${cls(p.t.pnl)}">${moneyS(p.t.pnl)}</b></div>
        <div class="r">Trade #<b>${idx + 1}</b></div>`, e.clientX, e.clientY);
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("opacity", "0"); dot.setAttribute("opacity", "0"); hideTT(); });
    const host = $("#equity"); host.innerHTML = ""; host.append(svg);
  }

  /* ---------------- Daily P&L bars ---------------- */
  function renderDaily() {
    const days = dailyPnl(trades);
    const W = 920, H = 220, P = { t: 14, r: 8, b: 24, l: 54 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const maxA = Math.max(...days.map(d => Math.abs(d.pnl))) || 1;
    const bw = Math.max(2, iw / days.length * 0.72);
    const X = i => P.l + (i + 0.5) / days.length * iw;
    const Y0 = P.t + ih / 2;
    const Yscale = v => v / maxA * (ih / 2);
    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });
    svg.style.height = "220px";
    svg.append(svgEl("line", { class: "zero-line", x1: P.l, x2: W - P.r, y1: Y0, y2: Y0 }));
    // y labels
    [maxA, 0, -maxA].forEach(v => {
      const y = Y0 - Yscale(v);
      const lab = svgEl("text", { class: "axis-txt", x: P.l - 8, y: y + 3, "text-anchor": "end" });
      lab.textContent = moneyS(Math.round(v)); svg.append(lab);
    });
    days.forEach((d, i) => {
      const h = Math.abs(Yscale(d.pnl)), x = X(i) - bw / 2;
      const y = d.pnl >= 0 ? Y0 - h : Y0;
      const rect = svgEl("rect", { x, y, width: bw, height: Math.max(1, h), rx: 2, fill: d.pnl >= 0 ? "var(--win)" : "var(--loss)" });
      rect.style.cursor = "pointer";
      rect.addEventListener("pointerenter", e => showTT(`<div class="h">${fmtDateY(d.date)}</div><div class="r">Day P&L <b class="${cls(d.pnl)}">${moneyS(d.pnl)}</b></div>`, e.clientX, e.clientY));
      rect.addEventListener("pointermove", e => showTT(`<div class="h">${fmtDateY(d.date)}</div><div class="r">Day P&L <b class="${cls(d.pnl)}">${moneyS(d.pnl)}</b></div>`, e.clientX, e.clientY));
      rect.addEventListener("pointerleave", hideTT);
      svg.append(rect);
    });
    for (let k = 0; k <= 4; k++) {
      const idx = Math.round(k / 4 * (days.length - 1)), x = X(idx);
      const lab = svgEl("text", { class: "axis-txt", x, y: H - 7, "text-anchor": "middle" });
      lab.textContent = fmtDate(days[idx].date); svg.append(lab);
    }
    const host = $("#daily"); host.innerHTML = ""; host.append(svg);
  }

  /* ---------------- Symbol price chart w/ trade markers ---------------- */
  const chartable = meta.chartableSymbols.slice()
    .sort((a, b) => symbolPnl(b) - symbolPnl(a));
  function symbolPnl(sym) { return trades.filter(t => t.symbol === sym).reduce((s, t) => s + t.pnl, 0); }
  let currentSym = chartable.includes("SPY") ? "SPY" : chartable[0];
  let intradayMode = false;

  function renderSymbolControls() {
    const sel = $("#symSel"); sel.innerHTML = "";
    chartable.forEach(sym => {
      const n = trades.filter(t => t.symbol === sym).length;
      const o = el("option", { value: sym }, `${sym}  (${n} trades · ${moneyS(symbolPnl(sym))})`);
      if (sym === currentSym) o.selected = true;
      sel.append(o);
    });
    sel.onchange = () => { currentSym = sel.value; intradayMode = false; syncIntradayBtn(); renderSymbolChart(); };
    syncIntradayBtn();
    $("#intradayBtn").onclick = () => { intradayMode = !intradayMode; if (intradayMode) { currentSym = "SPY"; sel.value = "SPY"; } syncIntradayBtn(); renderSymbolChart(); };
  }
  function syncIntradayBtn() {
    const b = $("#intradayBtn");
    b.classList.toggle("active", intradayMode);
    b.textContent = intradayMode ? "◉ Intraday · SPY " + fmtDate(meta.intradayDate) : "○ Intraday · SPY " + fmtDate(meta.intradayDate);
  }

  function triangle(cx, cy, r, up) {
    const p = up
      ? `${cx},${cy - r} ${cx - r * 0.9},${cy + r * 0.72} ${cx + r * 0.9},${cy + r * 0.72}`
      : `${cx},${cy + r} ${cx - r * 0.9},${cy - r * 0.72} ${cx + r * 0.9},${cy - r * 0.72}`;
    return p;
  }

  function renderSymbolChart() {
    const host = $("#symChart"); host.innerHTML = "";
    const W = 920, H = 380, P = { t: 16, r: 16, b: 28, l: 56 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;

    // choose data source
    let bars, symTrades, xKey, labelFmt, title;
    if (intradayMode) {
      bars = D.intraday.map(b => ({ t: b.t, o: b.o, h: b.h, l: b.l, c: b.c }));
      symTrades = trades.filter(t => t.symbol === "SPY" && t.date === meta.intradayDate);
      title = `SPY · ${fmtDateY(meta.intradayDate)} · 5-min bars`;
      labelFmt = fmtTime;
    } else {
      const raw = D.prices[currentSym] || [];
      bars = raw.map(r => ({ t: r[0], o: r[1], h: r[2], l: r[3], c: r[4] }));
      symTrades = trades.filter(t => t.symbol === currentSym);
      title = `${currentSym} · daily · ${meta.rangeStart} → ${meta.rangeEnd}`;
      labelFmt = fmtDate;
    }
    $("#symTitle").textContent = title;
    if (!bars.length) { host.append(el("p", { class: "note" }, "No price data for this symbol.")); return; }

    const hi = Math.max(...bars.map(b => b.h)), lo = Math.min(...bars.map(b => b.l));
    const pad = (hi - lo) * 0.06 || 1;
    const yhi = hi + pad, ylo = lo - pad;
    const X = i => P.l + (bars.length <= 1 ? iw / 2 : (i + 0.5) / bars.length * iw);
    const Y = v => P.t + (yhi - v) / (yhi - ylo) * ih;
    const cw = Math.max(1.4, iw / bars.length * 0.6);

    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });
    svg.style.height = "380px";
    // y grid
    const ticks = 5;
    for (let k = 0; k <= ticks; k++) {
      const v = ylo + (yhi - ylo) * k / ticks, y = Y(v);
      svg.append(svgEl("line", { class: "grid-line", x1: P.l, x2: W - P.r, y1: y, y2: y }));
      const lab = svgEl("text", { class: "axis-txt", x: P.l - 8, y: y + 3, "text-anchor": "end" });
      lab.textContent = "$" + v.toFixed(v > 100 ? 0 : 1); svg.append(lab);
    }
    // candles
    bars.forEach((b, i) => {
      const x = X(i), up = b.c >= b.o;
      const col = up ? "var(--win)" : "var(--loss)";
      svg.append(svgEl("line", { x1: x, x2: x, y1: Y(b.h), y2: Y(b.l), stroke: col, "stroke-width": 1, opacity: 0.55 }));
      const yO = Y(b.o), yC = Y(b.c);
      svg.append(svgEl("rect", { x: x - cw / 2, y: Math.min(yO, yC), width: cw, height: Math.max(1, Math.abs(yC - yO)), fill: col, opacity: 0.55, rx: 0.5 }));
    });
    // x labels
    for (let k = 0; k <= 5; k++) {
      const idx = Math.round(k / 5 * (bars.length - 1)), x = X(idx);
      const lab = svgEl("text", { class: "axis-txt", x, y: H - 9, "text-anchor": "middle" });
      lab.textContent = labelFmt(bars[idx].t); svg.append(lab);
    }

    // map trade -> bar index
    function barIndexFor(tr) {
      if (intradayMode) {
        const tms = new Date(tr.t).getTime();
        let best = 0, bd = Infinity;
        bars.forEach((b, i) => { const d = Math.abs(new Date(b.t).getTime() - tms); if (d < bd) { bd = d; best = i; } });
        return best;
      }
      let idx = bars.findIndex(b => b.t === tr.date);
      if (idx < 0) { // nearest prior trading day
        for (let i = bars.length - 1; i >= 0; i--) { if (bars[i].t <= tr.date) { idx = i; break; } }
      }
      return idx < 0 ? 0 : idx;
    }

    // group by bar to fan out overlapping markers
    const groups = new Map();
    symTrades.forEach(tr => { const i = barIndexFor(tr); if (!groups.has(i)) groups.set(i, []); groups.get(i).push(tr); });
    const maxAbs = Math.max(...symTrades.map(t => Math.abs(t.pnl)), 1);
    const layer = svgEl("g", {});
    groups.forEach((arr, i) => {
      arr.sort((a, b) => new Date(a.t) - new Date(b.t));
      const baseX = X(i), baseY = Y(bars[i].c);
      const spread = Math.min(cw * 1.1 + 6, 22);
      arr.forEach((tr, k) => {
        const win = tr.pnl >= 0;
        const r = 5 + Math.sqrt(Math.abs(tr.pnl) / maxAbs) * 6;
        const off = arr.length > 1 ? (k - (arr.length - 1) / 2) * (spread) : 0;
        const cx = baseX + off, cy = baseY;
        const tri = svgEl("polygon", {
          points: triangle(cx, cy, r, win),
          fill: win ? "var(--win)" : "var(--loss)",
          stroke: "var(--surface-1)", "stroke-width": 1.6,
        });
        tri.style.cursor = "pointer";
        const info = `<div class="h">${tr.symbol} · ${win ? "WIN" : "LOSS"}</div>
          <div class="r">${fmtDateY(tr.t)}${intradayMode ? " · " + fmtTime(tr.t) : ""}</div>
          <div class="r">Realized <b class="${cls(tr.pnl)}">${moneyS(tr.pnl)}</b></div>
          <div class="r">Contracts/shares <b>${tr.qty}</b></div>
          <div class="r">Exec price <b>$${tr.price}</b></div>
          <div class="r">Underlying <b>$${bars[i].c.toFixed(2)}</b></div>`;
        tri.addEventListener("pointerenter", e => showTT(info, e.clientX, e.clientY));
        tri.addEventListener("pointermove", e => showTT(info, e.clientX, e.clientY));
        tri.addEventListener("pointerleave", hideTT);
        layer.append(tri);
      });
    });
    svg.append(layer);
    host.append(svg);

    $("#symMeta").textContent = `${symTrades.length} trades plotted · ${symTrades.filter(t => t.pnl > 0).length}W / ${symTrades.filter(t => t.pnl < 0).length}L · net ${moneyS(symTrades.reduce((s, t) => s + t.pnl, 0))}`;
  }

  /* ---------------- Symbol breakdown ---------------- */
  function renderBreakdown() {
    const bySym = new Map();
    trades.forEach(t => {
      if (!bySym.has(t.symbol)) bySym.set(t.symbol, { sym: t.symbol, pnl: 0, n: 0, w: 0 });
      const o = bySym.get(t.symbol); o.pnl += t.pnl; o.n++; if (t.pnl > 0) o.w++;
    });
    const rows = [...bySym.values()].sort((a, b) => b.pnl - a.pnl);
    const maxAbs = Math.max(...rows.map(r => Math.abs(r.pnl)), 1);
    const host = $("#breakdown"); host.innerHTML = "";
    rows.slice(0, 14).forEach(r => {
      const w = Math.abs(r.pnl) / maxAbs * 100;
      const bar = el("div", { class: "bar-fill" });
      bar.style.width = w + "%";
      bar.style.background = r.pnl >= 0 ? "var(--win)" : "var(--loss)";
      const track = el("div", { class: "bar-track" }, bar);
      const row = el("div", { class: "symbar" }, [
        el("div", { class: "name" }, r.sym),
        track,
        el("div", { class: "amt " + cls(r.pnl) }, moneyS(r.pnl)),
      ]);
      row.title = `${r.sym}: ${r.n} trades, ${Math.round(r.w / r.n * 100)}% win`;
      host.append(row);
    });
  }

  /* ---------------- Trade log ---------------- */
  let logSort = { key: "t", dir: -1 }, logFilter = "all", logSearch = "";
  function renderLog() {
    let rows = trades.filter(t => {
      if (logFilter === "win" && t.pnl <= 0) return false;
      if (logFilter === "loss" && t.pnl >= 0) return false;
      if (logSearch && !t.symbol.toLowerCase().includes(logSearch.toLowerCase())) return false;
      return true;
    });
    const k = logSort.key, dir = logSort.dir;
    rows.sort((a, b) => {
      let va = a[k], vb = b[k];
      if (k === "t") { va = new Date(a.t).getTime(); vb = new Date(b.t).getTime(); }
      return va < vb ? -dir : va > vb ? dir : 0;
    });
    const tb = $("#logBody"); tb.innerHTML = "";
    rows.forEach(t => {
      const win = t.pnl > 0;
      tb.append(el("tr", {}, [
        el("td", { class: "sym mono" }, fmtDateY(t.t)),
        el("td", { class: "tag" }, fmtTime(t.t)),
        el("td", { class: "sym" }, [el("b", {}, t.symbol)]),
        el("td", {}, [el("span", { class: "pill kind" }, t.kind === "option" ? "OPT" : "EQ")]),
        el("td", {}, String(t.qty)),
        el("td", {}, "$" + t.price),
        el("td", {}, [el("span", { class: "pill " + (win ? "win" : "loss") }, moneyS(t.pnl))]),
      ]));
    });
    $("#logCount").textContent = `${rows.length} trade${rows.length !== 1 ? "s" : ""}`;
  }
  function wireLog() {
    document.querySelectorAll("#logTable thead th[data-k]").forEach(th => {
      th.onclick = () => {
        const key = th.dataset.k;
        if (logSort.key === key) logSort.dir *= -1; else logSort = { key, dir: key === "t" ? -1 : 1 };
        renderLog();
      };
    });
    document.querySelectorAll("#logFilter .chip").forEach(c => {
      c.onclick = () => { logFilter = c.dataset.f; document.querySelectorAll("#logFilter .chip").forEach(x => x.classList.toggle("active", x === c)); renderLog(); };
    });
    $("#logSearch").oninput = e => { logSearch = e.target.value.trim(); renderLog(); };
  }

  /* ---------------- theme ---------------- */
  function wireTheme() {
    const btn = $("#themeBtn");
    btn.onclick = () => {
      const cur = document.documentElement.getAttribute("data-theme");
      const dark = cur ? cur === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
      // re-render charts so var() colors resolve fresh
      renderEquity(); renderDaily(); renderSymbolChart();
    };
  }

  /* ---------------- header meta ---------------- */
  function renderHeader() {
    $("#hAccount").textContent = meta.account;
    $("#hRange").textContent = `${meta.rangeStart} → ${meta.rangeEnd}`;
    $("#hTrades").textContent = meta.tradeCount.toLocaleString();
    $("#hGen").textContent = meta.generatedAt.replace("T", " ").replace("Z", " UTC");
  }

  /* ---------------- boot ---------------- */
  renderHeader();
  renderKPIs();
  renderEquity();
  renderDaily();
  renderSymbolControls();
  renderSymbolChart();
  renderBreakdown();
  wireLog(); renderLog();
  wireTheme();
})();
