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

  /* ---------------- Monthly P&L calendar ---------------- */
  let calCursor = null;               // year*12 + month(0-based) of the shown month
  function renderCalendar(list) {
    const host = $("#calendar"); host.innerHTML = "";
    const dayMap = new Map();          // iso -> {pnl, n}
    list.forEach(t => { const o = dayMap.get(t.date) || { pnl: 0, n: 0 }; o.pnl += t.pnl; o.n++; dayMap.set(t.date, o); });
    if (!dayMap.size) { host.append(el("p", { class: "empty" }, "No trades in this view.")); return; }

    const toIdx = iso => { const [Y, M] = iso.split("-").map(Number); return Y * 12 + (M - 1); };
    const keys = [...dayMap.keys()].sort();
    const minIdx = toIdx(keys[0]), maxIdx = toIdx(keys[keys.length - 1]);
    if (calCursor == null || calCursor < minIdx || calCursor > maxIdx) calCursor = maxIdx;
    const y = Math.floor(calCursor / 12), m = calCursor % 12;
    const pad = n => String(n).padStart(2, "0");
    const monKey = `${y}-${pad(m + 1)}`;

    // bucket the month's days into calendar weeks (Mon-Fri columns)
    const dim = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
    const bucket = new Map();
    for (let d = 1; d <= dim; d++) {
      const dt = new Date(Date.UTC(y, m, d)), wd = (dt.getUTCDay() + 6) % 7;
      const mon = new Date(dt); mon.setUTCDate(dt.getUTCDate() - wd);
      const wk = mon.toISOString().slice(0, 10);
      if (!bucket.has(wk)) bucket.set(wk, { mon: wk, cells: new Array(5).fill(undefined), total: 0, n: 0, green: 0, td: 0 });
      const b = bucket.get(wk), iso = dt.toISOString().slice(0, 10), rec = dayMap.get(iso);
      if (wd <= 4) b.cells[wd] = { day: d, iso, rec };
      if (rec) { b.total += rec.pnl; b.n += rec.n; b.td++; if (rec.pnl > 0) b.green++; }
    }
    const weeks = [...bucket.values()].sort((a, b) => a.mon < b.mon ? -1 : 1);

    // month summary
    let mTot = 0, mN = 0, mG = 0, mR = 0, maxAbs = 1;
    dayMap.forEach((o, iso) => { if (iso.slice(0, 7) === monKey) { mTot += o.pnl; mN += o.n; if (o.pnl > 0) mG++; else if (o.pnl < 0) mR++; maxAbs = Math.max(maxAbs, Math.abs(o.pnl)); } });

    // nav bar
    const title = new Date(Date.UTC(y, m, 1)).toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
    const mkNav = (label, delta, enabled) => { const b = el("button", { class: "cal-nav-btn", "aria-label": delta < 0 ? "Previous month" : "Next month", onclick: () => { if (!enabled) return; calCursor += delta; renderCalendar(list); } }, label); b.disabled = !enabled; return b; };
    const nav = el("div", { class: "cal-nav" }, [
      el("div", { class: "cal-nav-l" }, [mkNav("‹", -1, calCursor > minIdx), el("div", { class: "cal-title" }, title), mkNav("›", 1, calCursor < maxIdx)]),
      el("div", { class: "cal-nav-r" }, [
        el("div", { class: "cal-msum " + cls(mTot) }, moneyS(mTot)),
        el("div", { class: "cal-msub" }, mN ? `${mN} trades · ${mG}G / ${mR}R` : "no trades"),
      ]),
    ]);

    // grid
    const scroll = el("div", { class: "cal-scroll" });
    const head = el("div", { class: "cal-grid cal-head" });
    ["Mon", "Tue", "Wed", "Thu", "Fri", "Week"].forEach(l => head.append(el("div", { class: "cal-wdh" }, l)));
    const grid = el("div", { class: "cal-grid" });
    weeks.forEach(w => {
      for (let i = 0; i < 5; i++) {
        const c = w.cells[i];
        if (!c) { grid.append(el("div", { class: "cal-cell out" })); continue; }
        if (!c.rec) { grid.append(el("div", { class: "cal-cell empty" }, [el("span", { class: "cal-dnum" }, String(c.day))])); continue; }
        const p = c.rec.pnl, pos = p >= 0;
        const cell = el("div", { class: "cal-cell " + (pos ? "win" : "loss") }, [
          el("span", { class: "cal-dnum" }, String(c.day)),
          el("div", { class: "cal-pnl " + cls(p) }, money0(p)),
          el("div", { class: "cal-sub" }, `${c.rec.n} trade${c.rec.n > 1 ? "s" : ""}`),
        ]);
        cell.style.setProperty("--tint", (0.12 + 0.34 * Math.min(1, Math.abs(p) / maxAbs)).toFixed(3));
        bindTT(cell, `<div class="h">${fmtDateY(c.iso)}</div><div class="r">Net P&L <b class="${cls(p)}">${moneyS(p)}</b></div><div class="r">Trades <b>${c.rec.n}</b></div>`);
        grid.append(cell);
      }
      const wt = el("div", { class: "cal-cell week " + (w.n ? cls(w.total) : "") }, [
        el("span", { class: "cal-dnum" }, "Week"),
        el("div", { class: "cal-pnl " + cls(w.total) }, w.n ? money0(w.total) : "—"),
        el("div", { class: "cal-sub" }, w.n ? `${w.green}/${w.td} green` : ""),
      ]);
      grid.append(wt);
    });
    scroll.append(head, grid);
    host.append(nav, scroll);
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
  function symbolPnl(sym) { return ALL.filter(t => t.symbol === sym).reduce((s, t) => s + t.pnl, 0); }
  const INTRA = D.intraday2 || {};
  // days (per symbol) that have accurate intraday price data, newest first
  function intradayDays(sym) {
    return Object.keys(INTRA).filter(k => k.slice(0, k.indexOf("|")) === sym)
      .map(k => k.slice(k.indexOf("|") + 1)).sort().reverse();
  }
  // symbols we can chart: those with a daily series OR intraday data
  const chartable = [...new Set([...meta.chartableSymbols, ...(meta.intradaySymbols || [])])]
    .filter(s => (D.prices[s] && D.prices[s].length) || intradayDays(s).length)
    .sort((a, b) => symbolPnl(b) - symbolPnl(a));
  let currentSym = chartable.includes("TSLA") ? "TSLA" : chartable[0];
  let currentView = "";  // "" = daily, otherwise an ISO date with intraday data

  function renderSymbolControls() {
    const sel = $("#symSel"); sel.innerHTML = "";
    chartable.forEach(sym => {
      const n = ALL.filter(t => t.symbol === sym).length;
      const o = el("option", { value: sym }, `${sym}  (${n} trades · ${moneyS(symbolPnl(sym))})`);
      if (sym === currentSym) o.selected = true; sel.append(o);
    });
    sel.onchange = () => { currentSym = sel.value; currentView = defaultView(currentSym); renderDayControl(); renderSymbolChart(); };
    currentView = defaultView(currentSym);
    renderDayControl();
  }
  function defaultView(sym) { const d = intradayDays(sym); return d.length ? d[0] : ""; }
  function renderDayControl() {
    const dsel = $("#daySel"); dsel.innerHTML = "";
    const days = intradayDays(currentSym);
    if (D.prices[currentSym] && D.prices[currentSym].length)
      dsel.append(el("option", { value: "" }, "Daily · full history"));
    days.forEach(d => {
      const n = ALL.filter(t => t.symbol === currentSym && t.date === d).length;
      dsel.append(el("option", { value: d }, `${fmtDate(d)} · intraday · ${n} fill${n > 1 ? "s" : ""}`));
    });
    if (![...dsel.options].some(o => o.value === currentView)) currentView = dsel.options.length ? dsel.options[0].value : "";
    dsel.value = currentView;
    dsel.disabled = dsel.options.length <= 1;
    dsel.onchange = () => { currentView = dsel.value; renderSymbolChart(); };
  }
  const triangle = (cx, cy, r, up) => up
    ? `${cx},${cy - r} ${cx - r * 0.9},${cy + r * 0.72} ${cx + r * 0.9},${cy + r * 0.72}`
    : `${cx},${cy + r} ${cx - r * 0.9},${cy - r * 0.72} ${cx + r * 0.9},${cy - r * 0.72}`;

  function renderSymbolChart() {
    const host = $("#symChart"); host.innerHTML = "";
    const W = 920, H = 380, P = { t: 16, r: 16, b: 28, l: 56 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const filteredIds = new Set(getFiltered().map(tradeId));  // respect date/type filters for markers
    const intra = currentView !== "";
    let bars, symTrades, labelFmt, title;
    if (intra) {
      bars = (INTRA[`${currentSym}|${currentView}`] || []).map(r => ({ t: r[0], o: r[1], h: r[2], l: r[3], c: r[4] }));
      symTrades = ALL.filter(t => t.symbol === currentSym && t.date === currentView && filteredIds.has(tradeId(t)));
      title = `${currentSym} · ${fmtDateY(currentView)} · 5-min bars · fills at exact time & price`; labelFmt = fmtTime;
    } else {
      bars = (D.prices[currentSym] || []).map(r => ({ t: r[0], o: r[1], h: r[2], l: r[3], c: r[4] }));
      symTrades = ALL.filter(t => t.symbol === currentSym && filteredIds.has(tradeId(t)));
      title = `${currentSym} · daily · each fill on its trading day`; labelFmt = fmtDate;
    }
    $("#symTitle").textContent = title;
    if (!bars.length) { host.append(el("p", { class: "empty" }, "No price data for this view.")); $("#symMeta").textContent = ""; return; }
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
    // ----- accurate marker placement -----
    // Intraday: fractional bar position by fill time + interpolated underlying price.
    // Daily: the fill's own trading-day bar.
    const barMs = bars.length > 1 ? new Date(bars[1].t) - new Date(bars[0].t) : 3e5;
    function placeIntraday(tr) {
      const tms = new Date(tr.t).getTime();
      let j = 0;
      for (let i = 0; i < bars.length; i++) { if (new Date(bars[i].t).getTime() <= tms) j = i; else break; }
      const frac = Math.max(0, Math.min(1, (tms - new Date(bars[j].t).getTime()) / barMs));
      const b = bars[j];
      const price = Math.max(b.l, Math.min(b.h, b.o + frac * (b.c - b.o)));  // path within the bar
      return { x: X(j) + frac * (iw / bars.length), y: Y(price), price };
    }
    function placeDaily(tr) {
      let idx = bars.findIndex(b => b.t === tr.date);
      if (idx < 0) for (let i = bars.length - 1; i >= 0; i--) { if (bars[i].t <= tr.date) { idx = i; break; } }
      if (idx < 0) idx = 0;
      return { x: X(idx), y: Y(bars[idx].c), price: bars[idx].c, idx };
    }
    const maxAbs = Math.max(...symTrades.map(t => Math.abs(t.pnl)), 1);
    const layer = svgEl("g", {});
    // group daily fills that share a bar so we can fan them out; intraday fills stand alone
    const daily = new Map();
    if (!intra) symTrades.forEach(tr => { const p = placeDaily(tr); if (!daily.has(p.idx)) daily.set(p.idx, []); daily.get(p.idx).push(tr); });
    function drawMarker(tr, x, y, price, off) {
      const win = tr.pnl >= 0, r = 5 + Math.sqrt(Math.abs(tr.pnl) / maxAbs) * 6;
      const tri = svgEl("polygon", { points: triangle(x + (off || 0), y, r, win), fill: win ? "var(--win)" : "var(--loss)", stroke: "var(--surface-1)", "stroke-width": 1.6 });
      tri.style.cursor = "pointer";
      const nt = notes[tradeId(tr)];
      bindTT(tri, `<div class="h">${tr.symbol} · ${win ? "WIN" : "LOSS"}</div>
        <div class="r">${fmtDateY(tr.t)}${intra ? " · " + fmtTime(tr.t) : ""}</div>
        <div class="r">Realized <b class="${cls(tr.pnl)}">${moneyS(tr.pnl)}</b></div>
        <div class="r">Underlying <b>$${price.toFixed(2)}</b></div>
        ${nt && nt.tag ? `<div class="r">Tag <b>${nt.tag}</b></div>` : ""}${nt && nt.note ? `<div class="r">“${nt.note}”</div>` : ""}`);
      layer.append(tri);
    }
    if (intra) {
      symTrades.forEach(tr => { const p = placeIntraday(tr); drawMarker(tr, p.x, p.y, p.price, 0); });
    } else {
      const spread = Math.min(cw * 1.1 + 6, 22);
      daily.forEach(arr => {
        arr.sort((a, b) => new Date(a.t) - new Date(b.t));
        const p = placeDaily(arr[0]);
        arr.forEach((tr, k) => drawMarker(tr, p.x, p.y, p.price, arr.length > 1 ? (k - (arr.length - 1) / 2) * spread : 0));
      });
    }
    svg.append(layer); host.append(svg);
    $("#symMeta").textContent = `${symTrades.length} fills plotted · ${symTrades.filter(t => t.pnl > 0).length}W / ${symTrades.filter(t => t.pnl < 0).length}L · net ${moneyS(symTrades.reduce((s, t) => s + t.pnl, 0))}`;
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

  /* ---------------- Latest session recap ---------------- */
  function renderSession() {
    const card = $("#sessionCard");
    if (!ALL.length) { if (card) card.classList.add("hidden"); return; }
    const day = ALL[ALL.length - 1].date;
    const trades = ALL.filter(t => t.date === day);
    const net = trades.reduce((s, t) => s + t.pnl, 0);
    const wins = trades.filter(t => t.pnl > 0), losses = trades.filter(t => t.pnl < 0);
    const best = trades.reduce((m, t) => t.pnl > m.pnl ? t : m, trades[0]);
    const worst = trades.reduce((m, t) => t.pnl < m.pnl ? t : m, trades[0]);
    // context: average trading day
    const dm = new Map(); ALL.forEach(t => dm.set(t.date, (dm.get(t.date) || 0) + t.pnl));
    const days = [...dm.values()];
    const avgDay = days.reduce((a, b) => a + b, 0) / days.length;
    const rank = days.filter(v => v < net).length; // how many days were worse
    const pctl = Math.round(rank / days.length * 100);
    const dow = etDow(trades[0].t);
    const syms = [...new Set(trades.map(t => t.symbol))];

    $("#sessDate").textContent = `Latest session · ${fmtDateY(day)} (${dow})`;
    const netEl = $("#sessNet"); netEl.textContent = moneyS(net); netEl.className = "sess-net " + cls(net);
    $("#sessSub").textContent = `${trades.length} trade${trades.length !== 1 ? "s" : ""} · ${wins.length}W / ${losses.length}L · ${syms.join(", ")}`;

    const stats = $("#sessStats"); stats.innerHTML = "";
    const tiles = [
      { l: "Win rate", v: pct(trades.length ? wins.length / trades.length : 0), s: `${wins.length} of ${trades.length}` },
      { l: "Best trade", v: moneyS(best.pnl), vc: "pos", s: `${best.symbol} · ${fmtTime(best.t)}` },
      { l: "Worst trade", v: moneyS(worst.pnl), vc: worst.pnl < 0 ? "neg" : "", s: `${worst.symbol} · ${fmtTime(worst.t)}` },
      { l: "vs your avg day", v: moneyS(net - avgDay), vc: cls(net - avgDay), s: `avg ${moneyS(avgDay)}` },
    ];
    tiles.forEach(t => stats.append(el("div", { class: "sess-stat" }, [
      el("div", { class: "l" }, t.l),
      el("div", { class: "v " + (t.vc || "") }, t.v),
      el("div", { class: "s" }, t.s),
    ])));

    // honest, non-preachy note tied to the playbook
    const midday = trades.filter(t => etHour(t.t) === 12 || etHour(t.t) === 13);
    const big = trades.filter(t => t.qty > 3);
    let note;
    if (net > 0) {
      note = `A <b class="pos">${moneyS(net)}</b> day — better than ${pctl}% of your sessions. `;
      if (big.length && big.reduce((s, t) => s + t.pnl, 0) > 0)
        note += `Today's gains came largely from size (${big.length} trade${big.length > 1 ? "s" : ""} above 3 lots, net ${moneyS(big.reduce((s, t) => s + t.pnl, 0))}) — that works when you're right early, but the record still says oversizing is a coin-flip. `;
      if (midday.length) note += `Note: ${midday.length} trade${midday.length > 1 ? "s were" : " was"} in the 12–1pm ET window your data usually punishes. `;
      note += "Repeatable process beats a lucky size — bank the win and keep the rules.";
    } else if (net < 0) {
      note = `A <b class="neg">${moneyS(net)}</b> day. Log what setups you took while it's fresh — tag the trades below so the pattern shows up over time.`;
    } else {
      note = "A flat session — scratch days are fine. Keep the process tight.";
    }
    $("#sessNote").innerHTML = note;
  }

  /* ---------------- AI Coach ---------------- */
  function renderCoach() {
    const C = window.COACH;
    const card = $("#coachCard");
    if (!C) { if (card) card.classList.add("hidden"); return; }
    $("#coachGrade").textContent = C.grade || "—";
    $("#coachVerdict").innerHTML = C.verdict || "";
    const leaks = $("#coachLeaks"); leaks.innerHTML = "";
    (C.leaks || []).forEach((l, i) => leaks.append(el("div", { class: "coach-item" }, [
      el("div", { class: "n leak" }, String(i + 1)),
      el("div", { class: "b", html: `<b>${l.title}.</b> ${l.html}` }),
    ])));
    const plan = $("#coachPlan"); plan.innerHTML = "";
    (C.plan || []).forEach((p, i) => plan.append(el("div", { class: "coach-item" }, [
      el("div", { class: "n win" }, String(i + 1)),
      el("div", { class: "b", html: `<b>${p.title}.</b> ${p.html}` }),
    ])));
    $("#coachNote").textContent = (C.note || "") + (C.generatedAt ? `  ·  generated ${C.generatedAt}` : "");
  }

  /* ---------------- Playbook simulator ---------------- */
  const RULES = [
    { id: "midday", label: "Skip midday (12–1pm ET)", sub: "your worst hour by far", test: t => !(etHour(t.t) === 12 || etHour(t.t) === 13) },
    { id: "late", label: "Skip Thursday & Friday", sub: "net-negative weekdays", test: t => !(etDow(t.t) === "Thu" || etDow(t.t) === "Fri") },
    { id: "postloss", label: "No trade after a loss", sub: "one-trade cool-off", test: (t, i, arr) => !(i > 0 && arr[i - 1].pnl < 0) },
    { id: "cap3", label: "Cap size at 3 contracts", sub: "scale bigger trades down to 3", scale: t => t.qty > 3 ? 3 / t.qty : 1 },
  ];
  const simState = {};
  RULES.forEach(r => simState[r.id] = false);
  function simulate() {
    const kept = [];
    ALL.forEach((t, i) => {
      for (const r of RULES) { if (r.test && simState[r.id] && !r.test(t, i, ALL)) return; }
      let pnl = t.pnl;
      for (const r of RULES) { if (r.scale && simState[r.id]) pnl *= r.scale(t); }
      kept.push({ t: t.t, pnl });
    });
    const net = kept.reduce((s, x) => s + x.pnl, 0);
    const wins = kept.filter(x => x.pnl > 0).length;
    return { kept, net, n: kept.length, wr: kept.length ? wins / kept.length : 0 };
  }
  function renderSimToggles() {
    const host = $("#simToggles"); host.innerHTML = "";
    RULES.forEach(r => {
      host.append(el("div", { class: "sim-tog" + (simState[r.id] ? " on" : ""), onclick: () => { simState[r.id] = !simState[r.id]; renderSim(); } }, [
        el("div", { class: "box" }, simState[r.id] ? "✓" : ""),
        el("div", { class: "lab", html: `${r.label}<small>${r.sub}</small>` }),
      ]));
    });
    host.append(el("div", { class: "sim-tog", style: "justify-content:center;border-style:dashed", onclick: () => { RULES.forEach(r => simState[r.id] = false); renderSimToggles(); renderSim(); } }, [el("div", { class: "lab", style: "color:var(--muted)" }, "Reset")]));
  }
  function renderSim() {
    document.querySelectorAll("#simToggles .sim-tog").forEach((n, idx) => { const r = RULES[idx]; if (!r) return; n.classList.toggle("on", simState[r.id]); const b = n.querySelector(".box"); if (b) b.textContent = simState[r.id] ? "✓" : ""; });
    const base = ALL.reduce((s, t) => s + t.pnl, 0);
    const r = simulate();
    const dNet = r.net - base;
    const res = $("#simResult"); res.innerHTML = "";
    const tiles = [
      { l: "Net P&L", v: moneyS(r.net), vc: cls(r.net), d: `${moneyS(dNet)} vs actual`, dc: cls(dNet) },
      { l: "Win rate", v: pct(r.wr), d: `${r.kept.filter(x => x.pnl > 0).length}W / ${r.kept.filter(x => x.pnl < 0).length}L`, dc: "tag" },
      { l: "Trades kept", v: r.n.toLocaleString(), d: `of ${ALL.length}`, dc: "tag" },
    ];
    tiles.forEach(t => res.append(el("div", { class: "sim-stat" }, [
      el("div", { class: "l" }, t.l),
      el("div", { class: "v " + (t.vc || "") }, t.v),
      el("div", { class: "d " + (t.dc || "tag") }, t.d),
    ])));
    const host = $("#simEquity"); host.innerHTML = "";
    const W = 460, H = 150, P = { t: 10, r: 8, b: 8, l: 46 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    let cum = 0; const pts = r.kept.map((x, i) => { cum += x.pnl; return { i, cum }; });
    let bc = 0; const basePts = ALL.map((t, i) => { bc += t.pnl; return { i, cum: bc }; });
    const all = pts.concat(basePts);
    const hi = Math.max(0, ...all.map(p => p.cum)), lo = Math.min(0, ...all.map(p => p.cum));
    const pad = (hi - lo) * 0.08 || 1, yhi = hi + pad, ylo = lo - pad;
    const X = (i, n) => P.l + (n <= 1 ? 0 : i / (n - 1) * iw);
    const Y = v => P.t + (yhi - v) / (yhi - ylo) * ih;
    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" }); svg.style.height = "150px";
    if (ylo < 0 && yhi > 0) svg.append(svgEl("line", { class: "zero-line", x1: P.l, x2: W - P.r, y1: Y(0), y2: Y(0) }));
    [yhi, ylo].forEach(v => { const lab = svgEl("text", { class: "axis-txt", x: P.l - 6, y: Y(v) + 3, "text-anchor": "end" }); lab.textContent = money0(v); svg.append(lab); });
    if (basePts.length) svg.append(svgEl("path", { d: basePts.map((p, i) => (i ? "L" : "M") + X(p.i, basePts.length).toFixed(1) + " " + Y(p.cum).toFixed(1)).join(" "), fill: "none", stroke: "var(--muted)", "stroke-width": 1.2, "stroke-dasharray": "3 3", opacity: 0.8 }));
    if (pts.length) svg.append(svgEl("path", { d: pts.map((p, i) => (i ? "L" : "M") + X(p.i, pts.length).toFixed(1) + " " + Y(p.cum).toFixed(1)).join(" "), fill: "none", stroke: r.net >= 0 ? "var(--win)" : "var(--loss)", "stroke-width": 2 }));
    host.append(svg);
    const active = RULES.filter(x => simState[x.id]).length;
    $("#simNote").innerHTML = active
      ? `Dashed grey = your actual equity curve. Solid = your record with these rules applied to every trade. <b>${active} rule${active > 1 ? "s" : ""} on.</b>`
      : "Toggle rules on the right to see what your realized P&L would have been under them. Grey dashed line is your actual curve.";
  }

  /* ---------------- Discipline scorecard ---------------- */
  let discWin = 50;
  const DISC_RULES = [
    { id: "midday", label: "Avoided the 12–1pm ET chop", sub: "no midday entries", ok: t => !(etHour(t.t) === 12 || etHour(t.t) === 13) },
    { id: "size", label: "Kept size ≤ 3 contracts", sub: "no oversized bets", ok: t => t.qty <= 3 },
    { id: "postloss", label: "No revenge trade after a loss", sub: "one-trade cool-off", ok: (t, i, arr) => !(i > 0 && arr[i - 1].pnl < 0) },
    { id: "week", label: "Stayed out Thursday & Friday", sub: "trade Mon–Wed", ok: t => !(etDow(t.t) === "Thu" || etDow(t.t) === "Fri") },
  ];
  function renderDiscipline() {
    document.querySelectorAll("#discWindow .chip").forEach(c => c.classList.toggle("active", +c.dataset.w === discWin));
    const win = discWin > 0 ? ALL.slice(-discWin) : ALL;
    const offset = discWin > 0 ? Math.max(0, ALL.length - discWin) : 0;
    const per = DISC_RULES.map(r => {
      let ok = 0; const viol = [];
      win.forEach((t, k) => { const gi = offset + k; if (r.ok(t, gi, ALL)) ok++; else viol.push(t); });
      return { r, rate: win.length ? ok / win.length : 1, viol };
    });
    const overall = per.reduce((s, p) => s + p.rate, 0) / per.length;
    // ring
    const ring = $("#discRing"); ring.innerHTML = "";
    const R = 46, C = 2 * Math.PI * R, col = overall >= 0.8 ? "var(--win)" : overall >= 0.6 ? "var(--series-1)" : "var(--loss)";
    ring.append(svgEl("circle", { cx: 54, cy: 54, r: R, fill: "none", stroke: "var(--surface-2)", "stroke-width": 9 }));
    ring.append(svgEl("circle", { cx: 54, cy: 54, r: R, fill: "none", stroke: col, "stroke-width": 9, "stroke-linecap": "round", "stroke-dasharray": `${(overall * C).toFixed(1)} ${C.toFixed(1)}`, transform: "rotate(-90 54 54)" }));
    const t = svgEl("text", { x: 54, y: 61, "text-anchor": "middle", "font-size": "23", "font-weight": "700", fill: col }); t.textContent = Math.round(overall * 100) + "%"; ring.append(t);
    const grade = overall >= 0.85 ? "Locked in" : overall >= 0.7 ? "Mostly disciplined" : overall >= 0.55 ? "Slipping" : "Off the rails";
    $("#discGrade").textContent = grade;
    const worst = per.slice().sort((a, b) => a.rate - b.rate)[0];
    $("#discLede").textContent = win.length
      ? `Across your last ${win.length} trades, you followed the playbook ${Math.round(overall * 100)}% of the time. ${worst.rate < 0.9 ? `Weakest habit: ${worst.r.label.toLowerCase()} (${Math.round(worst.rate * 100)}%).` : "Every rule above 90% — keep it up."}`
      : "No trades in this window.";
    const host = $("#discRules"); host.innerHTML = "";
    per.forEach(p => {
      const rate = p.rate, c = rate >= 0.9 ? "var(--win)" : rate >= 0.7 ? "var(--series-1)" : "var(--loss)";
      const fill = el("div", { class: "fill" }); fill.style.width = (rate * 100) + "%"; fill.style.background = c;
      host.append(el("div", { class: "disc-rule" }, [
        el("div", { class: "rn", html: `${p.r.label}<small> · ${p.r.sub}</small>` }),
        el("div", { class: "rp", style: `color:${c}` }, Math.round(rate * 100) + "%"),
        el("div", { class: "track" }, fill),
      ]));
    });
    // cost of violations (unique trades that broke ≥1 rule)
    const violSet = new Map();
    per.forEach(p => p.viol.forEach(t => violSet.set(tradeId(t), t)));
    const violTrades = [...violSet.values()];
    const violPnl = violTrades.reduce((s, t) => s + t.pnl, 0);
    const winPnl = win.reduce((s, t) => s + t.pnl, 0);
    $("#discCost").innerHTML = violTrades.length
      ? `${violTrades.length} of ${win.length} trades broke at least one rule, for a combined <b class="${cls(violPnl)}">${moneyS(violPnl)}</b>. Following the playbook would have left this window at <b class="${cls(winPnl - violPnl)}">${moneyS(winPnl - violPnl)}</b> instead of <b class="${cls(winPnl)}">${moneyS(winPnl)}</b>.`
      : `Perfect run — every trade in this window followed the playbook.`;
  }

  /* ---------------- Monthly performance ---------------- */
  function renderMonthly() {
    const m = new Map();
    ALL.forEach(t => { const k = t.date.slice(0, 7); if (!m.has(k)) m.set(k, { pnl: 0, n: 0, w: 0 }); const o = m.get(k); o.pnl += t.pnl; o.n++; if (t.pnl > 0) o.w++; });
    const rows = [...m.entries()].sort((a, b) => a[0] < b[0] ? 1 : -1);
    const maxAbs = Math.max(...rows.map(r => Math.abs(r[1].pnl)), 1);
    const host = $("#monthly"); host.innerHTML = "";
    host.append(el("div", { class: "mon-row head" }, [
      el("div", {}, "Month"), el("div", {}, ""),
      el("div", { style: "text-align:right" }, "Net"),
      el("div", { style: "text-align:right" }, "Win %"),
    ]));
    rows.forEach(([k, o]) => {
      const [y, mo] = k.split("-");
      const name = new Date(Date.UTC(+y, +mo - 1, 1)).toLocaleDateString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" });
      const w = Math.abs(o.pnl) / maxAbs * 50; // half-width max
      const f = el("div", { class: "f" });
      f.style.background = o.pnl >= 0 ? "var(--win)" : "var(--loss)";
      if (o.pnl >= 0) { f.style.left = "50%"; f.style.width = w + "%"; } else { f.style.right = "50%"; f.style.width = w + "%"; }
      const bar = el("div", { class: "mon-bar" }, [el("div", { class: "z" }), f]);
      const wr = Math.round(o.w / o.n * 100);
      const wrFill = el("i"); wrFill.style.width = wr + "%"; wrFill.style.background = wr >= 50 ? "var(--win)" : "var(--loss)";
      const wrCell = el("div", { class: "mwr" }, [
        el("span", { class: "wrbar" }, wrFill),
        el("b", { class: cls(wr - 50) }, wr + "%"),
      ]);
      wrCell.title = `${o.w}W / ${o.n - o.w}L of ${o.n} trades`;
      host.append(el("div", { class: "mon-row" }, [
        el("div", { class: "mname" }, [name, el("small", {}, ` · ${o.n}`)]),
        bar,
        el("div", { class: "mamt " + cls(o.pnl) }, moneyS(o.pnl)),
        wrCell,
      ]));
    });
  }
  /* ---------------- $100K roadmap ---------------- */
  // US market holidays across the goal window (weekday closures only)
  const RM_HOL = new Set(["2026-09-07", "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18",
    "2027-02-15", "2027-03-26", "2027-05-31", "2027-07-05"]);
  const rmISO = d => d.toISOString().slice(0, 10);
  const rmParse = s => { const [y, m, dd] = s.split("-").map(Number); return new Date(Date.UTC(y, m - 1, dd)); };
  function rmTdays(a, b) {  // trading weekdays in (a, b]
    let n = 0; const d = new Date(a);
    while (true) { d.setUTCDate(d.getUTCDate() + 1); if (d > b) break; const wd = d.getUTCDay(); if (wd >= 1 && wd <= 5 && !RM_HOL.has(rmISO(d))) n++; }
    return n;
  }
  const rmMonthEnd = (y, m) => new Date(Date.UTC(y, m + 1, 0));  // last day of month m (0-based)
  function rmCheckpoints(anchor, deadline) {  // month-end dates from anchor's month through the deadline
    const out = []; let y = anchor.getUTCFullYear(), m = anchor.getUTCMonth();
    while (true) {
      const me = rmMonthEnd(y, m);
      if (me >= deadline) break;
      out.push(me);
      if (++m > 11) { m = 0; y++; }
    }
    out.push(deadline);
    return out;
  }
  function renderRoadmap() {
    const g = meta.goal; if (!g) { $("#roadmapCard").classList.add("hidden"); return; }
    const anchor = rmParse(g.anchorDate), deadline = rmParse(g.deadline), target = g.target;
    const nd = new Date(), today = new Date(Date.UTC(nd.getUTCFullYear(), nd.getUTCMonth(), nd.getUTCDate()));
    const cur = today < anchor ? anchor : (today > deadline ? deadline : today);
    const Ntot = rmTdays(anchor, deadline), daysLeft = rmTdays(cur, deadline), elapsed = Ntot - daysLeft;
    const bigMoney = v => "$" + Math.round(v).toLocaleString("en-US");
    const kMoney = v => v >= 1000 ? "$" + (v / 1000).toFixed(v < 10000 ? 1 : 0) + "k" : bigMoney(v);

    // ---- scheduled deposits ----
    const contribs = (g.contributions || []).map(c => ({ date: rmParse(c.d), amt: c.amt }));
    const byTd = {}; const cum = new Array(Ntot + 1).fill(0);
    contribs.forEach(c => { const td = c.date <= anchor ? 0 : Math.min(rmTdays(anchor, c.date), Ntot); byTd[td] = (byTd[td] || 0) + c.amt; });
    let running = 0; for (let t = 0; t <= Ntot; t++) { running += (byTd[t] || 0); cum[t] = running; }
    const totalContrib = contribs.reduce((s, c) => s + c.amt, 0);
    const toDate = contribs.filter(c => c.date <= cur).reduce((s, c) => s + c.amt, 0);
    const futureContrib = totalContrib - toDate;

    // ---- live account value = base + trading P&L + deposits banked so far ----
    const live = g.anchorEquity + (meta.totalPnl - g.anchorPnl) + toDate;
    const toGo = target - live, pctDone = Math.max(0, Math.min(1, live / target));

    // ---- solve the trading rate that (with deposits) reaches target ----
    const simEnd = r => { let v = g.anchorEquity + (byTd[0] || 0); for (let t = 1; t <= Ntot; t++) { v = v * (1 + r) + (byTd[t] || 0); } return v; };
    let lo = 0, hi = 0.25; for (let i = 0; i < 80; i++) { const m = (lo + hi) / 2; if (simEnd(m) < target) lo = m; else hi = m; }
    const r = (lo + hi) / 2;
    const path = new Array(Ntot + 1); { let v = g.anchorEquity + (byTd[0] || 0); path[0] = v; for (let t = 1; t <= Ntot; t++) { v = v * (1 + r) + (byTd[t] || 0); path[t] = v; } }
    const curveVal = td => { const i = Math.max(0, Math.min(Ntot - 1, Math.floor(td))), f = td - i; return path[i] + (path[i + 1] - path[i]) * f; };
    const baseVal = td => g.anchorEquity + cum[Math.max(0, Math.min(Ntot, Math.round(td)))];
    const rMonth = Math.pow(1 + r, 21) - 1, rWeek = Math.pow(1 + r, 5) - 1;
    const todayTarget = curveVal(elapsed);

    $("#rmDeadline").textContent = `by ${fmtDateY(g.deadline)} · ${daysLeft} trading days left`;
    $("#rmNow").textContent = bigMoney(live);
    $("#rmToGo").innerHTML = `<b>${bigMoney(toGo)}</b>`;
    $("#rmFill").style.width = (pctDone * 100).toFixed(1) + "%";
    $("#rmTick").style.left = (Math.min(1, todayTarget / target) * 100).toFixed(1) + "%";
    const ahead = live >= todayTarget - 1, gap = Math.abs(live - todayTarget);
    $("#rmStatus").innerHTML = ahead
      ? `<span class="ahead">▲ On pace</span> — at/above today's ${bigMoney(todayTarget)} mark`
      : `<span class="behind">● Behind pace</span> — ${bigMoney(gap)} under today's ${bigMoney(todayTarget)} mark`;

    const byDay = new Map(); ALL.forEach(t => byDay.set(t.date, (byDay.get(t.date) || 0) + t.pnl));
    const rdays = [...byDay.entries()].sort((a, b) => a[0] < b[0] ? 1 : -1).slice(0, 20);
    const avgDay = rdays.length ? rdays.reduce((s, d) => s + d[1], 0) / rdays.length : 0;
    const proj = live + avgDay * daysLeft + futureContrib;

    const mh = $("#rmMetrics"); mh.innerHTML = "";
    [["Trade / day", pct(r), "compounded"], ["Trade / month", pct(rMonth), ""],
     ["Deposits", "+" + kMoney(totalContrib), "incl. $9k May bonus"], ["Your pace", moneyS(avgDay) + "/day", `≈ ${pct(avgDay * 21 / live)} /mo`]]
      .forEach(([l, v, s]) => mh.append(el("div", { class: "rm-metric" }, [el("div", { class: "l" }, l), el("div", { class: "v" }, v), el("div", { class: "s" }, s)])));

    const nowKey = rmISO(cur).slice(0, 7);
    const cps = rmCheckpoints(anchor, deadline);
    const ch = $("#rmCheckpoints"); ch.innerHTML = "";
    cps.forEach(cd => {
      const isEnd = cd.getTime() === deadline.getTime();
      const td = Math.min(rmTdays(anchor, cd), Ntot), val = curveVal(td), done = live >= val - 1;
      const label = cd.toLocaleDateString("en-US", isEnd ? { month: "short", day: "numeric", timeZone: "UTC" } : { month: "short", timeZone: "UTC" });
      const isNow = rmISO(cd).slice(0, 7) === nowKey;
      ch.append(el("div", { class: "rm-cp " + (done ? "done" : isNow ? "now" : "") }, [
        el("div", { class: "m" }, label),
        el("div", { class: "t" }, kMoney(val)),
        el("div", { class: "d " + (done ? "pos" : "") }, done ? "✓ hit" : ""),
      ]));
    });

    drawRoadmapChart({ anchor, deadline, Ntot, elapsed, live, target, curveVal, baseVal, avgDay, daysLeft, futureContrib });
    const yourMonthly = avgDay * 21 / live;
    $("#rmNote").innerHTML = `Account value = your ${bigMoney(g.anchorEquity)} base + realized-P&L growth + deposits banked so far (auto-advances each refresh). Your <b>${kMoney(totalContrib)} of deposits</b> (incl. the $9k May bonus) do part of the climb — alone they'd reach <b>${bigMoney(g.anchorEquity + totalContrib)}</b> (dotted line), so trading only supplies the rest at <b>${pct(r)}/day (${pct(rMonth)}/mo)</b> — and you're <i>already</i> trading ≈ <b>${pct(yourMonthly)}/mo</b>. The catch is <b>compounding</b>: hold that % as the account grows (bigger size on a bigger base) and you clear the curve; keep sizing flat at ${moneyS(avgDay)}/day and you stall near <b>${bigMoney(proj)}</b>. Informational, not investment advice.`;
  }
  function drawRoadmapChart(c) {
    const { anchor, deadline, Ntot, elapsed, live, target, curveVal, baseVal, avgDay, daysLeft, futureContrib } = c;
    const host = $("#rmChart"); host.innerHTML = "";
    const W = 920, H = 230, P = { t: 14, r: 16, b: 26, l: 54 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b, ymax = target * 1.03;
    const X = td => P.l + td / Ntot * iw, Y = v => P.t + (1 - v / ymax) * ih;
    const svg = svgEl("svg", { class: "chart-svg", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none" }); svg.style.height = "230px";
    [0, 25000, 50000, 75000, 100000].forEach(v => { const y = Y(v); svg.append(svgEl("line", { class: "grid-line", x1: P.l, x2: W - P.r, y1: y, y2: y })); const lab = svgEl("text", { class: "axis-txt", x: P.l - 8, y: y + 3, "text-anchor": "end" }); lab.textContent = "$" + v / 1000 + "k"; svg.append(lab); });
    // required curve (trading + deposits)
    let dp = ""; for (let t = 0; t <= Ntot; t++) { dp += (t ? "L" : "M") + X(t).toFixed(1) + "," + Y(curveVal(t)).toFixed(1); }
    svg.append(svgEl("path", { d: dp + `L${X(Ntot).toFixed(1)},${Y(0).toFixed(1)}L${X(0).toFixed(1)},${Y(0).toFixed(1)}Z`, fill: "var(--accent)", "fill-opacity": 0.08, stroke: "none" }));
    svg.append(svgEl("path", { d: dp, fill: "none", stroke: "var(--accent)", "stroke-width": 2.5 }));
    // deposits-only baseline (dotted)
    let bp = ""; for (let t = 0; t <= Ntot; t++) { bp += (t ? "L" : "M") + X(t).toFixed(1) + "," + Y(baseVal(t)).toFixed(1); }
    svg.append(svgEl("path", { d: bp, fill: "none", stroke: "var(--text-secondary)", "stroke-width": 1.4, "stroke-dasharray": "2 3", opacity: 0.7 }));
    svg.append((() => { const t = svgEl("text", { class: "axis-txt", x: X(Ntot) - 3, y: Y(baseVal(Ntot)) - 5, "text-anchor": "end" }); t.textContent = "deposits only"; return t; })());
    // current-pace projection (trading pace + remaining deposits)
    const proj = Math.max(0, live + avgDay * daysLeft + futureContrib);
    svg.append(svgEl("line", { x1: X(elapsed), y1: Y(live), x2: X(Ntot), y2: Y(proj), stroke: "var(--muted)", "stroke-width": 1.5, "stroke-dasharray": "4 4" }));
    svg.append((() => { const t = svgEl("text", { class: "axis-txt", x: X(Ntot) - 3, y: Y(proj) - 5, "text-anchor": "end" }); t.textContent = "current pace"; return t; })());
    // milestone dots + you
    const cps = rmCheckpoints(anchor, deadline);
    cps.forEach(cd => { const td = Math.min(rmTdays(anchor, cd), Ntot); svg.append(svgEl("circle", { cx: X(td), cy: Y(curveVal(td)), r: 3.5, fill: "var(--accent)", stroke: "var(--surface-1)", "stroke-width": 1.5 })); });
    const hx = X(elapsed), hy = Y(live);
    svg.append(svgEl("circle", { cx: hx, cy: hy, r: 5, fill: "var(--win)", stroke: "var(--surface-1)", "stroke-width": 2 }));
    const hl = svgEl("text", { class: "axis-txt", x: hx + 8, y: hy - 6, style: "font-weight:700;fill:var(--win)" }); hl.textContent = "you"; svg.append(hl);
    cps.forEach(cd => { const td = Math.min(rmTdays(anchor, cd), Ntot); const t = svgEl("text", { class: "axis-txt", x: X(td), y: H - 8, "text-anchor": "middle" }); t.textContent = cd.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" }); svg.append(t); });
    host.append(svg);
  }
  function wireDiscipline() {
    document.querySelectorAll("#discWindow .chip").forEach(c => c.onclick = () => { discWin = +c.dataset.w; renderDiscipline(); });
  }

  /* ---------------- theme ---------------- */
  function wireTheme() {
    $("#themeBtn").onclick = () => {
      const cur = document.documentElement.getAttribute("data-theme");
      const dark = cur ? cur === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
      renderAll();
      renderSim();
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
  renderRoadmap();
  renderSession();
  renderCoach();
  renderFilterBar();
  renderSymbolControls();
  renderSimToggles();
  renderSim();
  wireDiscipline();
  renderDiscipline();
  renderMonthly();
  wireLog();
  wireTheme();
  renderAll();
})();
