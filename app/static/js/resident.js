import { api, el, fill, fmtDate, kerb, store, timeAgo, STATUS_STEPS } from "./common.js";
import { createLocationPicker } from "./location.js";

const T = {
  en: {
    brandCaption: "Neighbourhood care, made simple", residentServices: "RESIDENT SERVICES",
    issueHeading: "The issue", issueHint: "Show us what needs attention.", locationHint: "Help the team find the right spot.",
    moreDetails: "A few more details", optionalHint: "Optional · category, people affected and contact",
    reviewHint: "You can review everything before sending.", landmarkLabel: "Nearby landmark (optional)",
    hackathonCaption: "Sime Darby Property University Hackathon 2026 project",
    tabReport: "Report", tabMine: "My reports", tabTrack: "Track",
    title: "What needs fixing?", lede: "Take a photo or just tell us. We'll send it to the right team.",
    takePhoto: "Take a photo", photoOptional: "Optional, but it helps us find the spot",
    changePhoto: "Change photo", describe: "Describe it",
    describePh: "e.g. Streetlight broken in front of Block C, very dark at night",
    speak: "Speak instead", stop: "Stop", listening: "Listening… speak now",
    noVoice: "Voice input isn't available in this browser. Please type instead.",
    noVoiceHttp: "Voice needs a secure (https) link. Please type, or ask the organiser for the https link.",
    where: "Where is it?", locNone: "No location yet", useGps: "Use my current location", orArea: "Or pick the area",
    usePhotoLocation: "Use photo location", enterLocation: "Or enter the problem's location",
    locationHelp: "At the problem? Use GPS. Reporting later? Search for the place below.",
    locationPh: "Road, building or landmark", searchLocation: "Search",
    searchingLocation: "Searching…", chooseResult: "Select the correct place below.",
    searchShort: "Enter at least 3 characters to search.", noLocations: "No matching places. Try a road and township name, or choose an area below.",
    searchUnavailable: "Address search is unavailable. Choose an area below and adjust its pin, or try again shortly.",
    searchPrivacy: "Only your search text is shared with the map provider.",
    locAddress: "Location from address search", locPin: "Pin placed manually", locationConfirmed: "Location confirmed",
    confirmLocation: "Yes, the problem is here", needConfirmLoc: "Please confirm where the problem is on the location preview.",
    mapHelp: "Tap the map or drag the pin to the problem. You can also select the pin with Tab and move it with arrow keys.",
    mapUnavailable: "Map tiles could not load. Check the place name and coordinates, choose another area or try again online.",
    pinLabel: "Problem location pin. Use arrow keys to move it.", gpsAccuracy: (m) => `Phone accuracy: approximately ${m} m`,
    confirmedLocation: (s) => `Confirmed problem location: ${s}`, photoUploading: "Please wait for the photo to finish uploading.",
    chooseArea: "Choose an area", landmarkPh: "Nearby landmark (optional), e.g. Block C lift lobby",
    locPhoto: "Location from your photo", locDevice: "Location from your phone", locZone: "Area chosen",
    gpsWait: "Finding you…", gpsFail: "Couldn't get your location. Pick the area instead.",
    gpsHttp: "Your phone only shares location on a secure (https) link. Pick the area instead.",
    type: "Type of problem", suggested: "Suggested from your words",
    who: "Who does it affect?", behalf: "I'm reporting for someone else", behalfName: "Their name and unit",
    behalfPh: "e.g. Mak Cik Siti, C-3-2", contact: "Phone for updates (optional)",
    check: "Check my report", confirmTitle: "Is this right?", readAloud: "Read it aloud",
    edit: "Change something", send: "Send report", sending: "Sending…",
    needLoc: "Tell us where it is: use your location, a photo with location, or pick the area.",
    needWhat: "Add a photo or describe the problem.",
    existing: (code, n, why) => `Already reported by ${n} neighbour${n > 1 ? "s" : ""} (${code}). Your report will be added to it, which raises its priority. ${why}`,
    matchWhy: (m) => `(${[`${Math.round(m.distance_m)} m away`, m.same_type ? "same type of problem" : null, m.photo_match !== null ? `photo match ${m.photo_match}%` : null].filter(Boolean).join(", ")})`,
    possible: (code) => `Something similar is open nearby (${code}). Staff will check whether it's the same problem.`,
    emergency: "This sounds dangerous. Security will be alerted immediately. If anyone is in danger, call 999.",
    sentTitle: "Report sent. Your reference:",
    merged: (n) => `${n} residents have reported this problem. We added yours to the same job.`,
    newJob: (team) => `Sent to the ${team}.`,
    due: (d) => `Expected fix by ${d}`,
    seeMine: "See my reports", another: "Report another",
    mineTitle: "My reports", mineLede: "Saved on this phone. We'll ask you to check each repair.",
    mineEmpty: "No reports on this phone yet. Spotted something broken? Report it in under a minute.",
    reportNow: "Report a problem",
    steps: ["Received", "Assigned to team", "Being repaired", "Check the repair", "Closed"],
    checkFix: "The team says it's fixed. Is it?", before: "Your photo", after: "After repair",
    yesFixed: "Yes, it's fixed", notFixed: "No, still broken", why: "What's still wrong?",
    sendReopen: "Send back to team", confirmed: "Thanks! Closed.", reopened: "Sent back to the team.",
    reporters: (n) => `${n} resident${n > 1 ? "s" : ""} reported`,
    trackTitle: "Track a report", trackBtn: "Track", notFound: "No report with that reference.",
    closedBy: { resident_confirmed: "Confirmed fixed by a resident", auto_after_verified: "Repair verified (photo checked); no one objected in 3 days", supervisor_override: "Closed by a supervisor" },
    mergedInto: (c) => `Combined with ${c}`,
  },
  ms: {
    brandCaption: "Penjagaan kejiranan, lebih mudah", residentServices: "PERKHIDMATAN PENDUDUK",
    issueHeading: "Masalah", issueHint: "Tunjukkan perkara yang perlu dibaiki.", locationHint: "Bantu pasukan cari tempat yang betul.",
    moreDetails: "Sedikit maklumat tambahan", optionalHint: "Pilihan · kategori, orang terjejas dan telefon",
    reviewHint: "Anda boleh semak semuanya sebelum menghantar.", landmarkLabel: "Mercu tanda berdekatan (pilihan)",
    hackathonCaption: "Projek Sime Darby Property University Hackathon 2026",
    tabReport: "Lapor", tabMine: "Laporan saya", tabTrack: "Semak",
    title: "Apa yang perlu dibaiki?", lede: "Ambil gambar atau beritahu kami. Kami hantar kepada pasukan yang betul.",
    takePhoto: "Ambil gambar", photoOptional: "Pilihan, tetapi membantu kami cari tempatnya",
    changePhoto: "Tukar gambar", describe: "Terangkan",
    describePh: "cth. Lampu jalan rosak depan Blok C, gelap waktu malam",
    speak: "Cakap sahaja", stop: "Berhenti", listening: "Sedang mendengar… sila bercakap",
    noVoice: "Input suara tidak tersedia dalam pelayar ini. Sila taip.",
    noVoiceHttp: "Suara perlukan pautan selamat (https). Sila taip, atau minta pautan https.",
    where: "Di mana?", locNone: "Belum ada lokasi", useGps: "Guna lokasi semasa saya", orArea: "Atau pilih kawasan",
    usePhotoLocation: "Guna lokasi gambar", enterLocation: "Atau taip lokasi masalah",
    locationHelp: "Di tempat masalah? Guna GPS. Melapor kemudian? Cari tempatnya di bawah.",
    locationPh: "Jalan, bangunan atau mercu tanda", searchLocation: "Cari",
    searchingLocation: "Sedang mencari…", chooseResult: "Pilih tempat yang betul di bawah.",
    searchShort: "Taip sekurang-kurangnya 3 aksara untuk mencari.", noLocations: "Tiada tempat sepadan. Cuba nama jalan dan perbandaran, atau pilih kawasan di bawah.",
    searchUnavailable: "Carian alamat tidak tersedia. Pilih kawasan di bawah dan laraskan pin, atau cuba sebentar lagi.",
    searchPrivacy: "Hanya teks carian dikongsi dengan penyedia peta.",
    locAddress: "Lokasi daripada carian alamat", locPin: "Pin diletakkan secara manual", locationConfirmed: "Lokasi disahkan",
    confirmLocation: "Ya, masalah ada di sini", needConfirmLoc: "Sila sahkan tempat masalah pada pratonton lokasi.",
    mapHelp: "Sentuh peta atau seret pin ke tempat masalah. Anda juga boleh pilih pin dengan Tab dan gerakkannya dengan kekunci anak panah.",
    mapUnavailable: "Peta tidak dapat dimuatkan. Semak nama tempat dan koordinat, pilih kawasan lain atau cuba semula dalam talian.",
    pinLabel: "Pin lokasi masalah. Gunakan kekunci anak panah untuk menggerakkannya.", gpsAccuracy: (m) => `Ketepatan telefon: kira-kira ${m} m`,
    confirmedLocation: (s) => `Lokasi masalah yang disahkan: ${s}`, photoUploading: "Sila tunggu sehingga gambar selesai dimuat naik.",
    chooseArea: "Pilih kawasan", landmarkPh: "Mercu tanda berdekatan (pilihan), cth. lobi lif Blok C",
    locPhoto: "Lokasi daripada gambar", locDevice: "Lokasi daripada telefon", locZone: "Kawasan dipilih",
    gpsWait: "Mencari lokasi…", gpsFail: "Tidak dapat lokasi. Sila pilih kawasan.",
    gpsHttp: "Telefon hanya kongsi lokasi pada pautan selamat (https). Sila pilih kawasan.",
    type: "Jenis masalah", suggested: "Dicadangkan daripada kata-kata anda",
    who: "Siapa yang terjejas?", behalf: "Saya melapor bagi pihak orang lain", behalfName: "Nama dan unit mereka",
    behalfPh: "cth. Mak Cik Siti, C-3-2", contact: "Telefon untuk makluman (pilihan)",
    check: "Semak laporan saya", confirmTitle: "Betul ke?", readAloud: "Baca dengan kuat",
    edit: "Ubah sesuatu", send: "Hantar laporan", sending: "Menghantar…",
    needLoc: "Beritahu lokasinya: guna lokasi anda, gambar berlokasi, atau pilih kawasan.",
    needWhat: "Tambah gambar atau terangkan masalahnya.",
    existing: (code, n, why) => `Sudah dilaporkan oleh ${n} jiran (${code}). Laporan anda akan ditambah dan keutamaannya dinaikkan. ${why}`,
    matchWhy: (m) => `(${[`${Math.round(m.distance_m)} m dari sini`, m.same_type ? "jenis masalah sama" : null, m.photo_match !== null ? `gambar sepadan ${m.photo_match}%` : null].filter(Boolean).join(", ")})`,
    possible: (code) => `Ada laporan serupa berdekatan (${code}). Kakitangan akan semak sama ada ia masalah yang sama.`,
    emergency: "Ini nampak berbahaya. Pengawal keselamatan akan dimaklumkan segera. Jika ada yang dalam bahaya, hubungi 999.",
    sentTitle: "Laporan dihantar. Rujukan anda:",
    merged: (n) => `${n} penduduk telah melaporkan masalah ini. Laporan anda ditambah ke kerja yang sama.`,
    newJob: (team) => `Dihantar kepada ${team}.`,
    due: (d) => `Dijangka siap sebelum ${d}`,
    seeMine: "Lihat laporan saya", another: "Lapor lagi",
    mineTitle: "Laporan saya", mineLede: "Disimpan dalam telefon ini. Kami akan minta anda semak setiap pembaikan.",
    mineEmpty: "Belum ada laporan dalam telefon ini. Nampak sesuatu rosak? Lapor dalam masa kurang seminit.",
    reportNow: "Lapor masalah",
    steps: ["Diterima", "Diserahkan kepada pasukan", "Sedang dibaiki", "Semak pembaikan", "Ditutup"],
    checkFix: "Pasukan kata sudah dibaiki. Betul?", before: "Gambar anda", after: "Selepas dibaiki",
    yesFixed: "Ya, sudah elok", notFixed: "Belum, masih rosak", why: "Apa yang masih rosak?",
    sendReopen: "Hantar semula kepada pasukan", confirmed: "Terima kasih! Ditutup.", reopened: "Dihantar semula kepada pasukan.",
    reporters: (n) => `${n} penduduk melapor`,
    trackTitle: "Semak laporan", trackBtn: "Semak", notFound: "Tiada laporan dengan rujukan itu.",
    closedBy: { resident_confirmed: "Disahkan elok oleh penduduk", auto_after_verified: "Pembaikan disahkan (gambar disemak); tiada bantahan dalam 3 hari", supervisor_override: "Ditutup oleh penyelia" },
    mergedInto: (c) => `Digabungkan dengan ${c}`,
  },
};

const state = {
  lang: store.get("tf_lang", "en"), cfg: null, photo: null, loc: null, zone: "", category: null,
  suggested: null, flags: new Set(), flagsOff: new Set(), startedAt: null, analysis: null, sending: false,
};
let locationPicker;
let photoVersion = 0;
const $ = (id) => document.getElementById(id);
const t = (k, ...a) => { const v = T[state.lang][k]; return typeof v === "function" ? v(...a) : v; };

function touch() { if (!state.startedAt) state.startedAt = performance.now(); }

// ------------------------------------------------------------ language
function applyLang() {
  document.documentElement.lang = state.lang === "ms" ? "ms" : "en";
  document.querySelectorAll("[data-t]").forEach((n) => { const v = T[state.lang][n.dataset.t]; if (typeof v === "string") n.textContent = v; });
  document.querySelectorAll("[data-tp]").forEach((n) => { n.placeholder = T[state.lang][n.dataset.tp]; });
  document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === state.lang)));
  if (state.cfg) { renderCategories(); renderFlags(); }
  locationPicker?.render();
  if (state.photo) $("photo-drop").querySelector("img")?.setAttribute("alt", t("takePhoto"));
}

// ------------------------------------------------------------ tabs
function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  for (const p of ["report", "mine", "track"]) $(`pane-${p}`).hidden = p !== name;
  if (name === "mine") loadMine();
  window.scrollTo(0, 0);
}

// ------------------------------------------------------------ categories & flags
function renderCategories() {
  const box = $("categories");
  fill(box);
  for (const [id, c] of Object.entries(state.cfg.categories)) {
    const chosen = (state.category || state.suggested) === id;
    box.append(el("button", {
      type: "button", class: "chip" + (state.suggested === id && !state.category ? " suggested" : ""),
      "aria-pressed": String(chosen), "data-cat": id,
      onclick: () => { touch(); state.category = state.category === id ? null : id; renderCategories(); },
    }, c[state.lang]));
  }
}

function renderFlags() {
  const box = $("flags");
  fill(box);
  for (const [id, f] of Object.entries(state.cfg.flags)) {
    box.append(el("button", {
      type: "button", class: "chip", "aria-pressed": String(state.flags.has(id)), "data-flag": id,
      onclick: () => {
        touch();
        if (state.flags.has(id)) { state.flags.delete(id); state.flagsOff.add(id); }
        else { state.flags.add(id); state.flagsOff.delete(id); }
        renderFlags();
      },
    }, f[state.lang]));
  }
}

let suggestTimer;
function scheduleSuggest() {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(async () => {
    const text = $("text").value.trim();
    if (!text && !state.photo) { state.suggested = null; $("suggest-why").textContent = ""; renderCategories(); return; }
    try {
      const a = await api("/api/analyze", { method: "POST", json: { text, photo_ref: state.photo?.ref, lang: state.lang } });
      state.suggested = a.suggestion.category && a.suggestion.category !== "other" ? a.suggestion.category : null;
      const words = (a.suggestion.evidence || []).slice(0, 3).map((w) => `"${w}"`).join(", ");
      $("suggest-why").textContent = state.suggested ? `${t("suggested")}${words ? ": " + words : ""}` : "";
      for (const f of Object.keys(a.flags_detected || {})) if (!state.flagsOff.has(f)) state.flags.add(f);
      renderCategories(); renderFlags();
    } catch (_) { /* suggestion is a nice-to-have */ }
  }, 500);
}

// ------------------------------------------------------------ photo
async function onPhoto(file) {
  if (!file) return;
  touch();
  const version = ++photoVersion;
  state.photo = null;
  state.uploading = true;
  locationPicker.suggestPhoto(null);
  const drop = $("photo-drop");
  const url = URL.createObjectURL(file);
  drop.classList.add("has-photo");
  drop.querySelectorAll("svg, span").forEach((n) => n.toggleAttribute("hidden", true)); // works for SVG too
  drop.querySelector("img")?.remove();
  drop.prepend(el("img", { src: url, alt: t("takePhoto") }));
  const meta = $("photo-meta");
  fill(meta, el("span", { class: "tag" }, "…"));
  const fd = new FormData();
  fd.append("photo", file);
  try {
    const r = await api("/api/photos", { method: "POST", form: fd });
    if (version !== photoVersion) return;
    state.photo = r;
    locationPicker.suggestPhoto(r.gps);
    fill(meta, 
      el("span", { class: "tag good" }, state.lang === "ms" ? "Gambar dimuat naik" : "Photo uploaded"),
      r.privacy?.blurred ? el("span", { class: "tag" }, state.lang === "ms" ? `${r.privacy.blurred} wajah/plat dikaburkan` : `${r.privacy.blurred} face/plate blurred`) : null,
      el("span", { class: "tag" }, state.lang === "ms" ? "Data lokasi foto dibuang sebelum disimpan" : "Photo metadata removed before storing"),
    );
    scheduleSuggest();
  } catch (e) {
    if (version !== photoVersion) return;
    state.photo = null;
    fill(meta, el("span", { class: "tag bad" }, e.message));
  } finally { if (version === photoVersion) state.uploading = false; URL.revokeObjectURL(url); }
}

// ------------------------------------------------------------ voice
let recog = null;
function setupMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = $("mic");
  btn.addEventListener("click", () => {
    touch();
    if (!SR) { $("mic-status").textContent = window.isSecureContext ? t("noVoice") : t("noVoiceHttp"); return; }
    if (recog) { recog.stop(); return; }
    recog = new SR();
    recog.lang = state.lang === "ms" ? "ms-MY" : "en-MY";
    recog.interimResults = true;
    recog.continuous = false;
    const base = $("text").value.trim();
    recog.onresult = (ev) => {
      let said = "";
      for (const r of ev.results) said += r[0].transcript;
      $("text").value = (base ? base + " " : "") + said;
    };
    recog.onerror = (ev) => { $("mic-status").textContent = ev.error === "not-allowed" ? t("noVoiceHttp") : t("noVoice"); };
    recog.onend = () => {
      recog = null; btn.classList.remove("listening"); btn.setAttribute("aria-pressed", "false");
      btn.querySelector("span").textContent = t("speak");
      if ($("mic-status").textContent === t("listening")) $("mic-status").textContent = "";
      scheduleSuggest();
    };
    btn.classList.add("listening"); btn.setAttribute("aria-pressed", "true");
    btn.querySelector("span").textContent = t("stop");
    $("mic-status").textContent = t("listening");
    try { recog.start(); } catch (_) { recog = null; }
  });
}

function speak(text) {
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = state.lang === "ms" ? "ms-MY" : "en-MY";
  u.rate = 0.95;
  speechSynthesis.speak(u);
}

// ------------------------------------------------------------ check & send
function payload() {
  const p = {
    text: $("text").value.trim(), photo_ref: state.photo?.ref || null, lang: state.lang,
    category: state.category || state.suggested || null, flags: [...state.flags],
    landmark: [$("landmark").value.trim(), state.loc?.label].filter(Boolean).join("; ") || null, zone: state.zone || null,
    on_behalf_of: $("behalf-box").open ? $("behalf").value.trim() || null : null,
    contact: $("contact").value.trim() || null,
  };
  if (state.loc) Object.assign(p, { lat: state.loc.lat, lng: state.loc.lng, location_source: state.loc.source,
    location_accuracy_m: state.loc.accuracy });
  return p;
}

async function check() {
  const err = $("form-error");
  err.textContent = "";
  if (state.uploading) { err.textContent = t("photoUploading"); return; }
  const p = payload();
  if (!p.text && !p.photo_ref) { err.textContent = t("needWhat"); return; }
  if (!state.loc && !state.zone) { err.textContent = t("needLoc"); return; }
  if (!locationPicker.confirmed) { err.textContent = t("needConfirmLoc"); return; }
  const locationSummary = locationPicker.summary();
  $("check").disabled = true;
  try {
    const a = await api("/api/analyze", { method: "POST", json: p });
    if (!locationPicker.confirmed || locationPicker.summary() !== locationSummary) {
      err.textContent = t("needConfirmLoc"); return;
    }
    state.analysis = a;
    $("readback").textContent = a.readback;
    $("confirm-location-summary").textContent = t("confirmedLocation", locationSummary);
    const notes = $("confirm-notices");
    fill(notes);
    if (a.emergency?.length) notes.append(el("div", { class: "notice danger", role: "alert" }, t("emergency")));
    if (a.match.action === "merge" && a.match.ticket) {
      notes.append(el("div", { class: "notice" }, t("existing", a.match.ticket.code, a.match.ticket.reporters,
        a.match.distance_m !== null ? t("matchWhy", a.match) : "")));
    } else if (a.match.action === "suggest" && a.match.ticket) {
      notes.append(el("div", { class: "notice" }, t("possible", a.match.ticket.code)));
    }
    const img = $("confirm-photo");
    img.hidden = !state.photo;
    if (state.photo) img.src = state.photo.url;
    $("step-form").hidden = true;
    $("step-confirm").hidden = false;
    window.scrollTo(0, 0);
    $("send").focus();
  } catch (e) {
    err.textContent = e.message;
  } finally { $("check").disabled = false; }
}

async function send() {
  if (state.sending) return;
  if (!locationPicker.confirmed) { $("send-error").textContent = t("needConfirmLoc"); return; }
  state.sending = true;
  $("send").disabled = true;
  $("send").textContent = t("sending");
  $("send-error").textContent = "";
  const p = payload();
  p.category = state.category || state.analysis?.category || p.category;
  p.client_duration_ms = state.startedAt ? Math.round(performance.now() - state.startedAt) : null;
  try {
    const r = await api("/api/reports", { method: "POST", json: p });
    const mine = store.get("tf_reports", []);
    mine.unshift({ token: r.report_token, code: r.ticket.code, at: new Date().toISOString() });
    store.set("tf_reports", mine.slice(0, 50));
    $("done-code").textContent = r.ticket.code;
    $("done-msg").textContent = r.merged ? t("merged", r.reporters) : t("newJob", r.ticket.team);
    fill($("done-meta"), kerb(r.ticket.priority_band), " ", t("due", fmtDate(r.ticket.sla_due_at, state.lang)));
    $("step-confirm").hidden = true;
    $("step-done").hidden = false;
    window.scrollTo(0, 0);
  } catch (e) {
    $("send-error").textContent = e.message;
  } finally {
    state.sending = false;
    $("send").disabled = false;
    $("send").textContent = t("send");
  }
}

function resetForm() {
  photoVersion++;
  state.uploading = false;
  Object.assign(state, { photo: null, loc: null, zone: "", category: null, suggested: null, flags: new Set(), flagsOff: new Set(), startedAt: null, analysis: null });
  for (const id of ["text", "landmark", "behalf", "contact"]) $(id).value = "";
  $("zone").value = "";
  $("photo").value = "";
  $("behalf-box").open = false;
  $("optional-details").open = false;
  const drop = $("photo-drop");
  drop.classList.remove("has-photo");
  drop.querySelector("img")?.remove();
  drop.querySelectorAll("svg, span").forEach((n) => n.toggleAttribute("hidden", false));
  fill($("photo-meta"));
  $("suggest-why").textContent = "";
  $("form-error").textContent = "";
  locationPicker.reset();
  renderCategories(); renderFlags();
  $("step-done").hidden = true; $("step-confirm").hidden = true; $("step-form").hidden = false;
  window.scrollTo(0, 0);
}

// ------------------------------------------------------------ status views
function rail(ticket) {
  const idx = ticket.status === "merged" ? 0 : STATUS_STEPS.indexOf(ticket.status);
  return el("ol", { class: "rail" }, t("steps").map((label, i) =>
    el("li", { class: i < idx || ticket.status === "closed" ? "is-done" : i === idx ? "is-now" : "" },
      el("span", { class: "dot", "aria-hidden": "true" }, i < idx || ticket.status === "closed" ? "✓" : String(i + 1)),
      el("span", {}, label))));
}

function ticketCard(tk, token) {
  const cat = state.lang === "ms" ? tk.category_ms : tk.category_en;
  const card = el("article", { class: "card" },
    el("header", {}, el("span", { class: "plate" }, tk.code), kerb(tk.priority_band)),
    el("h2", { style: "margin:10px 0 2px" }, cat),
    el("p", { class: "hint", style: "margin:0" }, [tk.landmark, t("reporters", tk.reporters), timeAgo(tk.created_at, state.lang)].filter(Boolean).join(". ")),
    rail(tk));
  if (tk.status === "closed" && tk.close_reason) card.append(el("p", { class: "hint" }, t("closedBy")[tk.close_reason] || ""));
  if (tk.status === "awaiting_confirmation" && token) {
    const box = el("div", { class: "notice" }, el("strong", {}, t("checkFix")));
    box.append(el("div", { class: "pair" },
      tk.photos[0] ? el("figure", {}, el("img", { src: `/media/${tk.photos[0]}`, alt: t("before") }), el("figcaption", {}, t("before"))) : null,
      tk.after_photo ? el("figure", {}, el("img", { src: `/media/${tk.after_photo}`, alt: t("after") }), el("figcaption", {}, t("after"))) : null));
    const reason = el("textarea", { "aria-label": t("why"), placeholder: t("why"), hidden: true });
    const status = el("p", { class: "hint", "aria-live": "polite" });
    const yes = el("button", { type: "button", class: "btn primary", onclick: async () => {
      try { await api(`/api/tickets/${tk.code}/confirm`, { method: "POST", json: { token } }); status.textContent = t("confirmed"); setTimeout(loadMine, 600); }
      catch (e) { status.textContent = e.message; }
    } }, t("yesFixed"));
    const no = el("button", { type: "button", class: "btn danger", onclick: async () => {
      if (reason.hidden) { reason.hidden = false; no.textContent = t("sendReopen"); reason.focus(); return; }
      try { await api(`/api/tickets/${tk.code}/reopen`, { method: "POST", json: { token, reason: reason.value } }); status.textContent = t("reopened"); setTimeout(loadMine, 600); }
      catch (e) { status.textContent = e.message; }
    } }, t("notFixed"));
    box.append(reason, el("div", { class: "row", style: "flex-wrap:wrap;margin-top:8px" }, yes, no), status);
    card.append(box);
  }
  return card;
}

async function loadMine() {
  const list = $("mine-list");
  const mine = store.get("tf_reports", []);
  if (!mine.length) {
    fill(list, el("div", { class: "empty" }, el("p", {}, t("mineEmpty")),
      el("button", { type: "button", class: "btn primary", onclick: () => showTab("report") }, t("reportNow"))));
    return;
  }
  try {
    const r = await api("/api/my", { method: "POST", json: { tokens: mine.map((m) => m.token) } });
    // one card per problem, even if this phone reported it more than once
    const byCode = new Map();
    for (const i of r.items) if (!byCode.has(i.ticket.code)) byCode.set(i.ticket.code, i);
    fill(list, ...[...byCode.values()].map((i) => ticketCard(i.ticket, i.token)));
  } catch (e) { fill(list, el("p", { class: "error" }, e.message)); }
}

async function track(ev) {
  ev.preventDefault();
  const code = $("track-code").value.trim().toUpperCase();
  $("track-error").textContent = "";
  if (!code) return;
  try {
    const tk = await api(`/api/tickets/${encodeURIComponent(code)}`);
    const mine = store.get("tf_reports", []).find((m) => m.code === tk.code);
    fill($("track-result"), ticketCard(tk, mine?.token),
      tk.merged_into ? el("p", { class: "hint" }, t("mergedInto", tk.merged_into)) : "");
  } catch (e) {
    fill($("track-result"));
    $("track-error").textContent = e.status === 404 ? t("notFound") : e.message;
  }
}

// ------------------------------------------------------------ boot
async function boot() {
  state.cfg = await api("/api/config");
  for (const z of state.cfg.zones) $("zone").append(el("option", { value: z.id }, z.name));
  locationPicker = createLocationPicker({ cfg: state.cfg, t, onChange: (loc) => {
    if (loc) touch(); state.loc = loc; state.zone = $("zone").value;
  } });
  $("photo").addEventListener("change", (e) => onPhoto(e.target.files[0]));
  $("text").addEventListener("input", () => { touch(); scheduleSuggest(); });
  $("check").addEventListener("click", check);
  $("send").addEventListener("click", send);
  $("edit").addEventListener("click", () => { $("step-confirm").hidden = true; $("step-form").hidden = false; });
  $("speak-back").addEventListener("click", () => speak($("readback").textContent));
  $("new-report").addEventListener("click", resetForm);
  $("go-mine").addEventListener("click", () => { resetForm(); showTab("mine"); });
  $("track-form").addEventListener("submit", track);
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => {
    state.lang = b.dataset.lang; store.set("tf_lang", state.lang); applyLang();
    if (!$("pane-mine").hidden) loadMine();
  }));
  setupMic();
  applyLang();
  const code = new URLSearchParams(location.search).get("track");
  if (code) { showTab("track"); $("track-code").value = code; $("track-form").requestSubmit(); }
}

boot().catch((e) => { $("form-error").textContent = e.message; });
