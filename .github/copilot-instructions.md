### Project scope

CrowdCab is a pickup guidance system for crowded event exits. It is not a full cab booking, dispatch, payment, or ride-hailing platform.

Current MVP focus:
- Location: Suncorp Stadium only.
- Event context: large post-event crowds, with future relevance to Brisbane Olympics 2032.
- User goal: answer "Where should I walk to get a cab more easily?"
- Core product: recommend nearby cab pickup spots and guide the user to the selected spot.

The app should help users compare pickup points by:
- walking distance
- congestion level
- safety
- accessibility and accessible vehicle suitability
- driver/cab access practicality

Avoid building these until the pickup guidance MVP is strong:
- full Uber-style booking system
- real driver dispatch
- payment
- cab company integration
- complex user accounts
- multi-city support
- Olympics-wide coverage

### Architecture snapshot

CrowdCab is a small Flask app with server-side Jinja templates and plain JavaScript.

Key files:
- `app.py` - Flask routes, auth, SQLite/CSV data providers, recommendation helpers, API payloads.
- `templates/` - Jinja pages for the public product and internal tools.
- `static/js/main.js` - shared frontend helpers.
- `static/js/map.js` - live map, pickup markers, pickup option rendering.
- `static/js/booking.js` - selected pickup confirmation and `POST /api/bookings`.
- `static/js/my_trips.js` - saved trip rendering from `/api/my-trips`.
- `static/js/dashboard.js` - internal dashboard, allocation, and system views.
- `static/js/guidance.js` - GPS-style walking guidance to the selected pickup point.
- `static/css/styles.css` - visual design.
- `data/crowdcab.sqlite` - local operational database for bookings and allocations.
- `data/*.csv` - seed/reference data for static or periodically refreshed layers.

### Data direction

The project is moving from static CSV data toward live-ready providers.

Current state:
- `bookings` and `cab_allocations` are SQLite operational tables seeded from CSV.
- pickup and cab company summaries are derived from live operational rows.
- road, congestion, and candidate pickup point datasets are still local reference CSVs.

Future real-time upgrade:
- pull live traffic/event data
- re-rank pickup points dynamically
- allow pickup recommendation changes as traffic and crowd conditions change

Do not jump to external traffic APIs before the local recommendation engine is clear and working.

### Recommendation engine priority

The next important feature is the pickup recommendation engine.

Create and maintain a scoring system similar to:

```text
pickup_score =
  walking_score
  + congestion_score
  + safety_score
  + accessibility_score
  + driver_access_score
```

The API should return:
- best pickup point
- reason why it was chosen
- alternative pickup options
- walking time
- congestion level
- safety/accessibility notes

This becomes the brain of the system. Frontend features should support this decision model instead of inventing separate ranking logic.

### Routes and API surface

Public:
- `/`
- `/map`
- `/guidance`
- `/my-trips`
- `/api/map-feed`
- `/api/summary`
- `/api/bookings`
- `/api/my-trips`

Internal role-gated:
- `/internal`
- `/internal/dashboard`
- `/internal/dashboard/<kind>`
- `/internal/allocations`
- `/internal/system`
- `/api/dashboard/<kind>`
- `/api/allocations`
- `/api/system`

### Coding conventions

- Keep the app plain Flask, Jinja, SQLite, and plain JavaScript.
- Do not introduce React or a new frontend framework.
- Prefer small, focused edits that preserve the existing page structure and CSS.
- Keep frontend files feature-based; do not rebuild `static/js/app.js`.
- Use provider functions in `app.py` instead of reading operational datasets directly.
- Use `num(value, default)` for safe numeric parsing.
- Keep Suncorp/Brisbane coordinate bounds when adding map markers.
- Internal routes must use `internal_required`.

### Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

Demo logins:

```text
Customer: customer@crowdcab.com / customer123
Admin: admin@crowdcab.com / admin123
Developer: dev@crowdcab.com / dev123
```
