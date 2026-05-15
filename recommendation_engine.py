import csv
import math
import os
import sqlite3

from realtime_traffic import calculate_realtime_adjustments, get_realtime_context_for_pickup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'crowdcab.sqlite')
STADIUM = {'lat': -27.4648, 'lng': 153.0095}
DEFAULT_MAX_WALK_KM = 1.0
DEFAULT_SEARCH_RADIUS_KM = 2.0
DEFAULT_RESULT_LIMIT = 8
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


def read_table(table_name):
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        with conn:
            return [dict(row) for row in conn.execute(f'SELECT * FROM "{table_name}"').fetchall()]
    except Exception:
        return []


def venue_by_id(venue_id):
    venue_id = venue_id or 'suncorp_stadium'
    for venue in read_table('venues'):
        if venue.get('venue_id') == venue_id:
            return venue
    if venue_id == 'suncorp_stadium':
        return {'venue_id': 'suncorp_stadium', 'name': 'Suncorp Stadium', 'latitude': STADIUM['lat'], 'longitude': STADIUM['lng']}
    return {'venue_id': venue_id, 'name': venue_id.replace('_', ' ').title(), 'latitude': STADIUM['lat'], 'longitude': STADIUM['lng']}


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


def pickup_candidates_for_venue(venue_id):
    rows = [
        row for row in read_table('venue_pickup_points')
        if row.get('venue_id') == venue_id and str(row.get('candidate_pickup_point', '1')) in ['1', 'true', 'True']
    ]
    if rows:
        return rows

    if venue_id != 'suncorp_stadium':
        return []

    # Compatibility fallback for older databases that have not been seeded yet.
    fallback = []
    for index, row in enumerate(read_csv('candidate_pickup_points.csv'), start=1):
        label = row.get('pickup_point_label') or row.get('street') or f'Suncorp Pickup {index}'
        fallback.append({
            'venue_id': 'suncorp_stadium',
            'pickup_point_id': label,
            'label': label,
            'suburb': row.get('suburb', ''),
            'street': row.get('street', ''),
            'latitude': row.get('latitude', ''),
            'longitude': row.get('longitude', ''),
            'candidate_pickup_point': row.get('candidate_pickup_point', '1'),
            'source_dataset': row.get('source_dataset', 'candidate_pickup_points'),
            'official_event_role': 'candidate_pickup',
            'nearby_road_count': row.get('nearby_road_count', ''),
            'nearby_major_road_count': row.get('nearby_major_road_count', ''),
            'nearby_crossing_count': row.get('nearby_crossing_count', ''),
            'nearby_signal_count': row.get('nearby_signal_count', ''),
            'access_complexity_score': row.get('access_complexity_score', ''),
            'distance_to_venue_km': row.get('distance_to_suncorp_km', ''),
            'complexity_band': row.get('complexity_band', ''),
            'walk_band': row.get('walk_band', ''),
        })
    return fallback


def has_blocking_live_closure(row):
    event_types = {
        str(event_type).lower()
        for event_type in (row.get('nearby_qldtraffic_event_types') or row.get('nearby_live_event_types') or [])
    }
    if {'closure', 'road_closure'} & event_types:
        return True
    if 'roadwork_closure' in event_types and abs((row.get('score_adjustments') or {}).get('driver_access_score', 0)) >= 25:
        return True
    return bool(row.get('road_closure'))


def candidate_raw_rows(origin_lat, origin_lng, congestion_points, max_walk_km=DEFAULT_MAX_WALK_KM, venue_id='suncorp_stadium', search_radius_km=DEFAULT_SEARCH_RADIUS_KM):
    candidates = pickup_candidates_for_venue(venue_id)
    raw = []

    for row in candidates:
        lat = num(row.get('latitude'), None)
        lng = num(row.get('longitude'), None)
        if lat is None or lng is None:
            continue

        distance_km = num(row.get('distance_to_venue_km'), None)
        if distance_km is None:
            distance_km = km_between(origin_lat, origin_lng, lat, lng)

        nearby_roads = num(row.get('nearby_road_count'))
        nearby_major_roads = num(row.get('nearby_major_road_count'))
        nearby_crossings = num(row.get('nearby_crossing_count'))
        nearby_signals = num(row.get('nearby_signal_count'))
        complexity = num(row.get('access_complexity_score'), 150)
        congestion_nearby = nearby_congestion_count(lat, lng, congestion_points)
        driver_access_signal = nearby_roads * 0.45 + nearby_major_roads * 1.2 - complexity * 0.35
        if row.get('driver_access_score') not in [None, '']:
            driver_access_signal = num(row.get('driver_access_score'), driver_access_signal)
        if distance_km > search_radius_km:
            continue
        if driver_access_signal < MIN_DRIVER_ACCESS_SIGNAL:
            continue

        over_preferred_walk_km = max(0, distance_km - max_walk_km)
        walk_penalty = over_preferred_walk_km * 1.8

        # Pressure values are later inverted: lower pressure means better score.
        raw.append({
            'source': row,
            'lat': lat,
            'lng': lng,
            'distance_km': distance_km,
            'walk_min': max(2, round(distance_km * 12)),
            'walking_pressure': distance_km + walk_penalty,
            'congestion_pressure': nearby_signals * 2.5 + nearby_crossings * 0.8 + congestion_nearby * 2.0,
            'safety_pressure': complexity * 0.55 + nearby_signals * 7 + nearby_crossings * 3 + over_preferred_walk_km * 12,
            'accessibility_pressure': complexity * 0.75 + distance_km * 80 + nearby_crossings * 2 + over_preferred_walk_km * 40,
            'driver_access_signal': driver_access_signal,
            'congestion_nearby': congestion_nearby,
            'static_scores': {
                'congestion_score': num(row.get('base_congestion_score'), None),
                'safety_score': num(row.get('safety_score'), None),
                'accessibility_score': num(row.get('accessibility_score'), None),
                'driver_access_score': num(row.get('driver_access_score'), None),
            },
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
        static_scores = item.get('static_scores') or {}
        walking_score = normalize(item['walking_pressure'], walking_values, invert=True)
        congestion_score = static_scores.get('congestion_score')
        if congestion_score is None:
            congestion_score = normalize(item['congestion_pressure'], congestion_values, invert=True)
        safety_score = static_scores.get('safety_score')
        if safety_score is None:
            safety_score = normalize(item['safety_pressure'], safety_values, invert=True)
        accessibility_score = static_scores.get('accessibility_score')
        if accessibility_score is None:
            accessibility_score = normalize(item['accessibility_pressure'], accessibility_values, invert=True)
        driver_access_score = static_scores.get('driver_access_score')
        if driver_access_score is None:
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
        label = source.get('label') or source.get('pickup_point_label') or source.get('street') or 'Pickup point'
        result = {
            'venue_id': source.get('venue_id', 'suncorp_stadium'),
            'pickup_point_id': source.get('pickup_point_id') or label,
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
            'source_dataset': source.get('source_dataset', ''),
            'official_event_role': source.get('official_event_role', ''),
            'walk_band': source.get('walk_band', ''),
            'shortlist_status': 'preferred' if item['distance_km'] <= DEFAULT_MAX_WALK_KM else 'fallback',
        }
        adjusted = apply_realtime_scoring(result, weights)
        if not has_blocking_live_closure(adjusted):
            results.append(adjusted)

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


def score_selected_pickup(selected_pickup, scored_pickups, weights, accessibility_required=False, origin_lat=None, origin_lng=None):
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
    origin_lat = num(origin_lat, STADIUM['lat'])
    origin_lng = num(origin_lng, STADIUM['lng'])

    if match:
        result = dict(match)
        if lat is not None and lng is not None:
            result['latitude'] = round(lat, 6)
            result['longitude'] = round(lng, 6)
            result['distance_km'] = round(km_between(origin_lat, origin_lng, lat, lng), 3)
            result['walk_min'] = max(2, round(result['distance_km'] * 12))
        result['pickup_point_id'] = label
        result['label'] = label
        result['name'] = label
        return apply_realtime_scoring(result, weights)

    lat = lat if lat is not None else origin_lat
    lng = lng if lng is not None else origin_lng
    distance_km = km_between(origin_lat, origin_lng, lat, lng)
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


def recommend_pickups(venue_id='suncorp_stadium', user_lat=None, user_lng=None, preferences=None):
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
    search_radius_km = num(preferences.get('search_radius_km'), DEFAULT_SEARCH_RADIUS_KM)
    search_radius_km = min(max(search_radius_km, max_walk_km), 2.0)
    result_limit = preferences.get('result_limit', DEFAULT_RESULT_LIMIT)
    venue_id = preferences.get('venue_id') or venue_id or 'suncorp_stadium'
    venue = venue_by_id(venue_id)
    venue_lat = num(venue.get('latitude'), STADIUM['lat'])
    venue_lng = num(venue.get('longitude'), STADIUM['lng'])
    origin_lat = num(user_lat, venue_lat) if user_lat is not None else venue_lat
    origin_lng = num(user_lng, venue_lng) if user_lng is not None else venue_lng

    congestion_points = read_csv('congestion_points.csv')
    raw = candidate_raw_rows(
        origin_lat,
        origin_lng,
        congestion_points,
        max_walk_km=max_walk_km,
        venue_id=venue_id,
        search_radius_km=search_radius_km,
    )
    scored = score_raw_pickups(raw, weights, accessibility_required)
    if result_limit in [None, '', 0, '0', 'all']:
        return scored
    return scored[: int(result_limit)]
