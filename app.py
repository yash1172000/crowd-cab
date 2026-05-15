from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash, send_from_directory
import csv, os, math, json, sqlite3, random, smtplib, re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from uuid import uuid4
from recommendation_engine import DEFAULT_MAX_WALK_KM, WEIGHTS, recommend_pickups, score_selected_pickup
from realtime_traffic import realtime_status

app = Flask(__name__)
app.secret_key = 'crowdcab-demo-secret-change-for-production'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'crowdcab.sqlite')
STADIUM = {'name':'Suncorp Stadium', 'lat':-27.4648, 'lng':153.0095}

BOOKING_EXTRA_COLUMNS = {
    'created_by_email': 'TEXT',
    'venue_id': 'TEXT',
    'venue_name': 'TEXT',
    'destination': 'TEXT',
    'confirmed_pickup_label': 'TEXT',
    'confirmed_walk_min': 'TEXT',
    'confirmed_eta_min': 'TEXT',
    'confirmed_crowd': 'TEXT',
    'confirmed_at': 'TEXT',
    'booking_status': 'TEXT',
}

STAFF_USERS = {
    'admin@crowdcab.com': {
        'name': 'Admin User',
        'role': 'admin',
        'purpose': 'Management/demo access for assessors and stakeholders.',
    },
    'dev@crowdcab.com': {
        'name': 'Developer User',
        'role': 'developer',
        'purpose': 'Testing/debug access for development checks.',
    },
}

OTP_TTL_MINUTES = int(os.getenv('OTP_TTL_MINUTES', '10'))
EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
DEFAULT_PUBLIC_EMAIL_DOMAINS = {
    'gmail.com',
    'googlemail.com',
    'outlook.com',
    'hotmail.com',
    'live.com',
    'msn.com',
    'yahoo.com',
    'yahoo.co.in',
    'icloud.com',
    'me.com',
    'mac.com',
    'proton.me',
    'protonmail.com',
    'aol.com',
    'zoho.com',
    'mail.com',
    'gmx.com',
}
PUBLIC_EMAIL_DOMAINS = {
    domain.strip().lower()
    for domain in os.getenv('PUBLIC_EMAIL_DOMAINS', ','.join(sorted(DEFAULT_PUBLIC_EMAIL_DOMAINS))).split(',')
    if domain.strip()
}

DASHBOARDS = {
    'bookings': {'title': 'Booking Overview', 'question': 'How busy is the system?', 'short': 'Bookings, channels and peak movement.', 'icon': '●', 'style': 'pulse'},
    'pickups': {'title': 'Pickup Demand', 'question': 'Where is demand highest?', 'short': 'Zone ranking and accessibility pressure.', 'icon': '◆', 'style': 'rank'},
    'congestion': {'title': 'Congestion Status', 'question': 'Where is it crowded?', 'short': 'High, medium and clear movement signals.', 'icon': '▲', 'style': 'alert'},
    'cabs': {'title': 'Cab Performance', 'question': 'Are enough cabs available?', 'short': 'Fleet readiness, ETA and company coverage.', 'icon': '■', 'style': 'fleet'},
    'roads': {'title': 'Road Network', 'question': 'Which routes are usable?', 'short': 'Road support and route movement context.', 'icon': '═', 'style': 'route'},
}

# ---------- Helpers ----------
def current_role():
    return session.get('role', 'guest')

def internal_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_role() not in ['admin', 'developer']:
            flash('Internal pages require admin or developer access.')
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('email'):
            flash('Log in to plan your pickup guidance.')
            return redirect(url_for('login', next=request.full_path if request.query_string else request.path))
        return fn(*args, **kwargs)
    return wrapper

def display_name_from_email(email):
    local = email.split('@', 1)[0].replace('.', ' ').replace('_', ' ').replace('-', ' ')
    return local.title() or 'CrowdCab Rider'

def is_valid_email(email):
    return email_validation_error(email) is None

def email_validation_error(email):
    cleaned = (email or '').strip().lower()
    if not cleaned or not EMAIL_RE.fullmatch(cleaned):
        return 'Please enter a valid email address.'
    domain = cleaned.rsplit('@', 1)[-1]
    if cleaned in STAFF_USERS or domain in PUBLIC_EMAIL_DOMAINS:
        return None
    return 'Please check your email address. Use a valid public email such as Gmail, Outlook, Yahoo, iCloud, or Proton.'

def clear_pending_auth():
    session.pop('pending_auth', None)

def valid_pending_auth():
    pending = session.get('pending_auth') or {}
    email = (pending.get('email') or '').strip().lower()
    if not is_valid_email(email) or not pending.get('otp') or not pending.get('expires_at'):
        clear_pending_auth()
        return None
    pending['email'] = email
    return pending

def login_user(email, name, role):
    clear_pending_auth()
    session['email'] = email
    session['name'] = name
    session['role'] = role

def otp_expiry():
    return datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)

def generate_otp():
    return f'{random.SystemRandom().randint(0, 999999):06d}'

def send_otp_email(email, otp):
    """Send an OTP when SMTP is configured; otherwise log it for local demo use."""
    subject = 'Your CrowdCab login code'
    body = (
        f'Your CrowdCab login code is {otp}.\n\n'
        f'This code expires in {OTP_TTL_MINUTES} minutes. '
        'If you did not request it, you can ignore this email.'
    )
    smtp_host = os.getenv('SMTP_HOST', '').strip()
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USERNAME', '').strip()
    smtp_password = os.getenv('SMTP_PASSWORD', '').strip()
    if 'gmail.com' in smtp_host.lower():
        smtp_password = smtp_password.replace(' ', '')
    smtp_from = os.getenv('SMTP_FROM_EMAIL', smtp_user or 'no-reply@crowdcab.local').strip()
    if not smtp_host or not smtp_user or not smtp_password:
        app.logger.info('CrowdCab OTP for %s: %s', email, otp)
        return False
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = smtp_from
    message['To'] = email
    message.set_content(body)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)
    return True

def start_customer_otp(email, resend=False):
    otp = generate_otp()
    session['pending_auth'] = {
        'email': email,
        'otp': otp,
        'expires_at': otp_expiry().isoformat(),
    }
    try:
        sent = send_otp_email(email, otp)
    except Exception as exc:
        app.logger.warning('CrowdCab OTP email failed for %s: %s', email, exc)
        sent = False
    if sent:
        flash('A new code has been sent.' if resend else 'We sent a 6-digit CrowdCab code to your email.')
    elif os.getenv('SMTP_HOST', '').strip():
        flash(f'Email sending failed, so demo fallback is active. Use OTP {otp}.')
    else:
        prefix = 'A new demo code is ready.' if resend else 'Demo mode:'
        flash(f'{prefix} Use OTP {otp}. Configure SMTP in .env to send real email.')

def verify_customer_otp(otp):
    pending = valid_pending_auth() or {}
    email = pending.get('email')
    expected = pending.get('otp')
    expires_at = pending.get('expires_at')
    if not email or not expected or not expires_at:
        flash('Please request a new login code.')
        return False
    try:
        expired = datetime.utcnow() > datetime.fromisoformat(expires_at)
    except ValueError:
        expired = True
    if expired:
        session.pop('pending_auth', None)
        flash('That code expired. Please request a new one.')
        return False
    if otp != expected:
        flash('That code did not match. Please try again.')
        return False
    login_user(email, display_name_from_email(email), 'customer')
    return True

def read_csv(name, limit=None):
    path = os.path.join(DATA_DIR, name)
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            rows.append(row)
            if limit and i + 1 >= limit:
                break
    return rows

def db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'

def seed_table_from_csv(table_name, csv_name, primary_key=None, replace_existing=False):
    rows = read_csv(csv_name)
    if not rows:
        return

    columns = list(rows[0].keys())
    column_defs = []
    for column in columns:
        definition = f'{quote_identifier(column)} TEXT'
        if column == primary_key:
            definition += ' PRIMARY KEY'
        column_defs.append(definition)

    with db_connection() as conn:
        conn.execute(f'CREATE TABLE IF NOT EXISTS {quote_identifier(table_name)} ({", ".join(column_defs)})')
        existing = conn.execute(f'SELECT COUNT(*) FROM {quote_identifier(table_name)}').fetchone()[0]
        if existing and not replace_existing:
            return
        if existing and replace_existing:
            conn.execute(f'DELETE FROM {quote_identifier(table_name)}')

        placeholders = ', '.join(['?'] * len(columns))
        quoted_columns = ', '.join(quote_identifier(c) for c in columns)
        conn.executemany(
            f'INSERT INTO {quote_identifier(table_name)} ({quoted_columns}) VALUES ({placeholders})',
            [[row.get(column, '') for column in columns] for row in rows]
        )

def normalised_pickup_id(prefix, index, label):
    slug = ''.join(ch.lower() if ch.isalnum() else '_' for ch in label).strip('_')
    slug = '_'.join(part for part in slug.split('_') if part)
    return f'{prefix}_{index:03d}_{slug[:36] or "pickup"}'

def suncorp_pickup_rows_for_venue_table():
    rows = []
    for index, row in enumerate(read_csv('candidate_pickup_points.csv'), start=1):
        label = row.get('pickup_point_label') or row.get('street') or f'Suncorp Pickup {index}'
        rows.append({
            'venue_id': 'suncorp_stadium',
            'pickup_point_id': normalised_pickup_id('suncorp', index, label),
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
            'safety_score': '',
            'accessibility_score': '',
            'driver_access_score': '',
            'base_congestion_score': '',
            'notes': 'Imported from the original Suncorp candidate pickup dataset.',
        })
    return rows

def seed_venue_pickup_points():
    seed_table_from_csv(
        'venue_pickup_points',
        'venue_pickup_points.csv',
        'pickup_point_id',
        replace_existing=True
    )
    rows = suncorp_pickup_rows_for_venue_table()
    if not rows:
        return
    columns = list(rows[0].keys())
    quoted_columns = ', '.join(quote_identifier(c) for c in columns)
    placeholders = ', '.join(['?'] * len(columns))
    with db_connection() as conn:
        conn.executemany(
            f'INSERT OR REPLACE INTO venue_pickup_points ({quoted_columns}) VALUES ({placeholders})',
            [[row.get(column, '') for column in columns] for row in rows]
        )

def ensure_table_columns(table_name, columns):
    with db_connection() as conn:
        existing = {r['name'] for r in conn.execute(f'PRAGMA table_info({quote_identifier(table_name)})').fetchall()}
        for column, column_type in columns.items():
            if column not in existing:
                conn.execute(
                    f'ALTER TABLE {quote_identifier(table_name)} '
                    f'ADD COLUMN {quote_identifier(column)} {column_type}'
                )

def ensure_operational_tables():
    os.makedirs(DATA_DIR, exist_ok=True)
    seed_table_from_csv('venues', 'venues.csv', 'venue_id', replace_existing=True)
    seed_venue_pickup_points()
    seed_table_from_csv('bookings', 'bookings.csv', 'booking_id')
    seed_table_from_csv('cab_allocations', 'cab_allocations.csv', 'booking_id')
    ensure_table_columns('bookings', BOOKING_EXTRA_COLUMNS)

def read_table(table_name, limit=None):
    ensure_operational_tables()
    sql = f'SELECT * FROM {quote_identifier(table_name)}'
    params = []
    if limit:
        sql += ' LIMIT ?'
        params.append(limit)
    with db_connection() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]

def insert_booking(row):
    ensure_operational_tables()
    with db_connection() as conn:
        columns = [r['name'] for r in conn.execute('PRAGMA table_info(bookings)').fetchall()]
        insert_columns = [c for c in columns if c in row]
        quoted_columns = ', '.join(quote_identifier(c) for c in insert_columns)
        placeholders = ', '.join(['?'] * len(insert_columns))
        values = [row.get(c, '') for c in insert_columns]
        conn.execute(
            f'INSERT INTO bookings ({quoted_columns}) VALUES ({placeholders})',
            values
        )

def get_customer_bookings(email, limit=20):
    ensure_operational_tables()
    with db_connection() as conn:
        rows = conn.execute(
            '''
            SELECT *
            FROM bookings
            WHERE created_by_email = ?
            ORDER BY confirmed_at DESC, pickup_datetime DESC
            LIMIT ?
            ''',
            (email, limit)
        ).fetchall()
        return [dict(row) for row in rows]

# ---------- Data providers ----------
# These functions are the swap point for moving from CSV files to live APIs or a database.
def get_bookings(limit=None):
    return read_table('bookings', limit)

def get_allocations(limit=None):
    return read_table('cab_allocations', limit)

def get_candidate_pickup_points(limit=None):
    return read_csv('candidate_pickup_points.csv', limit)

def get_venues():
    return read_table('venues')

def get_venue(venue_id='suncorp_stadium'):
    venues = get_venues()
    for venue in venues:
        if venue.get('venue_id') == venue_id:
            return venue
    return {
        'venue_id': 'suncorp_stadium',
        'name': STADIUM['name'],
        'short_name': 'Suncorp',
        'latitude': STADIUM['lat'],
        'longitude': STADIUM['lng'],
        'default_radius_km': '1.0',
    }

def venue_map_anchor(venue):
    return {
        'venue_id': venue.get('venue_id', 'suncorp_stadium'),
        'name': venue.get('name') or 'Suncorp Stadium',
        'short_name': venue.get('short_name') or venue.get('name') or 'Venue',
        'lat': num(venue.get('latitude'), STADIUM['lat']),
        'lng': num(venue.get('longitude'), STADIUM['lng']),
    }

def get_congestion_points(limit=None):
    return read_csv('congestion_points.csv', limit)

def get_road_network_points(limit=None):
    return read_csv('road_network_points.csv', limit)

def num(v, default=0):
    try:
        if v is None or v == '':
            return default
        n = float(v)
        if math.isnan(n) or math.isinf(n):
            return default
        return n
    except Exception:
        return default

def km_between(a_lat, a_lng, b_lat, b_lng):
    R = 6371
    dlat = math.radians(b_lat-a_lat); dlng = math.radians(b_lng-a_lng)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(a_lat))*math.cos(math.radians(b_lat))*math.sin(dlng/2)**2
    return 2*R*math.atan2(math.sqrt(a), math.sqrt(1-a))

def crowd_band(bookings, eta):
    if bookings >= 55 or eta >= 8.5: return 'busy'
    if bookings >= 35 or eta >= 6: return 'medium'
    return 'easy'

def truthy(v):
    return str(v or '').strip().lower() in ['true', 'yes', '1']

def average(values, default=0):
    vals = [num(v, None) for v in values]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else default

def pickup_point_summary_rows(bookings=None, allocations=None):
    bookings = bookings if bookings is not None else get_bookings()
    allocations = allocations if allocations is not None else get_allocations()
    grouped = defaultdict(lambda: {
        'bookings': [],
        'people': [],
        'distance': [],
        'eta': [],
        'accessible': 0,
        'kids': 0,
    })

    for booking in bookings:
        zone = booking.get('pickup_location_name') or 'Unknown'
        grouped[zone]['bookings'].append(booking)
        grouped[zone]['people'].append(booking.get('number_of_people'))
        if truthy(booking.get('accessible_vehicle_required')):
            grouped[zone]['accessible'] += 1
        if truthy(booking.get('kids_under_5')) or num(booking.get('count_kids_under_5')) > 0:
            grouped[zone]['kids'] += 1

    for allocation in allocations:
        zone = allocation.get('pickup_location_name') or 'Unknown'
        grouped[zone]['distance'].append(allocation.get('distance_to_pickup_km'))
        grouped[zone]['eta'].append(allocation.get('estimated_arrival_to_pickup_min'))

    rows = []
    for zone, data in grouped.items():
        rows.append({
            'pickup_location_name': zone,
            'total_bookings': len(data['bookings']),
            'avg_people_per_booking': round(average(data['people']), 2),
            'avg_distance_to_pickup_km': round(average(data['distance']), 2),
            'avg_eta_min': round(average(data['eta'], 5), 2),
            'accessible_bookings': data['accessible'],
            'bookings_with_kids': data['kids'],
        })
    rows.sort(key=lambda r: (-r['total_bookings'], r['pickup_location_name']))
    return rows

def cab_company_summary_rows(bookings=None, allocations=None):
    bookings = bookings if bookings is not None else get_bookings()
    allocations = allocations if allocations is not None else get_allocations()
    grouped = defaultdict(lambda: {'bookings': 0, 'eta': [], 'distance': [], 'people': []})

    for booking in bookings:
        company = booking.get('cab_company_name') or 'Unknown'
        grouped[company]['bookings'] += 1
        grouped[company]['people'].append(booking.get('number_of_people'))

    for allocation in allocations:
        company = allocation.get('cab_company_name') or 'Unknown'
        grouped[company]['eta'].append(allocation.get('estimated_arrival_to_pickup_min'))
        grouped[company]['distance'].append(allocation.get('distance_to_pickup_km'))

    rows = []
    for company, data in grouped.items():
        rows.append({
            'cab_company_name': company,
            'total_bookings': data['bookings'],
            'avg_eta_min': round(average(data['eta']), 2),
            'avg_distance_to_pickup_km': round(average(data['distance']), 2),
            'avg_group_size': round(average(data['people']), 2),
        })
    rows.sort(key=lambda r: (-r['total_bookings'], r['cab_company_name']))
    return rows

def zone_fallback_coordinates():
    return {
        'Castlemaine St Pickup Zone': (-27.46392, 153.00872),
        'Caxton St Pickup Point': (-27.46360, 153.01159),
        'Milton Rd Pickup Bay': (-27.46672, 153.01109),
        'Heussler Tce Pickup Bay': (-27.46542, 153.00680),
        'Given Tce Pickup Point': (-27.46195, 153.00695),
        'Baroona Rd Pickup Point': (-27.46670, 153.00425),
        'Cribb St Pickup Bay': (-27.46755, 153.00630),
        'Upper Roma St Pickup Zone': (-27.46620, 153.01391),
        'Petrie Tce Pickup Point': (-27.46225, 153.01050),
        'Park Rd Pickup Zone': (-27.46865, 153.00480),
    }

def coordinates_from_bookings():
    grouped = defaultdict(lambda: {'lat': [], 'lng': []})
    for r in get_bookings():
        zone = r.get('pickup_location_name')
        lat = num(r.get('pickup_latitude'), None)
        lng = num(r.get('pickup_longitude'), None)
        if zone and lat and lng and -28 < lat < -27 and 152 < lng < 154:
            grouped[zone]['lat'].append(lat)
            grouped[zone]['lng'].append(lng)
    coords = {}
    for zone, vals in grouped.items():
        if vals['lat'] and vals['lng']:
            coords[zone] = (sum(vals['lat']) / len(vals['lat']), sum(vals['lng']) / len(vals['lng']))
    return coords

def pickup_recommendations():
    summary = pickup_point_summary_rows()
    booking_coords = coordinates_from_bookings()
    fallback = zone_fallback_coordinates()
    out = []
    for idx, r in enumerate(summary):
        zone = r.get('pickup_location_name') or f'Pickup Zone {idx+1}'
        lat, lng = booking_coords.get(zone, fallback.get(zone, (None, None)))
        if lat is None or lng is None:
            angle = (idx / max(len(summary), 1)) * (2 * math.pi)
            lat = STADIUM['lat'] + math.sin(angle) * 0.0048
            lng = STADIUM['lng'] + math.cos(angle) * 0.0056
        dist = km_between(STADIUM['lat'], STADIUM['lng'], lat, lng)
        eta = num(r.get('avg_eta_min'), 5)
        bookings = int(num(r.get('total_bookings'), 0))
        walk = max(2, round(dist * 12))
        band = crowd_band(bookings, eta)
        # decision score favours lower walk + lower ETA + lower crowd pressure
        score = (walk * 0.34) + (eta * 0.44) + (bookings * 0.025)
        out.append({
            'zone': zone,
            'label': zone.replace(' Pickup Zone','').replace(' Pickup Point','').replace(' Pickup Bay',''),
            'lat': round(lat, 6), 'lng': round(lng, 6),
            'bookings': bookings, 'eta': round(eta,1), 'walk_min': walk,
            'accessible': int(num(r.get('accessible_bookings'))),
            'kids': int(num(r.get('bookings_with_kids'))),
            'crowd': band,
            'score': round(score, 2),
            'why': 'short walk' if walk <= 3 else ('quicker cab' if eta <= 6.5 else 'balanced route')
        })
    out.sort(key=lambda x: x['score'])
    return out

def get_summary():
    bookings = get_bookings()
    allocations = get_allocations()
    pickup_counts = Counter(r.get('pickup_location_name','Unknown') for r in bookings)
    avg_eta = sum(num(r.get('estimated_arrival_to_pickup_min')) for r in allocations) / max(len(allocations), 1)
    accessible = sum(1 for r in bookings if truthy(r.get('accessible_vehicle_required')))
    top = pickup_counts.most_common(1)[0][0] if pickup_counts else 'No data'
    return {
        'total_bookings': len(bookings), 'active_cabs': len(allocations), 'avg_eta': round(avg_eta, 1),
        'top_pickup': top, 'accessible_requests': accessible, 'pickup_zones': len(pickup_counts)
    }

def cab_markers(limit=120):
    rows = get_allocations(limit)
    markers = []
    for r in rows:
        lat = num(r.get('cab_current_latitude'), None)
        lng = num(r.get('cab_current_longitude'), None)
        if lat and lng and -28 < lat < -27 and 152 < lng < 154:
            markers.append({
                'id': r.get('driver_id') or r.get('booking_id'),
                'company': r.get('cab_company_name','Cab'),
                'lat': lat, 'lng': lng,
                'eta': num(r.get('estimated_arrival_to_pickup_min')),
                'status': r.get('allocation_status','Assigned'),
                'vehicle': r.get('allocated_vehicle_make_model','Vehicle')
            })
    return markers

def build_booking_from_request(payload, email):
    now = datetime.now()
    booking_id = 'BK' + now.strftime('%m%d') + uuid4().hex[:6].upper()
    pickup_zone = payload.get('zone') or payload.get('pickup') or 'Suncorp Stadium Pickup'
    pickup_label = payload.get('pickup') or pickup_zone
    destination = payload.get('destination') or 'Destination not set'
    venue_id = payload.get('venue_id') or 'suncorp_stadium'
    venue_name = payload.get('venue_name') or get_venue(venue_id).get('name') or 'Suncorp Stadium'
    lat = payload.get('lat') or ''
    lng = payload.get('lng') or ''

    return {
        'customer_id': email,
        'booking_id': booking_id,
        'pickup_date': now.strftime('%Y-%m-%d'),
        'pickup_time': now.strftime('%I:%M %p'),
        'pickup_location_name': pickup_zone,
        'pickup_latitude': str(lat),
        'pickup_longitude': str(lng),
        'dropoff_suburb': destination,
        'dropoff_latitude': '',
        'dropoff_longitude': '',
        'number_of_people': str(payload.get('number_of_people') or 1),
        'kids_under_5': str(payload.get('kids_under_5') or 0),
        'count_kids_under_5': str(payload.get('count_kids_under_5') or 0),
        'accessible_vehicle_required': str(payload.get('accessible_vehicle_required') or 0),
        'special_requirements': payload.get('special_requirements') or 'None',
        'booking_channel': 'CrowdCab Web',
        'payment_method': payload.get('payment_method') or 'Not selected',
        'cab_company_name': payload.get('cab_company_name') or 'Pending allocation',
        'cab_company_id': payload.get('cab_company_id') or '',
        'pickup_time_parsed': now.strftime('%H:%M:%S'),
        'pickup_datetime': now.strftime('%Y-%m-%d %H:%M:%S'),
        'created_by_email': email,
        'venue_id': venue_id,
        'venue_name': venue_name,
        'destination': destination,
        'confirmed_pickup_label': pickup_label,
        'confirmed_walk_min': str(payload.get('walk_min') or ''),
        'confirmed_eta_min': str(payload.get('eta') or ''),
        'confirmed_crowd': payload.get('crowd') or '',
        'confirmed_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'booking_status': 'Confirmed',
    }

def trip_from_booking(row):
    return {
        'booking_id': row.get('booking_id'),
        'pickup': row.get('confirmed_pickup_label') or row.get('pickup_location_name'),
        'zone': row.get('pickup_location_name'),
        'lat': num(row.get('pickup_latitude'), None),
        'lng': num(row.get('pickup_longitude'), None),
        'walk_min': num(row.get('confirmed_walk_min')),
        'eta': num(row.get('confirmed_eta_min')),
        'crowd': row.get('confirmed_crowd') or 'Confirmed',
        'venue_id': row.get('venue_id') or 'suncorp_stadium',
        'venue_name': row.get('venue_name') or 'Suncorp Stadium',
        'destination': row.get('destination') or row.get('dropoff_suburb'),
        'confirmed_at': row.get('confirmed_at') or row.get('pickup_datetime'),
        'status': row.get('booking_status') or 'Confirmed',
    }

def dashboard_payload(kind):
    bookings = get_bookings()
    allocations = get_allocations()
    pickup_summary = pickup_point_summary_rows(bookings, allocations)
    companies = cab_company_summary_rows(bookings, allocations)
    congestion = get_congestion_points()
    roads = get_road_network_points(1600)
    summary = get_summary()

    def table(rows, columns, limit=32):
        return {'columns': columns, 'rows': [{c: r.get(c, '') for c in columns} for r in rows[:limit]]}

    if kind == 'bookings':
        by_channel = Counter(r.get('booking_channel', 'Unknown') for r in bookings)
        by_payment = Counter(r.get('payment_method', 'Unknown') for r in bookings)
        by_pickup = Counter(r.get('pickup_location_name', 'Unknown') for r in bookings)
        return {
            'summary': summary,
            'kpis': [
                {'label': 'Bookings', 'value': len(bookings)},
                {'label': 'Pickup zones', 'value': len(by_pickup)},
                {'label': 'Top pickup', 'value': summary['top_pickup']},
                {'label': 'Avg ETA', 'value': f"{summary['avg_eta']} min"},
            ],
            'bar': {'title': 'Booking channels', 'x': list(by_channel.keys()), 'y': list(by_channel.values())},
            'donut': {'title': 'Payment mix', 'labels': list(by_payment.keys()), 'values': list(by_payment.values())},
            'table': table(bookings, ['booking_id','pickup_location_name','dropoff_suburb','number_of_people','booking_channel','payment_method'], 38)
        }

    if kind == 'pickups':
        recs = pickup_recommendations()
        access_total = sum(int(num(r.get('accessible_bookings'))) for r in pickup_summary)
        top_pickup = max(pickup_summary, key=lambda r: int(num(r.get('total_bookings'))), default=None)
        top_zone = top_pickup.get('pickup_location_name') if top_pickup else 'No data'
        return {
            'kpis': [
                {'label': 'Pickup zones', 'value': len(pickup_summary)},
                {'label': 'Highest demand', 'value': top_zone},
                {'label': 'Accessible bookings', 'value': access_total},
                {'label': 'Avg ETA', 'value': f"{round(sum(x['eta'] for x in recs)/max(len(recs),1),1)} min"},
            ],
            'bar': {'title': 'Demand by pickup zone', 'x': [r['label'] for r in recs[:10]], 'y': [r['bookings'] for r in recs[:10]]},
            'donut': {'title': 'Accessibility share', 'labels': ['Accessible requests','Standard bookings'], 'values': [access_total, max(sum(r['bookings'] for r in recs)-access_total,0)]},
            'table': {'columns': ['zone','bookings','accessible','walk_min','eta','crowd'], 'rows': [{k: r.get(k,'') for k in ['zone','bookings','accessible','walk_min','eta','crowd']} for r in recs[:38]]}
        }

    if kind == 'congestion':
        by_type = Counter(r.get('element_type','Unknown') for r in congestion)
        by_signal = Counter('Traffic signals' if truthy(r.get('traffic_signals')) else 'Other congestion points' for r in congestion)
        high = sum(1 for r in congestion if truthy(r.get('traffic_signals')))
        crossings = sum(1 for r in congestion if r.get('crossing'))
        return {
            'kpis': [
                {'label': 'Congestion points', 'value': len(congestion)},
                {'label': 'Signal points', 'value': high},
                {'label': 'Crossings', 'value': crossings},
                {'label': 'Road types', 'value': len(set(r.get('highway','Unknown') for r in congestion))},
            ],
            'bar': {'title': 'Congestion point types', 'x': list(by_type.keys())[:10], 'y': list(by_type.values())[:10]},
            'donut': {'title': 'Signal pressure', 'labels': list(by_signal.keys()), 'values': list(by_signal.values())},
            'table': table(congestion, ['element_id','element_type','highway','crossing','traffic_signals','latitude','longitude'], 38)
        }

    if kind == 'cabs':
        by_status = Counter(r.get('allocation_status','Unknown') for r in allocations)
        avg_by_company = {r['cab_company_name']: r['avg_eta_min'] for r in companies}
        return {
            'summary': summary,
            'kpis': [
                {'label': 'Assigned cabs', 'value': len(allocations)},
                {'label': 'Avg ETA', 'value': f"{summary['avg_eta']} min"},
                {'label': 'Companies', 'value': len(companies)},
                {'label': 'Vehicle types', 'value': len(set(r.get('vehicle_type','Unknown') for r in allocations))},
            ],
            'bar': {'title': 'Average ETA by company', 'x': list(avg_by_company.keys()), 'y': list(avg_by_company.values())},
            'donut': {'title': 'Allocation status', 'labels': list(by_status.keys()), 'values': list(by_status.values())},
            'table': table(allocations, ['driver_id','cab_company_name','pickup_location_name','estimated_arrival_to_pickup_min','allocation_status','allocated_vehicle_make_model'], 38)
        }

    if kind == 'roads':
        by_highway = Counter(r.get('highway','Unknown') for r in roads)
        by_oneway = Counter('One-way' if truthy(r.get('oneway')) else 'Two-way / unknown' for r in roads)
        named = sum(1 for r in roads if r.get('name'))
        return {
            'kpis': [
                {'label': 'Road points', 'value': len(roads)},
                {'label': 'Named roads', 'value': named},
                {'label': 'Road categories', 'value': len(by_highway)},
                {'label': 'One-way points', 'value': by_oneway.get('One-way',0)},
            ],
            'bar': {'title': 'Road network by type', 'x': [x[0] for x in by_highway.most_common(10)], 'y': [x[1] for x in by_highway.most_common(10)]},
            'donut': {'title': 'Direction support', 'labels': list(by_oneway.keys()), 'values': list(by_oneway.values())},
            'table': table(roads, ['element_id','highway','name','maxspeed','lanes','oneway','latitude','longitude'], 38)
        }
    return {}

def clean(o):
    if isinstance(o, Counter): return dict(o)
    if isinstance(o, defaultdict): return dict(o)
    if isinstance(o, list): return [clean(x) for x in o]
    if isinstance(o, dict): return {k: clean(v) for k,v in o.items()}
    return o

# ---------- Public routes ----------
@app.context_processor
def inject_user():
    return {'user_role': current_role(), 'user_name': session.get('name'), 'dashboards': DASHBOARDS}

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.svg', mimetype='image/svg+xml')

@app.route('/')
def home(): return render_template('home.html', active='home')

@app.route('/map')
@login_required
def map_page(): return render_template('map.html', active='map')

@app.route('/how-it-works')
def how_it_works(): return redirect(url_for('home') + '#how')

@app.route('/safety')
def safety(): return redirect(url_for('home') + '#safety')

@app.route('/my-trips')
@login_required
def my_trips(): return render_template('my_trips.html', active='trips')

@app.route('/guidance')
@login_required
def guidance(): return render_template('guidance.html', active='trips')

# ---------- Auth routes ----------
@app.route('/login', methods=['GET','POST'])
def login():
    next_url = request.args.get('next')
    if request.method == 'POST':
        action = request.form.get('action', 'request_otp')
        pending = valid_pending_auth()

        if action == 'change_email':
            clear_pending_auth()
            flash('Enter the email address you want to use.')
            return redirect(url_for('login', next=next_url) if next_url else url_for('login'))

        if action == 'verify_otp':
            if not pending:
                flash('Please request a new login code.')
                return redirect(url_for('login', next=next_url) if next_url else url_for('login'))
            otp = request.form.get('otp','').strip()
            if verify_customer_otp(otp):
                return redirect(next_url or url_for('map_page'))

        elif action == 'resend_otp':
            if not pending:
                flash('Please enter your email to request a new code.')
                return redirect(url_for('login', next=next_url) if next_url else url_for('login'))
            start_customer_otp(pending['email'], resend=True)

        elif action == 'request_otp':
            email = (request.form.get('email') or '').strip().lower()
            email_error = email_validation_error(email)
            if email_error:
                flash(email_error)
            elif email in STAFF_USERS:
                user = STAFF_USERS[email]
                login_user(email, user['name'], user['role'])
                return redirect(next_url or url_for('internal_home'))
            else:
                start_customer_otp(email)

        else:
            flash('Please choose a valid login action.')

    pending = valid_pending_auth()
    return render_template('login.html', active='login', pending_auth=pending)

@app.route('/signin')
def signin():
    next_url = request.args.get('next')
    return redirect(url_for('login', next=next_url) if next_url else url_for('login'))

@app.route('/signup')
def signup():
    next_url = request.args.get('next')
    return redirect(url_for('login', next=next_url) if next_url else url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ---------- Internal routes ----------
@app.route('/internal')
@internal_required
def internal_home(): return render_template('internal.html', active='internal')

@app.route('/internal/dashboard')
@internal_required
def dashboard_hub(): return render_template('dashboard_hub.html', active='internal')

@app.route('/internal/dashboard/<kind>')
@internal_required
def dashboard(kind):
    meta = DASHBOARDS.get(kind, {'title':'Dashboard', 'short':'Internal view', 'icon':'●', 'style':'pulse'})
    return render_template('dashboard.html', active='internal', kind=kind, meta=meta)

@app.route('/internal/allocations')
@internal_required
def allocations(): return render_template('allocations.html', active='internal')

@app.route('/internal/system')
@internal_required
def system(): return render_template('system.html', active='internal')

# ---------- APIs ----------
@app.route('/api/summary')
def api_summary(): return jsonify(get_summary())

@app.route('/api/map-feed')
@login_required
def api_map_feed():
    ensure_operational_tables()
    venue_id = request.args.get('venue_id') or 'suncorp_stadium'
    user_lat = num(request.args.get('user_lat'), None)
    user_lng = num(request.args.get('user_lng'), None)
    venue = get_venue(venue_id)
    venue_anchor = venue_map_anchor(venue)
    scored = recommend_pickups(
        venue_id=venue_id,
        user_lat=user_lat,
        user_lng=user_lng,
        preferences={
            'priority': 'balanced',
            'max_walk_km': num(venue.get('default_radius_km'), DEFAULT_MAX_WALK_KM),
            'search_radius_km': 2.0,
            'result_limit': 'all',
        }
    )
    recs = [
        {
            'zone': p.get('pickup_point_id') or p.get('label'),
            'label': p.get('label'),
            'lat': p.get('latitude'),
            'lng': p.get('longitude'),
            'bookings': 0,
            'eta': max(4, round(num(p.get('walk_min'), 5) + (3 if num(p.get('congestion_score'), 60) < 50 else 1))),
            'walk_min': p.get('walk_min'),
            'accessible': round(num(p.get('accessibility_score'), 0)),
            'kids': 0,
            'crowd': 'easy' if num(p.get('congestion_score'), 70) >= 70 else 'medium' if num(p.get('congestion_score'), 70) >= 45 else 'busy',
            'score': p.get('total_score'),
            'total_score': p.get('total_score'),
            'congestion_score': p.get('congestion_score'),
            'safety_score': p.get('safety_score'),
            'accessibility_score': p.get('accessibility_score'),
            'driver_access_score': p.get('driver_access_score'),
            'nearby_qldtraffic_events_count': p.get('nearby_qldtraffic_events_count', 0),
            'live_traffic_note': p.get('live_traffic_note'),
            'reason': p.get('reason'),
            'why': p.get('reason') or 'balanced route',
        }
        for p in scored[:12]
    ]
    fastest = sorted(recs, key=lambda x: (x['eta'], x['walk_min']))[:8]
    quiet = sorted(recs, key=lambda x: (0 if x['crowd']=='easy' else 1 if x['crowd']=='medium' else 2, x['bookings'], x['walk_min']))[:8]
    accessible = sorted(recs, key=lambda x: (-x.get('accessible', 0), x['walk_min'], x['eta']))[:8]
    best = recs[:8]
    realtime = realtime_status(venue_anchor)
    return jsonify({
        'stadium': venue_anchor,
        'venue': venue_anchor,
        'user_location': {'lat': user_lat, 'lng': user_lng} if user_lat is not None and user_lng is not None else None,
        'venues': [venue_map_anchor(item) for item in get_venues()],
        'pickups': recs,
        'cabs': cab_markers(),
        'best': best,
        'fastest': fastest,
        'quiet': quiet,
        'accessible': accessible,
        'realtime': {
            'enabled': realtime['enabled'],
            'provider': realtime.get('provider'),
            'fallback_used': realtime['fallback_used'],
            'fallback_reason': realtime.get('fallback_reason'),
            'last_updated': realtime['last_updated'],
            'source': realtime.get('source'),
            'sources': realtime.get('sources'),
        },
        'traffic_events': realtime.get('events_near_venue') or realtime.get('events_near_suncorp') or [],
    })

@app.route('/api/recommend-pickups')
@login_required
def api_recommend_pickups():
    ensure_operational_tables()
    priority = request.args.get('priority', 'balanced')
    if priority not in WEIGHTS:
        priority = 'balanced'
    venue_id = request.args.get('venue_id') or 'suncorp_stadium'
    accessibility_required = str(request.args.get('accessibility_required', '')).lower() in ['true', '1', 'yes']
    max_walk_km = num(request.args.get('max_walk_km'), DEFAULT_MAX_WALK_KM)
    max_walk_km = min(max(max_walk_km, 0.2), 1.0)
    search_radius_km = num(request.args.get('search_radius_km'), 2.0)
    search_radius_km = min(max(search_radius_km, max_walk_km), 2.0)
    result_limit = int(num(request.args.get('limit'), 8))
    result_limit = min(max(result_limit, 7), 12)
    user_lat = num(request.args.get('user_lat'), None)
    user_lng = num(request.args.get('user_lng'), None)
    selected_pickup = {
        'label': request.args.get('selected_label') or request.args.get('selected_pickup'),
        'pickup': request.args.get('selected_label') or request.args.get('selected_pickup'),
        'zone': request.args.get('selected_zone'),
        'lat': num(request.args.get('selected_lat'), None),
        'lng': num(request.args.get('selected_lng'), None),
    }
    selected_pickup = {k: v for k, v in selected_pickup.items() if v not in [None, '']}

    all_recommendations = recommend_pickups(
        venue_id=venue_id,
        user_lat=user_lat,
        user_lng=user_lng,
        preferences={
            'priority': priority,
            'accessibility_required': accessibility_required,
            'max_walk_km': max_walk_km,
            'search_radius_km': search_radius_km,
            'result_limit': 'all',
        }
    )
    recommendations = all_recommendations[:result_limit]
    venue = get_venue(venue_id)
    venue_anchor = venue_map_anchor(venue)
    selected_origin_lat = user_lat if user_lat is not None else venue_anchor['lat']
    selected_origin_lng = user_lng if user_lng is not None else venue_anchor['lng']
    selected_scored = score_selected_pickup(
        selected_pickup,
        all_recommendations,
        WEIGHTS[priority],
        accessibility_required,
        origin_lat=selected_origin_lat,
        origin_lng=selected_origin_lng,
    ) if selected_pickup else None
    realtime = realtime_status(venue_anchor)
    return jsonify({
        'priority': priority,
        'venue_id': venue_id,
        'weights': WEIGHTS[priority],
        'accessibility_required': accessibility_required,
        'pickup_filter': {
            'focus_area': 'Suncorp Stadium' if venue_id == 'suncorp_stadium' else 'Queensland Tennis Centre',
            'max_walk_km': max_walk_km,
            'max_walk_m': round(max_walk_km * 1000),
            'search_radius_km': search_radius_km,
            'result_limit': result_limit,
            'goal': 'show the best 7-8 pickup options, mostly under 1 km, with fallback points up to 2 km only when useful',
        },
        'realtime': {
            'enabled': realtime['enabled'],
            'provider': realtime.get('provider'),
            'fallback_used': realtime['fallback_used'],
            'fallback_reason': realtime.get('fallback_reason'),
            'last_updated': realtime['last_updated'],
            'source': realtime.get('source'),
            'sources': realtime.get('sources'),
        },
        'selected_pickup': selected_scored,
        'recommended_pickup': recommendations[0] if recommendations else None,
        'best': recommendations[0] if recommendations else None,
        'alternatives': recommendations[1:4],
        'recommendations': recommendations,
        'candidate_pool_count': len(all_recommendations),
    })

@app.route('/api/realtime-traffic')
def api_realtime_traffic():
    venue_id = request.args.get('venue_id') or 'suncorp_stadium'
    return jsonify(realtime_status(venue_map_anchor(get_venue(venue_id))))

@app.route('/api/bookings', methods=['POST'])
def api_create_booking():
    email = session.get('email')
    if not email:
        return jsonify({'error': 'Log in before confirming a pickup.'}), 401

    payload = request.get_json(silent=True) or {}
    if not payload.get('zone') and not payload.get('pickup'):
        return jsonify({'error': 'Pickup zone is required.'}), 400

    booking = build_booking_from_request(payload, email)
    insert_booking(booking)
    return jsonify({'booking': trip_from_booking(booking)}), 201

@app.route('/api/my-trips')
@login_required
def api_my_trips():
    return jsonify({'trips': [trip_from_booking(row) for row in get_customer_bookings(session.get('email'))]})

@app.route('/api/dashboard/<kind>')
@internal_required
def api_dash(kind): return jsonify(clean(dashboard_payload(kind)))

@app.route('/api/allocations')
@internal_required
def api_allocations(): return jsonify({'rows': get_allocations(80), 'summary': dashboard_payload('cabs')})

@app.route('/api/system')
@internal_required
def api_system():
    ensure_operational_tables()
    files=[]
    for f in os.listdir(DATA_DIR):
        if f.endswith('.csv'):
            rows=read_csv(f)
            source = 'seed data' if f in ['bookings.csv', 'cab_allocations.csv'] else 'csv reference data'
            files.append({'file':f,'rows':len(rows),'columns':list(rows[0].keys())[:10] if rows else [], 'source': source})
    with db_connection() as conn:
        for table_name in ['venues', 'venue_pickup_points', 'bookings', 'cab_allocations']:
            rows = conn.execute(f'SELECT COUNT(*) FROM {quote_identifier(table_name)}').fetchone()[0]
            columns = [r['name'] for r in conn.execute(f'PRAGMA table_info({quote_identifier(table_name)})').fetchall()]
            source = 'sqlite reference table' if table_name in ['venues', 'venue_pickup_points'] else 'sqlite operational table'
            files.append({'file': table_name, 'rows': rows, 'columns': columns[:10], 'source': source})
    files.extend([
        {
            'file': 'pickup_point_summary',
            'rows': len(pickup_point_summary_rows()),
            'columns': ['pickup_location_name','total_bookings','avg_people_per_booking','avg_distance_to_pickup_km','avg_eta_min','accessible_bookings','bookings_with_kids'],
            'source': 'derived live from bookings + allocations',
        },
        {
            'file': 'cab_company_summary',
            'rows': len(cab_company_summary_rows()),
            'columns': ['cab_company_name','total_bookings','avg_eta_min','avg_distance_to_pickup_km','avg_group_size'],
            'source': 'derived live from bookings + allocations',
        },
    ])
    endpoints = [
        {'path':'/api/map-feed','purpose':'Customer pickup map and recommendations'},
        {'path':'/api/recommend-pickups','purpose':'Scored pickup guidance engine'},
        {'path':'/api/summary','purpose':'Top-level booking and fleet metrics'},
        {'path':'/api/dashboard/<kind>','purpose':'Role-gated internal dashboard data'},
        {'path':'/api/allocations','purpose':'Dispatcher allocation records'},
        {'path':'/api/system','purpose':'Dataset and API health check'},
    ]
    return jsonify({'files':files, 'endpoints': endpoints, 'flow':['Data providers','Derived live summaries','Flask JSON API','Customer map + internal tools'], 'roles':['customer','admin','developer']})

if __name__ == '__main__':
    app.run(debug=True)
