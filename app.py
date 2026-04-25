"""
Route Optimizer - Flask Web App
================================
Run with: python app.py
Then open: http://localhost:5000
"""

import os
import urllib.parse
from datetime import datetime
from typing import List

from flask import Flask, render_template, request, jsonify
import googlemaps

app = Flask(__name__)

API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")


def build_matrix(client, locations: List[str]) -> List[List[float]]:
    result = client.distance_matrix(
        origins=locations,
        destinations=locations,
        mode="driving",
        departure_time=datetime.now(),
        units="metric",
    )
    n = len(locations)
    matrix = [[float("inf")] * n for _ in range(n)]
    for i, row in enumerate(result["rows"]):
        for j, element in enumerate(row["elements"]):
            if element["status"] == "OK":
                matrix[i][j] = element["distance"]["value"]
    return matrix


def nearest_neighbor(matrix: List[List[float]], start: int = 0) -> List[int]:
    unvisited = set(range(len(matrix)))
    route = [start]
    unvisited.remove(start)
    while unvisited:
        current = route[-1]
        nearest = min(unvisited, key=lambda j: matrix[current][j])
        route.append(nearest)
        unvisited.remove(nearest)
    return route


def two_opt(route: List[int], matrix: List[List[float]]) -> List[int]:
    best = route[:]
    best_dist = sum(matrix[best[i]][best[(i + 1) % len(best)]] for i in range(len(best)))
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 1):
            for j in range(i + 1, len(best)):
                new_route = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                new_dist = sum(matrix[new_route[k]][new_route[(k + 1) % len(new_route)]] for k in range(len(new_route)))
                if new_dist < best_dist - 1:
                    best, best_dist = new_route[:], new_dist
                    improved = True
    return best


def build_maps_url(ordered: List[str]) -> str:
    origin      = urllib.parse.quote(ordered[0])
    destination = urllib.parse.quote(ordered[-1])
    waypoints   = "|".join(urllib.parse.quote(loc) for loc in ordered[1:-1])
    return (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin}"
        f"&destination={destination}"
        f"&waypoints={waypoints}"
        f"&travelmode=driving"
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/optimize", methods=["POST"])
def optimize():
    data          = request.get_json()
    locations     = [l.strip() for l in data.get("locations", []) if l.strip()]
    start_index   = int(data.get("start_index", 0))
    fuel_type     = data.get("fuel_type", "gasoline")
    km_per_liter  = float(data.get("km_per_liter", 12))
    price_per_liter = float(data.get("price_per_liter", 61.30))

    if len(locations) < 2:
        return jsonify({"error": "Please enter at least 2 locations."}), 400

    if not API_KEY:
        return jsonify({"error": "GOOGLE_MAPS_API_KEY is not set."}), 500

    try:
        client  = googlemaps.Client(key=API_KEY)
        matrix  = build_matrix(client, locations)
        route   = two_opt(nearest_neighbor(matrix, start=start_index), matrix)

        total_metres = sum(
            matrix[route[i]][route[(i + 1) % len(route)]]
            for i in range(len(route))
        )
        total_km      = total_metres / 1000
        liters_needed = total_km / km_per_liter
        fuel_cost     = liters_needed * price_per_liter

        ordered = [locations[i] for i in route]
        maps_url = build_maps_url(ordered)

        # Build legs
        legs = []
        for step in range(len(route)):
            frm = route[step]
            to  = route[(step + 1) % len(route)]
            legs.append({
                "from": locations[frm],
                "to":   locations[to],
                "km":   round(matrix[frm][to] / 1000, 2),
            })

        return jsonify({
            "ordered_stops": ordered,
            "total_km":      round(total_km, 2),
            "liters_needed": round(liters_needed, 2),
            "fuel_cost":     round(fuel_cost, 2),
            "fuel_type":     fuel_type,
            "km_per_liter":  km_per_liter,
            "price_per_liter": price_per_liter,
            "maps_url":      maps_url,
            "legs":          legs,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
