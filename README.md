# CampusRide — college bus transport

A responsive college transport application for phone, tablet and desktop browsers. All application layers are authored in Python: NiceGUI defines the interface and serves it through FastAPI; `transport.py` contains business rules and SQLite persistence. NiceGUI supplies the browser HTML/CSS/JavaScript internally; browsers do not execute Python directly.

## Features

- Student registration and sign-in, with salted scrypt password hashing and signed sessions.
- Routes, ordered stops, bus numbers, departure times, travel date and route/stop search.
- Date-specific seat reservations, passes and cancellation; atomic capacity checks prevent overbooking.
- Administrator-only route creation, route archiving and passenger lists.
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

The browser interface runs on Android and iOS and uses the same backend. This repository does not yet produce an Android APK, iOS binary or offline-installable PWA. Those require a separate packaging and device-validation step. No live GPS tracking, driver app, payments, notifications, email verification or password recovery are included in this first version. Registration is open; add college identity verification or SSO before a public college rollout. Departure times and booking dates use the server's local calendar; configure its timezone to match the college.

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
