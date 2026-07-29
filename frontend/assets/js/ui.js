/* Shared UI helpers: formatting, badges, toasts, modals, small DOM utils. */

export const STATUS_LABEL = {
  intake: "Intake", inspection: "Inspection", quote_pending: "Awaiting Approval",
  approved: "Approved", quote_rejected: "Quote Rejected", in_repair: "In Repair",
  testing: "Testing", ready: "Ready", shipped: "Shipped", closed: "Closed",
  on_hold: "On Hold", cancelled: "Cancelled",
};

export const TYPE_LABEL = {
  motor: "Motor", valve: "Valve", actuator: "Actuator", pump: "Pump",
  blower: "Blower", gearbox: "Gearbox", other: "Equipment",
};

export const TYPE_ICON = {
  motor: "⚙️", valve: "🔧", actuator: "🎛️", pump: "🌀", blower: "💨", gearbox: "⛓️", other: "📦",
};

export const el = (sel, root = document) => root.querySelector(sel);
export const els = (sel, root = document) => [...root.querySelectorAll(sel)];

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const money = (n) =>
  (n ?? 0).toLocaleString("en-US", { style: "currency", currency: "USD" });

export function fmtDate(d) {
  if (!d) return "—";
  const dt = new Date(d);
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
export function fmtDateTime(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export const statusBadge = (s) =>
  `<span class="badge status ${s}">${esc(STATUS_LABEL[s] || s)}</span>`;
export const prioBadge = (p) => `<span class="prio ${p}">${esc(p)}</span>`;

const OPEN_SLA = ["intake", "inspection", "quote_pending", "approved", "in_repair", "testing", "ready", "on_hold"];
const DONE_SLA = ["shipped", "closed"];

/** Client-side SLA badge from a work order's status + promised date. */
export function slaBadge(w) {
  if (!w.promised_date) return "";
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const promised = new Date(w.promised_date + "T00:00");
  const days = Math.round((promised - today) / 86400000);
  if (OPEN_SLA.includes(w.status)) {
    if (days < 0) return `<span class="badge status cancelled">⚠ ${Math.abs(days)}d overdue</span>`;
    if (days <= 3) return `<span class="badge status on_hold">Due in ${days}d</span>`;
    return `<span class="badge status ready">On track</span>`;
  }
  if (DONE_SLA.includes(w.status)) {
    // updated_at ~ completion; on time if completed on/before promised.
    const done = w.updated_at ? new Date(w.updated_at) : today;
    done.setHours(0, 0, 0, 0);
    return done <= promised
      ? `<span class="badge status shipped">On time</span>`
      : `<span class="badge status cancelled">Late</span>`;
  }
  return "";
}

export function toast(msg, kind = "") {
  let wrap = el(".toast-wrap");
  if (!wrap) { wrap = document.createElement("div"); wrap.className = "toast-wrap"; document.body.appendChild(wrap); }
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.textContent = msg;
  wrap.appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

/** Read the current theme, defaulting to the OS preference. */
export function currentTheme() {
  return localStorage.getItem("sf_theme")
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

/** Flip light/dark, persist, and update the button label if given. */
export function toggleTheme(btn) {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("sf_theme", next);
  if (btn) btn.textContent = next === "dark" ? "☀️ Light mode" : "🌙 Dark mode";
}

/** Wire a theme-toggle button and set its initial label. */
export function initThemeToggle(btn) {
  if (!btn) return;
  btn.textContent = currentTheme() === "dark" ? "☀️ Light mode" : "🌙 Dark mode";
  btn.addEventListener("click", () => toggleTheme(btn));
}

export function modal(html) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `<div class="modal card">${html}</div>`;
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });
  document.body.appendChild(backdrop);
  return { root: backdrop, close: () => backdrop.remove() };
}
