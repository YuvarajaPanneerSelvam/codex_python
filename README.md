# CampusRide — college bus transport

A responsive college transport application for phone, tablet and desktop browsers. All application layers are authored in Python: NiceGUI defines the interface and serves it through FastAPI; `transport.py` contains business rules and SQLite persistence. NiceGUI supplies the browser HTML/CSS/JavaScript internally; browsers do not execute Python directly.

## Features

- Student registration and sign-in, with salted scrypt password hashing and signed sessions.
- Routes, ordered stops, bus numbers, departure times, travel date and route/stop search.
- Date-specific seat reservations, passes and cancellation; atomic capacity checks prevent overbooking.
- Administrator-only route creation, route archiving and passenger lists.
- Daily bus QR check-in with numbered seats or standing status; seated claims cannot overlap.
- Foreground GPS updates from consenting checked-in riders; embedded OpenStreetMap/Leaflet bus map.
- Campus, bus-code and pickup-stop search, check-in based remaining seats, and an admin-only onboard roster.
- Persistent SQLite data and a database-backed `/health` readiness endpoint.
- Responsive layout for mobile and desktop. Optional native desktop window using pywebview.

## Run

Use Python **3.12**. This project was tested on Python 3.12.14 on Linux. Python 3.12.10 is expected to work but was not separately tested. Python 3.14 and Windows execution have not been validated here.

### Windows — VS Code PowerShell

Open the cloned repository folder in VS Code, then choose **Terminal → New Terminal**. Run each command separately from the folder containing `app.py` and `requirements.txt`.

For first-time setup:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

If `py -3.12` is not found, install Python 3.12, reopen VS Code, and retry. Check an existing environment with `.\.venv\Scripts\python.exe --version`. If it uses Python 3.14, stop the app, rename that `.venv` folder to an unused backup name, then create a new `.venv` using Python 3.12. Do not overwrite an existing backup or delete your source files or `data/`.

After pulling updates, if `.venv` already uses Python 3.12:

```powershell
git pull origin main
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

VS Code's **Pull** action can replace the first command when your branch tracks `origin/main`. The install and run commands still belong in PowerShell. Calling the environment's Python directly requires no activation script or PowerShell execution-policy change. `uvloop==0.23.0` is skipped on Windows because it is unsupported there; Uvicorn can use the standard `asyncio` event loop instead.

Once startup succeeds, open **http://localhost:8080** on that laptop. Stop the app with **Ctrl+C** before restarting it.

### Linux / macOS

From this repository:

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
| `PUBLIC_BASE_URL` | Public HTTPS app address used in boarding QR links; set before printing |
| `NATIVE_DESKTOP` | Set to 1 for optional desktop window mode |

Supply both admin variables for first startup, sign in with that account, and add routes under Administration. They provision a new account, never reset an existing password. Remove the password variable after provisioning. Preserve `data/` and `.nicegui/` across restarts, keep them private and out of version control, and back up the database. Changing the session secret invalidates existing sessions.

## Desktop window

On a local Windows, macOS or Linux computer with a graphical desktop:

```bash
.venv/bin/python -m pip install -r requirements-desktop.txt
```

Set `NATIVE_DESKTOP=1`, then run `app.py`. pywebview requires a supported OS webview backend (WebView2 on Windows, WebKit on macOS, GTK/Qt and associated system packages on Linux). Desktop packaging and native execution are not validated in the headless cloud environment.

## Mobile

The browser interface runs on Android and iOS and uses the same backend. This repository does not yet produce an Android APK, iOS binary or offline-installable PWA. Those require a separate packaging and device-validation step. Check-ins can share GPS about every 15 seconds while the browser page remains open and visible; background/locked-screen tracking is not guaranteed. A dedicated driver app, payments, notifications, email verification and password recovery are not included in this version. Registration is open; add college identity verification or SSO before a public college rollout. Departure times and booking dates use the server's local calendar; configure its timezone to match the college.

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

## Boarding QR and numbered seats

Each bus code has one active route and a destination campus. Admins can generate and download a daily QR as SVG from **Administration → Daily boarding QR**. Set `PUBLIC_BASE_URL` to your reachable HTTPS app address before generating the QR. Display it inside the bus on a screen, or replace the printed sheet daily. A permanently printed sticker cannot change by itself. Codes expire at the next server calendar day; configure the server timezone to match your college. Seats must be numbered from 1 to the configured capacity.

Scan the QR using the phone's camera/QR reader. It opens `/board`, asks you to sign in, then opens the bus check-in dialog. Choose your actual numbered seat, or standing only where permitted, and grant browser location permission. Desktop users can open or paste the scanned QR link. A current daily token for the correct bus is required. Expired and wrong-bus tokens are rejected. Concurrent check-ins cannot claim the same seat. A QR can be photographed or shared, so it is an access gate, not proof of physical presence; college identity verification remains necessary before public rollout.

Seats remaining = configured capacity minus today's seated check-ins. Standing riders are counted separately and do not consume numbered seats. The app does not authorize standing travel or enforce a standing capacity. A seat reservation is separate from an onboard check-in: **reservation slots** must not be confused with occupied seats. Checked-in accounts are self-reports, not verified headcounts. Only admins can see member names and seat assignments.

**End my check-in** or sign out when leaving. Switching buses releases the previous seat after a valid new check-in. GPS loss does not release a seat; membership persists for the rest of the calendar day unless checked out. At midnight seat claims expire and users must scan the new QR. Admins should reconcile forgotten check-outs operationally; there is no automated proof that someone left the bus.

## Foreground GPS and open-source maps

Explicit consent starts a GPS request about every 15 seconds while the page is open and visible. No separate GPS device or paid map key is needed. The user must keep location services, browser permission and internet enabled. The app cannot turn them on remotely. Reloading or closing the page stops foreground sharing; a saved check-in alone does not restart it. Check in again after reloading to resume.

The **Bus map** tab lets signed-in users select a bus by code, route and campus. It shows the newest contributor position, accuracy and age; the marker and occupancy refresh about every 15 seconds. Reports older than 60 seconds are marked delayed; reports older than 10 minutes are hidden. No report means unknown status, not a cancelled bus. Conflicting reports are not fused: the newest one wins, so GPS spoofing and malicious reports remain limitations. There is no route polyline, ETA calculation or automatic route matching yet.

Map rendering uses bundled open-source Leaflet with OpenStreetMap tiles and visible attribution. Tiles load only after **Load OpenStreetMap** is selected. The cloud environment must allow `tile.openstreetmap.org`; a blocked tile request leaves the base map unavailable even if GPS updates work. The saved configuration includes that hostname, but saving the draft does not apply network changes. Review/save settings and publish the environment to activate the prepared configuration.

Respect the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/): retain attribution, normal browser caching and Referer headers; do not bulk-download or prefetch tiles. The community service has no availability guarantee. For a large deployment, self-host tiles or choose a provider whose terms fit your load. Open-source libraries do not eliminate hosting, bandwidth or operational costs.

Browser geolocation requires HTTPS (localhost is allowed for development) and uses a minimal native JavaScript API bridge called from the Python UI. All business rules and persistence are Python. Real GPS, phone camera scanning and background behavior need physical-device testing. Browser tests use mocked GPS and tile responses and therefore do not establish real tile-server connectivity.

## Campus Hub modules

Select **Campus modules** in the transport header (or open `/campus`) after signing in. The same account and SQLite database are used. On startup the app adds the new tables without deleting existing transport accounts, routes, passes or check-ins. Back up `data/transport.db` before upgrading a deployment.

### First administrator on Windows

From the repository's VS Code PowerShell terminal, with the Python 3.12 environment already installed:

```powershell
.\.venv\Scripts\python.exe manage.py create-admin
.\.venv\Scripts\python.exe app.py
```

The first command privately prompts for the administrator's name, email and password (10 or more characters), including password confirmation. It creates a new account and never promotes or overwrites an existing account. You can alternatively provision an administrator with the existing environment-variable workflow. Sign in with that administrator, open **Campus modules → Access**, select an existing member and choose **Edit member access**.

### Permissions and audiences

Administrators can use all campus modules. They can independently grant **Energy access**, **Leave manager** and **Training manager** permissions to other accounts. Academic role (`student` or `staff`) and industry assignment are separate from those administrative permissions. Registered users cannot grant themselves roles or change their training audience. Energy reads and writes, leave reviews, training management and member assignments all enforce permissions in the Python service, not just through hidden UI elements.

### Campus Energy

Authorized users record manual daily readings per campus: green-energy source, production, campus consumption, battery charge/discharge, distribution/export, destination, losses, and the first reading's opening storage. All quantities are kWh, stored internally as integer Wh to avoid floating-point balance errors.

The ledger requires `production + discharge = consumption + charge + distribution + losses`. Stored balance is `opening + charge - discharge`; negative storage is rejected. Subsequent readings carry forward the last stored balance and must use a later date. One summary per campus per day is supported; entries are append-only, and backfilling/editing earlier readings is not implemented. Distribution requires a building/grid destination. This is accounting and monitoring from entered readings, not a physical system for generating, switching, charging or exporting electricity; no live meter, battery or inverter integration is included.

### Campus Time-sheet

This first phase covers regular/medical leave requests, a shared holiday calendar, campus rules text, review notes, approval/rejection and cancellation of your own pending request. Users see their own requests; leave managers see the approval desk. No one can approve their own request. Overlapping pending/approved requests are rejected. Working days currently mean Monday–Friday excluding configured holidays. Requests spanning only nonworking days are rejected; backdated requests are allowed for cases such as medical leave. Holiday dates overlapping pending or approved requests cannot be changed through this module.

Rules text is informational: it does not configure a quota engine, legal policy, medical-document verification or custom workweeks. There are no hourly timesheets, attendance devices, accrual balances, notifications or payroll calculations yet. Provide only necessary leave-reason details; do not upload medical reports. There is no public access to leave reasons.

### Campus Training

Training managers publish role-based courses (`student`, `staff`, `admin` or `all`) or industry-based courses matching the admin-assigned industry, such as manufacturing. Eligible users enroll and mark their own progress completed. Managers can see participation and archive courses; archived courses preserve prior enrollments. Completion is self-reported and does not issue a certification. Learning content delivery, assessment, external LMS integration and certificates are outside this phase.

### Campus Compute

A clearly marked **Requirements pending** tab reserves the module. Compute infrastructure, allocation, workloads, scheduling and billing have not been specified or implemented.

### Campus validation

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_campus.py tests/test_transport.py -q
```

The optional browser integration suite also exercises student leave submission and training progress, administrator leave approval, energy recording, and permission assignment. It runs with Linux system Chromium in the cloud; Windows, real devices and physical energy equipment have not been validated here.
