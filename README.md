# Fuel Route Planner API (Django)

`GET /api/route/?start=<address or lat,lng>&finish=<address or lat,lng>[&format=html]`

Returns the driving route (GeoJSON), the cost-optimal fuel stops, gallons and cost per stop, and the
total fuel cost. `format=html` returns a Leaflet map page of the route with the fuel stops marked.

## Run
```
pip install -r requirements.txt
python manage.py prepare_stations      # one-off, offline; builds data/stations.csv
python manage.py runserver
# example (no geocoding call, one OSRM call):
curl "http://127.0.0.1:8000/api/route/?start=34.0522,-118.2437&finish=40.7128,-74.0060"
python manage.py test
```

## How it works
1. **Station data** (`prepare_stations`): keeps US rows only (the file also has Canadian provinces),
   keeps the lowest price per truckstop ID (the file repeats IDs with different prices), and attaches
   city-centroid coordinates from `data/us_cities.csv`. Done once, so requests never geocode.
2. **Routing**: exactly one OSRM call per request when `lat,lng` is passed. Address input adds one
   Nominatim call per address (cached). Results are cached per start/finish pair.
3. **Stations on the route**: a KD-tree finds the nearest route vertex for each station; stations
   within 10 miles of the route are kept and given a mile marker along the route.
4. **Optimisation** (`routing/planner.py`): classic greedy refuelling. At each stop, if a cheaper
   stop is reachable within 500 miles, buy only enough to get there; otherwise fill up and go to the
   cheapest stop ahead. Checked against a dynamic-programming optimum on random cases.
5. **Cost**: gallons = miles / 10, cost = gallons bought x that stop's price.

## Assumptions (state these in the Loom)
- The vehicle starts with a full 500-mile tank; that initial fuel is not billed.
- Station coordinates are city-level, so the 10-mile corridor is a tolerance, not exact.
- If any gap between usable stations exceeds 500 miles the API returns HTTP 422.
