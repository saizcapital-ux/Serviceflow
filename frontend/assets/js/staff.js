/* Staff application — hash-routed SPA for service-center employees. */
import { api, auth, openPdf } from "/assets/js/api.js";
import {
  el, els, esc, money, fmtDate, fmtDateTime, statusBadge, prioBadge,
  STATUS_LABEL, TYPE_LABEL, TYPE_ICON, toast, modal,
} from "/assets/js/ui.js";

if (!auth.token) location.href = "/login.html";
if (auth.user && auth.user.role === "customer") location.href = "/portal/";

const view = el("#view");
let customersCache = null;

/* ---------- boot ---------- */
function boot() {
  const u = auth.user || {};
  el("#whoName").textContent = u.full_name || u.email || "—";
  el("#whoRole").textContent = (u.role || "").replace("_", " ");
  el("#logout").addEventListener("click", () => { auth.clear(); location.href = "/login.html"; });
  el("#newWoBtn").addEventListener("click", openNewWorkOrder);
  els(".nav-link[data-route]").forEach((a) =>
    a.addEventListener("click", () => (location.hash = `#/${a.dataset.route}`)));
  window.addEventListener("hashchange", router);
  if (!location.hash) location.hash = "#/dashboard";
  else router();
}

function setActive(route) {
  els(".nav-link[data-route]").forEach((a) =>
    a.classList.toggle("active", a.dataset.route === route));
}

/* ---------- router ---------- */
async function router() {
  const [, path, id] = location.hash.replace(/^#\//, "").split("/").reduce(
    (acc, p, i) => { acc[i + 1] = p; return acc; }, ["#"]);
  const route = path || "dashboard";
  setActive(route === "workorders" && id ? "workorders" : route);
  try {
    if (route === "dashboard") return renderDashboard();
    if (route === "workorders" && id) return renderWorkOrder(id);
    if (route === "workorders") return renderWorkOrders();
    if (route === "field") return renderWorkOrders({ service_type: "field_service" }, "Field Service");
    if (route === "customers") return renderCustomers();
    if (route === "equipment") return renderEquipment();
    if (route === "invoices") return renderInvoices();
    renderDashboard();
  } catch (ex) { view.innerHTML = `<div class="empty"><div class="big">⚠</div>${esc(ex.message)}</div>`; }
}

const loading = () => (view.innerHTML = `<div class="empty"><div class="big">◍</div>Loading…</div>`);

/* ---------- dashboard ---------- */
async function renderDashboard() {
  loading();
  const d = await api.dashboard();
  const stat = (label, val, cls = "", sub = "") =>
    `<div class="stat ${cls}"><div class="stat-label">${label}</div>
     <div class="stat-value">${val}</div><div class="stat-sub">${sub}</div></div>`;
  const rows = d.recent.map(woRow).join("");
  const funnel = d.by_status
    .sort((a, b) => b.count - a.count)
    .map((s) => `<div class="spread" style="padding:6px 0">${statusBadge(s.status)}
      <strong>${s.count}</strong></div>`).join("");

  view.innerHTML = `
    <div class="page-title"><h1>Dashboard</h1>
      <span class="muted">${fmtDate(new Date())}</span></div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-bottom:22px">
      ${stat("Open Work Orders", d.open_work_orders, "", "in the shop &amp; field")}
      ${stat("Rush Jobs", d.rush_jobs, "accent", "need attention")}
      ${stat("Awaiting Approval", d.awaiting_approval, "warn", "quotes with customer")}
      ${stat("Ready to Ship", d.ready_to_ship, "ok", "completed &amp; tested")}
      ${stat("Field Visits", d.field_visits_scheduled, "", "scheduled on-site")}
    </div>
    <div class="grid" style="grid-template-columns:2fr 1fr">
      <div class="card">
        <div class="card-head"><h3>Recent activity</h3>
          <a href="#/workorders">View all →</a></div>
        <div class="table-wrap"><table class="data">
          <thead><tr><th>WO #</th><th>Equipment</th><th>Title</th><th>Status</th><th>Priority</th></tr></thead>
          <tbody>${rows || emptyRow(5)}</tbody></table></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>Pipeline by status</h3></div>
        <div class="card-body">${funnel || '<p class="muted">No work orders yet.</p>'}</div>
      </div>
    </div>`;
  wireWoRows();
  hydrateEquipment();
}

/* ---------- work orders list ---------- */
function woRow(w) {
  return `<tr data-wo="${w.id}">
    <td class="mono nowrap">${esc(w.number)}</td>
    <td class="nowrap">${w.equipment_id ? "" : '<span class="muted">—</span>'}<span data-eq="${w.equipment_id || ""}">${w.equipment_id ? "…" : ""}</span></td>
    <td>${esc(w.title)}</td>
    <td>${statusBadge(w.status)}</td>
    <td>${prioBadge(w.priority)}</td></tr>`;
}
function emptyRow(cols) { return `<tr><td colspan="${cols}" class="muted" style="text-align:center;padding:24px">No records.</td></tr>`; }

async function renderWorkOrders(params = {}, title = "Work Orders") {
  loading();
  const list = await api.workOrders(params);
  const filterBar = `
    <div class="row wrap" style="margin-bottom:16px">
      ${["", "intake", "inspection", "quote_pending", "approved", "in_repair", "testing", "ready"]
        .map((s) => `<button class="btn btn-ghost btn-sm filter ${s === (params.status || "") ? "active" : ""}"
          data-status="${s}" style="${s === (params.status || "") ? "border-color:var(--brand-500);color:var(--brand-700)" : ""}">
          ${s ? STATUS_LABEL[s] : "All"}</button>`).join("")}
    </div>`;
  view.innerHTML = `
    <div class="page-title"><h1>${title}</h1>
      <button class="btn btn-primary btn-sm" id="pgNew">+ New Work Order</button></div>
    ${title === "Work Orders" ? filterBar : ""}
    <div class="card"><div class="table-wrap"><table class="data">
      <thead><tr><th>WO #</th><th>Equipment</th><th>Title</th><th>Type</th><th>Status</th><th>Priority</th><th>Promised</th></tr></thead>
      <tbody>${list.map((w) => `<tr data-wo="${w.id}">
        <td class="mono nowrap">${esc(w.number)}</td>
        <td class="nowrap" data-eq="${w.equipment_id || ""}">${w.equipment_id ? "…" : '<span class="muted">—</span>'}</td>
        <td>${esc(w.title)}</td>
        <td class="nowrap">${w.service_type === "field_service" ? "📍 Field" : "🏭 Shop"}</td>
        <td>${statusBadge(w.status)}</td>
        <td>${prioBadge(w.priority)}</td>
        <td class="nowrap muted">${fmtDate(w.promised_date)}</td></tr>`).join("") || emptyRow(7)}
      </tbody></table></div></div>`;
  el("#pgNew").addEventListener("click", openNewWorkOrder);
  els(".filter").forEach((b) => b.addEventListener("click", () => {
    const s = b.dataset.status; renderWorkOrders(s ? { status: s } : {}, "Work Orders");
  }));
  wireWoRows();
  hydrateEquipment();
}

function wireWoRows() {
  els("tr[data-wo]").forEach((tr) =>
    tr.addEventListener("click", () => (location.hash = `#/workorders/${tr.dataset.wo}`)));
}

async function hydrateEquipment() {
  const cells = els("[data-eq]").filter((c) => c.dataset.eq);
  if (!cells.length) return;
  const eq = await api.equipment();
  const byId = Object.fromEntries(eq.map((e) => [e.id, e]));
  cells.forEach((c) => {
    const e = byId[c.dataset.eq];
    c.innerHTML = e ? `${TYPE_ICON[e.equipment_type] || ""} <span class="mono">${esc(e.tag || e.serial_number || "")}</span>` : '<span class="muted">—</span>';
  });
}

/* ---------- work order detail ---------- */
async function renderWorkOrder(id) {
  loading();
  const w = await api.workOrder(id);
  const eq = w.equipment;
  const nameplate = eq && eq.nameplate_data
    ? Object.entries(eq.nameplate_data).map(([k, v]) =>
        `<span class="badge" style="background:var(--surface-3)">${esc(k)}: <b>${esc(v)}</b></span>`).join(" ")
    : "";
  const timeline = w.events.map((e) => `
    <li class="${e.event_type}">
      <div class="tl-msg">${esc(e.message || (e.to_status ? `Status → ${STATUS_LABEL[e.to_status]}` : ""))}</div>
      <div class="tl-time">${fmtDateTime(e.created_at)}${e.visible_to_customer ? "" : " · internal"}</div>
    </li>`).join("");
  const findings = w.findings.map((f) => `
    <div class="spread" style="padding:8px 0;border-bottom:1px solid var(--line)">
      <div><strong>${esc(f.title)}</strong><div class="muted" style="font-size:.85rem">${esc(f.detail || "")}</div></div>
      <span class="badge" style="background:${sevColor(f.severity)};color:#fff">${esc(f.severity)}</span>
    </div>`).join("") || '<p class="muted">No findings recorded.</p>';
  const quotes = w.quotes.map(quoteBlock).join("") || '<p class="muted">No quotes yet.</p>';
  const hasApprovedQuote = (w.quotes || []).some((q) => q.status === "approved");
  const invoices = (w.invoices || []).map(invoiceBlock).join("") || '<p class="muted">No invoices yet.</p>';

  view.innerHTML = `
    <div class="row" style="margin-bottom:8px"><a href="#/workorders">← Work Orders</a></div>
    <div class="page-title">
      <div><h1 style="margin-bottom:4px">${esc(w.title)}</h1>
        <div class="row"><span class="mono">${esc(w.number)}</span> ${statusBadge(w.status)} ${prioBadge(w.priority)}
        <span class="badge">${w.service_type === "field_service" ? "📍 Field Service" : "🏭 Shop Repair"}</span></div></div>
      <div class="row">
        <button class="btn btn-ghost btn-sm" id="addFinding">+ Finding</button>
        <button class="btn btn-ghost btn-sm" id="addQuote">+ Quote</button>
        <button class="btn btn-primary btn-sm" id="advance">Advance status ▾</button>
      </div>
    </div>
    <div class="grid" style="grid-template-columns:1.6fr 1fr">
      <div class="stack">
        <div class="card"><div class="card-head"><h3>Problem &amp; scope</h3></div>
          <div class="card-body"><p>${esc(w.problem_description || "—")}</p></div></div>
        <div class="card"><div class="card-head"><h3>Inspection findings</h3></div>
          <div class="card-body">${findings}</div></div>
        <div class="card"><div class="card-head"><h3>Quotes</h3></div>
          <div class="card-body stack">${quotes}</div></div>
        <div class="card"><div class="card-head"><h3>Invoices</h3>
          ${hasApprovedQuote ? '<button class="btn btn-accent btn-sm" id="newInvoice">+ Create invoice</button>' : ""}</div>
          <div class="card-body stack">${invoices}</div></div>
      </div>
      <div class="stack">
        <div class="card"><div class="card-head"><h3>Equipment</h3></div>
          <div class="card-body">${eq ? `
            <div class="row" style="margin-bottom:10px"><span style="font-size:1.6rem">${TYPE_ICON[eq.equipment_type]}</span>
              <div><strong>${esc(eq.manufacturer || "")} ${esc(eq.model || "")}</strong>
              <div class="muted">${TYPE_LABEL[eq.equipment_type]} · ${esc(eq.tag || "")}</div></div></div>
            <dl class="kv"><dt>Serial</dt><dd class="mono">${esc(eq.serial_number || "—")}</dd>
              <dt>Location</dt><dd>${esc(eq.location || "—")}</dd></dl>
            <div class="row wrap" style="margin-top:10px">${nameplate}</div>` : '<p class="muted">No equipment linked.</p>'}</div></div>
        <div class="card"><div class="card-head"><h3>Customer</h3></div>
          <div class="card-body"><strong>${esc(w.customer?.name || "")}</strong>
            <div class="muted">${esc(w.customer?.account_number || "")}</div>
            <div class="muted">${esc(w.customer?.phone || "")}</div></div></div>
        <div class="card"><div class="card-head"><h3>Timeline</h3></div>
          <div class="card-body"><ul class="timeline">${timeline}</ul></div></div>
      </div>
    </div>`;

  el("#advance").addEventListener("click", () => openStatusMenu(w));
  el("#addFinding").addEventListener("click", () => openFinding(w.id));
  el("#addQuote").addEventListener("click", () => openQuote(w.id));
  const inv = el("#newInvoice");
  if (inv) inv.addEventListener("click", () => openInvoice(w.id));
  els("[data-inv-pdf]").forEach((b) =>
    b.addEventListener("click", () => openPdf(b.dataset.invPdf).catch((e) => toast(e.message, "err"))));
  els("[data-inv-paid]").forEach((b) =>
    b.addEventListener("click", async () => {
      try { await api.markInvoicePaid(b.dataset.invPaid, true); toast("Invoice marked paid", "ok"); renderWorkOrder(w.id); }
      catch (e) { toast(e.message, "err"); }
    }));
}

function invoiceBlock(inv) {
  const st = inv.status === "paid" ? "ready" : inv.status === "void" ? "cancelled" : "quote_pending";
  return `<div class="card" style="box-shadow:none;border-color:var(--line)"><div class="card-body">
    <div class="spread"><strong class="mono">${esc(inv.number)}</strong>
      <span class="badge status ${st}">${esc(inv.status)}</span></div>
    <div class="spread" style="margin-top:8px"><span class="muted">Total</span><strong class="mono">${money(inv.total)}</strong></div>
    <div class="spread"><span class="muted">Due</span><span>${fmtDate(inv.due_date)}</span></div>
    <div class="row" style="justify-content:flex-end;margin-top:10px">
      <button class="btn btn-ghost btn-sm" data-inv-pdf="${inv.id}">⬇ PDF</button>
      ${inv.status !== "paid" ? `<button class="btn btn-success btn-sm" data-inv-paid="${inv.id}">Mark paid</button>` : ""}
    </div></div></div>`;
}

function openInvoice(woId) {
  const m = modal(`<div class="card-head"><h3>Create invoice</h3></div>
    <div class="card-body stack">
      <p class="muted">Generates an invoice from this work order's approved quote.</p>
      <label class="field" style="max-width:180px"><span>Payment terms (days)</span>
        <input type="number" id="due" value="30" min="0" /></label>
      <label class="field"><span>Notes (optional)</span><textarea id="inote" placeholder="e.g. Net 30. Thank you."></textarea></label>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="ic">Cancel</button>
        <button class="btn btn-primary" id="iok">Create invoice</button></div></div>`);
  el("#ic", m.root).onclick = m.close;
  el("#iok", m.root).onclick = async () => {
    try {
      const inv = await api.createInvoice(woId, { due_in_days: +el("#due", m.root).value || 30, notes: el("#inote", m.root).value.trim() || null });
      m.close(); toast(`Created ${inv.number}`, "ok"); renderWorkOrder(woId);
    } catch (ex) { toast(ex.message, "err"); }
  };
}

function quoteBlock(q) {
  const lines = q.lines.map((l) => `<div class="spread" style="font-size:.86rem;padding:3px 0">
    <span>${esc(l.description)} <span class="muted">×${l.quantity}</span></span><span class="mono">${money(l.line_total)}</span></div>`).join("");
  return `<div class="card" style="box-shadow:none;border-color:var(--line)"><div class="card-body">
    <div class="spread"><strong class="mono">${esc(q.number)}</strong>
      <span class="badge status ${q.status === "approved" ? "ready" : q.status === "rejected" ? "cancelled" : "quote_pending"}">${esc(q.status)}</span></div>
    <div class="divider"></div>${lines}<div class="divider"></div>
    <div class="spread"><span class="muted">Subtotal</span><span class="mono">${money(q.subtotal)}</span></div>
    <div class="spread"><span class="muted">Tax</span><span class="mono">${money(q.tax)}</span></div>
    <div class="spread"><strong>Total</strong><strong class="mono">${money(q.total)}</strong></div></div></div>`;
}

const sevColor = (s) => ({ info: "#64748b", minor: "#0891b2", major: "#d97706", critical: "#dc2626" }[s] || "#64748b");

/* ---------- actions ---------- */
const NEXT = {
  intake: ["inspection", "on_hold", "cancelled"],
  inspection: ["quote_pending", "on_hold", "cancelled"],
  quote_pending: ["approved", "quote_rejected", "on_hold"],
  approved: ["in_repair", "on_hold"],
  quote_rejected: ["ready", "cancelled"],
  in_repair: ["testing", "on_hold"],
  testing: ["ready", "in_repair"],
  ready: ["shipped", "closed"],
  shipped: ["closed"],
  on_hold: ["inspection", "in_repair", "cancelled"],
};

function openStatusMenu(w) {
  const opts = NEXT[w.status] || [];
  if (!opts.length) return toast("This work order is in a terminal state.");
  const m = modal(`<div class="card-head"><h3>Advance ${esc(w.number)}</h3></div>
    <div class="card-body stack">
      <p class="muted">Current: ${statusBadge(w.status)}. Choose the next status.</p>
      <label class="field"><span>New status</span>
        <select id="ns">${opts.map((o) => `<option value="${o}">${STATUS_LABEL[o]}</option>`).join("")}</select></label>
      <label class="field"><span>Note (shown on customer timeline)</span>
        <textarea id="nmsg" placeholder="Optional update for the customer…"></textarea></label>
      <label class="row" style="font-size:.88rem"><input type="checkbox" id="nvis" checked style="width:auto"> Visible to customer</label>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="nc">Cancel</button>
        <button class="btn btn-primary" id="nok">Update status</button></div></div>`);
  el("#nc", m.root).onclick = m.close;
  el("#nok", m.root).onclick = async () => {
    try {
      await api.changeStatus(w.id, {
        status: el("#ns", m.root).value,
        message: el("#nmsg", m.root).value.trim() || null,
        visible_to_customer: el("#nvis", m.root).checked,
      });
      m.close(); toast("Status updated", "ok"); renderWorkOrder(w.id);
    } catch (ex) { toast(ex.message, "err"); }
  };
}

function openFinding(woId) {
  const m = modal(`<div class="card-head"><h3>Add inspection finding</h3></div>
    <div class="card-body stack">
      <label class="field"><span>Title</span><input id="ft" placeholder="e.g. Grounded winding, phase B" /></label>
      <label class="field"><span>Detail</span><textarea id="fd"></textarea></label>
      <label class="field"><span>Severity</span><select id="fs">
        <option value="info">Info</option><option value="minor">Minor</option>
        <option value="major">Major</option><option value="critical">Critical</option></select></label>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="fc">Cancel</button>
        <button class="btn btn-primary" id="fok">Save finding</button></div></div>`);
  el("#fc", m.root).onclick = m.close;
  el("#fok", m.root).onclick = async () => {
    const title = el("#ft", m.root).value.trim();
    if (!title) return toast("Title is required", "err");
    try {
      await api.addFinding(woId, { title, detail: el("#fd", m.root).value.trim() || null, severity: el("#fs", m.root).value });
      m.close(); toast("Finding added", "ok"); renderWorkOrder(woId);
    } catch (ex) { toast(ex.message, "err"); }
  };
}

function openQuote(woId) {
  const lineHtml = () => `<div class="row line" style="margin-bottom:8px">
    <select style="max-width:110px"><option value="labor">Labor</option><option value="part">Part</option><option value="misc">Misc</option></select>
    <input placeholder="Description" class="d" />
    <input type="number" value="1" min="0" step="0.5" class="q" style="max-width:80px" />
    <input type="number" value="0" min="0" step="0.01" class="p" style="max-width:110px" placeholder="Unit $" />
    <button class="btn btn-ghost btn-sm rm">✕</button></div>`;
  const m = modal(`<div class="card-head"><h3>New quote</h3></div>
    <div class="card-body stack">
      <div id="lines">${lineHtml()}</div>
      <button class="btn btn-ghost btn-sm" id="addLine" style="align-self:flex-start">+ Add line</button>
      <label class="field" style="max-width:180px"><span>Tax rate (e.g. 0.0825)</span>
        <input type="number" id="tax" value="0.0825" step="0.0001" /></label>
      <div class="spread"><strong>Estimated total</strong><strong class="mono" id="qtotal">$0.00</strong></div>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="qc">Cancel</button>
        <button class="btn btn-primary" id="qok">Send quote</button></div></div>`);
  const recalc = () => {
    let sub = 0;
    els(".line", m.root).forEach((r) => { sub += (+el(".q", r).value || 0) * (+el(".p", r).value || 0); });
    const tax = sub * (+el("#tax", m.root).value || 0);
    el("#qtotal", m.root).textContent = money(sub + tax);
  };
  const wire = () => {
    els(".rm", m.root).forEach((b) => b.onclick = () => { if (els(".line", m.root).length > 1) { b.closest(".line").remove(); recalc(); } });
    els(".q,.p", m.root).forEach((i) => i.oninput = recalc);
  };
  wire();
  el("#addLine", m.root).onclick = () => { el("#lines", m.root).insertAdjacentHTML("beforeend", lineHtml()); wire(); };
  el("#qc", m.root).onclick = m.close;
  el("#qok", m.root).onclick = async () => {
    const lines = els(".line", m.root).map((r) => ({
      kind: r.querySelector("select").value, description: el(".d", r).value.trim(),
      quantity: +el(".q", r).value || 0, unit_price: +el(".p", r).value || 0,
    })).filter((l) => l.description);
    if (!lines.length) return toast("Add at least one line", "err");
    try {
      await api.createQuote(woId, { lines, tax_rate: +el("#tax", m.root).value || 0 });
      m.close(); toast("Quote sent to customer", "ok"); renderWorkOrder(woId);
    } catch (ex) { toast(ex.message, "err"); }
  };
}

/* ---------- new work order ---------- */
async function openNewWorkOrder() {
  const customers = customersCache || (customersCache = await api.customers());
  const m = modal(`<div class="card-head"><h3>New work order</h3></div>
    <div class="card-body stack">
      <label class="field"><span>Customer</span><select id="wc">
        <option value="">Select customer…</option>
        ${customers.map((c) => `<option value="${c.id}">${esc(c.name)} (${esc(c.account_number)})</option>`).join("")}</select></label>
      <label class="field"><span>Equipment</span><select id="we"><option value="">— none / new intake —</option></select></label>
      <label class="field"><span>Title</span><input id="wt" placeholder="e.g. 250HP motor failed to start" /></label>
      <label class="field"><span>Problem description</span><textarea id="wp"></textarea></label>
      <div class="row">
        <label class="field grow"><span>Service type</span><select id="ws">
          <option value="shop_repair">Shop repair</option><option value="field_service">Field service</option></select></label>
        <label class="field grow"><span>Priority</span><select id="wpr">
          <option value="normal">Normal</option><option value="low">Low</option>
          <option value="high">High</option><option value="rush">Rush</option></select></label>
      </div>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="wcx">Cancel</button>
        <button class="btn btn-primary" id="wok">Create work order</button></div></div>`);
  const eqSel = el("#we", m.root);
  el("#wc", m.root).addEventListener("change", async (e) => {
    eqSel.innerHTML = '<option value="">— none / new intake —</option>';
    if (!e.target.value) return;
    const eq = await api.equipment(e.target.value);
    eq.forEach((x) => eqSel.insertAdjacentHTML("beforeend",
      `<option value="${x.id}">${TYPE_ICON[x.equipment_type]} ${esc(x.tag || x.serial_number || TYPE_LABEL[x.equipment_type])} — ${esc(x.manufacturer || "")} ${esc(x.model || "")}</option>`));
  });
  el("#wcx", m.root).onclick = m.close;
  el("#wok", m.root).onclick = async () => {
    const customer_id = +el("#wc", m.root).value;
    const title = el("#wt", m.root).value.trim();
    if (!customer_id || !title) return toast("Customer and title are required", "err");
    try {
      const wo = await api.createWorkOrder({
        customer_id, equipment_id: +el("#we", m.root).value || null, title,
        problem_description: el("#wp", m.root).value.trim() || null,
        service_type: el("#ws", m.root).value, priority: el("#wpr", m.root).value,
      });
      m.close(); toast(`Created ${wo.number}`, "ok"); location.hash = `#/workorders/${wo.id}`;
    } catch (ex) { toast(ex.message, "err"); }
  };
}

/* ---------- customers ---------- */
async function renderCustomers() {
  loading();
  const list = await api.customers();
  view.innerHTML = `
    <div class="page-title"><h1>Customers</h1></div>
    <div class="card"><div class="table-wrap"><table class="data">
      <thead><tr><th>Account</th><th>Name</th><th>Contact</th><th>Phone</th></tr></thead>
      <tbody>${list.map((c) => `<tr>
        <td class="mono">${esc(c.account_number)}</td><td><strong>${esc(c.name)}</strong></td>
        <td>${esc(c.contacts?.[0]?.name || "—")}<div class="muted" style="font-size:.82rem">${esc(c.contacts?.[0]?.title || "")}</div></td>
        <td class="muted">${esc(c.phone || "—")}</td></tr>`).join("") || emptyRow(4)}
      </tbody></table></div></div>`;
  els("tr", view).forEach((tr) => tr.style.cursor = "default");
}

/* ---------- equipment ---------- */
async function renderEquipment() {
  loading();
  const list = await api.equipment();
  const cust = customersCache || (customersCache = await api.customers());
  const byId = Object.fromEntries(cust.map((c) => [c.id, c.name]));
  view.innerHTML = `
    <div class="page-title"><h1>Equipment</h1></div>
    <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr))">
      ${list.map((e) => `<div class="card card-pad">
        <div class="row" style="margin-bottom:8px"><span style="font-size:1.8rem">${TYPE_ICON[e.equipment_type]}</span>
          <div><strong>${esc(e.tag || TYPE_LABEL[e.equipment_type])}</strong>
          <div class="muted" style="font-size:.84rem">${TYPE_LABEL[e.equipment_type]}</div></div></div>
        <dl class="kv"><dt>Owner</dt><dd>${esc(byId[e.customer_id] || "—")}</dd>
          <dt>Make/Model</dt><dd>${esc(e.manufacturer || "—")} ${esc(e.model || "")}</dd>
          <dt>Serial</dt><dd class="mono" style="font-size:.82rem">${esc(e.serial_number || "—")}</dd>
          <dt>Location</dt><dd>${esc(e.location || "—")}</dd></dl></div>`).join("") ||
      '<div class="empty"><div class="big">⚙️</div>No equipment yet.</div>'}
    </div>`;
}

/* ---------- invoices (global list) ---------- */
async function renderInvoices() {
  loading();
  const [list, cust] = await Promise.all([api.invoices(), customersCache || api.customers()]);
  customersCache = cust;
  const byId = Object.fromEntries(cust.map((c) => [c.id, c.name]));
  const outstanding = list.filter((i) => i.status !== "paid" && i.status !== "void")
    .reduce((s, i) => s + i.total, 0);
  view.innerHTML = `
    <div class="page-title"><h1>Invoices</h1>
      <div class="stat" style="padding:10px 16px"><div class="stat-label">Outstanding</div>
        <div class="stat-value" style="font-size:1.4rem">${money(outstanding)}</div></div></div>
    <div class="card"><div class="table-wrap"><table class="data">
      <thead><tr><th>Invoice #</th><th>Customer</th><th>Work order</th><th>Status</th><th class="text-right">Total</th><th>Due</th><th></th></tr></thead>
      <tbody>${list.map((i) => `<tr data-nostyle>
        <td class="mono">${esc(i.number)}</td>
        <td>${esc(byId[i.customer_id] || "—")}</td>
        <td class="mono muted">WO #${i.work_order_id}</td>
        <td><span class="badge status ${i.status === "paid" ? "ready" : i.status === "void" ? "cancelled" : "quote_pending"}">${esc(i.status)}</span></td>
        <td class="text-right mono">${money(i.total)}</td>
        <td class="muted nowrap">${fmtDate(i.due_date)}</td>
        <td class="text-right"><button class="btn btn-ghost btn-sm" data-inv-pdf="${i.id}">⬇ PDF</button>
          ${i.status !== "paid" ? `<button class="btn btn-success btn-sm" data-inv-paid="${i.id}">Paid</button>` : ""}</td></tr>`).join("") ||
      '<tr><td colspan="7" class="muted" style="text-align:center;padding:24px">No invoices yet.</td></tr>'}
      </tbody></table></div></div>`;
  els("tr[data-nostyle]").forEach((tr) => (tr.style.cursor = "default"));
  els("[data-inv-pdf]").forEach((b) =>
    b.addEventListener("click", () => openPdf(b.dataset.invPdf).catch((e) => toast(e.message, "err"))));
  els("[data-inv-paid]").forEach((b) =>
    b.addEventListener("click", async () => {
      try { await api.markInvoicePaid(b.dataset.invPaid, true); toast("Marked paid", "ok"); renderInvoices(); }
      catch (e) { toast(e.message, "err"); }
    }));
}

boot();
