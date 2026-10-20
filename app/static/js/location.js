import { api, el, fill } from "./common.js";

// One candidate location at a time. Explicit choices invalidate pending GPS
// and searches, so a late response can never overwrite a resident's correction.
export function createLocationPicker({ cfg, t, onChange }) {
  const $ = (id) => document.getElementById(id);
  let value = null, confirmed = false, revision = 0, photo = null, explicit = false;
  let map = null, marker = null, accuracyCircle = null;

  function changed() { onChange(value, confirmed); }
  function coordinates() { return value ? `${value.lat.toFixed(6)}, ${value.lng.toFixed(6)}` : ""; }
  function render() {
    $("location-preview").hidden = !value;
    $("use-photo-location").hidden = !photo;
    $("loc-status").className = value ? "tag good" : "tag";
    const source = { photo_gps: "locPhoto", device_gps: "locDevice", zone: "locZone",
      address_search: "locAddress", map_pin: "locPin" };
    $("loc-status").textContent = value ? t(confirmed ? "locationConfirmed" : source[value.source]) : t("locNone");
    $("confirm-location").textContent = t(confirmed ? "locationConfirmed" : "confirmLocation");
    $("confirm-location").disabled = confirmed;
    $("location-label").textContent = value?.label || "";
    $("location-coordinates").textContent = value ? `${coordinates()}${value.accuracy != null ? ` · ${t("gpsAccuracy", Math.round(value.accuracy))}` : ""}` : "";
    if (value) showMap();
  }

  function choose(next, manual = true) {
    revision++;
    explicit = explicit || manual;
    value = next;
    confirmed = false;
    $("location-search-status").textContent = "";
    $("location-map-status").textContent = "";
    changed(); render();
  }

  function movePin(latlng) {
    if (!value) return;
    const lng = ((latlng.lng + 180) % 360 + 360) % 360 - 180;
    $("zone").value = "";
    choose({ lat: Math.max(-85, Math.min(85, latlng.lat)), lng,
      source: "map_pin", label: t("locPin"), accuracy: null });
  }

  function showMap() {
    if (!window.L) { $("location-map-status").textContent = t("mapUnavailable"); return; }
    if (!map) {
      map = L.map("location-map", { center: [value.lat, value.lng], zoom: 17, scrollWheelZoom: false });
      const tiles = L.tileLayer(cfg.map_tiles, { maxZoom: 19 });
      // Attribution is text, including when an operator configures another provider.
      const credit = L.control({ position: "bottomright" });
      credit.onAdd = () => {
        const div = L.DomUtil.create("div", "leaflet-control-attribution");
        const link = document.createElement("a");
        link.href = "https://www.openstreetmap.org/copyright";
        link.target = "_blank"; link.rel = "noopener";
        link.textContent = cfg.map_attribution;
        div.append(link);
        return div;
      };
      credit.addTo(map);
      tiles.on("tileerror", () => { $("location-map-status").textContent = t("mapUnavailable"); });
      tiles.addTo(map);
      marker = L.marker([value.lat, value.lng], { draggable: true,
        icon: L.divIcon({ className: "report-pin", html: "<span aria-hidden='true'>●</span>", iconSize: [32, 40], iconAnchor: [16, 36] }) }).addTo(map);
      marker.on("dragend", () => movePin(marker.getLatLng()));
      const pin = marker.getElement();
      pin.setAttribute("role", "button");
      pin.setAttribute("aria-label", t("pinLabel"));
      pin.addEventListener("keydown", (ev) => {
        const offsets = { ArrowUp: [0, -10], ArrowDown: [0, 10], ArrowLeft: [-10, 0], ArrowRight: [10, 0] };
        if (!offsets[ev.key]) return;
        ev.preventDefault(); ev.stopPropagation();
        const p = map.latLngToContainerPoint(marker.getLatLng());
        movePin(map.containerPointToLatLng(p.add(offsets[ev.key])));
      });
      map.on("click", (ev) => movePin(ev.latlng));
    }
    map.invalidateSize();
    marker.setLatLng([value.lat, value.lng]);
    marker.getElement().setAttribute("aria-label", t("pinLabel"));
    if (accuracyCircle) { map.removeLayer(accuracyCircle); accuracyCircle = null; }
    if (value.accuracy != null) accuracyCircle = L.circle([value.lat, value.lng], { radius: value.accuracy, weight: 1, color: "#d71920", interactive: false }).addTo(map);
    map.setView([value.lat, value.lng], map.getZoom() || 17);
  }

  function useGps() {
    explicit = true;
    const request = ++revision;
    confirmed = false; value = null;
    $("zone").value = "";
    $("location-query").value = "";
    fill($("location-results")); changed(); render();
    if (!window.isSecureContext) { $("loc-status").textContent = t("gpsHttp"); return; }
    if (!navigator.geolocation) { $("loc-status").textContent = t("gpsFail"); return; }
    $("loc-status").textContent = t("gpsWait");
    navigator.geolocation.getCurrentPosition((position) => {
      if (request !== revision) return;
      const { latitude, longitude, accuracy } = position.coords;
      choose({ lat: latitude, lng: longitude, accuracy, source: "device_gps", label: t("locDevice") });
    }, () => {
      if (request === revision) { $("loc-status").className = "tag warn"; $("loc-status").textContent = t("gpsFail"); }
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
  }

  async function search() {
    const query = $("location-query").value.trim();
    if (query.length < 3) { $("location-search-status").textContent = t("searchShort"); return; }
    const request = ++revision;
    value = null; confirmed = false; explicit = true; $("zone").value = "";
    changed(); render(); fill($("location-results"));
    $("location-search-status").textContent = t("searchingLocation");
    try {
      const result = await api(`/api/locations/search?q=${encodeURIComponent(query)}`);
      if (request !== revision) return;
      $("location-search-status").textContent = t(result.items.length ? "chooseResult" : result.unavailable ? "searchUnavailable" : "noLocations");
      fill($("location-results"), ...result.items.map((item) => el("li", {}, el("button", {
        type: "button", class: "location-result", onclick: () => {
          $("zone").value = item.zone || "";
          fill($("location-results"));
          choose({ lat: item.lat, lng: item.lng, source: item.source, label: item.label, accuracy: null });
        },
      }, item.label))));
    } catch (_) {
      if (request === revision) $("location-search-status").textContent = t("searchUnavailable");
    }
  }

  $("use-gps").addEventListener("click", useGps);
  $("search-location").addEventListener("click", search);
  $("location-query").addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); search(); } });
  $("location-query").addEventListener("input", () => {
    explicit = true; $("zone").value = ""; fill($("location-results")); choose(null);
  });
  $("zone").addEventListener("change", () => {
    const z = cfg.zones.find((item) => item.id === $("zone").value);
    $("location-query").value = ""; fill($("location-results"));
    choose(z ? { lat: z.lat, lng: z.lng, source: "zone", label: z.name, accuracy: null } : null);
  });
  $("use-photo-location").addEventListener("click", () => {
    $("zone").value = ""; $("location-query").value = ""; fill($("location-results")); choose(photo);
  });
  $("confirm-location").addEventListener("click", () => { if (value) { confirmed = true; changed(); render(); } });

  return {
    render,
    get confirmed() { return confirmed; },
    summary() { return value ? `${value.label} (${coordinates()})` : ""; },
    suggestPhoto(gps) {
      photo = gps ? { lat: gps.lat, lng: gps.lng, source: "photo_gps", label: t("locPhoto"), accuracy: null } : null;
      if (!explicit) choose(photo, false);
      else render();
    },
    reset() {
      revision++; value = null; photo = null; confirmed = false; explicit = false;
      $("zone").value = ""; $("location-query").value = "";
      fill($("location-results")); $("location-search-status").textContent = "";
      changed(); render();
    },
  };
}
