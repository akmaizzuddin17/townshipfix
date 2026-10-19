// Small shared helpers. No build step, no framework: runs anywhere Python runs.

export async function api(path, { method = "GET", json, form, pin } = {}) {
  const headers = {};
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form) body = form;
  if (pin) headers["X-Staff-Pin"] = pin;
  let res;
  try {
    res = await fetch(path, { method, headers, body });
  } catch (e) {
    throw new Error("No connection to the TownshipFix server. Check your internet and try again.");
  }
  let data = {};
  try { data = await res.json(); } catch (_) { /* empty body */ }
  if (!res.ok) {
    const err = new Error(data.error || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

export function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "html") n.innerHTML = v; // only used with constant strings
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

/** replaceChildren that skips null/undefined/false (so conditional children are easy). */
export function fill(node, ...kids) {
  node.replaceChildren(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
  return node;
}

export function timeAgo(iso, lang = "en") {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  const ms = lang === "ms";
  if (s < 60) return ms ? "baru sahaja" : "just now";
  if (s < 3600) return ms ? `${Math.round(s / 60)} min lalu` : `${Math.round(s / 60)} min ago`;
  if (s < 86400) return ms ? `${Math.round(s / 3600)} jam lalu` : `${Math.round(s / 3600)} h ago`;
  return ms ? `${Math.round(s / 86400)} hari lalu` : `${Math.round(s / 86400)} days ago`;
}

export function fmtDate(iso, lang = "en") {
  return new Date(iso).toLocaleString(lang === "ms" ? "ms-MY" : "en-MY", {
    weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
  });
}

export function kerb(band) {
  return el("span", { class: `kerb ${band}`, title: `Priority ${band}` }, el("span", {}, band));
}

export const STATUS_STEPS = ["open", "assigned", "in_progress", "awaiting_confirmation", "closed"];

export const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch (_) { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* private mode: keep going */ }
  },
};
