"""Build data/stations.csv: US-only, de-duplicated, with city-level coordinates.

Run once:  python manage.py prepare_stations
No network needed. Coordinates come from data/us_cities.csv (city centroids).
"""
import re
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

DATA = Path(settings.BASE_DIR) / "data"


def norm(s: str) -> str:
    s = str(s).lower().strip()
    s = re.sub(r"^(saint|st\.?)\s", "st ", s)
    s = re.sub(r"^(mount|mt\.?)\s", "mt ", s)
    s = re.sub(r"^(fort|ft\.?)\s", "ft ", s)
    return re.sub(r"[^a-z0-9 ]", "", s)


class Command(BaseCommand):
    help = "Geocode (city level) and clean the fuel price CSV into data/stations.csv"

    def handle(self, *args, **opts):
        fuel = pd.read_csv(DATA / "fuel-prices.csv")
        cities = pd.read_csv(DATA / "us_cities.csv")

        # Keep US states only (the file also contains Canadian provinces).
        fuel = fuel[fuel["State"].isin(set(cities["STATE_CODE"]))].copy()

        # One row per truckstop ID: the file repeats IDs with different prices,
        # so keep the lowest price (documented assumption).
        fuel = fuel.sort_values("Retail Price").drop_duplicates("OPIS Truckstop ID")

        cities["key"] = cities["STATE_CODE"] + "|" + cities["CITY"].map(norm)
        centroid = cities.drop_duplicates("key").set_index("key")[["LATITUDE", "LONGITUDE"]]
        fuel["key"] = fuel["State"] + "|" + fuel["City"].map(norm)
        fuel = fuel.join(centroid, on="key")

        missing = fuel["LATITUDE"].isna().sum()
        fuel = fuel.dropna(subset=["LATITUDE", "LONGITUDE"])

        out = fuel.rename(columns={
            "OPIS Truckstop ID": "id", "Truckstop Name": "name", "Address": "address",
            "City": "city", "State": "state", "Retail Price": "price",
            "LATITUDE": "lat", "LONGITUDE": "lng",
        })[["id", "name", "address", "city", "state", "price", "lat", "lng"]]
        out.to_csv(DATA / "stations.csv", index=False)
        self.stdout.write(self.style.SUCCESS(
            f"Wrote {len(out)} stations ({missing} skipped: city not found)"))
