/* Customer portal — read-mostly SPA: status, history, and quote approval. */
import { api, auth, openPdf, openAttachment } from "/assets/js/api.js";
import {
  el, els, esc, money, fmtDate, fmtDateTime, statusBadge, prioBadge,
  STATUS_LABEL, TYPE_LABEL, TYPE_ICON, toast, modal,
} from "/assets/js/ui.js";

if (!auth.token) location.href = "/login.html";
if (auth.user && auth.user.role !== "customer") location.href = "/app/";

const view = el("#view");

// Ordered lifecycle for the progress tracker shown to customers.
const FLOW = ["intake", "inspection", "quote_pending", "approved", "in_repair", "testing", "ready", "shipped"];

function boot() {
  const u = auth.user || {};
  el("#whoName").textContent = u.full_name || u.email;
  el("#logout").addEventListener("click", () => { auth.clear(); location.href = "/login.html"; });
  els(".nav-link[data-route]").forEach((a) =>
    a.addEventListener("click", () => (location.hash = `#/${a.dataset.route}`)));
  window.addEventListener("hashchange", router);
  if (!location.hash) location.hash = "#/orders"; else router();
}

function setActive(r) {
  els(".nav-link[data-route]").forEach((a) => a.classList.toggle("active", a.dataset.route === r));
}

async function router() {
  const parts = location.hash.replace(/^#\//, "").split("/");
  const route = parts[0] || "orders";
  setActive(route === "orders" && parts[1] ? "orders" : route);
  try {
    if (route === "orders" && parts[1]) return renderDetail(parts[1]);
    if (route === "equipment") return renderEquipment();
    if (route === "invoices") return renderInvoices();
    return renderOrders();
  } catch (ex) { view.innerHTML = `<div class="empty"><div class="big">⚠</div>${esc(ex.message)}</div>`; }
}
const loading = () => (view.innerHTML = `<div class="empty"><div class="big">◍</div>Loading…</div>`);

/* ---------- list ---------- */
async function renderOrders() {
  loading();
  const list = await api.portalWorkOrders();
  const open = list.filter((w) => !["closed", "cancelled", "shipped"].includes(w.status));
  const history = list.filter((w) => ["closed", "cancelled", "shipped"].includes(w.status));
  const card = (w) => `
    <div class="card card-pad" data-wo="${w.id}" style="cursor:pointer">
      <div class="spread"><span class="mono muted">${esc(w.number)}</span>${statusBadge(w.status)}</div>
      <h3 style="margin:8px 0 4px">${esc(w.title)}</h3>
      ${miniTracker(w.status)}
      <div class="spread" style="margin-top:12px;font-size:.85rem">
        <span class="muted">Promised ${fmtDate(w.promised_date)}</span>
        ${w.status === "quote_pending" ? '<span class="badge status quote_pending">Action needed</span>' : ""}
      </div></div>`;
  view.innerHTML = `
    <div class="page-title"><h1>My repairs</h1></div>
    ${open.length ? `<h3 class="muted" style="text-transform:uppercase;font-size:.8rem;letter-spacing:.05em">Active (${open.length})</h3>
      <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(320px,1fr));margin-bottom:24px">${open.map(card).join("")}</div>` :
      '<div class="empty"><div class="big">✅</div>No active repairs right now.</div>'}
    ${history.length ? `<h3 class="muted" style="text-transform:uppercase;font-size:.8rem;letter-spacing:.05em">History (${history.length})</h3>
      <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(320px,1fr))">${history.map(card).join("")}</div>` : ""}`;
  els("[data-wo]").forEach((c) => c.addEventListener("click", () => (location.hash = `#/orders/${c.dataset.wo}`)));
}

function miniTracker(status) {
  if (["cancelled", "quote_rejected", "on_hold", "closed"].includes(status)) return "";
  const idx = FLOW.indexOf(status);
  return `<div class="row" style="gap:4px;margin-top:6px">${FLOW.map((s, i) =>
    `<div title="${STATUS_LABEL[s]}" style="height:6px;flex:1;border-radius:3px;background:${i <= idx ? "var(--brand-500)" : "var(--line)"}"></div>`).join("")}</div>`;
}

/* ---------- detail ---------- */
async function renderDetail(id) {
  loading();
  const w = await api.portalWorkOrder(id);
  const eq = w.equipment;
  const pendingQuote = w.quotes.find((q) => q.status === "sent" || q.status === "draft");
  const timeline = w.events.map((e) => `
    <li class="${e.event_type}">
      <div class="tl-msg">${esc(e.message || (e.to_status ? `Status updated to ${STATUS_LABEL[e.to_status]}` : ""))}</div>
      <div class="tl-time">${fmtDateTime(e.created_at)}</div></li>`).join("");

  view.innerHTML = `
    <div class="row" style="margin-bottom:8px"><a href="#/orders">← My repairs</a></div>
    <div class="page-title">
      <div><h1 style="margin-bottom:4px">${esc(w.title)}</h1>
        <div class="row"><span class="mono">${esc(w.number)}</span>${statusBadge(w.status)}</div></div>
    </div>
    <div class="card card-pad" style="margin-bottom:18px">${bigTracker(w.status)}</div>
    ${pendingQuote ? quoteApprovalCard(pendingQuote, w) : ""}
    <div class="grid" style="grid-template-columns:1.4fr 1fr">
      <div class="card"><div class="card-head"><h3>Status history</h3></div>
        <div class="card-body"><ul class="timeline">${timeline}</ul></div></div>
      <div class="stack">
        <div class="card"><div class="card-head"><h3>Equipment</h3></div>
          <div class="card-body">${eq ? `
            <div class="row" style="margin-bottom:8px"><span style="font-size:1.6rem">${TYPE_ICON[eq.equipment_type]}</span>
              <div><strong>${esc(eq.manufacturer || "")} ${esc(eq.model || "")}</strong>
              <div class="muted">${TYPE_LABEL[eq.equipment_type]} · ${esc(eq.tag || "")}</div></div></div>
            <dl class="kv"><dt>Serial</dt><dd class="mono">${esc(eq.serial_number || "—")}</dd>
              <dt>Location</dt><dd>${esc(eq.location || "—")}</dd></dl>` : '<p class="muted">—</p>'}</div></div>
        ${w.quotes.length ? `<div class="card"><div class="card-head"><h3>Quotes</h3></div>
          <div class="card-body stack">${w.quotes.map((q) => `<div class="spread">
            <span class="mono">${esc(q.number)}</span><span>${money(q.total)}
            <span class="badge status ${q.status === "approved" ? "ready" : q.status === "rejected" ? "cancelled" : "quote_pending"}">${esc(q.status)}</span></span></div>`).join("")}</div></div>` : ""}
        ${(w.invoices || []).length ? `<div class="card"><div class="card-head"><h3>Invoices</h3></div>
          <div class="card-body stack">${w.invoices.map((i) => `<div class="spread">
            <span class="mono">${esc(i.number)}</span>
            <span>${money(i.total)} <span class="badge status ${i.status === "paid" ? "ready" : "quote_pending"}">${esc(i.status)}</span>
            <button class="btn btn-ghost btn-sm" data-inv="${i.id}">⬇ PDF</button></span></div>`).join("")}</div></div>` : ""}
        ${(w.attachments || []).length ? `<div class="card"><div class="card-head"><h3>Photos &amp; reports</h3></div>
          <div class="card-body stack">${w.attachments.map((a) => `<button class="btn btn-ghost btn-sm" data-att="${a.id}" style="justify-content:flex-start">
            ${({photo:"📷",nameplate:"🔖",report:"📊",document:"📄"})[a.kind] || "📎"} ${esc(a.filename)}</button>`).join("")}</div></div>` : ""}
      </div>
    </div>`;

  const ap = el("#approveBtn"), rj = el("#rejectBtn");
  if (ap) ap.addEventListener("click", () => decide(pendingQuote.id, true, id));
  if (rj) rj.addEventListener("click", () => decide(pendingQuote.id, false, id));
  els("[data-inv]").forEach((b) =>
    b.addEventListener("click", () => openPdf(b.dataset.inv).catch((e) => toast(e.message, "err"))));
  els("[data-att]").forEach((b) =>
    b.addEventListener("click", () => openAttachment(b.dataset.att).catch((e) => toast(e.message, "err"))));
}

function bigTracker(status) {
  if (["cancelled", "quote_rejected"].includes(status))
    return `<div class="row">${statusBadge(status)} <span class="muted">This repair is not progressing. Contact the service center.</span></div>`;
  const idx = FLOW.indexOf(status) < 0 ? (status === "closed" ? FLOW.length : 0) : FLOW.indexOf(status);
  const labels = { intake: "Received", inspection: "Inspection", quote_pending: "Quote", approved: "Approved", in_repair: "Repair", testing: "Testing", ready: "Ready", shipped: "Shipped" };
  return `<div class="row" style="gap:0;align-items:flex-start">${FLOW.map((s, i) => `
    <div style="flex:1;text-align:center;position:relative">
      <div style="height:4px;background:${i <= idx ? "var(--brand-500)" : "var(--line)"};position:absolute;top:11px;left:0;right:0"></div>
      <div style="position:relative;width:24px;height:24px;margin:0 auto;border-radius:50%;
        background:${i < idx ? "var(--brand-500)" : i === idx ? "#fff" : "var(--surface-3)"};
        border:3px solid ${i <= idx ? "var(--brand-500)" : "var(--line-strong)"};
        display:grid;place-items:center;color:#fff;font-size:.7rem">${i < idx ? "✓" : ""}</div>
      <div style="font-size:.72rem;margin-top:6px;color:${i <= idx ? "var(--ink-900)" : "var(--ink-400)"};font-weight:${i === idx ? 700 : 400}">${labels[s]}</div>
    </div>`).join("")}</div>`;
}

function quoteApprovalCard(q, w) {
  const lines = q.lines.map((l) => `<div class="spread" style="padding:4px 0;font-size:.9rem">
    <span>${esc(l.description)} <span class="muted">×${l.quantity}</span></span><span class="mono">${money(l.line_total)}</span></div>`).join("");
  return `<div class="card" style="border:2px solid var(--accent-500);margin-bottom:18px">
    <div class="card-head" style="background:#fffbeb"><h3>⚡ Action needed — approve your repair quote</h3>
      <span class="mono muted">${esc(q.number)}</span></div>
    <div class="card-body">${lines}<div class="divider"></div>
      <div class="spread"><span class="muted">Subtotal</span><span class="mono">${money(q.subtotal)}</span></div>
      <div class="spread"><span class="muted">Tax</span><span class="mono">${money(q.tax)}</span></div>
      <div class="spread" style="font-size:1.1rem"><strong>Total</strong><strong class="mono">${money(q.total)}</strong></div>
      ${q.valid_until ? `<p class="muted" style="font-size:.82rem;margin-top:8px">Valid until ${fmtDate(q.valid_until)}</p>` : ""}
      <div class="row" style="justify-content:flex-end;margin-top:14px">
        <button class="btn btn-danger" id="rejectBtn">Decline</button>
        <button class="btn btn-success" id="approveBtn">✓ Approve &amp; authorize repair</button></div></div></div>`;
}

async function decide(quoteId, approve, woId) {
  const m = modal(`<div class="card-head"><h3>${approve ? "Approve quote" : "Decline quote"}</h3></div>
    <div class="card-body stack">
      <p class="muted">${approve ? "This authorizes the service center to begin the repair." : "Let the service center know why you're declining (optional)."}</p>
      <label class="field"><span>Note (optional)</span><textarea id="dn"></textarea></label>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="dc">Cancel</button>
        <button class="btn ${approve ? "btn-success" : "btn-danger"}" id="dok">${approve ? "Approve" : "Decline"}</button></div></div>`);
  el("#dc", m.root).onclick = m.close;
  el("#dok", m.root).onclick = async () => {
    try {
      await api.decideQuote(quoteId, approve, el("#dn", m.root).value.trim() || null);
      m.close(); toast(approve ? "Quote approved — thank you!" : "Quote declined.", approve ? "ok" : "");
      renderDetail(woId);
    } catch (ex) { toast(ex.message, "err"); }
  };
}

/* ---------- equipment ---------- */
async function renderEquipment() {
  loading();
  const [eq, orders] = await Promise.all([api.portalEquipment(), api.portalWorkOrders()]);
  const counts = orders.reduce((a, w) => { if (w.equipment_id) a[w.equipment_id] = (a[w.equipment_id] || 0) + 1; return a; }, {});
  view.innerHTML = `
    <div class="page-title"><h1>My equipment</h1></div>
    <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(300px,1fr))">
      ${eq.map((e) => `<div class="card card-pad">
        <div class="row" style="margin-bottom:8px"><span style="font-size:1.9rem">${TYPE_ICON[e.equipment_type]}</span>
          <div><strong>${esc(e.tag || TYPE_LABEL[e.equipment_type])}</strong>
          <div class="muted" style="font-size:.84rem">${esc(e.manufacturer || "")} ${esc(e.model || "")}</div></div></div>
        <dl class="kv"><dt>Type</dt><dd>${TYPE_LABEL[e.equipment_type]}</dd>
          <dt>Serial</dt><dd class="mono" style="font-size:.82rem">${esc(e.serial_number || "—")}</dd>
          <dt>Location</dt><dd>${esc(e.location || "—")}</dd>
          <dt>Repairs</dt><dd>${counts[e.id] || 0} on record</dd></dl></div>`).join("") ||
      '<div class="empty"><div class="big">⚙️</div>No equipment on file.</div>'}
    </div>`;
}

/* ---------- invoices ---------- */
async function renderInvoices() {
  loading();
  const list = await api.portalInvoices();
  const due = list.filter((i) => i.status !== "paid").reduce((s, i) => s + i.total, 0);
  view.innerHTML = `
    <div class="page-title"><h1>My invoices</h1>
      ${due ? `<div class="stat warn" style="padding:10px 16px"><div class="stat-label">Balance due</div>
        <div class="stat-value" style="font-size:1.4rem">${money(due)}</div></div>` : ""}</div>
    <div class="card"><div class="table-wrap"><table class="data">
      <thead><tr><th>Invoice #</th><th>Status</th><th class="text-right">Total</th><th>Due</th><th></th></tr></thead>
      <tbody>${list.map((i) => `<tr data-nostyle>
        <td class="mono">${esc(i.number)}</td>
        <td><span class="badge status ${i.status === "paid" ? "ready" : "quote_pending"}">${esc(i.status)}</span></td>
        <td class="text-right mono">${money(i.total)}</td>
        <td class="muted nowrap">${fmtDate(i.due_date)}</td>
        <td class="text-right"><button class="btn btn-ghost btn-sm" data-inv="${i.id}">⬇ Download PDF</button></td></tr>`).join("") ||
      '<tr><td colspan="5" class="muted" style="text-align:center;padding:24px">No invoices yet.</td></tr>'}
      </tbody></table></div></div>`;
  els("tr[data-nostyle]").forEach((tr) => (tr.style.cursor = "default"));
  els("[data-inv]").forEach((b) =>
    b.addEventListener("click", () => openPdf(b.dataset.inv).catch((e) => toast(e.message, "err"))));
}

boot();
