import { api, el, fill, fmtDate, kerb, timeAgo } from "./common.js";
import { createTicketMap } from "./staff-map.js";

const $ = (id) => document.getElementById(id);
const S = { pin: null, filter: "active", items: [], selected: null, cfg: null,
  known: null, shownFilter: null, fresh: new Map(), version: null, lastFull: 0, busy: null };
const POLL_MS = 3000;       // cheap "anything new?" check
const FULL_MS = 30000;      // full reload anyway, so due times and ageing priority stay current
const FRESH_MS = 120000;    // how long a new or re-reported ticket stays highlighted
const ticketMap = createTicketMap({
  container: $("map"), status: $("map-status"), fitButton: $("map-fit"),
  styleButtons: document.querySelectorAll("[data-map-style]"), imageryNote: $("map-imagery-note"),
  onSelect: (code) => select(code),
  onOpen: async (code) => {
    await select(code);
    $("detail").scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
    $("detail").focus({ preventScroll: true });
  },
});

const STATUS = {
  open: "New", assigned: "Assigned", in_progress: "Being repaired",
  awaiting_confirmation: "Awaiting resident", closed: "Closed", merged: "Merged",
};
const CLOSE = {
  resident_confirmed: "Resident confirmed the repair",
  auto_after_verified: "Verified photo, no objection in 3 days",
  supervisor_override: "Supervisor override",
};
const LOC = { photo_gps: "location from photo", device_gps: "phone GPS", zone: "area picked from list",
  address_search: "address search", map_pin: "pin placed manually" };
const EVENT = {
  created: "Ticket created", report_received: "Resident report", report_merged: "Duplicate report added",
  assigned: "Assigned", work_started: "Work started", completion_accepted: "Repair evidence accepted",
  completion_rejected: "Repair evidence rejected", closed: "Closed", reopened: "Reopened by resident",
  merged_into: "Merged into another ticket", merged_from: "Ticket merged in",
};

function sstore(k, v) { try { v === undefined ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch (_) {} }
function sget(k) { try { return sessionStorage.getItem(k); } catch (_) { return null; } }

const call = (path, opts = {}) => api(path, { ...opts, pin: S.pin }).catch((e) => {
  if (e.status === 401) { signOut(); }
  throw e;
});

// ---------------------------------------------------------------- gate
function signOut() { S.pin = null; sstore("tf_pin"); $("dash").hidden = true; $("gate").hidden = false; }
async function signIn(pin) {
  S.pin = pin;
  await call("/api/staff/metrics");
  sstore("tf_pin", pin);
  $("gate").hidden = true; $("dash").hidden = false;
  await refresh();
}

// ------------------------------------------------------------- metrics
function renderMetrics(m) {
  const fmt = (v, unit = "") => (v === null || v === undefined ? "–" : `${v}${unit}`);
  const tiles = [
    [fmt(m.open), `open jobs${m.overdue ? `, ${m.overdue} overdue` : ""}`],
    [fmt(m.duplicates_merged + m.duplicates_merged_by_staff), "duplicate reports grouped"],
    [fmt(m.median_report_seconds, " s"), "median time to report"],
    [fmt(m.median_resolution_hours, " h"), "median time to fix"],
    [fmt(m.closed_with_verified_evidence_pct, "%"), "closures with verified evidence"],
    [fmt(m.fake_or_weak_closures_blocked), "weak repair photos rejected"],
  ];
  fill($("metrics"), ...tiles.map(([v, l]) => el("div", { class: "metric" }, el("b", {}, v), el("span", {}, l))));
}

// --------------------------------------------------------------- queue
function dueText(t) {
  if (t.status === "closed") return { text: "Closed", late: false };
  if (!t.sla_due_at) return { text: "", late: false };
  const h = (new Date(t.sla_due_at) - Date.now()) / 3.6e6;
  if (h < 0) return { text: `${Math.ceil(-h)} h overdue`, late: true };
  return { text: h < 48 ? `due in ${Math.ceil(h)} h` : `due in ${Math.ceil(h / 24)} d`, late: false };
}

function renderQueue() {
  const q = $("queue");
  if (!S.items.length) {
    fill(q, el("li", { class: "empty" }, S.filter === "active"
      ? "No open jobs. New resident reports appear here, highest impact first."
      : "Nothing here yet."));
    return;
  }
  fill(q, ...S.items.map((t) => {
    const d = dueText(t);
    return el("li", { class: S.fresh.has(t.code) ? "is-new" : "" }, el("button", {
      type: "button", "aria-current": String(S.selected === t.code), onclick: () => select(t.code),
    },
    kerb(t.priority_band),
    el("span", { class: "title" }, `${t.code} ${t.category_en}`, S.fresh.has(t.code) ? el("span", { class: "new-tag" }, S.fresh.get(t.code).label) : null),
    el("span", { class: `due${d.late ? " overdue" : ""}` }, d.text),
    el("span", { class: "sub" }, [t.landmark || "Pinned location", `${t.reporters} reporter${t.reporters > 1 ? "s" : ""}`,
      STATUS[t.status], t.possible_dup_of ? `possible duplicate of ${t.possible_dup_of}` : null].filter(Boolean).join(". "))));
  }));
}

// ----------------------------------------------------------------- map
function renderMap(newCodes = []) {
  ticketMap.render(S.items, S.cfg, S.selected, S.filter, newCodes);
}

// --------------------------------------------------------------- detail
function checksList(v) {
  return el("ul", { class: "checks" }, v.checks.map((c) =>
    el("li", {}, el("span", { class: `mark ${c.ok === true ? "ok" : c.ok === false ? "no" : "unk"}` }, c.ok === true ? "✓" : c.ok === false ? "✗" : "?"),
      el("span", {}, c.detail))));
}

function actionArea(t) {
  const box = el("div", {});
  const status = el("p", { class: "hint", "aria-live": "polite" });
  const run = async (fn, okMsg, next) => {
    status.className = "hint"; status.textContent = "Working…";
    try { const r = await fn(); status.textContent = okMsg || ""; await refresh(); await select(next || t.code); return r; }
    catch (e) { status.className = "error"; status.textContent = e.message; }
  };

  if (t.status === "open" || t.status === "assigned") {
    const who = el("input", { type: "text", id: "assignee", value: t.assigned_to || "", placeholder: t.team });
    box.append(el("div", { class: "actions" },
      el("div", { class: "field" }, el("label", { for: "assignee" }, "Assign to (person or crew)"), who),
      el("button", { type: "button", class: "btn primary", onclick: () => run(() =>
        call(`/api/staff/tickets/${t.code}/assign`, { method: "POST", json: { assignee: who.value } })) }, "Assign"),
      t.status === "assigned" ? el("button", { type: "button", class: "btn", onclick: () => run(() =>
        call(`/api/staff/tickets/${t.code}/start`, { method: "POST" })) }, "Start work") : null));
  }
  if (t.status === "assigned" || t.status === "in_progress") {
    const file = el("input", { type: "file", id: "after", accept: "image/*", capture: "environment" });
    const send = el("button", { type: "button", class: "btn primary", onclick: async () => {
      if (!file.files[0]) { status.className = "error"; status.textContent = "Take or choose the after photo first."; return; }
      const fd = new FormData();
      fd.append("photo", file.files[0]);
      const r = await run(() => call(`/api/staff/tickets/${t.code}/complete`, { method: "POST", form: fd }));
      if (r) status.textContent = r.result.summary;
    } }, "Submit repair photo");
    box.append(el("h2", {}, "Mark as repaired"),
      el("p", { class: "hint" }, "Take the photo from roughly where residents stood. The system checks it is the same spot, that the problem visibly changed, and that it isn't a reused photo."),
      el("div", { class: "actions" }, el("div", { class: "field" }, el("label", { for: "after" }, "After photo"), file), send));
  }
  if (t.possible_dup_of && !["closed", "merged"].includes(t.status)) {
    box.append(el("div", { class: "notice" }, `Possible duplicate of ${t.possible_dup_of}. `,
      el("button", { type: "button", class: "btn", onclick: () => run(() =>
        call(`/api/staff/tickets/${t.code}/merge`, { method: "POST", json: { into: t.possible_dup_of } }), "", t.possible_dup_of) },
      `Merge into ${t.possible_dup_of}`)));
  }
  if (!["closed", "merged"].includes(t.status)) {
    const note = el("textarea", { id: "override", placeholder: "Why can't this be verified by photo? (kept in the audit log)" });
    box.append(el("details", { class: "more" }, el("summary", {}, "Supervisor override"),
      el("div", { class: "field" }, el("label", { for: "override" }, "Reason"), note),
      el("button", { type: "button", class: "btn danger", onclick: () => run(() =>
        call(`/api/staff/tickets/${t.code}/override`, { method: "POST", json: { note: note.value } }), "Closed by override.") }, "Close without photo check")));
  }
  box.append(status);
  return box;
}

async function select(code) {
  S.selected = code;
  S.fresh.delete(code);
  renderQueue(); renderMap();
  ticketMap.showTicket(code);
  let t;
  try { t = await call(`/api/staff/tickets/${code}`); } catch (e) { fill($("detail"), el("p", { class: "error" }, e.message)); return; }
  const v = t.verification;
  const d = $("detail");
  fill(d, 
    el("div", { class: "row", style: "align-items:center;flex-wrap:wrap" }, el("span", { class: "plate" }, t.code), kerb(t.priority_band),
      el("span", { class: "tag" }, STATUS[t.status]), t.urgent ? el("span", { class: "tag bad" }, "Emergency") : null,
      t.overdue ? el("span", { class: "tag bad" }, "Overdue") : null),
    el("h1", { style: "margin-top:10px" }, t.category_en),
    el("p", { class: "hint" }, `${t.landmark || "Pinned location"}. ${t.team}${t.assigned_to ? `, assigned to ${t.assigned_to}` : ""}. Reported ${timeAgo(t.created_at)}. Due ${fmtDate(t.sla_due_at)}.`),
    t.urgent_reasons?.length ? el("div", { class: "notice danger" }, `Danger words: ${t.urgent_reasons.join(", ")}. Security was alerted.`) : null,
    el("div", { class: "photos" },
      ...t.reports.filter((r) => r.photo).map((r, i) => el("figure", {}, el("a", { href: `/media/${r.photo}`, target: "_blank" },
        el("img", { src: `/media/${r.photo}`, alt: `Resident photo ${i + 1}` })), el("figcaption", {}, `Resident ${i + 1}${r.privacy?.blurred ? `, ${r.privacy.blurred} blurred` : ""}`))),
      t.after_photo ? el("figure", {}, el("img", { src: `/media/${t.after_photo}`, alt: "After repair" }), el("figcaption", {}, "After repair")) : null),
    el("h2", {}, `Why it ranks here: ${t.priority_score}/100`),
    el("table", { class: "reasons" }, el("tbody", {}, t.priority_reasons.map((r) =>
      el("tr", {}, el("td", {}, r.why), el("td", { class: "pts" }, r.points ? `+${r.points}` : ""))))),
    v ? el("div", {}, el("h2", {}, v.passed ? "Repair evidence accepted" : "Last repair photo rejected"), checksList(v)) : null,
    actionArea(t),
    el("h2", {}, `What residents said (${t.reports.length})`),
    el("ul", { class: "reports" }, t.reports.map((r) => el("li", {},
      el("div", {}, r.text ? `“${r.text}”` : "(photo only)"),
      el("small", { class: "hint" }, [r.lang === "ms" ? "Malay" : "English", LOC[r.location_source],
        r.location_accuracy_m != null ? `GPS accuracy approximately ${Math.round(r.location_accuracy_m)} m` : null,
        r.on_behalf_of ? `for ${r.on_behalf_of}` : null, r.merge_explanation, timeAgo(r.created_at)].filter(Boolean).join(". "))))),
    el("h2", {}, "Audit trail"),
    el("ul", { class: "log", style: "padding:0" }, t.events.map((e) => el("li", {}, EVENT[e.kind] || e.kind,
      el("small", {}, `${fmtDate(e.at)} by ${e.actor}${e.detail?.note ? `: ${e.detail.note}` : ""}${e.detail?.to ? `: ${e.detail.to}` : ""}`)))),
  );
}

// ------------------------------------------------------------- refresh
// Works out which tickets are new or got another resident's report since the last look.
function spotChanges(items) {
  const now = Date.now();
  for (const [code, f] of S.fresh) if (now - f.at > FRESH_MS) S.fresh.delete(code);
  const news = [];
  if (S.known && S.shownFilter === S.filter) {
    for (const t of items) {
      const before = S.known.get(t.code);
      if (before === undefined) news.push({ t, label: "New", text: `New report ${t.code}: ${t.category_en}, ${t.landmark || "location pinned"}` });
      else if (t.reporters > before) news.push({ t, label: "+1 report", text: `Another resident reported ${t.code} (${t.reporters} reporters)` });
    }
  }
  S.known = S.known || new Map();
  for (const t of items) S.known.set(t.code, t.reporters);
  S.shownFilter = S.filter;
  for (const n of news) S.fresh.set(n.t.code, { at: now, label: n.label });
  return news;
}

function toast(news) {
  const box = $("toasts");
  for (const n of news.slice(0, 3)) {
    const b = el("button", { type: "button", class: `toast${n.t.priority_band === "P0" ? " urgent" : ""}`,
      onclick: () => { b.remove(); select(n.t.code); } }, n.text, el("span", { class: "toast-open" }, "Open"));
    box.prepend(b);
    setTimeout(() => b.remove(), 12000);
  }
  while (box.children.length > 3) box.lastChild.remove();
  if (news.length && document.hidden) document.title = `(${news.length}) TownshipFix staff`;
}

function setLive(ok, text) {
  $("live").classList.toggle("is-down", !ok);
  $("live-text").textContent = text;
}

async function refresh() {
  // Never run two reloads at once; a caller arriving mid-reload waits for that one.
  if (S.busy) return S.busy;
  S.busy = (async () => {
    const [m, q, o, c] = await Promise.all([
      call("/api/staff/metrics"), call(`/api/staff/tickets?status=${S.filter}`), call("/api/staff/outbox"),
      call("/api/staff/changes"),
    ]);
    S.version = c.version; S.lastFull = Date.now();
    renderMetrics(m);
    S.items = q.items;
    const news = spotChanges(q.items);
    renderQueue(); renderMap(news.map((n) => n.t.code));
    if (news.length) toast(news);
    // The open ticket got another report: show the new photo and text without a click.
    if (S.selected && news.some((n) => n.t.code === S.selected)) select(S.selected);
    fill($("outbox"), ...(o.items.length ? o.items.slice(0, 40).map((x) => el("li", {}, x.message,
      el("small", {}, `${x.channel} to ${x.recipient} at ${fmtDate(x.at)}`))) : [el("li", { class: "hint" }, "No messages yet.")]));
    setLive(true, `Live. Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`);
  })();
  try { return await S.busy; } finally { S.busy = null; }
}

// Checks every few seconds; reloads only when something actually changed.
async function poll() {
  if (!S.pin || document.hidden) return;
  try {
    const c = await call("/api/staff/changes");
    if (c.version !== S.version || Date.now() - S.lastFull > FULL_MS) await refresh();
    else setLive(true, $("live-text").textContent.startsWith("Live") ? $("live-text").textContent : "Live");
  } catch (e) {
    if (e.status === 401) return;
    setLive(false, "Can't reach the server. Retrying… Check the app is still running on the laptop.");
  }
}

async function boot() {
  S.cfg = await api("/api/config");
  $("gate").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("gate-error").textContent = "";
    try { await signIn($("pin").value.trim()); } catch (err) { $("gate-error").textContent = err.status === 401 ? "That PIN is not right." : err.message; }
  });
  document.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", async () => {
    S.filter = b.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    await refresh();
  }));
  let armed = false;
  $("reset").addEventListener("click", async () => {
    if (!armed) { armed = true; $("reset").textContent = "Tap again to delete everything"; $("reset-hint").textContent = "This removes all tickets, reports and photos."; setTimeout(() => { armed = false; $("reset").textContent = "Clear all demo data"; $("reset-hint").textContent = ""; }, 5000); return; }
    armed = false;
    await call("/api/staff/reset", { method: "POST" });
    S.selected = null;
    fill($("detail"), el("p", { class: "empty" }, "All demo data cleared."));
    $("reset").textContent = "Clear all demo data"; $("reset-hint").textContent = "";
    await refresh();
  });
  const saved = sget("tf_pin");
  if (saved) { try { await signIn(saved); } catch (_) { signOut(); } } else { $("gate").hidden = false; $("pin").focus(); }
  setInterval(poll, POLL_MS);
  // Coming back to the tab (or the laptop waking up) catches up straight away.
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { document.title = "TownshipFix staff"; poll(); } });
  window.addEventListener("focus", poll);
}

boot().catch((e) => { document.body.prepend(el("p", { class: "error" }, e.message)); });
