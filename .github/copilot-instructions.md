### Quick context — what this repo is

CrowdCab is a small Flask demo delivering a customer-facing event exit product and an internal dashboard for admins/developers. The UI uses server-side Jinja templates in `templates/` and static assets in `static/`. CSV files in `data/` are the authoritative dataset the app reads at runtime.

Key files:
- `app.py` — single-file Flask app: routes, helpers, demo users, API endpoints and CSV readers.
- `templates/` — Jinja2 templates for public pages (`home.html`, `map.html`) and internal pages (`internal.html`, `dashboard.html`, `allocations.html`, `system.html`).
- `static/js/app.js` and `static/css/styles.css` — client-side map rendering and styles.
- `data/*.csv` — datasets used by the app (bookings, allocations, pickup summaries, congestion, road network, companies).

Run locally:
- Install dependencies: `pip install -r requirements.txt`.
- Start: `python app.py` (app runs on http://127.0.0.1:5000 by default). `Procfile` shows `web: python app.py` for Heroku-style deploys.

Why this layout matters for code suggestions
- The app is intentionally single-file and data-driven. Most business logic lives in `app.py` (helpers like `pickup_recommendations`, `dashboard_payload`, CSV readers). Code completion should prefer small, focused edits in `app.py` rather than adding multi-file architectures.
- Templates assume context variables injected by `app.context_processor` and route handlers (see `inject_user()` and route functions). When changing template variables, update both the route and the template.
- Data is read from CSVs at request time using `read_csv`. Performance-sensitive changes should consider caching or precomputing instead of frequent file reads.

Patterns and conventions to follow
- Role gating: use `internal_required` decorator for any internal/admin routes (see how it checks `session['role']`). Mirror that pattern for new protected endpoints.
- CSV access: use `read_csv(name, limit=None)` for reading datasets. This function returns a list of dict rows and handles missing files gracefully (returns empty list).
- Numeric parsing: prefer `num(value, default)` helper to parse floats safely and avoid NaN/Inf issues used across helpers.
- Geospatial bounds: helper functions filter coordinates to a Brisbane/Suncorp Stadium bounding box (`-28 < lat < -27` and `152 < lng < 154`). Keep this check when adding new marker logic.
- Dashboard payloads: `dashboard_payload(kind)` returns a JSON-serializable dict for the internal UI. Add new views by updating `DASHBOARDS` and returning a matching shape in `dashboard_payload`.

API surface
- Public: `/api/map-feed`, `/api/summary` — used by the public map and recommendations.
- Internal (role-gated): `/api/dashboard/<kind>`, `/api/allocations`, `/api/system` — used by internal UI pages.

Examples (concrete edits)
- To add a new dashboard `ridership`: add an entry in `DASHBOARDS` and handle `if kind == 'ridership':` inside `dashboard_payload` returning `kpis`, `bar`, `donut`, and `table` keys.
- To expose a filtered CSV endpoint: add a new route that calls `read_csv('bookings.csv')`, filters rows (e.g., by `booking_channel`) and returns `jsonify({'rows': filtered})`.

Developer workflows and debugging tips
- Demo logins are defined in `DEMO_USERS` with clear credentials shown in `README.md` — use these to access internal pages.
- To debug templates, render smaller contexts from a temp route or use `print()`/`app.logger.debug()` in `app.py`. The app runs with `debug=True` when started with `python app.py`.
- When editing CSV columns, note `api_system()` lists columns for each CSV — use that endpoint to inspect current column names at runtime: `/api/system` (requires internal access).

Safety & production notes (discoverable facts)
- The secret `app.secret_key` is hard-coded for demo; do not rely on it for production. The app does not use a database — CSV files are the source of truth.

If you need more context
- Look at `static/js/app.js` for how the frontend consumes `/api/map-feed` and dashboard APIs (this will show expected JSON shapes and keys).
- Inspect `templates/dashboard.html` and `templates/dashboard_hub.html` for the fields expected from `dashboard_payload(kind)`.

If something isn't discoverable here (CI, custom deploy steps, caching, external APIs), ask the maintainer for the missing detail and include reproduction commands and any environment variables.

End of instructions — ask me to iterate if anything here is unclear or missing specific workflows.
