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
  createEquipment: (b) => request("/api/equipment", { method: "POST", body: b }),
  // work orders (staff)
  workOrders: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/work-orders${qs ? `?${qs}` : ""}`);
  },
  workOrder: (id) => request(`/api/work-orders/${id}`),
  createWorkOrder: (b) => request("/api/work-orders", { method: "POST", body: b }),
  changeStatus: (id, b) => request(`/api/work-orders/${id}/status`, { method: "POST", body: b }),
  addFinding: (id, b) => request(`/api/work-orders/${id}/findings`, { method: "POST", body: b }),
  createQuote: (id, b) => request(`/api/work-orders/${id}/quotes`, { method: "POST", body: b }),
  // portal
  portalWorkOrders: () => request("/api/portal/work-orders"),
  portalWorkOrder: (id) => request(`/api/portal/work-orders/${id}`),
  portalEquipment: () => request("/api/portal/equipment"),
  decideQuote: (quoteId, approve, note) =>
    request(`/api/portal/quotes/${quoteId}/decision`, { method: "POST", body: { approve, note } }),
};
