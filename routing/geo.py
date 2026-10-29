"""Calls to the free map APIs: OSRM for routing, Nominatim for addresses."""
import re

import numpy as np
import requests
from django.conf import settings
from django.core.cache import cache

HEADERS = {"User-Agent": "fuel-route-assessment/1.0"}
LATLNG = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class GeoError(Exception):
    pass


def resolve_point(text):
    """Accept 'lat,lng' (no API call) or an address (one Nominatim call, cached)."""
    m = LATLNG.match(text or "")
    if m:
        return float(m.group(1)), float(m.group(2))
    key = "geocode:" + (text or "").strip().lower()
    hit = cache.get(key)
    if hit:
        return hit
    r = requests.get(f"{settings.NOMINATIM_URL}/search", headers=HEADERS,
                     params={"q": text, "format": "json", "limit": 1, "countrycodes": "us"},
                     timeout=settings.HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise GeoError(f"Could not find a US location for '{text}'")
    point = (float(data[0]["lat"]), float(data[0]["lon"]))
    cache.set(key, point, 60 * 60 * 24)
    return point


def get_route(start, finish):
    """ONE OSRM call. Returns (Nx2 array of (lat, lng), distance in miles, GeoJSON geometry)."""
    url = (f"{settings.OSRM_URL}/route/v1/driving/"
           f"{start[1]},{start[0]};{finish[1]},{finish[0]}")
    r = requests.get(url, headers=HEADERS, timeout=settings.HTTP_TIMEOUT,
                     params={"overview": "full", "geometries": "geojson"})
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise GeoError("No driving route found between those locations")
    route = data["routes"][0]
    geometry = route["geometry"]
    coords = np.array([(lat, lng) for lng, lat in geometry["coordinates"]])
    return coords, route["distance"] / 1609.344, geometry
