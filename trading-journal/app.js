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
      else if (k.startsWith("on") && typeof a[k] === "function") n.addEventListener(k.slice(2), a[k]);
      else n.setAttribute(k, a[k]);
    }
    (Array.isArray(kids) ? kids : [kids]).forEach(c => c != null && n.append(c.nodeType ? c : document.createTextNode(c)));
    return n;
  };
  const SVGNS = "http://www.w3.org/2000/svg";
  const svgEl = (t, a = {}) => { const n = document.createElementNS(SVGNS, t); for (const k in a) n.setAttribute(k, a[k]); return n; };

  const money = v => (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const moneyS = v => (v > 0 ? "+" : v < 0 ? "-" : "") + "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const money0 = v => (v > 0 ? "+" : v < 0 ? "-" : "") + "$" + Math.abs(Math.round(v)).toLocaleString("en-US");
  const pct = v => (v * 100).toFixed(1) + "%";
  const fmtDate = iso => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  const fmtDateY = iso => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  const fmtTime = iso => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" });
  const cls = v => v > 0 ? "pos" : v < 0 ? "neg" : "";
  const etHour = iso => +new Intl.DateTimeFormat("en-US", { hour: "2-digit", hour12: false, timeZone: "America/New_York" }).format(new Date(iso)) % 24;
  const etDow = iso => new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: "America/New_York" }).format(new Date(iso));
  const tradeId = t => `${t.t}|${t.symbol}|${t.pnl}|${t.qty}`;

  const ALL = D.trades.slice();      // chronological, immutable
  const meta = D.meta;
  const maxDateMs = new Date(ALL[ALL.length - 1].t).getTime();

  /* ---------------- notes store (localStorage) ---------------- */
  const NOTE_KEY = "tj_notes_v1";
  let notes = {};
  try { notes = JSON.parse(localStorage.getItem(NOTE_KEY) || "{}"); } catch (e) { notes = {}; }
  const saveNotes = () => { try { localStorage.setItem(NOTE_KEY, JSON.stringify(notes)); } catch (e) {} };
  const TAGS = ["", "A+ setup", "Good", "Scalp", "News", "FOMO", "Revenge", "Overtraded", "Chop", "Mistake"];
  const TAG_COLOR = {
    "A+ setup": "var(--win)", "Good": "var(--win)", "Scalp": "var(--series-1)", "News": "var(--accent)",
    "FOMO": "var(--loss)", "Revenge": "var(--loss)", "Overtraded": "var(--loss)", "Chop": "var(--muted)", "Mistake": "var(--loss)",
  };

  /* ---------------- filters ---------------- */
  const filters = { symbol: "all", kind: "all", range: "all" };
  function rangeStartMs() {
    const d = new Date(maxDateMs);
    switch (filters.range) {
      case "ytd": return Date.UTC(new Date(maxDateMs).getUTCFullYear(), 0, 1);
      case "90": return maxDateMs - 90 * 864e5;
      case "30": return maxDateMs - 30 * 864e5;
      case "mtd": return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
      default: return -Infinity;
    }
  }
  function getFiltered() {
    const start = rangeStartMs();
    return ALL.filter(t => {
      if (filters.symbol !== "all" && t.symbol !== filters.symbol) return false;
      if (filters.kind !== "all" && t.kind !== filters.kind) return false;
      if (new Date(t.t).getTime() < start) return false;
      return true;
    });
  }

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
  const bindTT = (node, html) => {
    node.addEventListener("pointerenter", e => showTT(html, e.clientX, e.clientY));
    node.addEventListener("pointermove", e => showTT(html, e.clientX, e.clientY));
    node.addEventListener("pointerleave", hideTT);
  };

  /* ---------------- stats ---------------- */
  function computeStats(list) {
    const wins = list.filter(t => t.pnl > 0), losses = list.filter(t => t.pnl < 0);
    const gross = list.reduce((s, t) => s + t.pnl, 0);
    const winSum = wins.reduce((s, t) => s + t.pnl, 0);
    const lossSum = losses.reduce((s, t) => s + t.pnl, 0);
    // drawdown + streaks over chronological order
    let cum = 0, peak = 0, maxDD = 0, curW = 0, curL = 0, maxW = 0, maxL = 0;
    list.forEach(t => {
      cum += t.pnl; peak = Math.max(peak, cum); maxDD = Math.min(maxDD, cum - peak);
      if (t.pnl > 0) { curW++; curL = 0; maxW = Math.max(maxW, curW); }
      else if (t.pnl < 0) { curL++; curW = 0; maxL = Math.max(maxL, curL); }
    });
    return {
      n: list.length, gross,
      wins: wins.length, losses: losses.length,
      winRate: list.length ? wins.length / list.length : 0,
      avgWin: wins.length ? winSum / wins.length : 0,
      avgLoss: losses.length ? lossSum / losses.length : 0,
      expectancy: list.length ? gross / list.length : 0,
      profitFactor: lossSum ? winSum / Math.abs(lossSum) : (winSum ? Infinity : 0),
      maxDD, maxW, maxL,
      best: list.length ? list.reduce((m, t) => t.pnl > m.pnl ? t : m, list[0]) : null,
      worst: list.length ? list.reduce((m, t) => t.pnl < m.pnl ? t : m, list[0]) : null,
    };
  }
  function dailyPnl(list) {
    const m = new Map();
    list.forEach(t => m.set(t.date, (m.get(t.date) || 0) + t.pnl));
    return [...m.entries()].map(([date, pnl]) => ({ date, pnl })).sort((a, b) => a.date < b.date ? -1 : 1);
  }

  /* ---------------- KPIs ---------------- */
  function renderKPIs(list) {
    const s = computeStats(list);
    const days = dailyPnl(list);
    const bestDay = days.length ? days.reduce((m, d) => d.pnl > m.pnl ? d : m, days[0]) : { pnl: 0, date: "" };
    const greenDays = days.filter(d => d.pnl > 0).length;
    const pf = s.profitFactor === Infinity ? "∞" : s.profitFactor.toFixed(2);
    const tiles = [
      { label: "Net realized P&L", value: moneyS(s.gross), vcls: cls(s.gross), foot: `${s.n} trades` },
      { label: "Win rate", value: pct(s.winRate), foot: `${s.wins}W / ${s.losses}L` },
      { label: "Expectancy", value: moneyS(s.expectancy), vcls: cls(s.expectancy), foot: "avg per trade" },
      { label: "Profit factor", value: pf, foot: "gross win ÷ gross loss" },
      { label: "Avg win", value: moneyS(s.avgWin), vcls: "pos", foot: "per winner" },
      { label: "Avg loss", value: moneyS(s.avgLoss), vcls: "neg", foot: "per loser" },
      { label: "Max drawdown", value: money0(s.maxDD), vcls: "neg", foot: "peak-to-trough" },
      { label: "Streaks", value: `${s.maxW}W · ${s.maxL}L`, foot: "longest win / loss run" },
      { label: "Best day", value: money0(bestDay.pnl), vcls: cls(bestDay.pnl), foot: bestDay.date ? `${fmtDateY(bestDay.date)} · ${greenDays}/${days.length} green` : "—" },
      { label: "Best trade", value: s.best ? money0(s.best.pnl) : "—", vcls: "pos", foot: s.best ? `${s.best.symbol} · ${fmtDate(s.best.t)}` : "" },
      { label: "Worst trade", value: s.worst ? money0(s.worst.pnl) : "—", vcls: "neg", foot: s.worst ? `${s.worst.symbol} · ${fmtDate(s.worst.t)}` : "" },
    ];
    const root = $("#kpis"); root.innerHTML = "";
    tiles.forEach(t => root.append(el("div", { class: "kpi" }, [
      el("div", { class: "label" }, t.label),
      el("div", { class: "value " + (t.vcls || "") }, t.value),
      el("div", { class: "foot" }, t.foot),
    ])));
  }

  /* ---------------- Equity curve + drawdown ---------------- */
  function renderEquity(list) {
    const host = $("#equity"); host.innerHTML = "";
    if (!list.length) { host.append(el("p", { class: "empty" }, "No trades in this view.")); return; }
    const W = 920, H = 300, P = { t: 16, r: 16, b: 26, l: 58 };
    let cum = 0, peak = 0;
    const pts = list.map((t, i) => { cum += t.pnl; peak = Math.max(peak, cum); return { i, cum, peak, t }; });
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const maxC = Math.max(0, ...pts.map(p => p.peak));
    const minC = Math.min(0, ...pts.map(p => p.cum));
    const pad = (maxC - minC) * 0.08 || 1;
    const yhi = maxC + pad, ylo = minC - pad;
    const X = i => P.l + (pts.length <= 1 ? iw / 2 : i / (pts.length - 1) * iw);
    const Y = v => P.t + (yhi - v) / (yhi - ylo) * ih;
    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" });
    svg.style.height = "300px";
    for (let k = 0; k <= 5; k++) {
      const v = ylo + (yhi - ylo) * k / 5, y = Y(v);
      svg.append(svgEl("line", { class: "grid-line", x1: P.l, x2: W - P.r, y1: y, y2: y }));
      const lab = svgEl("text", { class: "axis-txt", x: P.l - 8, y: y + 3, "text-anchor": "end" }); lab.textContent = money0(v); svg.append(lab);
    }
    if (ylo < 0 && yhi > 0) svg.append(svgEl("line", { class: "zero-line", x1: P.l, x2: W - P.r, y1: Y(0), y2: Y(0) }));
    const areaColor = cum >= 0 ? "var(--win)" : "var(--loss)";
    const dLine = pts.map((p, i) => (i ? "L" : "M") + X(p.i).toFixed(1) + " " + Y(p.cum).toFixed(1)).join(" ");
    svg.append(svgEl("path", { d: `${dLine} L ${X(pts.length - 1)} ${Y(Math.max(ylo, 0))} L ${X(0)} ${Y(Math.max(ylo, 0))} Z`, fill: areaColor, opacity: "0.10" }));
    // running peak (drawdown reference)
    const dPeak = pts.map((p, i) => (i ? "L" : "M") + X(p.i).toFixed(1) + " " + Y(p.peak).toFixed(1)).join(" ");
    svg.append(svgEl("path", { d: dPeak, fill: "none", stroke: "var(--muted)", "stroke-width": 1, "stroke-dasharray": "2 3", opacity: 0.7 }));
    svg.append(svgEl("path", { class: "price-line", d: dLine, stroke: areaColor }));
    for (let k = 0; k <= 4; k++) {
      const idx = Math.round(k / 4 * (pts.length - 1)), x = X(idx);
      const lab = svgEl("text", { class: "axis-txt", x, y: H - 8, "text-anchor": "middle" }); lab.textContent = fmtDate(pts[idx].t.t); svg.append(lab);
    }
    const cross = svgEl("line", { class: "zero-line", y1: P.t, y2: H - P.b, opacity: "0", stroke: "var(--muted)" });
    const dot = svgEl("circle", { r: 4, fill: areaColor, stroke: "var(--surface-1)", "stroke-width": 2, opacity: "0" });
    svg.append(cross, dot);
    const hit = svgEl("rect", { x: P.l, y: P.t, width: iw, height: ih, fill: "transparent" }); svg.append(hit);
    hit.addEventListener("pointermove", e => {
      const r = svg.getBoundingClientRect();
      let idx = Math.round(((e.clientX - r.left) / r.width * W - P.l) / iw * (pts.length - 1));
      idx = Math.max(0, Math.min(pts.length - 1, idx));
      const p = pts[idx], dd = p.cum - p.peak;
      cross.setAttribute("x1", X(idx)); cross.setAttribute("x2", X(idx)); cross.setAttribute("opacity", "0.6");
      dot.setAttribute("cx", X(idx)); dot.setAttribute("cy", Y(p.cum)); dot.setAttribute("opacity", "1");
      showTT(`<div class="h">${fmtDateY(p.t.t)} · ${fmtTime(p.t.t)}</div>
        <div class="r">Equity <b class="${cls(p.cum)}">${moneyS(p.cum)}</b></div>
        <div class="r">Drawdown <b class="${dd < 0 ? "neg" : ""}">${money0(dd)}</b></div>
        <div class="r">${p.t.symbol} <b class="${cls(p.t.pnl)}">${moneyS(p.t.pnl)}</b></div>`, e.clientX, e.clientY);
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("opacity", "0"); dot.setAttribute("opacity", "0"); hideTT(); });
    host.append(svg);
  }

  /* ---------------- Daily P&L bars ---------------- */
  function renderDaily(list) {
    const host = $("#daily"); host.innerHTML = "";
    const days = dailyPnl(list);
    if (!days.length) { host.append(el("p", { class: "empty" }, "No trades in this view.")); return; }
    const W = 920, H = 220, P = { t: 14, r: 8, b: 24, l: 58 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const maxA = Math.max(...days.map(d => Math.abs(d.pnl))) || 1;
    const bw = Math.max(2, iw / days.length * 0.72);
    const X = i => P.l + (i + 0.5) / days.length * iw;
    const Y0 = P.t + ih / 2, Ys = v => v / maxA * (ih / 2);
    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" }); svg.style.height = "220px";
    svg.append(svgEl("line", { class: "zero-line", x1: P.l, x2: W - P.r, y1: Y0, y2: Y0 }));
    [maxA, -maxA].forEach(v => { const y = Y0 - Ys(v); const lab = svgEl("text", { class: "axis-txt", x: P.l - 8, y: y + 3, "text-anchor": "end" }); lab.textContent = money0(v); svg.append(lab); });
    days.forEach((d, i) => {
      const h = Math.abs(Ys(d.pnl)), x = X(i) - bw / 2, y = d.pnl >= 0 ? Y0 - h : Y0;
      const rect = svgEl("rect", { x, y, width: bw, height: Math.max(1, h), rx: 2, fill: d.pnl >= 0 ? "var(--win)" : "var(--loss)" });
      rect.style.cursor = "pointer";
      bindTT(rect, `<div class="h">${fmtDateY(d.date)}</div><div class="r">Day P&L <b class="${cls(d.pnl)}">${moneyS(d.pnl)}</b></div>`);
      svg.append(rect);
    });
    for (let k = 0; k <= 4; k++) { const idx = Math.round(k / 4 * (days.length - 1)), x = X(idx); const lab = svgEl("text", { class: "axis-txt", x, y: H - 7, "text-anchor": "middle" }); lab.textContent = fmtDate(days[idx].date); svg.append(lab); }
    host.append(svg);
  }

  /* ---------------- Calendar heatmap ---------------- */
  function renderCalendar(list) {
    const host = $("#calendar"); host.innerHTML = "";
    const days = dailyPnl(list);
    if (!days.length) { host.append(el("p", { class: "empty" }, "No trades in this view.")); return; }
    const pnlByDate = new Map(days.map(d => [d.date, d.pnl]));
    const maxAbs = Math.max(...days.map(d => Math.abs(d.pnl))) || 1;
    const parse = s => { const [y, m, d] = s.split("-").map(Number); return new Date(Date.UTC(y, m - 1, d)); };
    let first = parse(days[0].date), last = parse(days[days.length - 1].date);
    // back up to Monday
    const startMon = new Date(first); const dow = (startMon.getUTCDay() + 6) % 7; startMon.setUTCDate(startMon.getUTCDate() - dow);
    const cell = 15, gap = 4, top = 18, left = 30;
    const weeks = Math.ceil((last - startMon) / (7 * 864e5)) + 1;
    const W = left + weeks * (cell + gap) + 4, H = top + 5 * (cell + gap) + 6;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, style: "max-width:100%" });
    ["Mon", "Wed", "Fri"].forEach((lab, i) => { const t = svgEl("text", { class: "axis-txt", x: left - 6, y: top + (i * 2) * (cell + gap) + cell - 3, "text-anchor": "end" }); t.textContent = lab; svg.append(t); });
    let lastMonth = -1;
    for (let w = 0; w < weeks; w++) {
      for (let d = 0; d < 5; d++) {
        const day = new Date(startMon); day.setUTCDate(startMon.getUTCDate() + w * 7 + d);
        if (day < first || day > last) continue;
        const iso = day.toISOString().slice(0, 10);
        const x = left + w * (cell + gap), y = top + d * (cell + gap);
        // month label
        if (day.getUTCMonth() !== lastMonth && d === 0) {
          lastMonth = day.getUTCMonth();
          const ml = svgEl("text", { class: "axis-txt", x, y: top - 6 }); ml.textContent = day.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" }); svg.append(ml);
        }
        const has = pnlByDate.has(iso);
        const pnl = pnlByDate.get(iso) || 0;
        let fill = "var(--surface-2)", op = 1;
        if (has) { fill = pnl >= 0 ? "var(--win)" : "var(--loss)"; op = 0.28 + 0.72 * Math.min(1, Math.abs(pnl) / maxAbs); }
        const rect = svgEl("rect", { x, y, width: cell, height: cell, rx: 3, fill, "fill-opacity": op, stroke: "var(--border)" });
        if (has) { rect.style.cursor = "pointer"; bindTT(rect, `<div class="h">${fmtDateY(iso)}</div><div class="r">Day P&L <b class="${cls(pnl)}">${moneyS(pnl)}</b></div>`); }
        svg.append(rect);
      }
    }
    host.append(svg);
  }

  /* ---------------- grouped bars (time-of-day / weekday) ---------------- */
  function renderGroupBars(hostSel, items) {
    const host = $(hostSel); host.innerHTML = "";
    if (!items.length) { host.append(el("p", { class: "empty" }, "No trades in this view.")); return; }
    const W = 440, H = 210, P = { t: 14, r: 8, b: 40, l: 50 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const maxA = Math.max(...items.map(d => Math.abs(d.pnl)), 1);
    const bw = Math.min(46, iw / items.length * 0.66);
    const X = i => P.l + (i + 0.5) / items.length * iw;
    const Y0 = P.t + ih / 2, Ys = v => v / maxA * (ih / 2);
    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" }); svg.style.height = "210px";
    svg.append(svgEl("line", { class: "zero-line", x1: P.l, x2: W - P.r, y1: Y0, y2: Y0 }));
    [maxA, -maxA].forEach(v => { const y = Y0 - Ys(v); const lab = svgEl("text", { class: "axis-txt", x: P.l - 8, y: y + 3, "text-anchor": "end" }); lab.textContent = money0(v); svg.append(lab); });
    items.forEach((d, i) => {
      const h = Math.abs(Ys(d.pnl)), x = X(i) - bw / 2, y = d.pnl >= 0 ? Y0 - h : Y0;
      const rect = svgEl("rect", { x, y, width: bw, height: Math.max(1, h), rx: 3, fill: d.pnl >= 0 ? "var(--win)" : "var(--loss)" });
      rect.style.cursor = "pointer";
      bindTT(rect, `<div class="h">${d.label}</div><div class="r">Net P&L <b class="${cls(d.pnl)}">${moneyS(d.pnl)}</b></div><div class="r">Win rate <b>${pct(d.wr)}</b></div><div class="r">Trades <b>${d.n}</b></div>`);
      svg.append(rect);
      const kl = svgEl("text", { class: "axis-txt", x: X(i), y: H - 22, "text-anchor": "middle" }); kl.textContent = d.label; svg.append(kl);
      const wl = svgEl("text", { class: "axis-txt", x: X(i), y: H - 9, "text-anchor": "middle", style: "font-weight:600" }); wl.textContent = d.n ? Math.round(d.wr * 100) + "%" : "—"; svg.append(wl);
    });
    host.append(svg);
  }
  function bucket(list, keyFn, order, labelFn) {
    const m = new Map();
    list.forEach(t => { const k = keyFn(t); if (!m.has(k)) m.set(k, { pnl: 0, n: 0, w: 0 }); const o = m.get(k); o.pnl += t.pnl; o.n++; if (t.pnl > 0) o.w++; });
    return order.filter(k => m.has(k)).map(k => { const o = m.get(k); return { label: labelFn(k), pnl: o.pnl, n: o.n, wr: o.n ? o.w / o.n : 0 }; });
  }
  function renderTimeOfDay(list) {
    const items = bucket(list, t => etHour(t.t), [9, 10, 11, 12, 13, 14, 15], h => (h > 12 ? h - 12 : h) + (h >= 12 ? "p" : "a"));
    renderGroupBars("#timeofday", items);
  }
  function renderDayOfWeek(list) {
    const items = bucket(list, t => etDow(t.t), ["Mon", "Tue", "Wed", "Thu", "Fri"], k => k);
    renderGroupBars("#dayofweek", items);
  }

  /* ---------------- Symbol price chart ---------------- */
  const chartable = meta.chartableSymbols.slice().sort((a, b) => symbolPnl(b) - symbolPnl(a));
  function symbolPnl(sym) { return ALL.filter(t => t.symbol === sym).reduce((s, t) => s + t.pnl, 0); }
  let currentSym = chartable.includes("SPY") ? "SPY" : chartable[0];
  let intradayMode = false;

  function renderSymbolControls() {
    const sel = $("#symSel"); sel.innerHTML = "";
    chartable.forEach(sym => {
      const n = ALL.filter(t => t.symbol === sym).length;
      const o = el("option", { value: sym }, `${sym}  (${n} trades · ${moneyS(symbolPnl(sym))})`);
      if (sym === currentSym) o.selected = true; sel.append(o);
    });
    sel.onchange = () => { currentSym = sel.value; intradayMode = false; syncIntradayBtn(); renderSymbolChart(); };
    syncIntradayBtn();
    $("#intradayBtn").onclick = () => { intradayMode = !intradayMode; if (intradayMode) { currentSym = "SPY"; sel.value = "SPY"; } syncIntradayBtn(); renderSymbolChart(); };
  }
  function syncIntradayBtn() {
    const b = $("#intradayBtn"); b.classList.toggle("active", intradayMode);
    b.textContent = (intradayMode ? "◉ " : "○ ") + "Intraday · SPY " + fmtDate(meta.intradayDate);
  }
  const triangle = (cx, cy, r, up) => up
    ? `${cx},${cy - r} ${cx - r * 0.9},${cy + r * 0.72} ${cx + r * 0.9},${cy + r * 0.72}`
    : `${cx},${cy + r} ${cx - r * 0.9},${cy - r * 0.72} ${cx + r * 0.9},${cy - r * 0.72}`;

  function renderSymbolChart() {
    const host = $("#symChart"); host.innerHTML = "";
    const W = 920, H = 380, P = { t: 16, r: 16, b: 28, l: 56 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const filteredIds = new Set(getFiltered().map(tradeId));  // respect date/type filters for markers
    let bars, symTrades, labelFmt, title;
    if (intradayMode) {
      bars = D.intraday.map(b => ({ t: b.t, o: b.o, h: b.h, l: b.l, c: b.c }));
      symTrades = ALL.filter(t => t.symbol === "SPY" && t.date === meta.intradayDate && filteredIds.has(tradeId(t)));
      title = `SPY · ${fmtDateY(meta.intradayDate)} · 5-min bars`; labelFmt = fmtTime;
    } else {
      const raw = D.prices[currentSym] || [];
      bars = raw.map(r => ({ t: r[0], o: r[1], h: r[2], l: r[3], c: r[4] }));
      symTrades = ALL.filter(t => t.symbol === currentSym && filteredIds.has(tradeId(t)));
      title = `${currentSym} · daily`; labelFmt = fmtDate;
    }
    $("#symTitle").textContent = title;
    if (!bars.length) { host.append(el("p", { class: "empty" }, "No price data for this symbol.")); $("#symMeta").textContent = ""; return; }
    const hi = Math.max(...bars.map(b => b.h)), lo = Math.min(...bars.map(b => b.l));
    const pad = (hi - lo) * 0.06 || 1, yhi = hi + pad, ylo = lo - pad;
    const X = i => P.l + (bars.length <= 1 ? iw / 2 : (i + 0.5) / bars.length * iw);
    const Y = v => P.t + (yhi - v) / (yhi - ylo) * ih;
    const cw = Math.max(1.4, iw / bars.length * 0.6);
    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" }); svg.style.height = "380px";
    for (let k = 0; k <= 5; k++) { const v = ylo + (yhi - ylo) * k / 5, y = Y(v); svg.append(svgEl("line", { class: "grid-line", x1: P.l, x2: W - P.r, y1: y, y2: y })); const lab = svgEl("text", { class: "axis-txt", x: P.l - 8, y: y + 3, "text-anchor": "end" }); lab.textContent = "$" + v.toFixed(v > 100 ? 0 : 1); svg.append(lab); }
    bars.forEach((b, i) => {
      const x = X(i), up = b.c >= b.o, col = up ? "var(--win)" : "var(--loss)";
      svg.append(svgEl("line", { x1: x, x2: x, y1: Y(b.h), y2: Y(b.l), stroke: col, "stroke-width": 1, opacity: 0.5 }));
      const yO = Y(b.o), yC = Y(b.c);
      svg.append(svgEl("rect", { x: x - cw / 2, y: Math.min(yO, yC), width: cw, height: Math.max(1, Math.abs(yC - yO)), fill: col, opacity: 0.5, rx: 0.5 }));
    });
    for (let k = 0; k <= 5; k++) { const idx = Math.round(k / 5 * (bars.length - 1)), x = X(idx); const lab = svgEl("text", { class: "axis-txt", x, y: H - 9, "text-anchor": "middle" }); lab.textContent = labelFmt(bars[idx].t); svg.append(lab); }
    function barIndexFor(tr) {
      if (intradayMode) { const tms = new Date(tr.t).getTime(); let best = 0, bd = Infinity; bars.forEach((b, i) => { const d = Math.abs(new Date(b.t).getTime() - tms); if (d < bd) { bd = d; best = i; } }); return best; }
      let idx = bars.findIndex(b => b.t === tr.date);
      if (idx < 0) { for (let i = bars.length - 1; i >= 0; i--) { if (bars[i].t <= tr.date) { idx = i; break; } } }
      return idx < 0 ? 0 : idx;
    }
    const groups = new Map();
    symTrades.forEach(tr => { const i = barIndexFor(tr); if (!groups.has(i)) groups.set(i, []); groups.get(i).push(tr); });
    const maxAbs = Math.max(...symTrades.map(t => Math.abs(t.pnl)), 1);
    const layer = svgEl("g", {});
    groups.forEach((arr, i) => {
      arr.sort((a, b) => new Date(a.t) - new Date(b.t));
      const baseX = X(i), baseY = Y(bars[i].c), spread = Math.min(cw * 1.1 + 6, 22);
      arr.forEach((tr, k) => {
        const win = tr.pnl >= 0, r = 5 + Math.sqrt(Math.abs(tr.pnl) / maxAbs) * 6;
        const off = arr.length > 1 ? (k - (arr.length - 1) / 2) * spread : 0;
        const tri = svgEl("polygon", { points: triangle(baseX + off, baseY, r, win), fill: win ? "var(--win)" : "var(--loss)", stroke: "var(--surface-1)", "stroke-width": 1.6 });
        tri.style.cursor = "pointer";
        const nt = notes[tradeId(tr)];
        bindTT(tri, `<div class="h">${tr.symbol} · ${win ? "WIN" : "LOSS"}</div>
          <div class="r">${fmtDateY(tr.t)}${intradayMode ? " · " + fmtTime(tr.t) : ""}</div>
          <div class="r">Realized <b class="${cls(tr.pnl)}">${moneyS(tr.pnl)}</b></div>
          <div class="r">Underlying <b>$${bars[i].c.toFixed(2)}</b></div>
          ${nt && nt.tag ? `<div class="r">Tag <b>${nt.tag}</b></div>` : ""}${nt && nt.note ? `<div class="r">“${nt.note}”</div>` : ""}`);
        layer.append(tri);
      });
    });
    svg.append(layer); host.append(svg);
    $("#symMeta").textContent = `${symTrades.length} trades plotted · ${symTrades.filter(t => t.pnl > 0).length}W / ${symTrades.filter(t => t.pnl < 0).length}L · net ${moneyS(symTrades.reduce((s, t) => s + t.pnl, 0))}`;
  }

  /* ---------------- Symbol breakdown ---------------- */
  function renderBreakdown(list) {
    const host = $("#breakdown"); host.innerHTML = "";
    const bySym = new Map();
    list.forEach(t => { if (!bySym.has(t.symbol)) bySym.set(t.symbol, { sym: t.symbol, pnl: 0, n: 0, w: 0 }); const o = bySym.get(t.symbol); o.pnl += t.pnl; o.n++; if (t.pnl > 0) o.w++; });
    const rows = [...bySym.values()].sort((a, b) => b.pnl - a.pnl);
    if (!rows.length) { host.append(el("p", { class: "empty" }, "No trades in this view.")); return; }
    const maxAbs = Math.max(...rows.map(r => Math.abs(r.pnl)), 1);
    rows.slice(0, 14).forEach(r => {
      const bar = el("div", { class: "bar-fill" }); bar.style.width = (Math.abs(r.pnl) / maxAbs * 100) + "%"; bar.style.background = r.pnl >= 0 ? "var(--win)" : "var(--loss)";
      const row = el("div", { class: "symbar" }, [el("div", { class: "name" }, r.sym), el("div", { class: "bar-track" }, bar), el("div", { class: "amt " + cls(r.pnl) }, moneyS(r.pnl))]);
      row.title = `${r.sym}: ${r.n} trades, ${Math.round(r.w / r.n * 100)}% win`; host.append(row);
    });
  }

  /* ---------------- Insights (auto-generated) ---------------- */
  const hourLabel = h => (h > 12 ? h - 12 : h) + (h >= 12 ? "pm" : "am");
  function computeInsights(list) {
    const out = [];
    if (list.length < 8) return out;
    const s = computeStats(list);
    // payoff / breakeven
    const be = (s.avgWin - s.avgLoss) ? Math.abs(s.avgLoss) / (s.avgWin + Math.abs(s.avgLoss)) : 0;
    out.push({
      tone: s.winRate >= be ? "good" : "bad",
      title: "Payoff math",
      text: `Win rate <b>${pct(s.winRate)}</b> vs breakeven <b>${pct(be)}</b> — winners avg <b class="pos">${moneyS(s.avgWin)}</b>, losers <b class="neg">${moneyS(s.avgLoss)}</b>. You ${s.winRate >= be ? "clear" : "fall short of"} the line your own trade sizes require.`,
    });
    // post-loss tilt
    let afterLoss = [], afterWin = [];
    for (let i = 1; i < list.length; i++) { if (list[i - 1].pnl < 0) afterLoss.push(list[i].pnl); else if (list[i - 1].pnl > 0) afterWin.push(list[i].pnl); }
    if (afterLoss.length >= 5 && afterWin.length >= 5) {
      const al = afterLoss.reduce((a, b) => a + b, 0) / afterLoss.length;
      const aw = afterWin.reduce((a, b) => a + b, 0) / afterWin.length;
      out.push({
        tone: al < aw - 2 ? "bad" : "good",
        title: "Tilt check",
        text: `After a loss your next trade averages <b class="${cls(al)}">${moneyS(al)}</b>, vs <b class="${cls(aw)}">${moneyS(aw)}</b> after a win. ${al < aw - 2 ? "Losses drag the trade that follows — a cool-off rule could help." : "You don't chase losses — good discipline."}`,
      });
    }
    // overtrading
    const days = {};
    list.forEach(t => { (days[t.date] = days[t.date] || { n: 0, pnl: 0 }); days[t.date].n++; days[t.date].pnl += t.pnl; });
    const dayArr = Object.values(days);
    if (dayArr.length >= 6) {
      const counts = dayArr.map(d => d.n).sort((a, b) => a - b);
      const thresh = counts[Math.floor(counts.length * 0.75)];
      const busy = dayArr.filter(d => d.n >= thresh), calm = dayArr.filter(d => d.n < thresh);
      if (busy.length && calm.length && thresh > 1) {
        const bAvg = busy.reduce((a, d) => a + d.pnl, 0) / busy.length;
        const cAvg = calm.reduce((a, d) => a + d.pnl, 0) / calm.length;
        out.push({
          tone: bAvg < cAvg - 5 ? "bad" : "good",
          title: "Overtrading",
          text: `On busy days (<b>${thresh}+</b> trades) you average <b class="${cls(bAvg)}">${money0(bAvg)}</b>/day vs <b class="${cls(cAvg)}">${money0(cAvg)}</b> on lighter days. ${bAvg < cAvg - 5 ? "More trades, worse days — activity is hurting you." : "Volume isn't hurting your daily result."}`,
        });
      }
    }
    // best/worst hour
    const hrs = bucket(list, t => etHour(t.t), [9, 10, 11, 12, 13, 14, 15], h => h).filter(x => true);
    const hrRaw = [9, 10, 11, 12, 13, 14, 15].map(h => { const arr = list.filter(t => etHour(t.t) === h); return { h, pnl: arr.reduce((a, b) => a + b.pnl, 0), n: arr.length }; }).filter(x => x.n >= 4);
    if (hrRaw.length >= 2) {
      const best = hrRaw.reduce((m, x) => x.pnl > m.pnl ? x : m);
      const worst = hrRaw.reduce((m, x) => x.pnl < m.pnl ? x : m);
      out.push({ tone: "warn", title: "Time of day", text: `Best hour <b>${hourLabel(best.h)} ET</b> at <b class="pos">${money0(best.pnl)}</b>; worst <b>${hourLabel(worst.h)} ET</b> at <b class="neg">${money0(worst.pnl)}</b>. Trade the hours that pay you.` });
    }
    // weekday
    const wdays = ["Mon", "Tue", "Wed", "Thu", "Fri"].map(k => { const arr = list.filter(t => etDow(t.t) === k); return { k, pnl: arr.reduce((a, b) => a + b.pnl, 0), n: arr.length }; }).filter(x => x.n >= 3);
    if (wdays.length >= 2) {
      const best = wdays.reduce((m, x) => x.pnl > m.pnl ? x : m);
      const worst = wdays.reduce((m, x) => x.pnl < m.pnl ? x : m);
      if (worst.pnl < 0) out.push({ tone: "warn", title: "Weekday", text: `<b>${worst.k}</b> is your weakest day (<b class="neg">${money0(worst.pnl)}</b>) while <b>${best.k}</b> leads (<b class="pos">${money0(best.pnl)}</b>).` });
    }
    // symbol drain
    const bySym = {};
    list.forEach(t => { (bySym[t.symbol] = bySym[t.symbol] || { pnl: 0, n: 0 }); bySym[t.symbol].pnl += t.pnl; bySym[t.symbol].n++; });
    const symArr = Object.entries(bySym).map(([k, v]) => ({ k, ...v })).filter(x => x.n >= 3);
    if (symArr.length >= 2) {
      const best = symArr.reduce((m, x) => x.pnl > m.pnl ? x : m);
      const worst = symArr.reduce((m, x) => x.pnl < m.pnl ? x : m);
      if (worst.pnl < 0) out.push({ tone: worst.n >= 20 ? "bad" : "warn", title: "Symbol focus", text: `<b>${worst.k}</b> has cost you <b class="neg">${money0(worst.pnl)}</b> over ${worst.n} trades; <b>${best.k}</b> is your best at <b class="pos">${money0(best.pnl)}</b>.` });
    }
    return out.slice(0, 6);
  }
  function renderInsights(list) {
    const host = $("#insights"); host.innerHTML = "";
    const items = computeInsights(list);
    if (!items.length) { host.append(el("p", { class: "empty" }, "Not enough trades in this view to surface patterns.")); return; }
    const icon = { good: "▲", bad: "▼", warn: "◆" };
    items.forEach(it => host.append(el("div", { class: "insight " + it.tone }, [
      el("div", { class: "ic" }, icon[it.tone] || "•"),
      el("div", {}, [el("div", { class: "t" }, it.title), el("div", { class: "d", html: it.text })]),
    ])));
  }

  /* ---------------- Distribution histogram ---------------- */
  function renderDistribution(list) {
    const host = $("#distribution"); host.innerHTML = "";
    if (!list.length) { host.append(el("p", { class: "empty" }, "No trades in this view.")); return; }
    const bins = [
      { lo: -Infinity, hi: -100, label: "≤-100", pos: false },
      { lo: -100, hi: -50, label: "-100..-50", pos: false },
      { lo: -50, hi: -25, label: "-50..-25", pos: false },
      { lo: -25, hi: 0, label: "-25..0", pos: false },
      { lo: 0, hi: 25, label: "0..25", pos: true },
      { lo: 25, hi: 50, label: "25..50", pos: true },
      { lo: 50, hi: 100, label: "50..100", pos: true },
      { lo: 100, hi: Infinity, label: "≥100", pos: true },
    ].map(b => ({ ...b, n: 0, sum: 0 }));
    list.forEach(t => {
      const v = t.pnl;
      let b = v < 0 ? bins.find(x => v > x.lo && v <= x.hi) : bins.find(x => v >= x.lo && v < x.hi && x.pos);
      if (!b) b = v >= 100 ? bins[7] : bins[0];
      b.n++; b.sum += v;
    });
    const W = 440, H = 230, P = { t: 14, r: 8, b: 40, l: 34 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const maxN = Math.max(...bins.map(b => b.n), 1);
    const bw = iw / bins.length * 0.74;
    const X = i => P.l + (i + 0.5) / bins.length * iw;
    const Y = n => P.t + ih - n / maxN * ih;
    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" }); svg.style.height = "230px";
    svg.append(svgEl("line", { class: "grid-line", x1: P.l, x2: W - P.r, y1: P.t + ih, y2: P.t + ih }));
    bins.forEach((b, i) => {
      const h = (b.n / maxN) * ih, x = X(i) - bw / 2;
      const rect = svgEl("rect", { x, y: P.t + ih - h, width: bw, height: Math.max(b.n ? 2 : 0, h), rx: 2, fill: b.pos ? "var(--win)" : "var(--loss)", opacity: b.n ? 0.9 : 0.25 });
      rect.style.cursor = "pointer";
      bindTT(rect, `<div class="h">$${b.label}</div><div class="r">Trades <b>${b.n}</b></div><div class="r">Total <b class="${cls(b.sum)}">${moneyS(b.sum)}</b></div>`);
      svg.append(rect);
      if (b.n) { const cl = svgEl("text", { class: "axis-txt", x: X(i), y: P.t + ih - h - 4, "text-anchor": "middle", style: "font-weight:600" }); cl.textContent = b.n; svg.append(cl); }
      const lab = svgEl("text", { class: "axis-txt", x: X(i), y: H - 22, "text-anchor": "middle", style: "font-size:9.5px" }); lab.textContent = b.label; svg.append(lab);
    });
    const zx = P.l + iw / 2;
    svg.append(svgEl("line", { x1: zx, x2: zx, y1: P.t, y2: P.t + ih, stroke: "var(--axis)", "stroke-dasharray": "3 3" }));
    const zl = svgEl("text", { class: "axis-txt", x: zx, y: H - 8, "text-anchor": "middle" }); zl.textContent = "◄ losses  ·  wins ►"; svg.append(zl);
    host.append(svg);
  }

  /* ---------------- Edge by position size ---------------- */
  function sizeBucket(q) { if (q < 1) return "<1"; if (q <= 3) return String(Math.round(q)); if (q <= 5) return "4-5"; if (q <= 9) return "6-9"; return "10+"; }
  function renderSizing(list) {
    const order = ["<1", "1", "2", "3", "4-5", "6-9", "10+"];
    const items = bucket(list, t => sizeBucket(t.qty), order, k => k);
    renderGroupBars("#sizing", items);
  }

  /* ---------------- Tag performance ---------------- */
  function renderTagPerf(list) {
    const host = $("#tagperf"); host.innerHTML = "";
    const m = new Map();
    list.forEach(t => { const nt = notes[tradeId(t)]; if (!nt || !nt.tag) return; if (!m.has(nt.tag)) m.set(nt.tag, { pnl: 0, n: 0, w: 0 }); const o = m.get(nt.tag); o.pnl += t.pnl; o.n++; if (t.pnl > 0) o.w++; });
    if (!m.size) { host.append(el("p", { class: "empty", style: "line-height:1.6" }, "Tag trades in the log below (A+ setup, FOMO, revenge…) and this shows which of your reads actually pay — win rate and net P&L per tag.")); return; }
    host.append(el("div", { class: "tp-row head" }, [el("div", {}, "Tag"), el("div", { class: "r" }, "N"), el("div", { class: "r" }, "Win%"), el("div", { class: "r" }, "Net P&L")]));
    [...m.entries()].sort((a, b) => b[1].pnl - a[1].pnl).forEach(([tag, o]) => {
      const chip = el("span", { class: "tag-chip" }, tag); chip.style.background = "var(--surface-1)"; chip.style.color = (TAG_COLOR[tag] || "var(--text-secondary)"); chip.style.border = "1px solid var(--border)";
      host.append(el("div", { class: "tp-row" }, [
        el("div", {}, chip),
        el("div", { class: "r mono" }, String(o.n)),
        el("div", { class: "r mono" }, Math.round(o.w / o.n * 100) + "%"),
        el("div", { class: "r mono " + cls(o.pnl) }, moneyS(o.pnl)),
      ]));
    });
  }

  /* ---------------- Trade log ---------------- */
  let logSort = { key: "t", dir: -1 }, logFilter = "all", logSearch = "";
  function currentLogRows() {
    let rows = getFiltered().filter(t => {
      if (logFilter === "win" && t.pnl <= 0) return false;
      if (logFilter === "loss" && t.pnl >= 0) return false;
      if (logFilter === "tagged") { const nt = notes[tradeId(t)]; if (!nt || (!nt.tag && !nt.note)) return false; }
      if (logSearch && !t.symbol.toLowerCase().includes(logSearch.toLowerCase())) return false;
      return true;
    });
    const k = logSort.key, dir = logSort.dir;
    rows.sort((a, b) => { let va = a[k], vb = b[k]; if (k === "t") { va = new Date(a.t).getTime(); vb = new Date(b.t).getTime(); } return va < vb ? -dir : va > vb ? dir : 0; });
    return rows;
  }
  function renderLog() {
    const rows = currentLogRows();
    const tb = $("#logBody"); tb.innerHTML = "";
    if (!rows.length) { tb.append(el("tr", {}, [el("td", { class: "left", colspan: 9 }, el("div", { class: "empty" }, "No trades match these filters."))])); $("#logCount").textContent = "0 trades"; return; }
    rows.forEach(t => {
      const win = t.pnl > 0, id = tradeId(t), nt = notes[id] || {};
      const tagSel = el("select", { class: "tag-sel", onchange: e => { setNote(id, "tag", e.target.value); } },
        TAGS.map(tg => { const o = el("option", { value: tg }, tg || "—"); if ((nt.tag || "") === tg) o.selected = true; return o; }));
      const noteInp = el("input", { class: "note-input", type: "text", value: nt.note || "", placeholder: "why…",
        onchange: e => setNote(id, "note", e.target.value.trim()) });
      tb.append(el("tr", {}, [
        el("td", { class: "sym mono" }, fmtDateY(t.t)),
        el("td", { class: "tag" }, fmtTime(t.t)),
        el("td", { class: "sym" }, [el("b", {}, t.symbol)]),
        el("td", {}, [el("span", { class: "pill kind" }, t.kind === "option" ? "OPT" : "EQ")]),
        el("td", {}, String(t.qty)),
        el("td", {}, "$" + t.price),
        el("td", {}, [el("span", { class: "pill " + (win ? "win" : "loss") }, moneyS(t.pnl))]),
        el("td", { class: "left" }, tagSel),
        el("td", { class: "left" }, noteInp),
      ]));
    });
    $("#logCount").textContent = `${rows.length} trade${rows.length !== 1 ? "s" : ""}`;
  }
  function setNote(id, field, val) {
    if (!notes[id]) notes[id] = {};
    notes[id][field] = val;
    if (!notes[id].tag && !notes[id].note) delete notes[id];
    saveNotes();
    if (field === "tag") renderTagPerf(getFiltered());
    if (logFilter === "tagged") renderLog();
  }
  function wireLog() {
    document.querySelectorAll("#logTable thead th[data-k]").forEach(th => {
      th.onclick = () => { const key = th.dataset.k; if (logSort.key === key) logSort.dir *= -1; else logSort = { key, dir: key === "t" ? -1 : 1 }; renderLog(); };
    });
    document.querySelectorAll("#logFilter .chip").forEach(c => {
      c.onclick = () => { logFilter = c.dataset.f; document.querySelectorAll("#logFilter .chip").forEach(x => x.classList.toggle("active", x === c)); renderLog(); };
    });
    $("#logSearch").oninput = e => { logSearch = e.target.value.trim(); renderLog(); };
    $("#exportBtn").onclick = exportCSV;
    $("#backupBtn").onclick = () => {
      if (!Object.keys(notes).length) { showModal("Backup notes", "{}", { note: "You haven't tagged or noted any trades yet." }); return; }
      showModal(`Backup notes · ${Object.keys(notes).length} annotated trades`, JSON.stringify(notes, null, 2), { note: "Copy this JSON somewhere safe. Paste it into Restore on another device or after refreshing data." });
    };
    $("#restoreBtn").onclick = () => {
      showModal("Restore notes", "", {
        editable: true,
        note: "Paste a previously backed-up notes JSON and Apply. It merges into your current annotations.",
        onApply: txt => {
          let obj; try { obj = JSON.parse(txt); } catch (e) { return "Invalid JSON — check and try again."; }
          if (typeof obj !== "object" || !obj) return "That isn't a notes object.";
          let added = 0; for (const k in obj) { notes[k] = obj[k]; added++; }
          saveNotes(); renderLog(); renderTagPerf(getFiltered());
          return true;
        },
      });
    };
  }
  function exportCSV() {
    const rows = currentLogRows();
    const head = ["date_utc", "time_et", "symbol", "type", "qty", "exec_price", "realized_pnl", "tag", "note"];
    const lines = [head.join(",")];
    rows.forEach(t => {
      const nt = notes[tradeId(t)] || {};
      const cells = [t.t, fmtTime(t.t), t.symbol, t.kind, t.qty, t.price, t.pnl, nt.tag || "", (nt.note || "").replace(/"/g, '""')];
      lines.push(cells.map(c => /[",\n]/.test(String(c)) ? `"${c}"` : c).join(","));
    });
    showModal(`Export ${rows.length} trades (CSV)`, lines.join("\n"));
  }

  /* ---------------- modal ---------------- */
  function showModal(title, text, opts) {
    opts = opts || {};
    const ta = el("textarea", opts.editable ? {} : { readonly: "" }); ta.value = text;
    if (opts.editable) ta.placeholder = "Paste JSON here…";
    const msg = el("p", { class: "note", style: "margin-bottom:8px" }, opts.note || "Downloads are blocked inside shared pages — select all and copy, or use the button.");
    const actions = el("div", { class: "modal-actions" }, [el("button", { class: "btn", onclick: () => bg.remove() }, "Close")]);
    if (opts.editable && opts.onApply) {
      actions.append(el("button", { class: "btn primary", onclick: () => {
        const res = opts.onApply(ta.value.trim());
        if (res === true) bg.remove(); else { msg.textContent = res || "Could not apply."; msg.style.color = "var(--loss)"; }
      } }, "Apply"));
    } else {
      actions.append(el("button", { class: "btn primary", onclick: () => { ta.select(); try { navigator.clipboard.writeText(text); } catch (e) { document.execCommand("copy"); } } }, "Copy to clipboard"));
    }
    const bg = el("div", { class: "modal-bg", onclick: e => { if (e.target === bg) bg.remove(); } }, [el("div", { class: "modal" }, [el("h3", {}, title), msg, ta, actions])]);
    document.body.append(bg); if (!opts.editable) ta.select();
  }

  /* ---------------- filter bar ---------------- */
  function renderFilterBar() {
    const sel = $("#fSymbol");
    sel.append(el("option", { value: "all" }, "All symbols"));
    meta.symbolsTraded.forEach(s => sel.append(el("option", { value: s }, s)));
    sel.onchange = () => { filters.symbol = sel.value; renderAll(); };
    document.querySelectorAll("#fKind .chip").forEach(c => c.onclick = () => { filters.kind = c.dataset.k; document.querySelectorAll("#fKind .chip").forEach(x => x.classList.toggle("active", x === c)); renderAll(); });
    document.querySelectorAll("#fRange .chip").forEach(c => c.onclick = () => { filters.range = c.dataset.r; document.querySelectorAll("#fRange .chip").forEach(x => x.classList.toggle("active", x === c)); renderAll(); });
    $("#fTotal").textContent = ALL.length;
  }

  /* ---------------- theme ---------------- */
  function wireTheme() {
    $("#themeBtn").onclick = () => {
      const cur = document.documentElement.getAttribute("data-theme");
      const dark = cur ? cur === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
      renderAll();
    };
  }
  function renderHeader() {
    $("#hAccount").textContent = meta.account;
    $("#hRange").textContent = `${meta.rangeStart} → ${meta.rangeEnd}`;
    $("#hTrades").textContent = meta.tradeCount.toLocaleString();
    $("#hGen").textContent = meta.generatedAt.replace("T", " ").replace("Z", " UTC");
  }

  /* ---------------- orchestration ---------------- */
  function renderAll() {
    const list = getFiltered();
    const net = list.reduce((s, t) => s + t.pnl, 0);
    $("#fCount").textContent = list.length;
    const netEl = $("#fNet"); netEl.textContent = moneyS(net); netEl.className = "mono " + cls(net);
    renderKPIs(list);
    renderInsights(list);
    renderEquity(list);
    renderDaily(list);
    renderCalendar(list);
    renderTimeOfDay(list);
    renderDayOfWeek(list);
    renderDistribution(list);
    renderSizing(list);
    renderSymbolChart();
    renderBreakdown(list);
    renderTagPerf(list);
    renderLog();
  }

  /* ---------------- boot ---------------- */
  renderHeader();
  renderFilterBar();
  renderSymbolControls();
  wireLog();
  wireTheme();
  renderAll();
})();
