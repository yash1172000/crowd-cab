# CrowdCab Pickup Guidance MVP

CrowdCab is a Suncorp Stadium pickup guidance system for crowded event exits.

It is not a full cab booking, payment, or driver dispatch app. The MVP answers one user question:

```text
Where should I walk to get a cab more easily after an event?
```

The app recommends nearby pickup points using walking distance, live/open traffic context, congestion, safety, accessibility, and driver access.

## Features

- Suncorp Stadium focused pickup recommendations.
- Live map with stadium, pickup zones, congestion/events, cabs, and walking route.
- GPS-style walking guidance to the selected pickup point.
- Pickup ranking priorities: best, fastest, less crowded, and accessible.
- Customer pickup plan history.
- Internal dashboards for operational/demo data.
- Open-data traffic fallback model so the app keeps working if external APIs fail.

## Tech Stack

- Python 3
- Flask
- SQLite generated locally at runtime
- Vanilla JavaScript
- Leaflet maps
- Brisbane City Council open data and QLDTraffic when configured

## Project Structure

```text
app.py                         Flask routes and JSON APIs
recommendation_engine.py       Pickup scoring and ranking
realtime_traffic.py            Open-data/TomTom traffic integrations
data/                          CSV seed/reference data
templates/                     Jinja pages
static/css/styles.css          App styling and responsive layout
static/js/main.js              Shared frontend helpers
static/js/map.js               Live map logic
static/js/booking.js           Pickup confirmation flow
static/js/my_trips.js          Saved pickup plans
static/js/dashboard.js         Internal dashboard logic
static/js/guidance.js          GPS-style route guidance
static/js/app.js               Legacy placeholder after JS refactor
```

## Local Setup

1. Clone the project.

```bash
git clone <your-repo-url>
cd crowdcab_right_guidance_build-2
```

2. Create and activate a virtual environment.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Create a local environment file.

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

5. Update `.env` if you have API keys.

```text
ENABLE_REALTIME_TRAFFIC=True
REALTIME_PROVIDER=open_data
QLDTRAFFIC_API_KEY=your_qldtraffic_api_key_here
TOMTOM_API_KEY=your_tomtom_api_key_here
```

Traffic keys are optional for local development. If traffic APIs are missing, unavailable, or blocked, the app uses fallback scoring and still runs.

6. Start the app.

```bash
python app.py
```

7. Open the site.

```text
http://127.0.0.1:5000
```

## Demo Logins

```text
Customer:  customer@crowdcab.com / customer123
Admin:     admin@crowdcab.com / admin123
Developer: dev@crowdcab.com / dev123
```

## Data Notes

- `data/bookings.csv` and `data/cab_allocations.csv` seed the local SQLite database.
- `data/candidate_pickup_points.csv`, `data/congestion_points.csv`, and `data/road_network_points.csv` are local reference datasets.
- `data/crowdcab.sqlite` is generated automatically when the app runs and is intentionally ignored by git.
- `cab_company_summary` and `pickup_point_summary` are derived in code, not stored as static CSV dependencies.

## Useful Routes

```text
/                       Home page
/map                    Live pickup map
/guidance               GPS-style walking guidance
/my-trips               Customer pickup plans
/internal-dashboard     Internal dashboard hub
/allocations            Allocation view
/system                 System/data overview
/api/recommend-pickups  Pickup recommendation JSON
/api/realtime-traffic   Realtime traffic status JSON
/api/map-feed           Live map feed JSON
```

## Validation

Run these checks before committing:

```bash
python -m py_compile app.py realtime_traffic.py recommendation_engine.py
node --check static/js/*.js
```

If `node --check static/js/*.js` does not expand on your shell, run each JS file individually.

## Environment And Git Hygiene

The repository should commit source code, templates, static assets, and CSV seed/reference data.

Do not commit:

- `.env`
- generated SQLite databases
- `__pycache__`
- `.pyc` files
- local virtual environments
- zip archives or backup files

`.env.example` is safe to commit because it contains placeholders only.

## Traffic Data Troubleshooting

Open-data provider:

- Default provider is `open_data`.
- Brisbane City Council traffic volume and intersection location URLs are configured in `.env.example`.
- QLDTraffic can be configured with either `QLDTRAFFIC_GEOJSON_URL` or `QLDTRAFFIC_API_KEY`.
- If one source fails, CrowdCab uses any remaining source.
- If all traffic sources fail, CrowdCab falls back to static scoring.

TomTom provider:

- TomTom is optional and only used when `REALTIME_PROVIDER=tomtom`.
- TomTom Traffic API is separate from TomTom Traffic Stats/MOVE.
- HTTP 403 usually means the API key exists but is not authorised for the live Traffic API endpoint.

## Current Scope

Build a polished pickup guidance MVP for Suncorp Stadium first. Later expansion can add richer real-time event feeds, multi-venue support, stronger GPS navigation, and production user accounts.
