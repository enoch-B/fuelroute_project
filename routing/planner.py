"""Pure fuel-stop optimisation (no Django, no network) so it is easy to test."""
from dataclasses import dataclass


@dataclass
class Stop:
    mile: float          # distance from start along the route
    price: float         # $/gallon
    ref: object = None   # caller's station record


class NoFeasiblePlan(Exception):
    pass


def plan_fuel_stops(stations, total_miles, tank_miles=500.0, mpg=10.0):
    """Greedy cheapest-fuel plan.

    Assumes the vehicle starts with a FULL tank (that initial fuel is not billed)
    and may arrive at the destination with fuel left over.

    stations: list[Stop] along the route, any order.
    Returns (purchases, total_cost) where purchases is a list of
    {"stop": Stop, "gallons": float, "cost": float}.
    """
    dest = Stop(total_miles, 0.0, "destination")   # free "station": always the cheapest
    nodes = sorted((s for s in stations if s.mile < total_miles), key=lambda s: s.mile)
    nodes.append(dest)
    mile, fuel = 0.0, tank_miles          # fuel is measured in miles of range
    price_here = float("inf")             # the start is not a station: nothing can be bought
    buys = {}                             # id(stop) -> [stop, miles of range bought]
    order = []

    def buy(stop, miles_of_range):
        if miles_of_range <= 1e-9:
            return
        key = id(stop)
        if key not in buys:
            buys[key] = [stop, 0.0]
            order.append(key)
        buys[key][1] += miles_of_range

    current = None
    while current is not dest:
        reach = tank_miles if current is not None else fuel   # cannot buy at the start
        in_range = [s for s in nodes if mile < s.mile <= mile + reach + 1e-9]
        if not in_range:
            raise NoFeasiblePlan(
                f"No fuel station within {tank_miles:.0f} miles after mile {mile:.0f}")

        cheaper = next((s for s in in_range if s.price < price_here), None)
        if current is None:
            # Nothing is bought at the start: drive to the cheapest reachable stop.
            nxt = min(in_range, key=lambda s: (s.price, -s.mile))
            fuel -= nxt.mile - mile
        elif cheaper is not None:
            # Buy only enough here to reach the next cheaper stop (or the destination).
            need = cheaper.mile - mile
            buy(current, max(0.0, need - fuel))
            fuel = max(fuel, need) - need
            nxt = cheaper
        else:
            # Nothing cheaper in range: fill up, then go to the cheapest stop ahead.
            buy(current, tank_miles - fuel)
            fuel = tank_miles
            nxt = min(in_range, key=lambda s: (s.price, -s.mile))
            fuel -= nxt.mile - mile
        mile, current, price_here = nxt.mile, nxt, nxt.price

    purchases, total = [], 0.0
    for key in order:
        stop, miles_bought = buys[key]
        gallons = miles_bought / mpg
        cost = gallons * stop.price
        total += cost
        purchases.append({"stop": stop, "gallons": gallons, "cost": cost})
    return purchases, total
