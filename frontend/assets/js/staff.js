/* Staff application — hash-routed SPA for service-center employees. */
import { api, auth, openPdf, openAttachment, uploadAttachment, fetchAuthedText } from "/assets/js/api.js";
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
  // Audit log is owner/manager only; Developers is owner only.
  if (!["owner", "manager"].includes(u.role)) el("#navAudit")?.classList.add("hide");
  if (u.role !== "owner") el("#navDev")?.classList.add("hide");
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
  setActive(route);
  try {
    if (route === "dashboard") return renderDashboard();
    if (route === "workorders" && id) return renderWorkOrder(id);
    if (route === "workorders") return renderWorkOrders();
    if (route === "field") return renderDispatch();
    if (route === "customers") return renderCustomers();
    if (route === "equipment" && id) return renderEquipmentDetail(id);
    if (route === "equipment") return renderEquipment();
    if (route === "inventory") return renderInventory();
    if (route === "invoices") return renderInvoices();
    if (route === "notifications") return renderNotifications();
    if (route === "audit") return renderAudit();
    if (route === "developer") return renderDeveloper();
    if (route === "billing") return renderBilling();
    if (route === "analytics") return renderAnalytics();
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
  const limit = w.customer?.approval_limit;
  const quotes = w.quotes.map((q) => quoteBlock(q, limit)).join("") || '<p class="muted">No quotes yet.</p>';
  const hasApprovedQuote = (w.quotes || []).some((q) => q.status === "approved");
  const invoices = (w.invoices || []).map(invoiceBlock).join("") || '<p class="muted">No invoices yet.</p>';
  const attachments = attachmentGrid(w.attachments || []);
  const timeEntries = (w.time_entries || []).map((t) => `
    <div class="spread" style="padding:6px 0;border-bottom:1px solid var(--line)">
      <div><strong>${t.hours}h</strong> <span class="muted">${esc(t.note || "")}</span></div>
      <span class="muted nowrap">${fmtDate(t.worked_on)}</span>
    </div>`).join("") || '<p class="muted">No labor logged yet.</p>';

  view.innerHTML = `
    <div class="row" style="margin-bottom:8px"><a href="#/workorders">← Work Orders</a></div>
    <div class="page-title">
      <div><h1 style="margin-bottom:4px">${esc(w.title)}</h1>
        <div class="row"><span class="mono">${esc(w.number)}</span> ${statusBadge(w.status)} ${prioBadge(w.priority)}
        <span class="badge">${w.service_type === "field_service" ? "📍 Field Service" : "🏭 Shop Repair"}</span></div></div>
      <div class="row">
        ${w.service_type === "field_service" ? '<button class="btn btn-ghost btn-sm" id="schedBtn">📅 Schedule</button>' : ""}
        <button class="btn btn-ghost btn-sm" id="addFinding">+ Finding</button>
        <button class="btn btn-ghost btn-sm" id="addQuote">+ Quote</button>
        <button class="btn btn-primary btn-sm" id="advance">Advance status ▾</button>
      </div>
    </div>
    <div class="grid" style="grid-template-columns:1.6fr 1fr">
      <div class="stack">
        <div class="card"><div class="card-head"><h3>Problem &amp; scope</h3></div>
          <div class="card-body"><p>${esc(w.problem_description || "—")}</p></div></div>
        <div class="card"><div class="card-head"><h3>Checklist / traveler</h3>
          <span id="clProgress" class="badge"></span></div>
          <div class="card-body" id="checklist"><p class="muted">Loading…</p></div></div>
        <div class="card"><div class="card-head"><h3>Inspection findings</h3></div>
          <div class="card-body">${findings}</div></div>
        <div class="card"><div class="card-head"><h3>Attachments &amp; photos</h3>
          <button class="btn btn-ghost btn-sm" id="uploadBtn">+ Upload</button></div>
          <div class="card-body">${attachments}</div></div>
        <div class="card"><div class="card-head"><h3>Quotes</h3></div>
          <div class="card-body stack">${quotes}</div></div>
        <div class="card"><div class="card-head"><h3>Labor &amp; costing</h3>
          <button class="btn btn-ghost btn-sm" id="logTime">+ Log time</button></div>
          <div class="card-body">
            <div id="costing" class="grid" style="grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px">
              <div class="muted" style="grid-column:1/-1">Loading costing…</div></div>
            ${timeEntries}
          </div></div>
        <div class="card"><div class="card-head"><h3>Parts used</h3>
          <button class="btn btn-ghost btn-sm" id="usePart">+ Use part</button></div>
          <div class="card-body" id="partsUsed"><p class="muted">Loading…</p></div></div>
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
            <div class="muted">${esc(w.customer?.phone || "")}</div>
            <div class="divider"></div>
            <dl class="kv"><dt>PO number</dt><dd>${w.po_number ? `<span class="mono">${esc(w.po_number)}</span>` : '<span class="muted">—</span>'}
              <button class="btn btn-ghost btn-sm" id="editPo" style="margin-left:6px;padding:.15rem .5rem">${w.po_number ? "Edit" : "Add"}</button></dd>
              <dt>Approval limit</dt><dd>${w.customer?.approval_limit != null ? money(w.customer.approval_limit) : '<span class="muted">none</span>'}</dd></dl>
          </div></div>
        <div class="card"><div class="card-head"><h3>Timeline</h3></div>
          <div class="card-body"><ul class="timeline">${timeline}</ul></div></div>
      </div>
    </div>`;

  el("#advance").addEventListener("click", () => openStatusMenu(w));
  el("#addFinding").addEventListener("click", () => openFinding(w.id));
  el("#addQuote").addEventListener("click", () => openQuote(w.id));
  el("#logTime").addEventListener("click", () => openLogTime(w.id));
  el("#uploadBtn").addEventListener("click", () => openUpload(w.id));
  el("#usePart").addEventListener("click", () => openUsePart(w.id));
  renderChecklist(w);
  el("#editPo").addEventListener("click", async () => {
    const po = prompt("Customer PO number for this job:", w.po_number || "");
    if (po === null) return;
    try { await api.updateWorkOrder(w.id, { po_number: po.trim() || null }); toast("PO updated", "ok"); renderWorkOrder(w.id); }
    catch (e) { toast(e.message, "err"); }
  });
  loadPartsUsed(w);
  const sb = el("#schedBtn");
  if (sb) sb.addEventListener("click", async () =>
    openSchedule(w.id, techCache || (techCache = await api.users("technician")), () => renderWorkOrder(w.id)));
  wireAttachments();
  loadCosting(w.id);
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

const ATT_ICON = { photo: "📷", nameplate: "🔖", report: "📊", document: "📄" };

function attachmentGrid(atts) {
  if (!atts.length) return '<p class="muted">No attachments yet. Add nameplate photos, inspection pictures, or test reports.</p>';
  return `<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px">
    ${atts.map((a) => `<button class="card" data-att="${a.id}" style="cursor:pointer;text-align:left;border:1px solid var(--line);padding:12px;background:var(--surface-2)">
      <div style="font-size:1.6rem">${ATT_ICON[a.kind] || "📎"}</div>
      <div style="font-size:.82rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(a.filename)}</div>
      <span class="badge" style="margin-top:4px">${esc(a.kind)}</span></button>`).join("")}</div>`;
}

function wireAttachments() {
  els("[data-att]").forEach((b) =>
    b.addEventListener("click", () => openAttachment(b.dataset.att).catch((e) => toast(e.message, "err"))));
}

function openUpload(woId) {
  const m = modal(`<div class="card-head"><h3>Upload attachment</h3></div>
    <div class="card-body stack">
      <label class="field"><span>File (max 15 MB)</span><input type="file" id="uf" /></label>
      <label class="field"><span>Type</span><select id="uk">
        <option value="photo">Photo</option><option value="nameplate">Nameplate</option>
        <option value="report">Test report</option><option value="document">Document</option></select></label>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="uc">Cancel</button>
        <button class="btn btn-primary" id="uok">Upload</button></div></div>`);
  el("#uc", m.root).onclick = m.close;
  el("#uok", m.root).onclick = async () => {
    const f = el("#uf", m.root).files[0];
    if (!f) return toast("Choose a file", "err");
    try {
      await uploadAttachment(woId, f, el("#uk", m.root).value);
      m.close(); toast("Uploaded", "ok"); renderWorkOrder(woId);
    } catch (ex) { toast(ex.message, "err"); }
  };
}

function renderChecklist(w) {
  const box = el("#checklist"), prog = el("#clProgress");
  if (!box) return;
  const items = w.checklist_items || [];
  const updateProgress = () => {
    const done = els("input[data-cl]", box).filter((i) => i.checked).length;
    const total = items.length;
    prog.textContent = total ? `${done}/${total}` : "";
    const bar = el("#clBar", box);
    if (bar) bar.style.width = total ? `${(done / total) * 100}%` : "0%";
  };
  if (!items.length) {
    box.innerHTML = `<p class="muted" style="margin-bottom:10px">No checklist yet. Apply a traveler template.</p>
      <button class="btn btn-ghost btn-sm" id="applyTmpl">+ Apply template</button>`;
    prog.textContent = "";
    el("#applyTmpl", box).addEventListener("click", () => openApplyTemplate(w));
    return;
  }
  box.innerHTML = `
    <div style="background:var(--surface-3);border-radius:5px;height:8px;margin-bottom:14px">
      <div id="clBar" style="height:100%;border-radius:5px;background:var(--ok);transition:width .2s"></div></div>
    <div class="stack" style="gap:8px">${items.map((it) => `
      <label class="row" style="gap:10px;align-items:flex-start;cursor:pointer">
        <input type="checkbox" data-cl="${it.id}" ${it.is_done ? "checked" : ""} style="width:auto;margin-top:3px">
        <span data-lbl="${it.id}" style="${it.is_done ? "text-decoration:line-through;color:var(--ink-400)" : ""}">${esc(it.label)}</span>
      </label>`).join("")}</div>`;
  els("input[data-cl]", box).forEach((cb) => cb.addEventListener("change", async () => {
    const lbl = el(`[data-lbl="${cb.dataset.cl}"]`, box);
    lbl.style.cssText = cb.checked ? "text-decoration:line-through;color:var(--ink-400)" : "";
    updateProgress();
    try { await api.updateChecklistItem(cb.dataset.cl, { is_done: cb.checked }); }
    catch (e) { toast(e.message, "err"); cb.checked = !cb.checked; lbl.style.cssText = cb.checked ? "text-decoration:line-through;color:var(--ink-400)" : ""; updateProgress(); }
  }));
  updateProgress();
}

async function openApplyTemplate(w) {
  const templates = await api.checklistTemplates();
  const eqType = w.equipment?.equipment_type;
  const relevant = templates.filter((t) => !t.equipment_type || t.equipment_type === eqType);
  const list = relevant.length ? relevant : templates;
  if (!list.length) return toast("No templates yet. Create one in settings.", "err");
  const m = modal(`<div class="card-head"><h3>Apply traveler template</h3></div>
    <div class="card-body stack">
      <label class="field"><span>Template</span><select id="tsel">
        ${list.map((t) => `<option value="${t.id}">${esc(t.name)} (${t.items.length} steps)</option>`).join("")}</select></label>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="tcx">Cancel</button>
        <button class="btn btn-primary" id="tok">Apply</button></div></div>`);
  el("#tcx", m.root).onclick = m.close;
  el("#tok", m.root).onclick = async () => {
    try { await api.applyChecklist(w.id, +el("#tsel", m.root).value); m.close(); toast("Checklist applied", "ok"); renderWorkOrder(w.id); }
    catch (e) { toast(e.message, "err"); }
  };
}

async function loadPartsUsed(w) {
  const box = el("#partsUsed");
  if (!box) return;
  const used = w.parts_used || [];
  if (!used.length) { box.innerHTML = '<p class="muted">No parts consumed yet.</p>'; return; }
  const parts = partsCache || (partsCache = await api.parts());
  const byId = Object.fromEntries(parts.map((p) => [p.id, p]));
  box.innerHTML = used.map((u) => {
    const p = byId[u.part_id];
    return `<div class="spread" style="padding:6px 0;border-bottom:1px solid var(--line)">
      <div><strong>${u.quantity} ×</strong> ${esc(p ? p.name : "Part #" + u.part_id)}
        ${p ? `<span class="muted mono" style="font-size:.8rem">${esc(p.sku)}</span>` : ""}</div>
      <span class="mono">${money(u.quantity * u.unit_price)}</span></div>`;
  }).join("");
}

async function openUsePart(woId) {
  const parts = (partsCache || (partsCache = await api.parts())).filter((p) => p.quantity_on_hand > 0);
  if (!parts.length) return toast("No parts in stock. Add inventory first.", "err");
  const m = modal(`<div class="card-head"><h3>Use a part on this job</h3></div>
    <div class="card-body stack">
      <label class="field"><span>Part</span><select id="up">
        ${parts.map((p) => `<option value="${p.id}">${esc(p.sku)} — ${esc(p.name)} (${p.quantity_on_hand} in stock)</option>`).join("")}</select></label>
      <label class="field" style="max-width:140px"><span>Quantity</span><input type="number" id="uq" value="1" min="1" /></label>
      <p class="muted" style="font-size:.82rem">This decrements inventory stock.</p>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="ucx">Cancel</button>
        <button class="btn btn-primary" id="uok">Use part</button></div></div>`);
  el("#ucx", m.root).onclick = m.close;
  el("#uok", m.root).onclick = async () => {
    try {
      await api.consumePart(woId, { part_id: +el("#up", m.root).value, quantity: +el("#uq", m.root).value || 1 });
      partsCache = null; // stock changed
      m.close(); toast("Part recorded", "ok"); renderWorkOrder(woId);
    } catch (ex) { toast(ex.message, "err"); }
  };
}

async function loadCosting(woId) {
  const box = el("#costing");
  if (!box) return;
  try {
    const c = await api.costing(woId);
    const marginCls = c.margin >= 0 ? "ok" : "warn";
    const tile = (label, val, cls = "") =>
      `<div class="stat ${cls}" style="padding:12px 14px"><div class="stat-label">${label}</div>
       <div class="stat-value" style="font-size:1.35rem">${val}</div></div>`;
    box.innerHTML =
      tile("Logged hours", `${c.logged_hours}h`) +
      tile("Labor cost", money(c.labor_cost), "warn") +
      tile("Quoted", money(c.estimate)) +
      tile("Margin", `${money(c.margin)}${c.margin_pct != null ? ` · ${c.margin_pct}%` : ""}`, marginCls);
  } catch {
    box.innerHTML = '<div class="muted" style="grid-column:1/-1">Costing unavailable.</div>';
  }
}

function openLogTime(woId) {
  const today = new Date().toISOString().slice(0, 10);
  const m = modal(`<div class="card-head"><h3>Log labor time</h3></div>
    <div class="card-body stack">
      <div class="row">
        <label class="field grow"><span>Hours</span><input type="number" id="lh" min="0.25" step="0.25" value="1" /></label>
        <label class="field grow"><span>Date</span><input type="date" id="ld" value="${today}" /></label>
      </div>
      <label class="field"><span>Note</span><textarea id="ln" placeholder="What was done…"></textarea></label>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="lc">Cancel</button>
        <button class="btn btn-primary" id="lok">Log time</button></div></div>`);
  el("#lc", m.root).onclick = m.close;
  el("#lok", m.root).onclick = async () => {
    const hours = +el("#lh", m.root).value;
    if (!hours || hours <= 0) return toast("Enter hours", "err");
    try {
      await api.logTime(woId, { hours, note: el("#ln", m.root).value.trim() || null, worked_on: el("#ld", m.root).value || null });
      m.close(); toast("Time logged", "ok"); renderWorkOrder(woId);
    } catch (ex) { toast(ex.message, "err"); }
  };
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

function quoteBlock(q, approvalLimit) {
  const lines = q.lines.map((l) => `<div class="spread" style="font-size:.86rem;padding:3px 0">
    <span>${esc(l.description)} <span class="muted">×${l.quantity}</span></span><span class="mono">${money(l.line_total)}</span></div>`).join("");
  const overLimit = approvalLimit != null && q.total > approvalLimit && q.status !== "rejected";
  return `<div class="card" style="box-shadow:none;border-color:${overLimit ? "var(--accent-500)" : "var(--line)"}"><div class="card-body">
    <div class="spread"><strong class="mono">${esc(q.number)}</strong>
      <span class="badge status ${q.status === "approved" ? "ready" : q.status === "rejected" ? "cancelled" : "quote_pending"}">${esc(q.status)}</span></div>
    <div class="divider"></div>${lines}<div class="divider"></div>
    <div class="spread"><span class="muted">Subtotal</span><span class="mono">${money(q.subtotal)}</span></div>
    <div class="spread"><span class="muted">Tax</span><span class="mono">${money(q.tax)}</span></div>
    <div class="spread"><strong>Total</strong><strong class="mono">${money(q.total)}</strong></div>
    ${overLimit ? `<div class="badge status on_hold" style="margin-top:8px">⚠ Exceeds customer approval limit (${money(approvalLimit)}) — PO required</div>` : ""}</div></div>`;
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
      ${list.map((e) => `<div class="card card-pad" data-eqid="${e.id}" style="cursor:pointer">
        <div class="row" style="margin-bottom:8px"><span style="font-size:1.8rem">${TYPE_ICON[e.equipment_type]}</span>
          <div><strong>${esc(e.tag || TYPE_LABEL[e.equipment_type])}</strong>
          <div class="muted" style="font-size:.84rem">${TYPE_LABEL[e.equipment_type]}</div></div></div>
        <dl class="kv"><dt>Owner</dt><dd>${esc(byId[e.customer_id] || "—")}</dd>
          <dt>Make/Model</dt><dd>${esc(e.manufacturer || "—")} ${esc(e.model || "")}</dd>
          <dt>Serial</dt><dd class="mono" style="font-size:.82rem">${esc(e.serial_number || "—")}</dd>
          <dt>Location</dt><dd>${esc(e.location || "—")}</dd></dl></div>`).join("") ||
      '<div class="empty"><div class="big">⚙️</div>No equipment yet.</div>'}
    </div>`;
  els("[data-eqid]").forEach((c) => c.addEventListener("click", () => (location.hash = `#/equipment/${c.dataset.eqid}`)));
}

async function renderEquipmentDetail(id) {
  loading();
  const [eq, history] = await Promise.all([api.equipmentOne(id), api.workOrders({ equipment_id: id })]);
  const cust = customersCache || (customersCache = await api.customers());
  const owner = (cust.find((c) => c.id === eq.customer_id) || {}).name || "—";
  const nameplate = eq.nameplate_data
    ? Object.entries(eq.nameplate_data).map(([k, v]) =>
        `<span class="badge" style="background:var(--surface-3)">${esc(k)}: <b>${esc(v)}</b></span>`).join(" ")
    : "";
  const rows = history.map((w) => `<tr data-wo="${w.id}">
    <td class="mono nowrap">${esc(w.number)}</td><td>${esc(w.title)}</td>
    <td>${statusBadge(w.status)}</td><td class="muted nowrap">${fmtDate(w.created_at)}</td></tr>`).join("")
    || '<tr><td colspan="4" class="muted" style="text-align:center;padding:20px">No repair history yet.</td></tr>';

  view.innerHTML = `
    <div class="row" style="margin-bottom:8px"><a href="#/equipment">← Equipment</a></div>
    <div class="page-title">
      <div><h1 style="margin-bottom:4px">${TYPE_ICON[eq.equipment_type]} ${esc(eq.tag || TYPE_LABEL[eq.equipment_type])}</h1>
        <div class="muted">${esc(eq.manufacturer || "")} ${esc(eq.model || "")} · ${TYPE_LABEL[eq.equipment_type]} · owned by ${esc(owner)}</div></div>
    </div>
    <div class="grid" style="grid-template-columns:1.6fr 1fr;align-items:start">
      <div class="stack">
        <div class="card"><div class="card-head"><h3>Nameplate</h3></div>
          <div class="card-body">
            <dl class="kv"><dt>Serial</dt><dd class="mono">${esc(eq.serial_number || "—")}</dd>
              <dt>Location</dt><dd>${esc(eq.location || "—")}</dd></dl>
            <div class="row wrap" style="margin-top:10px">${nameplate}</div></div></div>
        <div class="card"><div class="card-head"><h3>Repair history <span class="badge">${history.length}</span></h3></div>
          <div class="table-wrap"><table class="data">
            <thead><tr><th>WO #</th><th>Title</th><th>Status</th><th>Opened</th></tr></thead>
            <tbody>${rows}</tbody></table></div></div>
      </div>
      <div class="card"><div class="card-head"><h3>Asset tag</h3>
        <button class="btn btn-ghost btn-sm" id="printLabel">🖨 Print label</button></div>
        <div class="card-body" style="text-align:center">
          <div id="qrBox" style="max-width:200px;margin:0 auto">Loading QR…</div>
          <p class="muted" style="font-size:.82rem;margin-top:10px">Scan to open this asset's history on any device.</p></div></div>
    </div>`;

  els("tr[data-wo]").forEach((tr) => tr.addEventListener("click", () => (location.hash = `#/workorders/${tr.dataset.wo}`)));
  let svg = "";
  try { svg = await fetchAuthedText(`/api/equipment/${id}/qr.svg`); el("#qrBox").innerHTML = svg; }
  catch { el("#qrBox").innerHTML = '<span class="muted">QR unavailable</span>'; }
  el("#printLabel").addEventListener("click", () => printLabel(eq, owner, svg));
}

function printLabel(eq, owner, svg) {
  const w = window.open("", "_blank", "width=420,height=560");
  if (!w) return toast("Allow pop-ups to print", "err");
  w.document.write(`<!doctype html><html><head><title>Asset ${esc(eq.tag || eq.id)}</title>
    <style>body{font-family:Arial,sans-serif;margin:0;padding:24px;text-align:center}
      .tag{border:2px solid #0f172a;border-radius:12px;padding:20px;max-width:340px;margin:0 auto}
      h1{font-size:20px;margin:0 0 4px} .sub{color:#475569;font-size:13px;margin-bottom:12px}
      svg{width:200px;height:200px} .kv{font-size:12px;text-align:left;margin-top:12px}
      .kv div{display:flex;justify-content:space-between;border-bottom:1px solid #e2e8f0;padding:3px 0}</style></head>
    <body><div class="tag"><h1>${esc(eq.tag || TYPE_LABEL[eq.equipment_type] || "Asset")}</h1>
      <div class="sub">${esc(eq.manufacturer || "")} ${esc(eq.model || "")}</div>
      ${svg}
      <div class="kv"><div><span>Serial</span><b>${esc(eq.serial_number || "—")}</b></div>
        <div><span>Owner</span><b>${esc(owner)}</b></div>
        <div><span>Serviceflow</span><b>${esc(eq.equipment_type)}</b></div></div></div>
      <script>window.onload=()=>window.print()<\/script></body></html>`);
  w.document.close();
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

/* ---------- field dispatch board ---------- */
let techCache = null;

async function renderDispatch() {
  loading();
  const [list, cust, techs] = await Promise.all([
    api.workOrders({ service_type: "field_service" }),
    customersCache || api.customers(),
    techCache || api.users("technician"),
  ]);
  customersCache = cust; techCache = techs;
  const custById = Object.fromEntries(cust.map((c) => [c.id, c.name]));
  const techById = Object.fromEntries(techs.map((t) => [t.id, t.full_name]));
  const active = list.filter((w) => !["closed", "cancelled", "shipped"].includes(w.status));

  // Group by scheduled day (YYYY-MM-DD) or "unscheduled".
  const groups = {};
  const unscheduled = [];
  active.forEach((w) => {
    if (w.scheduled_at) {
      const day = new Date(w.scheduled_at).toISOString().slice(0, 10);
      (groups[day] ||= []).push(w);
    } else unscheduled.push(w);
  });
  const days = Object.keys(groups).sort();

  const card = (w) => `
    <div class="card" data-wo="${w.id}" style="cursor:pointer;padding:12px;margin-bottom:10px;border-left:4px solid var(--st-testing)">
      <div class="spread"><span class="mono muted">${esc(w.number)}</span>${prioBadge(w.priority)}</div>
      <div style="font-weight:600;margin:4px 0">${esc(w.title)}</div>
      <div class="muted" style="font-size:.84rem">🏢 ${esc(custById[w.customer_id] || "")}</div>
      <div class="spread" style="margin-top:8px">
        <span class="badge">${w.scheduled_at ? "🕑 " + fmtDateTime(w.scheduled_at).split(", ").slice(1).join(", ") : "unscheduled"}</span>
        <span class="muted" style="font-size:.82rem">${w.assigned_to ? "👷 " + esc(techById[w.assigned_to] || "Tech") : "unassigned"}</span>
      </div>
      <button class="btn btn-ghost btn-sm" data-sched="${w.id}" style="margin-top:8px;width:100%">📅 ${w.scheduled_at ? "Reschedule" : "Schedule visit"}</button>
    </div>`;

  const dayLabel = (d) => new Date(d + "T00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });

  view.innerHTML = `
    <div class="page-title"><h1>Field dispatch</h1>
      <span class="muted">${active.length} active field job${active.length === 1 ? "" : "s"}</span></div>
    <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr));align-items:start">
      <div class="card card-pad" style="background:var(--surface-2)">
        <h3 style="margin-bottom:12px">📥 Unscheduled <span class="badge">${unscheduled.length}</span></h3>
        ${unscheduled.map(card).join("") || '<p class="muted">Nothing waiting.</p>'}
      </div>
      ${days.map((d) => `<div class="card card-pad">
        <h3 style="margin-bottom:12px">${dayLabel(d)} <span class="badge">${groups[d].length}</span></h3>
        ${groups[d].sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at)).map(card).join("")}
      </div>`).join("")}
    </div>`;

  els("[data-wo]").forEach((c) => c.addEventListener("click", (e) => {
    if (e.target.closest("[data-sched]")) return;
    location.hash = `#/workorders/${c.dataset.wo}`;
  }));
  els("[data-sched]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    openSchedule(b.dataset.sched, techs);
  }));
}

function openSchedule(woId, techs, after) {
  const refresh = after || (() => renderDispatch());
  const now = new Date();
  now.setMinutes(0, 0, 0); now.setHours(now.getHours() + 1);
  const localVal = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const m = modal(`<div class="card-head"><h3>Schedule field visit</h3></div>
    <div class="card-body stack">
      <label class="field"><span>Date &amp; time</span><input type="datetime-local" id="sdt" value="${localVal}" /></label>
      <label class="field"><span>Technician</span><select id="stech">
        <option value="">— unassigned —</option>
        ${techs.map((t) => `<option value="${t.id}">${esc(t.full_name)}</option>`).join("")}</select></label>
      <label class="row" style="font-size:.88rem"><input type="checkbox" id="snotify" checked style="width:auto"> Notify customer by email</label>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="scx">Cancel</button>
        <button class="btn btn-primary" id="sok">Schedule</button></div></div>`);
  el("#scx", m.root).onclick = m.close;
  el("#sok", m.root).onclick = async () => {
    const dt = el("#sdt", m.root).value;
    if (!dt) return toast("Pick a date & time", "err");
    try {
      await api.scheduleVisit(woId, {
        scheduled_at: new Date(dt).toISOString(),
        assigned_to: +el("#stech", m.root).value || null,
        notify_customer: el("#snotify", m.root).checked,
      });
      m.close(); toast("Visit scheduled", "ok"); refresh();
    } catch (ex) { toast(ex.message, "err"); }
  };
}

/* ---------- inventory ---------- */
let partsCache = null;

async function renderInventory(lowOnly = false) {
  loading();
  const list = await api.parts(lowOnly ? { low_stock: true } : {});
  partsCache = await api.parts();
  const lowCount = partsCache.filter((p) => p.quantity_on_hand <= p.reorder_point).length;
  view.innerHTML = `
    <div class="page-title"><h1>Inventory</h1>
      <div class="row">
        <button class="btn btn-ghost btn-sm ${lowOnly ? "" : ""}" id="lowToggle"
          style="${lowOnly ? "border-color:var(--accent-500);color:var(--accent-600)" : ""}">⚠ Low stock (${lowCount})</button>
        <button class="btn btn-primary btn-sm" id="addPart">+ Add part</button>
      </div></div>
    <div class="card"><div class="table-wrap"><table class="data">
      <thead><tr><th>SKU</th><th>Part</th><th>Location</th><th class="text-right">On hand</th><th class="text-right">Reorder</th><th class="text-right">Unit price</th><th></th></tr></thead>
      <tbody>${list.map((p) => {
        const low = p.quantity_on_hand <= p.reorder_point;
        return `<tr data-nostyle>
          <td class="mono">${esc(p.sku)}</td>
          <td><strong>${esc(p.name)}</strong>${low ? ' <span class="badge status on_hold">Low</span>' : ""}</td>
          <td class="muted">${esc(p.location || "—")}</td>
          <td class="text-right"><strong style="color:${low ? "var(--danger)" : "var(--ink-900)"}">${p.quantity_on_hand}</strong></td>
          <td class="text-right muted">${p.reorder_point}</td>
          <td class="text-right mono">${money(p.unit_price)}</td>
          <td class="text-right nowrap">
            <button class="btn btn-ghost btn-sm" data-adj="${p.id}" data-d="-1">−</button>
            <button class="btn btn-ghost btn-sm" data-adj="${p.id}" data-d="1">+</button>
            <button class="btn btn-ghost btn-sm" data-recv="${p.id}">Receive</button></td></tr>`;
      }).join("") || '<tr><td colspan="7" class="muted" style="text-align:center;padding:24px">No parts. Add your catalog.</td></tr>'}
      </tbody></table></div></div>`;
  els("tr[data-nostyle]").forEach((tr) => (tr.style.cursor = "default"));
  el("#addPart").addEventListener("click", openAddPart);
  el("#lowToggle").addEventListener("click", () => renderInventory(!lowOnly));
  els("[data-adj]").forEach((b) => b.addEventListener("click", async () => {
    try { await api.adjustStock(b.dataset.adj, +b.dataset.d); renderInventory(lowOnly); }
    catch (e) { toast(e.message, "err"); }
  }));
  els("[data-recv]").forEach((b) => b.addEventListener("click", async () => {
    const n = prompt("Receive how many units into stock?", "10");
    if (n === null) return;
    const d = parseInt(n, 10);
    if (!Number.isFinite(d) || d <= 0) return toast("Enter a positive number", "err");
    try { await api.adjustStock(b.dataset.recv, d, "received"); toast("Stock received", "ok"); renderInventory(lowOnly); }
    catch (e) { toast(e.message, "err"); }
  }));
}

function openAddPart() {
  const m = modal(`<div class="card-head"><h3>Add part</h3></div>
    <div class="card-body stack">
      <div class="row">
        <label class="field grow"><span>SKU</span><input id="psku" placeholder="BRG-6314" /></label>
        <label class="field grow"><span>Location</span><input id="ploc" placeholder="Bin A-12" /></label>
      </div>
      <label class="field"><span>Name</span><input id="pname" placeholder="Bearing 6314 (DE)" /></label>
      <div class="row">
        <label class="field grow"><span>Unit cost</span><input type="number" id="pcost" value="0" step="0.01" /></label>
        <label class="field grow"><span>Unit price</span><input type="number" id="pprice" value="0" step="0.01" /></label>
      </div>
      <div class="row">
        <label class="field grow"><span>On hand</span><input type="number" id="pqty" value="0" /></label>
        <label class="field grow"><span>Reorder point</span><input type="number" id="preorder" value="0" /></label>
      </div>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="pcx">Cancel</button>
        <button class="btn btn-primary" id="pok">Add part</button></div></div>`);
  el("#pcx", m.root).onclick = m.close;
  el("#pok", m.root).onclick = async () => {
    const sku = el("#psku", m.root).value.trim(), name = el("#pname", m.root).value.trim();
    if (!sku || !name) return toast("SKU and name are required", "err");
    try {
      await api.createPart({
        sku, name, location: el("#ploc", m.root).value.trim() || null,
        unit_cost: +el("#pcost", m.root).value || 0, unit_price: +el("#pprice", m.root).value || 0,
        quantity_on_hand: +el("#pqty", m.root).value || 0, reorder_point: +el("#preorder", m.root).value || 0,
      });
      m.close(); toast("Part added", "ok"); renderInventory();
    } catch (ex) { toast(ex.message, "err"); }
  };
}

/* ---------- analytics ---------- */
// Horizontal magnitude bars: identity via text label, magnitude via length,
// single hue (or a per-row color for the reserved status palette).
function hbars(rows, { fmt = (v) => v, color } = {}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return `<div class="stack" style="gap:10px">${rows.map((r) => `
    <div>
      <div class="spread" style="font-size:.85rem;margin-bottom:3px">
        <span>${esc(r.label)}</span><strong>${fmt(r.value)}</strong></div>
      <div style="background:var(--surface-3);border-radius:5px;height:12px" title="${esc(r.label)}: ${fmt(r.value)}">
        <div style="width:${Math.max(2, (r.value / max) * 100)}%;height:100%;border-radius:5px;background:${r.color || color || "var(--brand-500)"}"></div>
      </div>
    </div>`).join("")}</div>`;
}

function revenueChart(data) {
  const w = 520, h = 200, pad = 34, bw = (w - pad * 2) / data.length;
  const max = Math.max(1, ...data.map((d) => d.revenue));
  const bars = data.map((d, i) => {
    const bh = (d.revenue / max) * (h - pad - 20);
    const x = pad + i * bw, y = h - pad - bh;
    const label = new Date(d.month + "-01").toLocaleDateString("en-US", { month: "short" });
    return `<g>
      <rect x="${x + 6}" y="${y}" width="${bw - 12}" height="${Math.max(bh, 1)}" rx="4" fill="var(--brand-500)">
        <title>${label}: ${money(d.revenue)}</title></rect>
      ${d.revenue > 0 ? `<text x="${x + bw / 2}" y="${y - 5}" text-anchor="middle" font-size="10" fill="var(--ink-500)">${d.revenue >= 1000 ? "$" + (d.revenue / 1000).toFixed(1) + "k" : "$" + d.revenue.toFixed(0)}</text>` : ""}
      <text x="${x + bw / 2}" y="${h - pad + 14}" text-anchor="middle" font-size="10" fill="var(--ink-500)">${label}</text>
    </g>`;
  }).join("");
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto" role="img" aria-label="Revenue by month">
    <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="var(--line)" stroke-width="1"/>
    ${bars}</svg>`;
}

async function renderAnalytics() {
  loading();
  const a = await api.analytics();
  const stat = (label, val, cls = "", sub = "") =>
    `<div class="stat ${cls}"><div class="stat-label">${label}</div>
     <div class="stat-value">${val}</div><div class="stat-sub">${sub}</div></div>`;
  const statusRows = Object.entries(a.status_counts)
    .sort((x, y) => y[1] - x[1])
    .map(([s, c]) => ({ label: STATUS_LABEL[s] || s, value: c, color: `var(--st-${s === "quote_pending" ? "quote" : s === "in_repair" ? "repair" : s === "on_hold" ? "hold" : s})` }));
  const typeRows = Object.entries(a.by_type).sort((x, y) => y[1] - x[1])
    .map(([t, c]) => ({ label: (TYPE_LABEL[t] || t), value: c }));
  const workloadRows = a.tech_workload.map((r) => ({ label: r.technician, value: r.hours }));

  view.innerHTML = `
    <div class="page-title"><h1>Analytics</h1><span class="muted">Shop performance at a glance</span></div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin-bottom:22px">
      ${stat("Completed (30d)", a.completed_30d, "ok", `${a.completed_90d} in last 90d`)}
      ${stat("Avg turnaround", `${a.avg_turnaround_days}d`, "", "intake → shipped")}
      ${stat("Open jobs", a.open_total, "warn", "in shop &amp; field")}
      ${stat("Paid revenue", money(a.paid_revenue), "ok", "collected")}
      ${stat("Outstanding", money(a.outstanding_revenue), "accent", "awaiting payment")}
    </div>
    <div class="grid" style="grid-template-columns:1.4fr 1fr;align-items:start">
      <div class="card"><div class="card-head"><h3>Revenue by month</h3></div>
        <div class="card-body">${revenueChart(a.revenue_by_month)}</div></div>
      <div class="card"><div class="card-head"><h3>Open pipeline</h3></div>
        <div class="card-body">${statusRows.length ? hbars(statusRows) : '<p class="muted">No jobs.</p>'}</div></div>
    </div>
    <div class="grid" style="grid-template-columns:1fr 1fr;margin-top:16px;align-items:start">
      <div class="card"><div class="card-head"><h3>Jobs by equipment type</h3></div>
        <div class="card-body">${typeRows.length ? hbars(typeRows) : '<p class="muted">No data.</p>'}</div></div>
      <div class="card"><div class="card-head"><h3>Technician workload</h3></div>
        <div class="card-body">${workloadRows.length ? hbars(workloadRows, { fmt: (v) => v + "h", color: "var(--st-testing)" }) : '<p class="muted">No labor logged.</p>'}</div></div>
    </div>`;
}

/* ---------- billing (SaaS subscription) ---------- */
async function renderBilling() {
  loading();
  const [plans, sub] = await Promise.all([api.plans(), api.subscription()]);
  const isOwner = (auth.user || {}).role === "owner";
  const statusBadgeCls = { active: "ready", trialing: "quote_pending", past_due: "on_hold", canceled: "cancelled" }[sub.subscription_status] || "intake";
  const planCard = (p) => {
    const current = sub.plan === p.id;
    return `<div class="card card-pad" style="${current ? "border:2px solid var(--brand-500)" : ""}">
      <div class="spread"><h3>${esc(p.name)}</h3>${current ? '<span class="badge status ready">Current</span>' : ""}</div>
      <div style="font-size:2rem;font-weight:800;margin:8px 0">$${p.price_monthly}<span class="muted" style="font-size:.9rem;font-weight:400">/mo</span></div>
      <div class="muted" style="font-size:.84rem;margin-bottom:12px">Up to ${p.seats} users</div>
      <ul style="list-style:none;padding:0;margin:0 0 16px;display:grid;gap:6px;font-size:.88rem">
        ${p.features.map((f) => `<li>✓ ${esc(f)}</li>`).join("")}</ul>
      ${isOwner ? `<button class="btn ${current ? "btn-ghost" : "btn-primary"} btn-block" data-plan="${p.id}" ${current ? "disabled" : ""}>
        ${current ? "Current plan" : "Choose " + esc(p.name)}</button>` : '<p class="muted" style="font-size:.82rem">Only the owner can change the plan.</p>'}
    </div>`;
  };
  view.innerHTML = `
    <div class="page-title"><h1>Billing &amp; subscription</h1></div>
    <div class="card card-pad" style="margin-bottom:20px">
      <div class="spread wrap">
        <div><div class="stat-label">Current plan</div>
          <div style="font-size:1.5rem;font-weight:700;text-transform:capitalize">${esc(sub.plan)}
            <span class="badge status ${statusBadgeCls}">${esc(sub.subscription_status)}</span></div></div>
        <div><div class="stat-label">Seats</div><div style="font-size:1.5rem;font-weight:700">${sub.seats}</div></div>
        <div><div class="stat-label">Renews</div><div style="font-size:1.1rem">${sub.current_period_end ? fmtDate(sub.current_period_end) : "—"}</div></div>
        ${isOwner && sub.subscription_status === "active" ? '<button class="btn btn-danger" id="cancelSub">Cancel subscription</button>' : ""}
      </div>
    </div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr))">${plans.map(planCard).join("")}</div>
    <p class="muted" style="margin-top:16px;font-size:.84rem">💡 Running in mock billing mode — choosing a plan activates it instantly. Set <span class="mono">SERVICEFLOW_STRIPE_SECRET_KEY</span> to enable real Stripe checkout.</p>`;

  els("[data-plan]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "Processing…";
    try {
      const res = await api.checkout(b.dataset.plan);
      if (res.checkout_url) { location.href = res.checkout_url; return; }
      toast(res.message || "Subscription updated", "ok"); renderBilling();
    } catch (ex) { toast(ex.message, "err"); renderBilling(); }
  }));
  const cs = el("#cancelSub");
  if (cs) cs.addEventListener("click", async () => {
    try { await api.cancelSubscription(); toast("Subscription canceled", ""); renderBilling(); }
    catch (ex) { toast(ex.message, "err"); }
  });
}

/* ---------- developer (API keys + webhooks) ---------- */
const WEBHOOK_EVENTS = ["work_order.status_changed", "invoice.paid"];

async function renderDeveloper() {
  loading();
  const [keys, hooks] = await Promise.all([api.apiKeys(), api.webhooks()]);
  view.innerHTML = `
    <div class="page-title"><h1>Developers</h1><span class="muted">Programmatic access &amp; webhooks</span></div>
    <div class="card" style="margin-bottom:20px"><div class="card-head"><h3>API keys</h3>
      <button class="btn btn-primary btn-sm" id="newKey">+ New key</button></div>
      <div class="card-body">
        <p class="muted" style="font-size:.85rem;margin-bottom:12px">Authenticate integration requests with
          <span class="mono">X-API-Key: sf_…</span> against <span class="mono">/api/v1/*</span>.</p>
        <div class="table-wrap"><table class="data">
          <thead><tr><th>Name</th><th>Key</th><th>Last used</th><th>Status</th><th></th></tr></thead>
          <tbody>${keys.map((k) => `<tr data-nostyle>
            <td><strong>${esc(k.name)}</strong></td>
            <td class="mono">${esc(k.prefix)}…</td>
            <td class="muted nowrap">${k.last_used_at ? fmtDateTime(k.last_used_at) : "never"}</td>
            <td>${k.is_active ? '<span class="badge status ready">active</span>' : '<span class="badge status cancelled">revoked</span>'}</td>
            <td class="text-right">${k.is_active ? `<button class="btn btn-danger btn-sm" data-revoke="${k.id}">Revoke</button>` : ""}</td></tr>`).join("") ||
          '<tr><td colspan="5" class="muted" style="text-align:center;padding:20px">No API keys yet.</td></tr>'}
          </tbody></table></div></div></div>

    <div class="card"><div class="card-head"><h3>Webhooks</h3>
      <button class="btn btn-primary btn-sm" id="newHook">+ Add webhook</button></div>
      <div class="card-body stack">
        <p class="muted" style="font-size:.85rem">Serviceflow POSTs a signed JSON payload
          (<span class="mono">X-Serviceflow-Signature: sha256=…</span>) to your endpoint on each subscribed event.</p>
        ${hooks.map((h) => `<div class="card" style="box-shadow:none;border-color:var(--line)"><div class="card-body">
          <div class="spread"><div><strong class="mono" style="font-size:.86rem">${esc(h.url)}</strong>
            <div class="muted" style="font-size:.8rem">${(h.events || []).map((e) => esc(e)).join(", ")}</div></div>
            <div class="row">
              <button class="btn btn-ghost btn-sm" data-test="${h.id}">Send test</button>
              <button class="btn btn-ghost btn-sm" data-deliv="${h.id}">Deliveries</button>
              <button class="btn btn-danger btn-sm" data-delhook="${h.id}">✕</button></div></div>
          <div class="deliveries hide" data-deliv-box="${h.id}" style="margin-top:10px"></div></div></div>`).join("") ||
        '<p class="muted">No webhooks yet.</p>'}
      </div></div>`;

  el("#newKey").addEventListener("click", openNewKey);
  el("#newHook").addEventListener("click", openNewWebhook);
  els("[data-revoke]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("Revoke this API key? Integrations using it will stop working.")) return;
    try { await api.revokeApiKey(b.dataset.revoke); toast("Key revoked", ""); renderDeveloper(); }
    catch (e) { toast(e.message, "err"); }
  }));
  els("[data-delhook]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("Delete this webhook?")) return;
    try { await api.deleteWebhook(b.dataset.delhook); toast("Webhook deleted", ""); renderDeveloper(); }
    catch (e) { toast(e.message, "err"); }
  }));
  els("[data-test]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "Sending…";
    try {
      const d = await api.testWebhook(b.dataset.test);
      toast(d.success ? `Delivered (HTTP ${d.status_code})` : `Failed: ${d.error || "unreachable"}`, d.success ? "ok" : "err");
    } catch (e) { toast(e.message, "err"); }
    b.disabled = false; b.textContent = "Send test";
  }));
  els("[data-deliv]").forEach((b) => b.addEventListener("click", async () => {
    const box = el(`[data-deliv-box="${b.dataset.deliv}"]`);
    if (!box.classList.contains("hide")) { box.classList.add("hide"); return; }
    box.classList.remove("hide"); box.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const list = await api.webhookDeliveries(b.dataset.deliv);
      box.innerHTML = list.length ? `<table class="data"><thead><tr><th>When</th><th>Event</th><th>Result</th></tr></thead>
        <tbody>${list.map((d) => `<tr data-nostyle><td class="muted nowrap">${fmtDateTime(d.created_at)}</td><td class="mono">${esc(d.event)}</td>
          <td>${d.success ? `<span class="badge status ready">HTTP ${d.status_code}</span>` : `<span class="badge status cancelled">${esc(d.error || "failed")}</span>`}</td></tr>`).join("")}</tbody></table>`
        : '<p class="muted">No deliveries yet.</p>';
    } catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
  }));
}

function openNewKey() {
  const m = modal(`<div class="card-head"><h3>Create API key</h3></div>
    <div class="card-body stack">
      <label class="field"><span>Name / purpose</span><input id="kn" placeholder="e.g. ERP integration" /></label>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="kcx">Cancel</button>
        <button class="btn btn-primary" id="kok">Create</button></div></div>`);
  el("#kcx", m.root).onclick = m.close;
  el("#kok", m.root).onclick = async () => {
    const name = el("#kn", m.root).value.trim();
    if (!name) return toast("Name is required", "err");
    try {
      const created = await api.createApiKey(name);
      m.close();
      modal(`<div class="card-head"><h3>Copy your API key</h3></div>
        <div class="card-body stack">
          <div class="badge status on_hold" style="align-self:flex-start">⚠ Shown only once — store it now.</div>
          <input readonly value="${esc(created.key)}" class="mono" onclick="this.select()" style="font-size:.82rem" />
          <div class="row" style="justify-content:flex-end"><button class="btn btn-primary" onclick="this.closest('.modal-backdrop').remove()">Done</button></div>
        </div>`);
      renderDeveloper();
    } catch (ex) { toast(ex.message, "err"); }
  };
}

function openNewWebhook() {
  const m = modal(`<div class="card-head"><h3>Add webhook</h3></div>
    <div class="card-body stack">
      <label class="field"><span>Endpoint URL</span><input id="wu" placeholder="https://example.com/hooks/serviceflow" /></label>
      <div class="field"><span>Events</span>
        <label class="row" style="font-size:.9rem"><input type="checkbox" class="wev" value="*" checked style="width:auto"> All events</label>
        ${WEBHOOK_EVENTS.map((e) => `<label class="row" style="font-size:.9rem"><input type="checkbox" class="wev" value="${e}" style="width:auto"> ${e}</label>`).join("")}</div>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" id="wcx">Cancel</button>
        <button class="btn btn-primary" id="wok">Add webhook</button></div></div>`);
  el("#wcx", m.root).onclick = m.close;
  el("#wok", m.root).onclick = async () => {
    const url = el("#wu", m.root).value.trim();
    if (!/^https?:\/\//.test(url)) return toast("Enter a valid URL", "err");
    const events = els(".wev", m.root).filter((c) => c.checked).map((c) => c.value);
    try { await api.createWebhook(url, events.length ? events : ["*"]); m.close(); toast("Webhook added", "ok"); renderDeveloper(); }
    catch (ex) { toast(ex.message, "err"); }
  };
}

/* ---------- audit log ---------- */
const AUDIT_META = {
  "user.login": ["🔑", "var(--st-intake)"],
  "work_order.created": ["🆕", "var(--brand-500)"],
  "work_order.status_changed": ["🔄", "var(--st-repair)"],
  "work_order.scheduled": ["📅", "var(--st-testing)"],
  "quote.sent": ["📤", "var(--st-quote)"],
  "quote.approved": ["✅", "var(--ok)"],
  "quote.rejected": ["🚫", "var(--danger)"],
  "invoice.created": ["🧾", "var(--st-quote)"],
  "invoice.paid": ["💰", "var(--ok)"],
  "invoice.unpaid": ["↩️", "var(--st-hold)"],
  "part.consumed": ["📦", "var(--st-repair)"],
  "part.adjusted": ["📊", "var(--st-shipped)"],
  "billing.checkout": ["💳", "var(--brand-600)"],
  "billing.canceled": ["✖️", "var(--danger)"],
};

async function renderAudit(filter = "") {
  loading();
  const list = await api.audit(filter);
  const actions = [...new Set(list.map((e) => e.action))];
  const chip = (a, label) => `<button class="btn btn-ghost btn-sm afilter" data-a="${a}"
    style="${a === filter ? "border-color:var(--brand-500);color:var(--brand-700)" : ""}">${label}</button>`;
  view.innerHTML = `
    <div class="page-title"><h1>Audit log</h1><span class="muted">Who did what, across the workspace</span></div>
    <div class="row wrap" style="margin-bottom:16px">${chip("", "All")}
      ${actions.map((a) => chip(a, `${(AUDIT_META[a] || ["•"])[0]} ${a.replace(/[._]/g, " ")}`)).join("")}</div>
    <div class="card"><div class="table-wrap"><table class="data">
      <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Details</th></tr></thead>
      <tbody>${list.map((e) => {
        const [ic, color] = AUDIT_META[e.action] || ["•", "var(--ink-500)"];
        return `<tr data-nostyle>
          <td class="muted nowrap">${fmtDateTime(e.created_at)}</td>
          <td>${esc(e.actor_label)}</td>
          <td><span class="badge" style="background:${color};color:#fff">${ic} ${esc(e.action.replace(/[._]/g, " "))}</span></td>
          <td>${esc(e.summary)}</td></tr>`;
      }).join("") || '<tr><td colspan="4" class="empty" style="padding:32px"><div class="big">📜</div>No activity recorded yet.</td></tr>'}
      </tbody></table></div></div>`;
  els("tr[data-nostyle]").forEach((tr) => (tr.style.cursor = "default"));
  els(".afilter").forEach((b) => b.addEventListener("click", () => renderAudit(b.dataset.a)));
}

/* ---------- notifications ---------- */
async function renderNotifications() {
  loading();
  const list = await api.notifications();
  const chIcon = { email: "✉️", sms: "💬", inapp: "🔔" };
  const stBadge = (s) => `<span class="badge status ${s === "sent" ? "ready" : s === "failed" ? "cancelled" : "quote_pending"}">${esc(s)}</span>`;
  view.innerHTML = `
    <div class="page-title"><h1>Notifications</h1>
      <span class="muted">Messages sent to customers on status changes &amp; quotes</span></div>
    <div class="card"><div class="table-wrap"><table class="data">
      <thead><tr><th>Channel</th><th>Recipient</th><th>Subject</th><th>Status</th><th>When</th></tr></thead>
      <tbody>${list.map((n) => `<tr data-nostyle>
        <td class="nowrap">${chIcon[n.channel] || ""} ${esc(n.channel)}</td>
        <td class="mono" style="font-size:.82rem">${esc(n.recipient)}</td>
        <td>${esc(n.subject)}</td>
        <td>${stBadge(n.status)}</td>
        <td class="muted nowrap">${fmtDateTime(n.created_at)}</td></tr>`).join("") ||
      '<tr><td colspan="5" class="empty" style="padding:32px"><div class="big">🔔</div>No notifications yet. Change a job status or send a quote to trigger one.</td></tr>'}
      </tbody></table></div></div>`;
  els("tr[data-nostyle]").forEach((tr) => (tr.style.cursor = "default"));
}

boot();
