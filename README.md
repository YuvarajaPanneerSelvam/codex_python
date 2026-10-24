# CampusRide — college bus transport

A responsive college transport application for phone, tablet and desktop browsers. All application layers are authored in Python: NiceGUI defines the interface and serves it through FastAPI; `transport.py` contains business rules and SQLite persistence. NiceGUI supplies the browser HTML/CSS/JavaScript internally; browsers do not execute Python directly.

## Features

- Student registration and sign-in, with salted scrypt password hashing and signed sessions.
- Routes, ordered stops, bus numbers, departure times, travel date and route/stop search.
- Date-specific seat reservations, passes and cancellation; atomic capacity checks prevent overbooking.
- Administrator-only route creation, route archiving and passenger lists.
- Voluntary bus check-ins: any signed-in student, driver or staff member can report their current location without a seat booking.
- Persistent SQLite data and a database-backed `/health` readiness endpoint.
- Responsive layout for mobile and desktop. Optional native desktop window using pywebview.

## Run

Requires Python 3.12 or newer. From this repository:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open port 8080 in a browser. On another device, use the host's reachable address, not that device's localhost. For Internet access, deploy behind an HTTPS reverse proxy with WebSocket support. Keep one application worker with SQLite; migrate to a shared database before horizontal scaling.

The initial database is empty: configure an administrator, then add your college's real routes. No default administrator password or fictional routes are installed.

Set configuration in your shell or hosting provider before startup (a `.env` file is **not** automatically loaded):

| Variable | Purpose |
| --- | --- |
| `COLLEGE_NAME` | College name shown in the header; defaults to Your College |
| `COLLEGE_ADMIN_EMAIL` | Initial administrator email |
| `COLLEGE_ADMIN_PASSWORD` | Initial administrator password, at least 10 characters |
| `TRANSPORT_DB` | SQLite path; defaults to data/transport.db |
| `SESSION_SECRET` | Optional stable random signing secret; otherwise generated in data/session_secret |
| `HOST` / `PORT` | Bind address / port; defaults to 0.0.0.0 / 8080 |
| `NATIVE_DESKTOP` | Set to 1 for optional desktop window mode |

Supply both admin variables for first startup, sign in with that account, and add routes under Administration. They provision a new account, never reset an existing password. Remove the password variable after provisioning. Preserve `data/` and `.nicegui/` across restarts, keep them private and out of version control, and back up the database. Changing the session secret invalidates existing sessions.

## Desktop window

On a local Windows, macOS or Linux computer with a graphical desktop:

```bash
.venv/bin/python -m pip install -r requirements-desktop.txt
```

Set `NATIVE_DESKTOP=1`, then run `app.py`. pywebview requires a supported OS webview backend (WebView2 on Windows, WebKit on macOS, GTK/Qt and associated system packages on Linux). Desktop packaging and native execution are not validated in the headless cloud environment.

## Mobile

The browser interface runs on Android and iOS and uses the same backend. This repository does not yet produce an Android APK, iOS binary or offline-installable PWA. Those require a separate packaging and device-validation step. Check-ins share a single GPS snapshot, not continuous live tracking. A dedicated driver app, payments, notifications, email verification and password recovery are not included in this version. Registration is open; add college identity verification or SSO before a public college rollout. Departure times and booking dates use the server's local calendar; configure its timezone to match the college.

## Tests

```bash
.venv/bin/python -m pytest tests/test_transport.py -q
```

For browser integration checks with a system Chromium installation:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/test_ui.py -q
```

Browser tests start an isolated server and database and check desktop/mobile rendering, sign-in, reservations, cancellations, and admin route creation. Set `CHROMIUM_PATH` if Chromium is not at `/usr/bin/chromium`; otherwise the browser test skips explicitly.

## Community bus location reports

On a route card for today, sign in and select **I am on this bus · Check in**, confirm that you are aboard, then allow browser location permission. Students, drivers and staff can all contribute using a registered account; a seat booking is not required. Drivers should only interact with the app while safely stopped.

A check-in shares the phone/computer's current coordinates with signed-in users for 10 minutes. The route card shows the most recent report, its age, GPS accuracy and an OpenStreetMap link. Reporter identity is not displayed. Reports are community submissions: they do not verify that the person is aboard, prove bus movement, or calculate arrival time. No recent report means unknown status, not a cancelled bus. Tap Refresh to retrieve updated reports; there is no automatic background tracking.

Check in again to update the location. One account can report on only one route at a time. **End my check-in** deletes your report; signing out also removes it. Expired reports are hidden immediately by the read query and are deleted on the next check-in. Only the latest snapshot per contributor is retained, not a location history. Archiving a route hides its reports. Devices must provide finite coordinates and an accuracy radius within 1 km.

Geolocation requires HTTPS (or localhost during development) and device permission. Browser geolocation uses a small native JavaScript API bridge invoked from the Python interface; no separate frontend project is required. The rest of the feature, including access control, validation, expiry and persistence, is Python. Opening the map contacts OpenStreetMap; no map request occurs before clicking its link. Browser integration tests use mocked coordinates; real GPS accuracy and permissions still require testing on a physical phone.
