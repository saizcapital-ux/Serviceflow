/* Serviceflow API client — centralizes auth, fetch, and error handling. */

const API_BASE = (window.SERVICEFLOW_API || "http://127.0.0.1:8000");
const TOKEN_KEY = "sf_token";
const USER_KEY = "sf_user";

export const auth = {
  get token() { return localStorage.getItem(TOKEN_KEY); },
  get user() { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } },
  save(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); },
  get isStaff() { const u = this.user; return u && u.role !== "customer"; },
};

async function request(path, { method = "GET", body, auth: needAuth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (needAuth && auth.token) headers["Authorization"] = `Bearer ${auth.token}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method, headers, body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) { auth.clear(); location.href = "/login.html"; throw new Error("Unauthorized"); }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const msg = data?.detail || `Request failed (${res.status})`;
    throw new Error(Array.isArray(msg) ? msg.map(m => m.msg).join(", ") : msg);
  }
  return data;
}

export const api = {
  // auth
  login: (email, password) => request("/api/auth/login", { method: "POST", body: { email, password }, auth: false }),
  me: () => request("/api/auth/me"),
  // dashboard
  dashboard: () => request("/api/dashboard"),
  // customers & equipment
  customers: (q) => request(`/api/customers${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  createCustomer: (b) => request("/api/customers", { method: "POST", body: b }),
  equipment: (customerId) => request(`/api/equipment${customerId ? `?customer_id=${customerId}` : ""}`),
  equipmentOne: (id) => request(`/api/equipment/${id}`),
  createEquipment: (b) => request("/api/equipment", { method: "POST", body: b }),
  // work orders (staff)
  workOrders: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/work-orders${qs ? `?${qs}` : ""}`);
  },
  workOrder: (id) => request(`/api/work-orders/${id}`),
  createWorkOrder: (b) => request("/api/work-orders", { method: "POST", body: b }),
  updateWorkOrder: (id, b) => request(`/api/work-orders/${id}`, { method: "PATCH", body: b }),
  changeStatus: (id, b) => request(`/api/work-orders/${id}/status`, { method: "POST", body: b }),
  scheduleVisit: (id, b) => request(`/api/work-orders/${id}/schedule`, { method: "POST", body: b }),
  users: (role) => request(`/api/users${role ? `?role=${role}` : ""}`),
  addFinding: (id, b) => request(`/api/work-orders/${id}/findings`, { method: "POST", body: b }),
  createQuote: (id, b) => request(`/api/work-orders/${id}/quotes`, { method: "POST", body: b }),
  // labor & costing
  logTime: (woId, b) => request(`/api/work-orders/${woId}/time-entries`, { method: "POST", body: b }),
  costing: (woId) => request(`/api/work-orders/${woId}/costing`),
  // checklists / travelers
  checklistTemplates: () => request("/api/checklist-templates"),
  applyChecklist: (woId, templateId) => request(`/api/work-orders/${woId}/checklist/apply`, { method: "POST", body: { template_id: templateId } }),
  updateChecklistItem: (itemId, b) => request(`/api/checklist-items/${itemId}`, { method: "PATCH", body: b }),
  // parts & inventory
  parts: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/parts${qs ? `?${qs}` : ""}`);
  },
  createPart: (b) => request("/api/parts", { method: "POST", body: b }),
  adjustStock: (id, delta, reason) => request(`/api/parts/${id}/adjust`, { method: "POST", body: { delta, reason } }),
  consumePart: (woId, b) => request(`/api/work-orders/${woId}/parts`, { method: "POST", body: b }),
  // analytics
  analytics: () => request("/api/analytics/summary"),
  // billing (SaaS subscription)
  plans: () => request("/api/billing/plans"),
  subscription: () => request("/api/billing/subscription"),
  checkout: (planId) => request("/api/billing/checkout", { method: "POST", body: { plan_id: planId } }),
  cancelSubscription: () => request("/api/billing/cancel", { method: "POST" }),
  // notifications
  notifications: () => request("/api/notifications"),
  // invoices
  invoices: (customerId) => request(`/api/invoices${customerId ? `?customer_id=${customerId}` : ""}`),
  createInvoice: (woId, b) => request(`/api/work-orders/${woId}/invoices`, { method: "POST", body: b }),
  markInvoicePaid: (invoiceId, paid) => request(`/api/invoices/${invoiceId}/paid`, { method: "POST", body: { paid } }),
  // portal
  portalWorkOrders: () => request("/api/portal/work-orders"),
  portalInvoices: () => request("/api/portal/invoices"),
  portalWorkOrder: (id) => request(`/api/portal/work-orders/${id}`),
  portalEquipment: () => request("/api/portal/equipment"),
  decideQuote: (quoteId, approve, note, poNumber) =>
    request(`/api/portal/quotes/${quoteId}/decision`, { method: "POST", body: { approve, note, po_number: poNumber || null } }),
};

/** Fetch an authenticated binary endpoint and open it in a new tab (blob URL). */
export async function openAuthed(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
  });
  if (!res.ok) throw new Error("Could not load file");
  const url = URL.createObjectURL(await res.blob());
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export const openPdf = (invoiceId) => openAuthed(`/api/invoices/${invoiceId}/pdf`);
export const openAttachment = (attachmentId) => openAuthed(`/api/attachments/${attachmentId}/file`);

/** Fetch an authenticated text/SVG endpoint and return the body text. */
export async function fetchAuthedText(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
  });
  if (!res.ok) throw new Error("Could not load");
  return res.text();
}

/** Upload a file to a work order (multipart). */
export async function uploadAttachment(woId, file, kind) {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  const res = await fetch(`${API_BASE}/api/work-orders/${woId}/attachments`, {
    method: "POST",
    headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
    body: form,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail || `Upload failed (${res.status})`);
  return data;
}
