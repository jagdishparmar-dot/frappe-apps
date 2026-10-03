frappe.ui.form.on("Geofence Location", {
	refresh(frm) {
		draw_geofence_map(frm);
	},
	latitude(frm) {
		if (frm._geofence_writing) return;
		draw_geofence_map(frm);
	},
	longitude(frm) {
		if (frm._geofence_writing) return;
		draw_geofence_map(frm);
	},
	radius_meters(frm) {
		draw_geofence_map(frm);
	},
	location_name(frm) {
		draw_geofence_map(frm);
	},
});

function draw_geofence_map(frm) {
	const state = ensure_geofence_map(frm);
	if (!state) return;
	const defaults = frappe.utils.map_defaults;
	const point = map_point(frm.doc);
	const editable = frm.get_field("latitude").get_status() === "Write";

	state.map.off("click", state.on_click);
	state.on_click = (event) => write_map_point(frm, event.latlng);
	if (editable) state.map.on("click", state.on_click);

	if (!point) {
		if (state.marker) {
			state.map.removeLayer(state.marker);
			state.marker = null;
		}
		if (state.circle) {
			state.map.removeLayer(state.circle);
			state.circle = null;
		}
		state.map.setView(defaults.center, defaults.zoom);
		state.framed = false;
		fit_map(state.map);
		return;
	}

	if (!state.marker) {
		state.marker = L.marker(point, { draggable: editable }).addTo(state.map);
		state.marker.on("dragend", () => write_map_point(frm, state.marker.getLatLng()));
	} else {
		state.marker.setLatLng(point);
	}
	if (editable) state.marker.dragging.enable();
	else state.marker.dragging.disable();
	const title = frm.doc.location_name || __("Geofence");
	state.marker.bindPopup(frappe.utils.escape_html(title));

	const radius = Number(frm.doc.radius_meters);
	if (radius > 0) {
		if (!state.circle) {
			state.circle = L.circle(point, {
				radius,
				color: "#2490ef",
				weight: 2,
				fillColor: "#2490ef",
				fillOpacity: 0.15,
			}).addTo(state.map);
		} else {
			state.circle.setLatLng(point);
			state.circle.setRadius(radius);
		}
	} else if (state.circle) {
		state.map.removeLayer(state.circle);
		state.circle = null;
	}

	if (!state.framed) {
		if (state.circle) state.map.fitBounds(state.circle.getBounds(), { padding: [24, 24] });
		else state.map.setView(point, 16);
		state.framed = true;
	}
	fit_map(state.map);
}

function ensure_geofence_map(frm) {
	const field = frm.get_field("map");
	if (!field) return null;
	const existing = frm._geofence_map;
	if (existing && existing.el.isConnected) return existing;
	if (existing && existing.map) existing.map.remove();

	if (typeof L === "undefined" || !frappe.utils.map_defaults) {
		field.$wrapper.html(
			`<div class="text-muted" style="padding: 12px">${__("Map could not be loaded.")}</div>`
		);
		frm._geofence_map = null;
		return null;
	}

	field.$wrapper.html(
		`<div class="geofence-location-map" style="height: 420px; border: 1px solid var(--border-color); border-radius: 8px; z-index: 1;"></div>`
	);
	const el = field.$wrapper.find(".geofence-location-map").get(0);
	L.Icon.Default.imagePath = frappe.utils.map_defaults.image_path;
	const map = L.map(el);
	const tile = frappe.utils.map_defaults.tiles.default_tile;
	L.tileLayer(tile.url, tile.options).addTo(map);
	map.setView(frappe.utils.map_defaults.center, frappe.utils.map_defaults.zoom);
	frm._geofence_map = { map, el, marker: null, circle: null, framed: false, on_click: null };
	fit_map(map);
	return frm._geofence_map;
}

function write_map_point(frm, latlng) {
	if (frm.get_field("latitude").get_status() !== "Write") return;
	const latitude = Number(latlng.lat.toFixed(7));
	const longitude = Number(latlng.lng.toFixed(7));
	frm._geofence_writing = true;
	Promise.all([frm.set_value("latitude", latitude), frm.set_value("longitude", longitude)]).finally(() => {
		frm._geofence_writing = false;
		draw_geofence_map(frm);
	});
}

function map_point(doc) {
	const latitude = Number(doc.latitude);
	const longitude = Number(doc.longitude);
	if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
	if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null;
	return [latitude, longitude];
}

function fit_map(map) {
	setTimeout(() => map.invalidateSize(), 200);
}
