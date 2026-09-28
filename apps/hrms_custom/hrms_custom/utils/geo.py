"""Pure geofence math. Deliberately free of Frappe imports so it can be unit-tested in isolation."""

import math
from dataclasses import dataclass

EARTH_RADIUS_METERS = 6_371_008.8


@dataclass(frozen=True)
class Geofence:
	name: str
	latitude: float
	longitude: float
	radius_meters: float


@dataclass(frozen=True)
class GeofenceMatch:
	geofence: Geofence
	distance_meters: float
	is_within: bool


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	phi1, phi2 = math.radians(lat1), math.radians(lat2)
	d_phi = math.radians(lat2 - lat1)
	d_lambda = math.radians(lon2 - lon1)
	a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
	return 2 * EARTH_RADIUS_METERS * math.asin(min(1.0, math.sqrt(a)))


def validate_coordinates(latitude: float, longitude: float) -> None:
	if not (math.isfinite(latitude) and math.isfinite(longitude)):
		raise ValueError("Coordinates must be finite numbers")
	if not -90 <= latitude <= 90:
		raise ValueError("Latitude must be between -90 and 90")
	if not -180 <= longitude <= 180:
		raise ValueError("Longitude must be between -180 and 180")


def resolve_geofence(latitude: float, longitude: float, geofences: list[Geofence]) -> GeofenceMatch | None:
	"""Return the closest geofence containing the point; if none contains it, the closest overall.

	Returns None only when `geofences` is empty.
	"""
	best_inside: GeofenceMatch | None = None
	best_overall: GeofenceMatch | None = None

	for fence in geofences:
		distance = haversine_meters(latitude, longitude, fence.latitude, fence.longitude)
		match = GeofenceMatch(fence, distance, distance <= fence.radius_meters)
		if best_overall is None or distance < best_overall.distance_meters:
			best_overall = match
		if match.is_within and (best_inside is None or distance < best_inside.distance_meters):
			best_inside = match

	return best_inside or best_overall
