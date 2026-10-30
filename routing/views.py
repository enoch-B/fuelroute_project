import json

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from .geo import GeoError, get_route, resolve_point
from .planner import NoFeasiblePlan, Stop, plan_fuel_stops
from .stations import stations_along_route

MAP_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Fuel route</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>html,body,#map{height:100%;margin:0}
#info{position:absolute;z-index:1000;top:10px;right:10px;background:#fff;padding:10px 14px;
border-radius:8px;font:14px sans-serif;box-shadow:0 1px 6px #0004}</style></head><body>
<div id="map"></div><div id="info"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const data = __DATA__;
const map = L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: '&copy; OpenStreetMap'}).addTo(map);
const line = L.geoJSON(data.route, {style: {color: '#1a73e8', weight: 5}}).addTo(map);
map.fitBounds(line.getBounds());
const c = data.route.coordinates;
L.marker([c[0][1], c[0][0]]).addTo(map).bindPopup('Start');
L.marker([c[c.length-1][1], c[c.length-1][0]]).addTo(map).bindPopup('Finish');
data.fuel_stops.forEach((s, i) => L.circleMarker([s.lat, s.lng], {radius: 9, color: '#d93025', fillOpacity: .9})
  .addTo(map).bindPopup(`<b>${i+1}. ${s.name}</b><br>${s.address}, ${s.city}, ${s.state}<br>
  Mile ${s.mile_marker}<br>$${s.price_per_gallon}/gal &times; ${s.gallons_purchased} gal = $${s.cost}`));
document.getElementById('info').innerHTML = `<b>${data.total_distance_miles} mi</b><br>
  Fuel cost: <b>$${data.total_fuel_cost}</b><br>Stops: ${data.fuel_stops.length}`;
</script></body></html>"""


@require_GET
def route_plan(request):
    start_q, finish_q = request.GET.get("start"), request.GET.get("finish")
    if not start_q or not finish_q:
        return JsonResponse({"error": "Provide both 'start' and 'finish' "
                             "(address or 'lat,lng') query parameters."}, status=400)

    cache_key = f"plan:{start_q.strip().lower()}|{finish_q.strip().lower()}"
    result = cache.get(cache_key)
    if result is None:
        try:
            start, finish = resolve_point(start_q), resolve_point(finish_q)
            coords, miles, geometry = get_route(start, finish)
        except GeoError as e:
            return JsonResponse({"error": str(e)}, status=404)
        except requests.RequestException as e:
            return JsonResponse({"error": f"Map service unavailable: {e}"}, status=502)

        found = stations_along_route(coords, miles, settings.CORRIDOR_MILES)
        stops = [Stop(mile=m, price=row["price"], ref=(row, off)) for row, m, off in found]
        try:
            purchases, total = plan_fuel_stops(
                stops, miles, settings.VEHICLE_RANGE_MILES, settings.VEHICLE_MPG)
        except NoFeasiblePlan as e:
            return JsonResponse({"error": str(e)}, status=422)

        result = {
            "start": {"lat": start[0], "lng": start[1]},
            "finish": {"lat": finish[0], "lng": finish[1]},
            "total_distance_miles": round(miles, 1),
            "assumptions": {
                "range_miles": settings.VEHICLE_RANGE_MILES,
                "mpg": settings.VEHICLE_MPG,
                "starts_with_full_tank": True,
                "station_search_corridor_miles": settings.CORRIDOR_MILES,
            },
            "fuel_stops": [{
                "name": p["stop"].ref[0]["name"],
                "address": p["stop"].ref[0]["address"],
                "city": p["stop"].ref[0]["city"],
                "state": p["stop"].ref[0]["state"],
                "lat": float(p["stop"].ref[0]["lat"]),
                "lng": float(p["stop"].ref[0]["lng"]),
                "mile_marker": round(p["stop"].mile, 1),
                "price_per_gallon": round(float(p["stop"].price), 3),
                "gallons_purchased": round(p["gallons"], 2),
                "cost": round(p["cost"], 2),
            } for p in purchases],
            "total_gallons_purchased": round(sum(p["gallons"] for p in purchases), 2),
            "total_fuel_cost": round(total, 2),
            "route": geometry,
        }
        cache.set(cache_key, result, 60 * 60)

    if request.GET.get("format") == "html":
        return HttpResponse(MAP_HTML.replace("__DATA__", json.dumps(result)))
    return JsonResponse(result)

def thin(geometry, max_points=1500):
    c = geometry["coordinates"]
    step = max(1, len(c) // max_points)
    out = c[::step]
    if out[-1] != c[-1]:
        out.append(c[-1])
    return {"type": "LineString", "coordinates": out}