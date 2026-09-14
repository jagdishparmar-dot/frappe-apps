from __future__ import annotations

import math

EARTH_RADIUS_M = 6371000


def _to_rad(deg: float) -> float:
	return (deg * math.pi) / 180


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	d_lat = _to_rad(lat2 - lat1)
	d_lon = _to_rad(lon2 - lon1)
	a = (
		math.sin(d_lat / 2) ** 2
		+ math.cos(_to_rad(lat1)) * math.cos(_to_rad(lat2)) * math.sin(d_lon / 2) ** 2
	)
	return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def is_inside_geofence(
	lat: float,
	lon: float,
	site_lat: float,
	site_lon: float,
	radius_meters: float,
) -> tuple[bool, float]:
	distance = distance_meters(lat, lon, site_lat, site_lon)
	return distance <= radius_meters, distance
