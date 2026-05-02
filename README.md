# CrowdCab Premium Build

Customer-facing transport product for Suncorp Stadium event exits.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Main design direction

The public website is now customer-first:

- Home/Ride: premium split layout with destination input and live map preview
- Live Map: main product screen with full-map experience and floating recommendations
- How it works and Safety: integrated into the homepage instead of weak standalone pages
- Internal: dashboards, allocations and system pages are protected behind admin/developer login

## Demo logins

```text
Customer: customer@crowdcab.com / customer123
Admin: admin@crowdcab.com / admin123
Developer: dev@crowdcab.com / dev123
```

## Edit guide

- `templates/home.html` – homepage / product landing page
- `templates/map.html` – main Live Map product page
- `static/css/styles.css` – visual design
- `static/js/app.js` – map, recommendations and dashboard rendering
- `app.py` – routes, role-gating, backend APIs
- `data/*.csv` – cleaned CrowdCab datasets
