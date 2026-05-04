import csv
import math
import os

from realtime_traffic import calculate_realtime_adjustments, get_realtime_context_for_pickup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STADIUM = {'lat': -27.4648, 'lng': 153.0095}
DEFAULT_MAX_WALK_KM = 1.0
MIN_DRIVER_ACCESS_SIGNAL = -30
MIN_FINAL_DRIVER_ACCESS_SCORE = 15

WEIGHTS = {
    'balanced': {'walking': 30, 'congestion': 25, 'safety': 20, 'accessibility': 15, 'driver_access': 10},
    'fastest': {'walking': 50, 'congestion': 20, 'safety': 10, 'accessibility': 10, 'driver_access': 10},
    'least_congested': {'walking': 20, 'congestion': 45, 'safety': 15, 'accessibility': 10, 'driver_access': 10},
    'safest': {'walking': 15, 'congestion': 20, 'safety': 45, 'accessibility': 10, 'driver_access': 10},
    'accessible': {'walking': 20, 'congestion': 15, 'safety': 20, 'accessibility': 35, 'driver_access': 10},
}


def read_csv(name):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return []
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def num(value, default=0):
    try:
        if value is None or value == '':
            return default
        n = float(value)
        if math.isnan(n) or math.isinf(n):
            return default
        return n
    except Exception:
        return default


def clamp(value, low=0, high=100):
    return max(low, min(high, value))


def km_between(a_lat, a_lng, b_lat, b_lng):
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


def normalize(value, values, invert=False, default=50):
    clean = [v for v in values if v is not None]
    if not clean:
        return default
    low = min(clean)
    high = max(clean)
    if high == low:
        return default
    score = ((value - low) / (high - low)) * 100
    return round(100 - score if invert else score, 2)


def nearby_congestion_count(lat, lng, congestion_points, radius_km=0.25):
    count = 0
    for point in congestion_points:
        p_lat = num(point.get('latitude'), None)
        p_lng = num(point.get('longitude'), None)
        if p_lat is None or p_lng is None:
            continue
        if km_between(lat, lng, p_lat, p_lng) <= radius_km:
            count += 1
    return count


def reason_for(row):
    walk = row.get('walk_score', row.get('walking_score', 0))
    congestion = row.get('congestion_score', 0)
    safety = row.get('safety_score', 0)

    if walk > 80:
        walk_text = 'short walk'
    elif walk >= 50:
        walk_text = 'moderate walk'
    else:
        walk_text = 'longer walk'

    if congestion > 70:
        congestion_text = 'low congestion'
    elif congestion >= 40:
        congestion_text = 'moderate congestion'
    else:
        congestion_text = 'high congestion'

    if safety > 70:
        safety_text = 'safer movement'
    else:
        safety_text = 'moderate safety conditions'

    live_note = row.get('live_traffic_note') or row.get('live_congestion_note')
    event_types = [
        str(t).replace('_', ' ')
        for t in row.get('nearby_live_event_types', [])
        if t not in ['camera', 'info']
    ]
    penalty = sum(abs(v) for v in (row.get('score_adjustments') or {}).values())

    if event_types and penalty >= 35:
        return f"Not recommended because live traffic data shows nearby {', '.join(event_types)}."

    reason = f'Recommended for {walk_text}, {congestion_text}, and {safety_text}.'
    if live_note:
        reason = f'{reason} {live_note}'
    return reason


def weighted_total(row, weights):
    return (
        row.get('walking_score', row.get('walk_score', 0)) * weights['walking']
        + row.get('congestion_score', 0) * weights['congestion']
        + row.get('safety_score', 0) * weights['safety']
        + row.get('accessibility_score', 0) * weights['accessibility']
        + row.get('driver_access_score', 0) * weights['driver_access']
    ) / 100


def apply_realtime_scoring(result, weights):
    for score_key in ['congestion_score', 'safety_score', 'accessibility_score', 'driver_access_score', 'walking_score', 'walk_score']:
        static_key = f'static_{score_key}'
        if static_key in result:
            result[score_key] = result[static_key]
    context = get_realtime_context_for_pickup(result['latitude'], result['longitude'])
    result['realtime_context'] = context
    adjusted = calculate_realtime_adjustments(result)
    adjusted['total_score'] = round(weighted_total(adjusted, weights), 1)
    adjusted['recommendation_updated_by_realtime'] = any(
        value != 0 for value in (adjusted.get('score_adjustments') or {}).values()
    )
    adjusted['reason'] = reason_for(adjusted)
    adjusted.pop('realtime_context', None)
    return adjusted


def candidate_raw_rows(origin_lat, origin_lng, congestion_points, max_walk_km=DEFAULT_MAX_WALK_KM):
    candidates = read_csv('candidate_pickup_points.csv')
    raw = []

    for row in candidates:
        lat = num(row.get('latitude'), None)
        lng = num(row.get('longitude'), None)
        if lat is None or lng is None:
            continue

        distance_km = km_between(origin_lat, origin_lng, lat, lng)
        if origin_lat == STADIUM['lat'] and origin_lng == STADIUM['lng']:
            distance_km = num(row.get('distance_to_suncorp_km'), distance_km)

        nearby_roads = num(row.get('nearby_road_count'))
        nearby_major_roads = num(row.get('nearby_major_road_count'))
        nearby_crossings = num(row.get('nearby_crossing_count'))
        nearby_signals = num(row.get('nearby_signal_count'))
        complexity = num(row.get('access_complexity_score'), 150)
        congestion_nearby = nearby_congestion_count(lat, lng, congestion_points)
        driver_access_signal = nearby_roads * 0.45 + nearby_major_roads * 1.2 - complexity * 0.35
        if distance_km > max_walk_km:
            continue
        if driver_access_signal < MIN_DRIVER_ACCESS_SIGNAL:
            continue

        # Pressure values are later inverted: lower pressure means better score.
        raw.append({
            'source': row,
            'lat': lat,
            'lng': lng,
            'distance_km': distance_km,
            'walk_min': max(2, round(distance_km * 12)),
            'walking_pressure': distance_km,
            'congestion_pressure': nearby_signals * 2.5 + nearby_crossings * 0.8 + congestion_nearby * 2.0,
            'safety_pressure': complexity * 0.55 + nearby_signals * 7 + nearby_crossings * 3,
            'accessibility_pressure': complexity * 0.75 + distance_km * 80 + nearby_crossings * 2,
            'driver_access_signal': driver_access_signal,
            'congestion_nearby': congestion_nearby,
        })
    return raw


def score_raw_pickups(raw, weights, accessibility_required=False):
    if not raw:
        return []

    walking_values = [r['walking_pressure'] for r in raw]
    congestion_values = [r['congestion_pressure'] for r in raw]
    safety_values = [r['safety_pressure'] for r in raw]
    accessibility_values = [r['accessibility_pressure'] for r in raw]
    driver_values = [r['driver_access_signal'] for r in raw]

    results = []
    for item in raw:
        walking_score = normalize(item['walking_pressure'], walking_values, invert=True)
        congestion_score = normalize(item['congestion_pressure'], congestion_values, invert=True)
        safety_score = normalize(item['safety_pressure'], safety_values, invert=True)
        accessibility_score = normalize(item['accessibility_pressure'], accessibility_values, invert=True)
        driver_access_score = normalize(item['driver_access_signal'], driver_values)

        if accessibility_required:
            accessibility_score = clamp(accessibility_score + 8)
            safety_score = clamp(safety_score + 3)

        total_score = (
            walking_score * weights['walking']
            + congestion_score * weights['congestion']
            + safety_score * weights['safety']
            + accessibility_score * weights['accessibility']
            + driver_access_score * weights['driver_access']
        ) / 100

        source = item['source']
        label = source.get('pickup_point_label') or source.get('street') or 'Pickup point'
        result = {
            'pickup_point_id': label,
            'label': label,
            'name': label,
            'latitude': round(item['lat'], 6),
            'longitude': round(item['lng'], 6),
            'walk_min': item['walk_min'],
            'congestion_score': round(congestion_score, 1),
            'safety_score': round(safety_score, 1),
            'accessibility_score': round(accessibility_score, 1),
            'driver_access_score': round(driver_access_score, 1),
            'walking_score': round(walking_score, 1),
            'walk_score': round(walking_score, 1),
            'static_congestion_score': round(congestion_score, 1),
            'static_safety_score': round(safety_score, 1),
            'static_accessibility_score': round(accessibility_score, 1),
            'static_driver_access_score': round(driver_access_score, 1),
            'static_walking_score': round(walking_score, 1),
            'static_walk_score': round(walking_score, 1),
            'total_score': round(total_score, 1),
            'static_total_score': round(total_score, 1),
            'reason': '',
            'distance_km': round(item['distance_km'], 3),
            'congestion_nearby': item['congestion_nearby'],
            'suburb': source.get('suburb', ''),
            'street': source.get('street', ''),
        }
        results.append(apply_realtime_scoring(result, weights))

    ranked = sorted(results, key=lambda r: r['total_score'], reverse=True)
    deduped = []
    seen_labels = set()
    for pickup in ranked:
        key = str(pickup.get('label', '')).strip().lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        deduped.append(pickup)

    operational = [
        pickup for pickup in deduped
        if pickup.get('driver_access_score', 0) >= MIN_FINAL_DRIVER_ACCESS_SCORE
    ]
    return operational if len(operational) >= 5 else deduped


def find_scored_pickup(scored_pickups, selected_pickup):
    if not selected_pickup:
        return None
    selected_label = str(
        selected_pickup.get('label')
        or selected_pickup.get('pickup')
        or selected_pickup.get('zone')
        or selected_pickup.get('pickup_point_id')
        or ''
    ).strip().lower()
    selected_lat = num(selected_pickup.get('lat') or selected_pickup.get('latitude'), None)
    selected_lng = num(selected_pickup.get('lng') or selected_pickup.get('longitude'), None)

    if selected_label:
        for pickup in scored_pickups:
            labels = [
                pickup.get('label', ''),
                pickup.get('pickup_point_id', ''),
                pickup.get('street', ''),
            ]
            if any(selected_label == str(label).strip().lower() for label in labels):
                return pickup
        for pickup in scored_pickups:
            labels = [
                pickup.get('label', ''),
                pickup.get('pickup_point_id', ''),
                pickup.get('street', ''),
            ]
            if any(selected_label in str(label).strip().lower() for label in labels if label):
                return pickup

    if selected_lat is not None and selected_lng is not None:
        nearest = min(
            scored_pickups,
            key=lambda p: km_between(selected_lat, selected_lng, p['latitude'], p['longitude']),
            default=None
        )
        if nearest and km_between(selected_lat, selected_lng, nearest['latitude'], nearest['longitude']) <= 0.45:
            return nearest
    return None


def score_selected_pickup(selected_pickup, scored_pickups, weights, accessibility_required=False):
    """Score a selected pickup using the same scored candidate set.

    If the selected pickup is not one of the named candidate rows, the nearest
    scored candidate donates the contextual congestion/safety/access data while
    the selected pickup keeps its own label and coordinates.
    """
    if not selected_pickup:
        return None

    match = find_scored_pickup(scored_pickups, selected_pickup)
    label = (
        selected_pickup.get('label')
        or selected_pickup.get('pickup')
        or selected_pickup.get('zone')
        or (match or {}).get('label')
        or 'Selected pickup'
    )
    lat = num(selected_pickup.get('lat') or selected_pickup.get('latitude'), None)
    lng = num(selected_pickup.get('lng') or selected_pickup.get('longitude'), None)

    if match:
        result = dict(match)
        if lat is not None and lng is not None:
            result['latitude'] = round(lat, 6)
            result['longitude'] = round(lng, 6)
            result['distance_km'] = round(km_between(STADIUM['lat'], STADIUM['lng'], lat, lng), 3)
            result['walk_min'] = max(2, round(result['distance_km'] * 12))
        result['pickup_point_id'] = label
        result['label'] = label
        result['name'] = label
        return apply_realtime_scoring(result, weights)

    lat = lat if lat is not None else STADIUM['lat']
    lng = lng if lng is not None else STADIUM['lng']
    distance_km = km_between(STADIUM['lat'], STADIUM['lng'], lat, lng)
    walking_score = clamp(100 - min(distance_km / 1.5, 1) * 100)
    congestion_score = 50
    safety_score = 50
    accessibility_score = 50 + (8 if accessibility_required else 0)
    driver_access_score = 50
    total_score = (
        walking_score * weights['walking']
        + congestion_score * weights['congestion']
        + safety_score * weights['safety']
        + accessibility_score * weights['accessibility']
        + driver_access_score * weights['driver_access']
    ) / 100
    result = {
        'pickup_point_id': label,
        'label': label,
        'name': label,
        'latitude': round(lat, 6),
        'longitude': round(lng, 6),
        'walk_min': max(2, round(distance_km * 12)),
        'congestion_score': round(congestion_score, 1),
        'safety_score': round(safety_score, 1),
        'accessibility_score': round(accessibility_score, 1),
        'driver_access_score': round(driver_access_score, 1),
        'walking_score': round(walking_score, 1),
        'walk_score': round(walking_score, 1),
        'static_congestion_score': round(congestion_score, 1),
        'static_safety_score': round(safety_score, 1),
        'static_accessibility_score': round(accessibility_score, 1),
        'static_driver_access_score': round(driver_access_score, 1),
        'static_walking_score': round(walking_score, 1),
        'static_walk_score': round(walking_score, 1),
        'total_score': round(total_score, 1),
        'static_total_score': round(total_score, 1),
        'reason': '',
        'distance_km': round(distance_km, 3),
        'congestion_nearby': 0,
        'suburb': '',
        'street': '',
    }
    return apply_realtime_scoring(result, weights)


def recommend_pickups(user_lat=None, user_lng=None, preferences=None):
    """Rank candidate pickup points for event-exit guidance.

    Scores are 0-100 where higher is better. Missing live inputs are derived from
    the current candidate pickup and congestion CSVs so the engine is live-ready
    without requiring another database migration yet.
    """
    preferences = preferences or {}
    priority = preferences.get('priority') or 'balanced'
    weights = WEIGHTS.get(priority, WEIGHTS['balanced'])
    accessibility_required = bool(preferences.get('accessibility_required'))
    max_walk_km = num(preferences.get('max_walk_km'), DEFAULT_MAX_WALK_KM)
    origin_lat = num(user_lat, STADIUM['lat']) if user_lat is not None else STADIUM['lat']
    origin_lng = num(user_lng, STADIUM['lng']) if user_lng is not None else STADIUM['lng']

    congestion_points = read_csv('congestion_points.csv')
    raw = candidate_raw_rows(origin_lat, origin_lng, congestion_points, max_walk_km=max_walk_km)
    return score_raw_pickups(raw, weights, accessibility_required)
