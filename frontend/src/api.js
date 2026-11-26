// Small wrapper around fetch: every call goes to the FastAPI backend under /api.

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`/api${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    // The browser could not reach the server at all (it was stopped).
    throw new Error("Can't reach the Dealwatch server. Is it still running? Start it again and reload this page.");
  }
  if (res.status === 204) return null;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    // FastAPI errors: {"detail": "text"} or {"detail": [{msg: ...}]} for 422.
    const detail = body?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join(", ")
      : detail || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return body;
}

export const api = {
  search: (q) => request(`/games/search?q=${encodeURIComponent(q)}&limit=12`),
  watchlist: () => request("/watchlist"),
  addWatch: (externalId, targetPrice) =>
    request("/watchlist", {
      method: "POST",
      body: JSON.stringify({ external_id: externalId, target_price: targetPrice }),
    }),
  updateWatch: (id, targetPrice) =>
    request(`/watchlist/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ target_price: targetPrice }),
    }),
  removeWatch: (id) => request(`/watchlist/${id}`, { method: "DELETE" }),
  history: (id) => request(`/watchlist/${id}/history`),
  alerts: () => request("/alerts"),
  markRead: (id) => request(`/alerts/${id}/read`, { method: "POST" }),
  markAllRead: () => request("/alerts/read-all", { method: "POST" }),
  runCheck: () => request("/checker/run", { method: "POST" }),
};

export const money = (n) => (n == null ? "–" : `$${Number(n).toFixed(2)}`);
