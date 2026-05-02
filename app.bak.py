from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
import csv, os, math, json
from collections import Counter, defaultdict
from functools import wraps

app = Flask(__name__)
app.secret_key = 'crowdcab-demo-secret-change-for-production'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STADIUM = {'name':'Suncorp Stadium', 'lat':-27.4648, 'lng':153.0095}

DEMO_USERS = {
    'customer@crowdcab.com': {'name': 'Demo Customer', 'password': 'customer123', 'role': 'customer'},
    'admin@crowdcab.com': {'name': 'Admin User', 'password': 'admin123', 'role': 'admin'},
    'dev@crowdcab.com': {'name': 'Developer User', 'password': 'dev123', 'role': 'developer'},
}

DASHBOARDS = {
    'bookings': {'title': 'Booking Pulse', 'short': 'Demand, channels, and peak movement.', 'icon': '●', 'style': 'pulse'},
    'pickups': {'title': 'Pickup Demand', 'short': 'Which pickup zones need attention.', 'icon': '◆', 'style': 'rank'},
    'congestion': {'title': 'Congestion Watch', 'short': 'Crowd and road pressure near the stadium.', 'icon': '▲', 'style': 'alert'},
    'cabs': {'title': 'Cab Readiness', 'short': 'Fleet availability and ETA signals.', 'icon': '■', 'style': 'fleet'},
    'roads': {'title': 'Route Network', 'short': 'Movement support around Suncorp.', 'icon': '═', 'style': 'route'},
}

# ---------- Helpers ----------
def current_role():
    return session.get('role', 'guest')

def internal_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_role() not in ['admin', 'developer']:
            flash('Internal pages require admin or developer access.')
            return redirect(url_for('signin', next=request.path))
        return fn(*args, **kwargs)
    return wrapper

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

def num(v, default=0):
    try:
        if v is None or v == '':
            return default
        return float(v)
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
    for r in read_csv('bookings.csv'):
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
    summary = read_csv('pickup_point_summary.csv')
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
    bookings = read_csv('bookings.csv')
    allocations = read_csv('cab_allocations.csv')
    pickup_counts = Counter(r.get('pickup_location_name','Unknown') for r in bookings)
    avg_eta = sum(num(r.get('estimated_arrival_to_pickup_min')) for r in allocations) / max(len(allocations), 1)
    accessible = sum(1 for r in bookings if str(r.get('accessible_vehicle_required','')).lower() in ['true','yes','1'])
    top = pickup_counts.most_common(1)[0][0] if pickup_counts else 'No data'
    return {
        'total_bookings': len(bookings), 'active_cabs': len(allocations), 'avg_eta': round(avg_eta, 1),
        'top_pickup': top, 'accessible_requests': accessible, 'pickup_zones': len(pickup_counts)
    }

def cab_markers(limit=120):
    rows = read_csv('cab_allocations.csv', limit)
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

def dashboard_payload(kind):
    bookings = read_csv('bookings.csv')
    allocations = read_csv('cab_allocations.csv')
    pickup_summary = read_csv('pickup_point_summary.csv')
    companies = read_csv('cab_company_summary.csv')
    if kind == 'bookings':
        by_channel = Counter(r.get('booking_channel','Unknown') for r in bookings)
        by_pickup_time = Counter((r.get('pickup_time') or '')[:2] + ':00' for r in bookings if r.get('pickup_time'))
        return {'summary': get_summary(), 'channel': dict(by_channel), 'timeline': dict(sorted(by_pickup_time.items())), 'rows': bookings[:28]}
    if kind == 'pickups':
        recs = pickup_recommendations()
        return {'recommendations': recs, 'points': pickup_summary}
    if kind == 'congestion':
        congestion = read_csv('congestion_points.csv')
        groups = Counter(r.get('highway') or r.get('crossing') or r.get('element_type','Other') for r in congestion)
        return {'type_counts': groups.most_common(8), 'points': congestion[:160]}
    if kind == 'cabs':
        by_status = Counter(r.get('allocation_status','Unknown') for r in allocations)
        return {'summary': get_summary(), 'companies': companies, 'status': dict(by_status), 'rows': allocations[:40]}
    if kind == 'roads':
        roads = read_csv('road_network_points.csv', 1200)
        by_highway = Counter(r.get('highway','Unknown') for r in roads)
        return {'highway': by_highway.most_common(8), 'points': roads[:260]}
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

@app.route('/')
def home(): return render_template('home.html', active='home')

@app.route('/map')
def map_page(): return render_template('map.html', active='map')

@app.route('/how-it-works')
def how_it_works(): return redirect(url_for('home') + '#how')

@app.route('/safety')
def safety(): return redirect(url_for('home') + '#safety')

@app.route('/my-trips')
def my_trips(): return render_template('my_trips.html', active='trips')

# ---------- Auth routes ----------
@app.route('/signin', methods=['GET','POST'])
def signin():
    if request.method == 'POST':
        email = request.form.get('email','').strip().lower()
        password = request.form.get('password','')
        user = DEMO_USERS.get(email)
        if user and user['password'] == password:
            session['email'] = email; session['name'] = user['name']; session['role'] = user['role']
            return redirect(request.args.get('next') or (url_for('internal_home') if user['role'] in ['admin','developer'] else url_for('map_page')))
        flash('Use one of the demo logins shown below.')
    return render_template('signin.html', active='signin')

@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'POST':
        session['email'] = request.form.get('email','customer@crowdcab.com')
        session['name'] = request.form.get('name','CrowdCab Rider')
        session['role'] = 'customer'
        return redirect(url_for('map_page'))
    return render_template('signup.html', active='signup')

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
def api_map_feed():
    recs = pickup_recommendations()
    fastest = sorted(recs, key=lambda x: x['eta'])[:3]
    safest = sorted(recs, key=lambda x: (0 if x['crowd']=='easy' else 1 if x['crowd']=='medium' else 2, x['bookings']))[:3]
    return jsonify({'stadium': STADIUM, 'pickups': recs, 'cabs': cab_markers(), 'best': recs[:3], 'fastest': fastest, 'safest': safest})

@app.route('/api/dashboard/<kind>')
@internal_required
def api_dash(kind): return jsonify(clean(dashboard_payload(kind)))

@app.route('/api/allocations')
@internal_required
def api_allocations(): return jsonify({'rows': read_csv('cab_allocations.csv', 80), 'summary': dashboard_payload('cabs')})

@app.route('/api/system')
@internal_required
def api_system():
    files=[]
    for f in os.listdir(DATA_DIR):
        if f.endswith('.csv'):
            rows=read_csv(f)
            files.append({'file':f,'rows':len(rows),'columns':list(rows[0].keys())[:10] if rows else []})
    return jsonify({'files':files, 'flow':['CSV data','Flask API','Role-gated pages','Customer map product']})

if __name__ == '__main__':
    app.run(debug=True)
