"""In-memory station index. Loaded once per process, so requests never touch a DB."""
import functools
import math
from pathlib import Path

import numpy as np
import pandas as pd
from django.conf import settings

MILES_PER_DEG_LAT = 69.0


@functools.lru_cache(maxsize=1)
def load_stations():
    df = pd.read_csv(Path(settings.BASE_DIR) / "data" / "stations.csv")
    return df.reset_index(drop=True)


def project(lat, lng, lat0):
    """Equirectangular projection to miles; accurate enough for a ~10 mile corridor."""
    x = np.asarray(lng) * math.cos(math.radians(lat0)) * MILES_PER_DEG_LAT
    y = np.asarray(lat) * MILES_PER_DEG_LAT
    return np.column_stack([x, y])


def stations_along_route(coords, route_miles, corridor):
    """coords: Nx2 array of (lat, lng) route vertices; route_miles: OSRM total distance.

    Returns list of (station_row_dict, mile_marker, offset_miles) within `corridor`
    miles of the route line.
    """
    from scipy.spatial import cKDTree

    df = load_stations()
    lat, lng = coords[:, 0], coords[:, 1]

    # Cumulative distance along the line, scaled to OSRM's reported total.
    lat0 = float(lat.mean())
    pts = project(lat, lng, lat0)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    cum *= route_miles / cum[-1] if cum[-1] > 0 else 1.0

    # Cheap bounding-box prefilter, then nearest route vertex via a KD-tree.
    pad = corridor / MILES_PER_DEG_LAT * 1.5
    box = df[(df.lat.between(lat.min() - pad, lat.max() + pad)) &
             (df.lng.between(lng.min() - pad * 2, lng.max() + pad * 2))]
    if box.empty:
        return []
    tree = cKDTree(pts)
    dist, idx = tree.query(project(box.lat.values, box.lng.values, lat0))
    keep = dist <= corridor
    out = []
    for row, d, i in zip(box[keep].to_dict("records"), dist[keep], idx[keep]):
        out.append((row, float(cum[i]), float(d)))
    return out
