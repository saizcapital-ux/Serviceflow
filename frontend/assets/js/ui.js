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

export function toast(msg, kind = "") {
  let wrap = el(".toast-wrap");
  if (!wrap) { wrap = document.createElement("div"); wrap.className = "toast-wrap"; document.body.appendChild(wrap); }
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.textContent = msg;
  wrap.appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

export function modal(html) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `<div class="modal card">${html}</div>`;
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });
  document.body.appendChild(backdrop);
  return { root: backdrop, close: () => backdrop.remove() };
}
