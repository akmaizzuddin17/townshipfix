import { el } from "./common.js";

const validLocation = (p) => Number.isFinite(p.lat) && Number.isFinite(p.lng)
  && Math.abs(p.lat) <= 90 && Math.abs(p.lng) <= 180;
const priority = (band) => ["P0", "P1", "P2", "P3"].includes(band) ? band : "P3";

export function createTicketMap({ container, status, fitButton, styleButtons, imageryNote, onSelect, onOpen }) {
  let map, zones, tiles, bounds, lastFilter, tileErrors = 0;
  let activeStyle = "streets";
  try { if (sessionStorage.getItem("tf_map_style") === "satellite") activeStyle = "satellite"; } catch (_) {}
  const baseLayers = {};
  const markers = new Map();
  let shown = 0, missing = 0;

  function describe() {
    let text = tileErrors
      ? activeStyle === "satellite"
        ? "Satellite imagery could not load. Ticket pins still work; try Streets or check your internet connection."
        : "Street map could not load. Ticket pins still work; check your internet connection."
      : shown ? `${shown} ticket${shown === 1 ? "" : "s"} shown. Select a marker for details and photos.`
        : "No located tickets in this view. Sample township areas are shown.";
    if (missing) text += ` ${missing} ticket${missing === 1 ? " has" : "s have"} no map location.`;
    if (status.textContent !== text) status.textContent = text;
  }

  function updateStyleControls() {
    for (const button of styleButtons) button.setAttribute("aria-pressed", String(button.dataset.mapStyle === activeStyle));
    imageryNote.hidden = activeStyle !== "satellite";
  }

  function switchStyle(style) {
    if (!baseLayers[style] || style === activeStyle) return;
    activeStyle = style;
    tileErrors = 0;
    if (tiles) map.removeLayer(tiles);
    tiles = baseLayers[style];
    tiles.addTo(map);
    updateStyleControls();
    describe();
    try { sessionStorage.setItem("tf_map_style", style); } catch (_) {}
  }
  for (const button of styleButtons) button.addEventListener("click", () => switchStyle(button.dataset.mapStyle));
  updateStyleControls();

  function baseLayer(L, url, attribution) {
    const layer = L.tileLayer(url, { attribution, maxZoom: 19, referrerPolicy: "strict-origin-when-cross-origin" });
    // Ignore late requests from a layer that has already been switched off.
    layer.on("loading", () => { if (tiles === layer) tileErrors = 0; });
    layer.on("tileerror", () => { if (tiles === layer) { tileErrors++; describe(); } });
    layer.on("load", () => { if (tiles === layer) describe(); });
    return layer;
  }

  function fit() {
    if (map && bounds?.isValid()) {
      map.closePopup();
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 17, animate: false });
    }
  }
  fitButton.addEventListener("click", fit);

  function popup(t) {
    const content = el("div", { class: "ticket-popup" },
      el("strong", {}, `${t.code} · ${priority(t.priority_band)}`),
      el("p", {}, t.category_en),
      el("p", { class: "hint" }, `${t.landmark || "Pinned location"} · ${t.reporters} reporter${t.reporters === 1 ? "" : "s"}`));
    const photo = t.photos?.[0];
    if (photo) content.append(el("img", { src: `/media/${encodeURIComponent(photo)}`, alt: `${t.category_en}: resident photo` }));
    content.append(el("button", { type: "button", class: "btn primary", onclick: () => onOpen(t.code) }, "View ticket & photos"));
    return content;
  }

  function icon(t, selected) {
    const band = priority(t.priority_band);
    return window.L.divIcon({
      className: `ticket-marker ${band}${selected ? " is-selected" : ""}`,
      html: `<span>${band}</span>`, iconSize: [44, 44], iconAnchor: [22, 22], popupAnchor: [0, -20],
    });
  }

  return {
    showTicket(code) { markers.get(code)?.marker.openPopup(); },
    render(items, cfg, selected, filter, newCodes = []) {
      const L = window.L;
      if (!L) {
        status.textContent = "Map unavailable. Select a ticket from the queue to view its details and photos.";
        fitButton.disabled = true;
        for (const button of styleButtons) button.disabled = true;
        return;
      }
      const points = items.filter(validLocation);
      const areas = (cfg.zones || []).filter(validLocation);
      shown = points.length; missing = items.length - shown;
      bounds = L.latLngBounds((points.length ? points : areas).map((p) => [p.lat, p.lng]));
      if (!map) {
        map = L.map(container, {
          scrollWheelZoom: true, touchZoom: true, dragging: true, zoomControl: true,
          // Smaller zoom steps keep trackpad scrolling and phone pinches smooth.
          zoomSnap: 0.25, zoomDelta: 0.5, wheelPxPerZoomLevel: 120,
        });
        // Establish a view before markers are added so their keyboard targets exist.
        if (bounds.isValid()) fit();
        else map.setView([3.0721, 101.5182], 14);
        baseLayers.streets = baseLayer(L, cfg.map.tile_url, cfg.map.attribution);
        baseLayers.satellite = baseLayer(L, cfg.map.satellite_tile_url, cfg.map.satellite_attribution);
        // Only the chosen layer downloads tiles; changing layers keeps pins and the viewport.
        tiles = baseLayers[activeStyle];
        tiles.addTo(map);
        zones = L.layerGroup().addTo(map);
        for (const z of areas) {
          L.circleMarker([z.lat, z.lng], { radius: 4, color: "#0f5c45", weight: 1, fillOpacity: .25 })
            .bindTooltip(el("span", {}, z.name)).addTo(zones);
        }
        // Dashboard panels resize when a phone rotates or the sidebar changes width.
        new ResizeObserver(() => map.invalidateSize({ pan: false })).observe(container);
      }

      const visible = new Set(points.map((t) => t.code));
      for (const [code, entry] of markers) {
        if (!visible.has(code)) { entry.marker.remove(); markers.delete(code); }
      }
      for (const t of points) {
        const label = `${t.code} ${t.category_en}, ${priority(t.priority_band)}`;
        let entry = markers.get(t.code);
        if (!entry) {
          entry = { ticket: t };
          entry.marker = L.marker([t.lat, t.lng], { icon: icon(t, selected === t.code), title: label, alt: label })
            .bindPopup(popup(t), { maxWidth: 240 }).addTo(map);
          entry.marker.on("click", () => onSelect(entry.ticket.code));
          // Both keys select the ticket as well as opening Leaflet's popup.
          entry.marker.getElement().addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); entry.marker.openPopup(); onSelect(entry.ticket.code); }
          });
          markers.set(t.code, entry);
        }
        const signature = JSON.stringify([t.category_en, t.landmark, t.reporters, t.photos, t.priority_band]);
        if (entry.signature !== signature) {
          entry.marker.setPopupContent(popup(t));
          const node = entry.marker.getElement();
          node.title = label; node.setAttribute("aria-label", label);
          entry.signature = signature;
        }
        // Reuse each marker so polling preserves popups, focus and the user's viewport.
        const node = entry.marker.getElement();
        node.classList.remove("P0", "P1", "P2", "P3");
        node.classList.add(priority(t.priority_band));
        node.classList.toggle("is-selected", selected === t.code);
        node.setAttribute("aria-pressed", String(selected === t.code));
        node.firstElementChild.textContent = priority(t.priority_band);
        entry.marker.setLatLng([t.lat, t.lng]);
        entry.marker.setZIndexOffset(selected === t.code ? 1000 : 0);
        entry.ticket = t;
      }
      fitButton.disabled = !bounds.isValid();
      if (lastFilter !== filter) {
        if (bounds.isValid()) fit();
        else map.setView([3.0721, 101.5182], 14);
        lastFilter = filter;
      } else if (newCodes.length) {
        // A new report landed outside the part of the map on screen (e.g. a phone's real GPS
        // away from the sample township): widen the view so the new pin is visible.
        const view = map.getBounds();
        const offscreen = points.some((t) => newCodes.includes(t.code) && !view.contains([t.lat, t.lng]));
        if (offscreen && bounds.isValid()) fit();
      }
      describe();
    },
  };
}
