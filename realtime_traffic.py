"""Realtime traffic providers for CrowdCab.

Default provider is free/open data:
- Brisbane City Council intersection volume
- Brisbane City Council intersection locations reference
- QLDTraffic GeoJSON events when a URL is configured

TomTom remains available only when REALTIME_PROVIDER=tomtom.
"""

from datetime import datetime, timezone
import logging
import math
import os
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")


def _load_dotenv(path=ENV_PATH):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

ENABLE_REALTIME_TRAFFIC = os.getenv("ENABLE_REALTIME_TRAFFIC", "true").lower() not in {"0", "false", "no", "off"}
REALTIME_PROVIDER = os.getenv("REALTIME_PROVIDER", "open_data").lower()
REALTIME_CACHE_SECONDS = int(os.getenv("REALTIME_CACHE_SECONDS", "120"))
SUNCORP_LAT = float(os.getenv("SUNCORP_LAT", "-27.4648"))
SUNCORP_LNG = float(os.getenv("SUNCORP_LNG", "153.0095"))
HTTP_TIMEOUT_SECONDS = 5

BRISBANE_TRAFFIC_VOLUME_URL = os.getenv(
    "BRISBANE_TRAFFIC_VOLUME_URL",
    "https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/traffic-data-at-intersection/records?limit=100",
)
BRISBANE_INTERSECTION_LOCATIONS_URL = os.getenv(
    "BRISBANE_INTERSECTION_LOCATIONS_URL",
    "https://data.brisbane.qld.gov.au/api/explore/v2.1/catalog/datasets/traffic-management-intersection-locations-reference/records?limit=100",
)
QLDTRAFFIC_GEOJSON_URL = os.getenv("QLDTRAFFIC_GEOJSON_URL", "").strip()
QLDTRAFFIC_API_KEY = os.getenv("QLDTRAFFIC_API_KEY", "").strip()
QLDTRAFFIC_EVENTS_ENDPOINT = os.getenv(
    "QLDTRAFFIC_EVENTS_ENDPOINT",
    "https://api.qldtraffic.qld.gov.au/v2/events",
).strip()

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "").strip()
TOMTOM_FLOW_ENDPOINT = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"

OPEN_DATA_SOURCES = [
    "Brisbane City Council Intersection Volume",
    "Brisbane City Council Intersection Locations",
    "QLDTraffic GeoJSON",
]

logger = logging.getLogger(__name__)

_cache = {
    "volume": {"timestamp": 0, "data": [], "fallback_reason": "not_fetched", "records": 0},
    "locations": {"timestamp": 0, "data": [], "fallback_reason": "not_fetched", "records": 0},
    "qldtraffic": {"timestamp": 0, "data": [], "fallback_reason": "not_configured", "records": 0},
    "live_intersections": {"timestamp": 0, "data": [], "joined_locations": 0, "near_suncorp": 0},
    "tomtom": {"timestamp": 0, "fallback_reason": "not_fetched", "flow_results": []},
}


def _now():
    return time.time()


def _fresh(key):
    ts = _cache.get(key, {}).get("timestamp") or 0
    return ts and (_now() - ts) < REALTIME_CACHE_SECONDS


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


def _age(ts):
    return round(max(0, _now() - ts), 1) if ts else None


def _num(value, default=None):
    try:
        if value is None or value == "":
            return default
        n = float(value)
        if math.isnan(n) or math.isinf(n):
            return default
        return n
    except Exception:
        return default


def _clamp(value, low=0, high=100):
    return max(low, min(high, value))


def _km_between(a_lat, a_lng, b_lat, b_lng):
    radius = 6371
    dlat = math.radians(b_lat - a_lat)
    dlng = math.radians(b_lng - a_lng)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a_lat))
        * math.cos(math.radians(b_lat))
        * math.sin(dlng / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _normal_key(key):
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


def _records(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    rows = payload.get("results") or payload.get("records") or payload.get("features") or []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(row.get("fields") or row.get("properties") or row)
    return out


def _pick(row, names):
    wanted = {_normal_key(name) for name in names}
    for key, value in row.items():
        if _normal_key(key) in wanted:
            return value
    for key, value in row.items():
        normal = _normal_key(key)
        if any(name in normal for name in wanted):
            return value
    return None


def _first_number(row, fragments):
    for key, value in row.items():
        normal = _normal_key(key)
        if any(fragment in normal for fragment in fragments):
            n = _num(value, None)
            if n is not None:
                return n
    return None


def _extract_lat_lng(row):
    lat = _first_number(row, ["latitude", "lat"])
    lng = _first_number(row, ["longitude", "lng", "lon"])
    if lat is not None and lng is not None:
        return lat, lng

    for key, value in row.items():
        normal = _normal_key(key)
        if normal in {"geopoint2d", "geo", "location", "coordinates"}:
            if isinstance(value, dict):
                lat = _num(value.get("lat") or value.get("latitude"), None)
                lng = _num(value.get("lon") or value.get("lng") or value.get("longitude"), None)
                if lat is not None and lng is not None:
                    return lat, lng
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                a = _num(value[0], None)
                b = _num(value[1], None)
                if a is not None and b is not None:
                    return (a, b) if -90 <= a <= 90 else (b, a)
    return None, None


def _intersection_id(row):
    value = _pick(row, ["intersection_id", "intersectionid", "site_id", "siteid", "tsc", "location_id", "locationid"])
    return str(value).strip() if value not in [None, ""] else None


def _intersection_name(row):
    value = _pick(row, ["intersection_name", "intersection", "name", "location_name", "location"])
    return str(value).strip() if value not in [None, ""] else ""


def _request_json(url, source_name):
    if not url:
        return None, "not_configured"
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.Timeout:
        logger.warning("%s timed out; using partial/fallback traffic model.", source_name)
        return None, "timeout"
    except Exception as exc:
        message = str(exc)
        if QLDTRAFFIC_API_KEY:
            message = message.replace(QLDTRAFFIC_API_KEY, "REDACTED")
        if TOMTOM_API_KEY:
            message = message.replace(TOMTOM_API_KEY, "REDACTED")
        logger.warning("%s failed; using partial/fallback traffic model: %s", source_name, message)
        return None, message


def _qldtraffic_url():
    if QLDTRAFFIC_GEOJSON_URL:
        return QLDTRAFFIC_GEOJSON_URL
    if not QLDTRAFFIC_API_KEY:
        return ""
    return f"{QLDTRAFFIC_EVENTS_ENDPOINT}?apikey={QLDTRAFFIC_API_KEY}"


def _redacted_qldtraffic_url():
    url = _qldtraffic_url()
    if QLDTRAFFIC_API_KEY:
        url = url.replace(QLDTRAFFIC_API_KEY, "REDACTED")
    return url


def fetch_brisbane_intersection_volume():
    if _fresh("volume"):
        return _cache["volume"]["data"]
    payload, error = _request_json(BRISBANE_TRAFFIC_VOLUME_URL, "Brisbane intersection volume")
    rows = _records(payload) if payload is not None else []
    volumes = []
    for row in rows:
        intersection_id = _intersection_id(row)
        volume = _first_number(row, ["volume", "count", "flow"])
        occupancy = _first_number(row, ["occupancy"])
        if occupancy is not None and occupancy > 1:
            occupancy = occupancy / 100
        volumes.append(
            {
                "intersection_id": intersection_id,
                "name": _intersection_name(row),
                "volume": volume or 0,
                "occupancy": occupancy,
                "timestamp": _pick(row, ["timestamp", "datetime", "date_time", "last_updated", "time"]),
                "detector": _pick(row, ["detector", "detector_id", "lane", "approach"]),
            }
        )
    _cache["volume"] = {
        "timestamp": _now(),
        "data": volumes,
        "fallback_reason": error,
        "records": len(volumes),
    }
    return volumes


def fetch_brisbane_intersection_locations():
    if _fresh("locations"):
        return _cache["locations"]["data"]
    payload, error = _request_json(BRISBANE_INTERSECTION_LOCATIONS_URL, "Brisbane intersection locations")
    rows = _records(payload) if payload is not None else []
    locations = []
    for row in rows:
        lat, lng = _extract_lat_lng(row)
        if lat is None or lng is None:
            continue
        locations.append(
            {
                "intersection_id": _intersection_id(row),
                "name": _intersection_name(row),
                "latitude": lat,
                "longitude": lng,
                "approaches": _pick(row, ["approaches", "approach", "lanes", "detectors"]),
            }
        )
    _cache["locations"] = {
        "timestamp": _now(),
        "data": locations,
        "fallback_reason": error,
        "records": len(locations),
    }
    return locations


def _joined_intersections():
    if _fresh("live_intersections"):
        return _cache["live_intersections"]["data"]
    volumes = fetch_brisbane_intersection_volume()
    locations = fetch_brisbane_intersection_locations()
    by_id = {loc["intersection_id"]: loc for loc in locations if loc.get("intersection_id")}
    live = []
    for volume in volumes:
        loc = by_id.get(volume.get("intersection_id"))
        if not loc and volume.get("name"):
            name = volume["name"].lower()
            loc = next((item for item in locations if item.get("name", "").lower() == name), None)
        if not loc:
            continue
        item = {
            "intersection_id": volume.get("intersection_id") or loc.get("intersection_id"),
            "name": loc.get("name") or volume.get("name"),
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "volume": volume.get("volume") or 0,
            "occupancy": volume.get("occupancy"),
            "last_updated": volume.get("timestamp"),
            "detector": volume.get("detector"),
        }
        live.append(item)
    near = [
        item for item in live
        if _km_between(SUNCORP_LAT, SUNCORP_LNG, item["latitude"], item["longitude"]) <= 3
    ]
    _cache["live_intersections"] = {
        "timestamp": _now(),
        "data": live,
        "joined_locations": len(live),
        "near_suncorp": len(near),
    }
    return live


def _event_point(geometry):
    if not geometry:
        return None
    coords = geometry.get("coordinates")
    gtype = str(geometry.get("type", "")).lower()
    if gtype == "geometrycollection":
        for child in geometry.get("geometries", []):
            point = _event_point(child)
            if point:
                return point
    if not coords:
        return None
    if gtype == "point" and len(coords) >= 2:
        return _num(coords[1]), _num(coords[0])
    if gtype == "linestring" and coords and len(coords[0]) >= 2:
        mid = coords[len(coords) // 2]
        return _num(mid[1]), _num(mid[0])
    if gtype == "multilinestring" and coords and coords[0] and len(coords[0][0]) >= 2:
        line = coords[0]
        mid = line[len(line) // 2]
        return _num(mid[1]), _num(mid[0])
    return None


def _event_type(props):
    text = " ".join(str(value).lower() for value in props.values() if value is not None)
    event_type = str(props.get("event_type") or props.get("eventType") or "").lower()
    event_due_to = str(props.get("event_due_to") or props.get("eventDueTo") or "").lower()
    text = f"{event_type} {event_due_to} {text}"
    if "crash" in text or "accident" in text or "collision" in text:
        return "crash"
    if "roadwork" in text or "road work" in text or "works" in text or "closure" in text or "closed" in text:
        return "roadwork_closure"
    if "hazard" in text or "flood" in text or "debris" in text:
        return "hazard_flood"
    if "congestion" in text or "heavy traffic" in text or "queue" in text:
        return "congestion"
    if "special event" in text or "event" in text:
        return "special_event"
    return "info"


def fetch_qldtraffic_events():
    if _fresh("qldtraffic"):
        return _cache["qldtraffic"]["data"]
    url = _qldtraffic_url()
    payload, error = _request_json(url, "QLDTraffic GeoJSON")
    features = payload.get("features", []) if isinstance(payload, dict) else []
    events = []
    for idx, feature in enumerate(features):
        props = feature.get("properties") or {}
        point = _event_point(feature.get("geometry") or {})
        if not point:
            continue
        lat, lng = point
        if lat is None or lng is None:
            continue
        distance = _km_between(SUNCORP_LAT, SUNCORP_LNG, lat, lng)
        if distance > 3:
            continue
        events.append(
            {
                "id": str(props.get("id") or props.get("eventId") or idx),
                "type": _event_type(props),
                "description": str(
                    props.get("headline")
                    or props.get("title")
                    or props.get("description")
                    or props.get("eventDescription")
                    or "Traffic event"
                ),
                "latitude": round(lat, 6),
                "longitude": round(lng, 6),
                "distance_to_suncorp_km": round(distance, 3),
                "source": "QLDTraffic GeoJSON",
            }
        )
    _cache["qldtraffic"] = {
        "timestamp": _now(),
        "data": events,
        "fallback_reason": error,
        "records": len(features),
        "endpoint_tested": _redacted_qldtraffic_url(),
    }
    return events


def get_open_data_context_for_pickup(pickup_lat, pickup_lng, radius_m=800):
    lat = _num(pickup_lat, SUNCORP_LAT)
    lng = _num(pickup_lng, SUNCORP_LNG)
    radius_km = radius_m / 1000
    intersections = []
    for item in _joined_intersections():
        distance = _km_between(lat, lng, item["latitude"], item["longitude"])
        if distance <= radius_km:
            copy = dict(item)
            copy["distance_to_pickup_m"] = round(distance * 1000)
            intersections.append(copy)
    events = []
    for event in fetch_qldtraffic_events():
        distance = _km_between(lat, lng, event["latitude"], event["longitude"])
        if distance <= radius_km:
            copy = dict(event)
            copy["distance_to_pickup_m"] = round(distance * 1000)
            events.append(copy)

    occupancies = [item["occupancy"] for item in intersections if item.get("occupancy") is not None]
    avg_occupancy = sum(occupancies) / len(occupancies) if occupancies else None
    volume = sum(_num(item.get("volume"), 0) for item in intersections)
    source_ok = bool(_cache["live_intersections"]["joined_locations"] or _cache["qldtraffic"]["data"])
    return {
        "provider": "open_data",
        "enabled": bool(ENABLE_REALTIME_TRAFFIC and REALTIME_PROVIDER == "open_data"),
        "fallback_used": not source_ok,
        "nearby_intersections": intersections,
        "nearby_intersections_count": len(intersections),
        "avg_nearby_occupancy": round(avg_occupancy, 3) if avg_occupancy is not None else None,
        "nearby_traffic_volume": round(volume, 1),
        "qldtraffic_events": events,
        "nearby_qldtraffic_events_count": len(events),
        "nearby_qldtraffic_event_types": sorted({event["type"] for event in events}),
        "last_updated": _iso(max(_cache["volume"]["timestamp"], _cache["locations"]["timestamp"], _cache["qldtraffic"]["timestamp"])),
    }


def calculate_open_data_adjustments(context):
    adjustments = {"congestion_score": 0, "safety_score": 0, "driver_access_score": 0}
    occupancy = context.get("avg_nearby_occupancy")
    volume = _num(context.get("nearby_traffic_volume"), 0)
    if occupancy is not None:
        if occupancy >= 0.75:
            adjustments["congestion_score"] -= 35
            adjustments["driver_access_score"] -= 25
        elif occupancy >= 0.50:
            adjustments["congestion_score"] -= 20
            adjustments["driver_access_score"] -= 15
        elif occupancy >= 0.30:
            adjustments["congestion_score"] -= 10
    if volume >= 1000:
        adjustments["congestion_score"] -= 10

    event_types = set(context.get("nearby_qldtraffic_event_types", []))
    if "crash" in event_types:
        adjustments["congestion_score"] -= 20
        adjustments["safety_score"] -= 15
        adjustments["driver_access_score"] -= 20
    if "roadwork_closure" in event_types:
        adjustments["congestion_score"] -= 25
        adjustments["driver_access_score"] -= 25
    if "hazard_flood" in event_types:
        adjustments["safety_score"] -= 25
        adjustments["driver_access_score"] -= 15
    if "congestion" in event_types:
        adjustments["congestion_score"] -= 25
    if "special_event" in event_types:
        adjustments["congestion_score"] -= 15
    return adjustments


def _open_data_note(context):
    event_types = context.get("nearby_qldtraffic_event_types", [])
    occupancy = context.get("avg_nearby_occupancy")
    if event_types:
        first = event_types[0].replace("_", " ")
        return f"QLDTraffic shows {first} near this pickup."
    if occupancy is not None:
        if occupancy >= 0.75:
            return "Nearby signal occupancy suggests heavy congestion."
        if occupancy >= 0.50:
            return "Nearby signal occupancy suggests moderate congestion."
        if occupancy >= 0.30:
            return "Nearby signal occupancy suggests light congestion."
        return "Nearby signal occupancy suggests low congestion."
    if context.get("fallback_used"):
        return "Using fallback traffic model."
    return "Open traffic data shows no nearby incident or high occupancy."


def _tomtom_context_for_pickup(pickup_lat, pickup_lng):
    if not TOMTOM_API_KEY:
        return {"provider": "tomtom", "enabled": False, "fallback_used": True, "flow": {}}
    try:
        response = requests.get(
            TOMTOM_FLOW_ENDPOINT,
            params={"point": f"{pickup_lat},{pickup_lng}", "unit": "KMPH", "key": TOMTOM_API_KEY},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        flow = response.json().get("flowSegmentData", {})
        current = _num(flow.get("currentSpeed"))
        free = _num(flow.get("freeFlowSpeed"))
        ratio = round(current / free, 3) if current is not None and free else None
        return {
            "provider": "tomtom",
            "enabled": True,
            "fallback_used": False,
            "flow": {
                "current_speed_kmph": current,
                "free_flow_speed_kmph": free,
                "congestion_ratio": ratio,
                "traffic_confidence": _num(flow.get("confidence")),
                "road_closure": bool(flow.get("roadClosure")),
            },
        }
    except Exception as exc:
        logger.warning("TomTom fallback provider failed: %s", exc)
        return {"provider": "tomtom", "enabled": True, "fallback_used": True, "fallback_reason": str(exc), "flow": {}}


def _tomtom_adjustments(context):
    flow = context.get("flow", {})
    ratio = flow.get("congestion_ratio")
    adjustments = {"congestion_score": 0, "safety_score": 0, "driver_access_score": 0}
    if context.get("fallback_used"):
        return adjustments
    if flow.get("road_closure"):
        adjustments["congestion_score"] -= 60
        adjustments["driver_access_score"] -= 50
        adjustments["safety_score"] -= 20
    elif ratio is not None and ratio < 0.45:
        adjustments["congestion_score"] -= 40
        adjustments["driver_access_score"] -= 25
    elif ratio is not None and ratio < 0.65:
        adjustments["congestion_score"] -= 25
        adjustments["driver_access_score"] -= 10
    elif ratio is not None and ratio < 0.85:
        adjustments["congestion_score"] -= 10
    return adjustments


def get_realtime_context_for_pickup(pickup_lat, pickup_lng, radius_m=800):
    if not ENABLE_REALTIME_TRAFFIC:
        return {"provider": REALTIME_PROVIDER, "enabled": False, "fallback_used": True}
    if REALTIME_PROVIDER == "tomtom":
        return _tomtom_context_for_pickup(pickup_lat, pickup_lng)
    return get_open_data_context_for_pickup(pickup_lat, pickup_lng, radius_m)


def calculate_realtime_adjustments(pickup):
    updated = dict(pickup)
    context = updated.get("realtime_context") or get_realtime_context_for_pickup(
        updated.get("latitude") or updated.get("lat"),
        updated.get("longitude") or updated.get("lng"),
    )
    if context.get("provider") == "tomtom":
        adjustments = _tomtom_adjustments(context)
        flow = context.get("flow", {})
        updated["tomtom_flow_enabled"] = not context.get("fallback_used", True)
        updated["current_speed_kmph"] = flow.get("current_speed_kmph")
        updated["free_flow_speed_kmph"] = flow.get("free_flow_speed_kmph")
        updated["congestion_ratio"] = flow.get("congestion_ratio")
        updated["traffic_confidence"] = flow.get("traffic_confidence")
        updated["road_closure"] = flow.get("road_closure", False)
        updated["live_traffic_note"] = "Using fallback traffic model." if context.get("fallback_used") else "Live TomTom traffic is influencing this pickup."
    else:
        adjustments = calculate_open_data_adjustments(context)
        updated["open_data_enabled"] = bool(context.get("enabled") and not context.get("fallback_used"))
        updated["nearby_intersections_count"] = context.get("nearby_intersections_count", 0)
        updated["avg_nearby_occupancy"] = context.get("avg_nearby_occupancy")
        updated["nearby_traffic_volume"] = context.get("nearby_traffic_volume", 0)
        updated["nearby_qldtraffic_events_count"] = context.get("nearby_qldtraffic_events_count", 0)
        updated["nearby_qldtraffic_event_types"] = context.get("nearby_qldtraffic_event_types", [])
        updated["live_traffic_note"] = _open_data_note(context)

    for score_key, delta in adjustments.items():
        updated[score_key] = round(_clamp(_num(updated.get(score_key), 50) + delta), 1)
    updated["realtime_provider"] = context.get("provider", REALTIME_PROVIDER)
    updated["realtime_enabled"] = bool(context.get("enabled"))
    updated["realtime_data_age_seconds"] = _age(max(_cache["volume"]["timestamp"], _cache["locations"]["timestamp"], _cache["qldtraffic"]["timestamp"]))
    updated["live_congestion_note"] = updated["live_traffic_note"]
    updated["score_adjustments"] = adjustments
    updated["realtime_context"] = context
    return updated


def realtime_status():
    if REALTIME_PROVIDER == "tomtom":
        context = _tomtom_context_for_pickup(SUNCORP_LAT, SUNCORP_LNG)
        return {
            "enabled": bool(ENABLE_REALTIME_TRAFFIC),
            "provider": "tomtom",
            "fallback_used": context.get("fallback_used", True),
            "fallback_reason": context.get("fallback_reason"),
            "source": "TomTom Traffic API",
            "last_updated": _iso(_now()),
            "events_near_suncorp": [],
            "count": 0,
        }

    intersections = _joined_intersections()
    events = fetch_qldtraffic_events()
    volume_ok = _cache["volume"]["fallback_reason"] is None
    locations_ok = _cache["locations"]["fallback_reason"] is None
    qld_ok = _cache["qldtraffic"]["fallback_reason"] is None
    source_ok = bool(_cache["live_intersections"]["joined_locations"]) or qld_ok
    return {
        "enabled": bool(ENABLE_REALTIME_TRAFFIC),
        "provider": "open_data",
        "fallback_used": not source_ok,
        "fallback_reason": None if source_ok else "all_open_data_sources_unavailable",
        "sources": OPEN_DATA_SOURCES,
        "source": " / ".join(OPEN_DATA_SOURCES),
        "last_updated": _iso(max(_cache["volume"]["timestamp"], _cache["locations"]["timestamp"], _cache["qldtraffic"]["timestamp"])),
        "intersection_volume": {
            "records": _cache["volume"]["records"],
            "joined_locations": _cache["live_intersections"]["joined_locations"],
            "near_suncorp": _cache["live_intersections"]["near_suncorp"],
            "volume_source_ok": volume_ok,
            "locations_source_ok": locations_ok,
        },
        "qldtraffic": {
            "events_total": _cache["qldtraffic"]["records"],
            "events_near_suncorp": len(events),
            "source_ok": qld_ok,
            "endpoint_tested": _cache["qldtraffic"].get("endpoint_tested") or _redacted_qldtraffic_url(),
        },
        "events_near_suncorp": events,
        "count": len(events),
    }
