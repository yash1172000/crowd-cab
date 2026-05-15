import csv
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
QTC_LAT = -27.525518
QTC_LNG = 153.007202
EARTH_RADIUS_KM = 6371
TARGET_GENERATED_ROWS = 150

FIELDS = [
    "venue_id",
    "pickup_point_id",
    "label",
    "suburb",
    "street",
    "latitude",
    "longitude",
    "candidate_pickup_point",
    "source_dataset",
    "official_event_role",
    "nearby_road_count",
    "nearby_major_road_count",
    "nearby_crossing_count",
    "nearby_signal_count",
    "access_complexity_score",
    "distance_to_venue_km",
    "complexity_band",
    "walk_band",
    "safety_score",
    "accessibility_score",
    "driver_access_score",
    "base_congestion_score",
    "notes",
]


def km_between(a_lat, a_lng, b_lat, b_lng):
    dlat = math.radians(b_lat - a_lat)
    dlng = math.radians(b_lng - a_lng)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a_lat))
        * math.cos(math.radians(b_lat))
        * math.sin(dlng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def slug(value):
    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return "_".join(part for part in text.split("_") if part)[:40] or "pickup"


def walk_band(distance_km):
    if distance_km < 0.25:
        return "under-250m"
    if distance_km < 0.5:
        return "250m-500m"
    if distance_km <= 1:
        return "500m-1km"
    if distance_km <= 1.5:
        return "1-1.5km"
    return "1.5-2km"


def complexity_band(value):
    if value < 110:
        return "Low"
    if value < 160:
        return "Medium"
    if value < 220:
        return "High"
    return "Very High"


def approximate_suburb(lat, lng):
    if lng < 153.005 or lat < -27.527:
        return "Tennyson"
    return "Yeerongpilly"


def fetch_osm_roads():
    quote = '"'
    query = (
        "[out:json][timeout:30];"
        "(way(around:2000,-27.525518,153.007202)["
        + quote
        + "highway"
        + quote
        + "];"
        "node(around:2000,-27.525518,153.007202)["
        + quote
        + "highway"
        + quote
        + "="
        + quote
        + "traffic_signals"
        + quote
        + "];"
        "node(around:2000,-27.525518,153.007202)["
        + quote
        + "highway"
        + quote
        + "="
        + quote
        + "crossing"
        + quote
        + "];);out geom;"
    )
    request = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "CrowdCab local QTC research"},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read())


def build_candidates(osm):
    allowed = {"residential", "tertiary", "secondary", "primary", "unclassified", "service", "living_street"}
    major = {"tertiary", "secondary", "primary", "trunk"}
    ways = []
    road_points = []
    crossings = []
    signals = []

    for element in osm.get("elements", []):
        if element.get("type") == "node":
            tags = element.get("tags") or {}
            point = (float(element["lat"]), float(element["lon"]))
            if tags.get("highway") == "traffic_signals":
                signals.append(point)
            if tags.get("highway") == "crossing":
                crossings.append(point)
            continue

        if element.get("type") != "way":
            continue

        tags = element.get("tags") or {}
        highway = tags.get("highway", "")
        geometry = element.get("geometry") or []
        if highway not in allowed or not geometry:
            continue

        points = [(float(point["lat"]), float(point["lon"])) for point in geometry]
        name = tags.get("name") or f"Unnamed {highway.title()} Road"
        ways.append({"id": element.get("id"), "name": name, "highway": highway, "points": points})
        road_points.extend([(lat, lng, highway) for lat, lng in points])

    candidates = []
    seen = []
    for way in ways:
        samples = []
        last = None
        accumulated = 0
        for point in way["points"]:
            if last is None:
                last = point
                samples.append(point)
                continue
            accumulated += km_between(last[0], last[1], point[0], point[1])
            last = point
            if accumulated >= 0.12:
                samples.append(point)
                accumulated = 0

        for point in samples:
            distance = km_between(QTC_LAT, QTC_LNG, point[0], point[1])
            if distance > 2:
                continue
            if any(km_between(point[0], point[1], other[0], other[1]) < 0.09 for other in seen):
                continue
            seen.append(point)

            nearby_roads = sum(1 for lat, lng, _ in road_points if km_between(point[0], point[1], lat, lng) <= 0.25)
            nearby_major = sum(
                1 for lat, lng, highway in road_points
                if highway in major and km_between(point[0], point[1], lat, lng) <= 0.35
            )
            nearby_crossings = sum(1 for lat, lng in crossings if km_between(point[0], point[1], lat, lng) <= 0.25)
            nearby_signals = sum(1 for lat, lng in signals if km_between(point[0], point[1], lat, lng) <= 0.25)

            road_class = way["highway"]
            major_bonus = 18 if road_class in {"secondary", "tertiary"} else 8 if road_class == "primary" else 0
            service_penalty = 18 if road_class == "service" else 0
            distance_penalty = max(0, distance - 1)
            complexity = round(
                95
                + nearby_signals * 12
                + nearby_crossings * 4
                + nearby_major * 5
                + service_penalty
                + distance_penalty * 35,
                1,
            )
            safety = max(
                45,
                min(94, 86 - nearby_signals * 2.5 - nearby_crossings - (8 if road_class == "primary" else 0) - distance_penalty * 8),
            )
            accessibility = max(42, min(94, 88 - distance * 12 - nearby_crossings * 0.8 - (10 if road_class == "service" else 0)))
            driver_access = max(
                35,
                min(96, 58 + min(nearby_roads, 35) * 0.8 + min(nearby_major, 12) * 2.2 + major_bonus - service_penalty - nearby_signals * 1.8),
            )
            congestion = max(35, min(90, 76 - nearby_signals * 3 - nearby_major * 1.4 - (7 if road_class == "primary" else 0)))

            candidates.append(
                {
                    "point": point,
                    "distance": distance,
                    "name": way["name"],
                    "highway": road_class,
                    "nearby_roads": nearby_roads,
                    "nearby_major": nearby_major,
                    "nearby_crossings": nearby_crossings,
                    "nearby_signals": nearby_signals,
                    "complexity": complexity,
                    "safety": round(safety, 1),
                    "accessibility": round(accessibility, 1),
                    "driver_access": round(driver_access, 1),
                    "congestion": round(congestion, 1),
                }
            )

    candidates.sort(key=lambda item: (item["distance"] > 1, item["distance"], -item["driver_access"], item["name"]))
    return candidates[:TARGET_GENERATED_ROWS], {
        "ways": len(ways),
        "crossings": len(crossings),
        "signals": len(signals),
        "candidate_pool": len(candidates),
    }


def candidate_to_row(candidate, index):
    lat, lng = candidate["point"]
    suburb = approximate_suburb(lat, lng)
    label = f"{candidate['name'].upper()} QTC CANDIDATE {index:03d} | {suburb.upper()}"
    return {
        "venue_id": "queensland_tennis_centre",
        "pickup_point_id": f"qtc_osm_{index:03d}_{slug(candidate['name'])}",
        "label": label,
        "suburb": suburb,
        "street": candidate["name"],
        "latitude": f"{lat:.6f}",
        "longitude": f"{lng:.6f}",
        "candidate_pickup_point": "1",
        "source_dataset": "osm_qtc_road_candidates",
        "official_event_role": "raw_road_candidate",
        "nearby_road_count": candidate["nearby_roads"],
        "nearby_major_road_count": candidate["nearby_major"],
        "nearby_crossing_count": candidate["nearby_crossings"],
        "nearby_signal_count": candidate["nearby_signals"],
        "access_complexity_score": candidate["complexity"],
        "distance_to_venue_km": round(candidate["distance"], 3),
        "complexity_band": complexity_band(candidate["complexity"]),
        "walk_band": walk_band(candidate["distance"]),
        "safety_score": candidate["safety"],
        "accessibility_score": candidate["accessibility"],
        "driver_access_score": candidate["driver_access"],
        "base_congestion_score": candidate["congestion"],
        "notes": (
            "Generated from OpenStreetMap road geometry within 2 km of Queensland Tennis Centre. "
            f"Road class: {candidate['highway']}. Requires final human review before becoming a preferred pickup."
        ),
    }


def main():
    path = DATA_DIR / "venue_pickup_points.csv"
    existing = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    manual_rows = [row for row in existing if row.get("source_dataset") != "osm_qtc_road_candidates"]
    candidates, stats = build_candidates(fetch_osm_roads())
    generated_rows = [candidate_to_row(candidate, index) for index, candidate in enumerate(candidates, start=1)]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(manual_rows + generated_rows)

    print(f"manual rows: {len(manual_rows)}")
    print(f"generated qtc rows: {len(generated_rows)}")
    print(f"total csv rows: {len(manual_rows) + len(generated_rows)}")
    print(f"osm ways: {stats['ways']}")
    print(f"osm crossings: {stats['crossings']}")
    print(f"osm signals: {stats['signals']}")
    print(f"candidate pool before limit: {stats['candidate_pool']}")


if __name__ == "__main__":
    main()
