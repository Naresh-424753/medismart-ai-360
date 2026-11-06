const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// NOTE: the JWT lives in localStorage for simplicity. For production prefer an httpOnly cookie + CSRF protection.
export const tokenStore = {
  get: () => localStorage.getItem("ms_token"),
  set: (t) => localStorage.setItem("ms_token", t),
  clear: () => localStorage.removeItem("ms_token"),
};

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const t = tokenStore.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, { method, headers, body: payload });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && t && !path.startsWith("/auth/login")) {
    tokenStore.clear();
    window.location.assign("/login");
  }
  if (!res.ok) {
    const d = data.detail;
    const msg =
      typeof d === "string" ? d : Array.isArray(d) ? d.map((e) => `${(e.loc || []).slice(-1)[0]}: ${e.msg}`).join("; ") : d?.message || "Request failed";
    const err = new Error(msg);
    err.status = res.status;
    err.detail = d;
    throw err;
  }
  return data;
}

export const wsUrl = (path) => BASE.replace(/^http/, "ws") + path;
