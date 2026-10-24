"""Python-authored responsive interface served by NiceGUI/FastAPI."""
import os
from datetime import date
from pathlib import Path
import secrets
import time
from urllib.parse import parse_qs, urlsplit

import qrcode
from qrcode.image.svg import SvgPathImage

from nicegui import app, ui
from transport import Transport, bootstrap

service = Transport(os.getenv('TRANSPORT_DB', 'data/transport.db'))
bootstrap(service)
secret_path = Path('data/session_secret')
secret_path.parent.mkdir(exist_ok=True)
if not secret_path.exists():
    fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(secrets.token_urlsafe(48))


@app.get('/health')
def health():
    with service.connection() as db:
        db.execute('SELECT 1').fetchone()
    return {'status': 'ok'}


async def current_position():
    position = await ui.run_javascript('''return await new Promise(resolve => {
        if (!navigator.geolocation) {
            resolve({error: 'Location is unavailable. Use a supported browser over HTTPS.'});
            return;
        }
        navigator.geolocation.getCurrentPosition(
            p => resolve({latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: p.coords.accuracy}),
            e => resolve({error: e.code === 1 ? 'Location permission was denied. Allow location in browser settings to check in.' : 'Could not obtain your location. Try again where GPS is available.'}),
            {enableHighAccuracy: true, maximumAge: 0, timeout: 10000});
    });''', timeout=15)
    if not position or position.get('error'):
        raise ValueError((position or {}).get('error', 'Location is unavailable.'))
    return position


@ui.page('/board')
def board(token: str = ''):
    try:
        service.route_for_qr(token)
    except ValueError as exc:
        ui.label(str(exc))
        ui.link('Back to transport app', '/')
        return
    app.storage.user['pending_bus_token'] = token
    ui.navigate.to('/')


@ui.page('/')
def home():
    ui.colors(primary='#12685e', secondary='#e5a23c', accent='#12685e')
    ui.query('body').classes('bg-slate-50 text-slate-800')
    user = service.user(app.storage.user.get('user_id'))
    college = os.getenv('COLLEGE_NAME', 'Your College')
    tracking = {'route_id': None, 'busy': False, 'generation': 0, 'status': 'Location sharing is off.'}

    def action(callback, success=None):
        try:
            callback()
            if success:
                ui.notify(success, type='positive')
            content.refresh()
        except ValueError as exc:
            ui.notify(str(exc), type='warning')

    def logout():
        tracking['route_id'] = None
        tracking['generation'] += 1
        if user:
            service.check_out(user['id'])
        app.storage.user.clear()
        ui.navigate.to('/')

    with ui.header().classes('bg-white text-slate-800 shadow-none border-b border-slate-200'):
        with ui.row().classes('w-full max-w-6xl mx-auto items-center justify-between py-2'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('directions_bus', size='32px').classes('text-teal-700')
                with ui.column().classes('gap-0'):
                    ui.label('CampusRide').classes('text-xl font-bold')
                    ui.label(college + ' · College transport').classes('text-xs text-slate-500')
            if user:
                with ui.row().classes('items-center gap-2'):
                    ui.label(user['name']).classes('text-sm')
                    ui.button('Sign out', on_click=logout).props('flat dense')

    def auth_dialog():
        with ui.dialog() as dialog, ui.card().classes('w-96 max-w-full p-6'):
            ui.label('Welcome aboard').classes('text-2xl font-bold')
            ui.label('Sign in or create a student account.').classes('text-slate-500')
            with ui.tabs().classes('w-full') as tabs:
                sign_in = ui.tab('Sign in')
                register = ui.tab('Create account')
            with ui.tab_panels(tabs, value=sign_in).classes('w-full'):
                with ui.tab_panel(sign_in).classes('px-0'):
                    email = ui.input('College email').props('type=email outlined').classes('w-full')
                    password = ui.input('Password', password=True, password_toggle_button=True).props('outlined').classes('w-full')
                    def login():
                        try:
                            person = service.authenticate(email.value, password.value)
                            app.storage.user['user_id'] = person['id']
                            ui.navigate.to('/')
                        except ValueError as exc:
                            ui.notify(str(exc), type='warning')
                    ui.button('Sign in', on_click=login).classes('w-full mt-3')
                with ui.tab_panel(register).classes('px-0'):
                    name = ui.input('Full name').props('outlined').classes('w-full')
                    new_email = ui.input('College email').props('type=email outlined').classes('w-full')
                    new_password = ui.input('Password (10+ characters)', password=True, password_toggle_button=True).props('outlined').classes('w-full')
                    def signup():
                        try:
                            user_id = service.register(name.value, new_email.value, new_password.value)
                            app.storage.user['user_id'] = user_id
                            ui.navigate.to('/')
                        except ValueError as exc:
                            ui.notify(str(exc), type='warning')
                    ui.button('Create student account', on_click=signup).classes('w-full mt-3')
        dialog.open()

    with ui.column().classes('w-full max-w-6xl mx-auto px-4 md:px-8 py-8 gap-6'):
        with ui.row().classes('w-full items-center justify-between gap-6'):
            with ui.column().classes('gap-2'):
                ui.label('A better way to campus.').classes('text-3xl md:text-5xl font-bold tracking-tight')
                ui.label('Find your route. Reserve your seat. Arrive ready.').classes('text-base text-slate-500')
            if not user:
                ui.button('Student / admin sign in', icon='login', on_click=auth_dialog).props('unelevated rounded')
        with ui.card().classes('w-full bg-teal-900 text-white p-6 shadow-none rounded-2xl'):
            ui.label('YOUR DAILY JOURNEY, SIMPLIFIED').classes('text-xs tracking-widest text-teal-200')
            ui.label('Campus connections').classes('text-2xl font-semibold')
            ui.label('Browse college bus services and book a seat for your travel date.').classes('text-teal-100')

        with ui.tabs().classes('w-full justify-start') as sections:
            routes_tab = ui.tab('Routes & schedules', icon='route')
            bookings_tab = ui.tab('My bookings', icon='confirmation_number')
            tracking_tab = ui.tab('Bus map', icon='map')
            admin_tab = ui.tab('Administration', icon='admin_panel_settings') if user and user['role'] == 'admin' else None

        selected_day = {'value': date.today().isoformat()}
        search = {'value': ''}

        def checkin_dialog(route, scanned_token=''):
            if not user:
                auth_dialog()
                return
            with ui.dialog() as dialog, ui.card().classes('w-96 max-w-full p-6'):
                ui.label(f"On board {route['bus']}?").classes('text-xl font-semibold')
                ui.label('Drivers, students and staff can all report a bus location. Only check in while you are on this bus. Drivers must stop safely before using the app.')
                ui.label('Share GPS about every 15 seconds while this page stays open and visible. Signed-in users see the bus position; transport admins can see who checked in. Location permission and internet are required. End your check-in when you leave. Closing the page stops updates but keeps your check-in listed as stale.').classes('text-slate-500')
                current = service.active_session(user['id'])
                seating = ui.select({'seated': 'I am seated', 'standing': 'I am standing (only where permitted)'}, value=current['seating'] if current and current['route_id'] == route['id'] else 'seated', label='Seat status').classes('w-full')
                ui.label('Scan the daily QR displayed inside this bus using your phone camera. It opens this app; sign in, then select the numbered seat you occupy. You can also paste the scanned link below.').classes('text-sm')
                qr_input = ui.input('Daily bus QR token or link', value=scanned_token, password=True, password_toggle_button=True).classes('w-full')
                seats = service.available_seats(user['id'], route['id'])
                selected_seat = current['seat_number'] if current and current['route_id'] == route['id'] and current['seat_number'] in seats else next(iter(seats), None)
                seat = ui.select({n: f'Seat {n}' for n in seats}, label='Your seat number', value=selected_seat).classes('w-full')
                seat.bind_visibility_from(seating, 'value', backward=lambda v: v == 'seated')

                async def share():
                    share_button.disable()
                    try:
                        raw = (qr_input.value or '').strip()
                        token = parse_qs(urlsplit(raw).query).get('token', [raw])[0]
                        if service.route_for_qr(token)['id'] != route['id']:
                            raise ValueError('This QR belongs to another bus. Scan the code on this bus.')
                        # Browser geolocation requires its native JavaScript API; all
                        # application logic, validation and persistence remain Python.
                        generation = tracking['generation']
                        position = await current_position()
                        if generation != tracking['generation']:
                            raise ValueError('Location sharing was stopped.')
                        if app.storage.user.get('user_id') != user['id']:
                            raise ValueError('Sign in again before sharing location.')
                        service.check_in(user['id'], route['id'], position['latitude'], position['longitude'], position['accuracy'], seating=seating.value, seat_number=seat.value, qr_token=token)
                        app.storage.user.pop('pending_bus_token', None)
                        dialog.close()
                        tracking['route_id'] = route['id']
                        tracking['status'] = f"Sharing GPS for bus {route['bus']} while this page is visible."
                        ui.notify('Checked in. GPS updates while this page stays open.', type='positive')
                        content.refresh()
                    except (ValueError, TimeoutError) as exc:
                        ui.notify(str(exc) or 'Location request timed out. Please try again.', type='warning')
                    finally:
                        share_button.enable()
                share_button = ui.button('Start sharing bus location', icon='my_location', on_click=share)
                ui.button('Not now', on_click=dialog.close).props('flat')
            dialog.open()

        def end_checkin():
            tracking['route_id'] = None
            tracking['generation'] += 1
            tracking['status'] = 'Location sharing is off.'
            action(lambda: service.check_out(user['id']), 'Checked out. Location sharing stopped.')

        async def update_gps():
            route_id = tracking['route_id']
            if not route_id or tracking['busy']:
                return
            tracking['busy'] = True
            generation = tracking['generation']
            try:
                visible = await ui.run_javascript('return document.visibilityState === "visible";', timeout=3)
                if not visible:
                    tracking['status'] = 'GPS paused while this page is hidden. Keep it open to share.'
                    return
                position = await current_position()
                if generation != tracking['generation'] or app.storage.user.get('user_id') != user['id']:
                    return
                service.check_in(user['id'], route_id, position['latitude'], position['longitude'], position['accuracy'], require_active=True)
                tracking['status'] = 'GPS updated. Keep this page visible and internet connected.'
            except (ValueError, TimeoutError) as exc:
                tracking['status'] = str(exc) or 'GPS update failed. Check location permission and internet.'
            finally:
                tracking['busy'] = False

        if user:
            ui.label().bind_text_from(tracking, 'status').classes('text-sm text-teal-700')
            prior = service.active_session(user['id'])
            if prior:
                ui.label(f"You are checked in on bus {prior['bus']}. Sharing is paused after reload; check in again to resume.").classes('text-sm text-amber-700')
            ui.timer(15, update_gps)

        @ui.refreshable
        def content():
            with ui.tab_panels(sections, value=sections.value or routes_tab).classes('w-full bg-transparent'):
                with ui.tab_panel(routes_tab).classes('p-0'):
                    with ui.row().classes('w-full items-center gap-4 mb-5'):
                        def change_day(e):
                            selected_day['value'] = e.value
                            content.refresh()
                        ui.input('Travel date', value=selected_day['value'], on_change=change_day).props('type=date outlined')
                        ui.input('Search bus code, campus, route or stop', value=search['value'], on_change=lambda e: (search.update(value=e.value), content.refresh())).props('outlined debounce=400').classes('flex-grow')
                        ui.button(icon='refresh', on_click=content.refresh).props('flat round').tooltip('Refresh seats')
                    try:
                        all_routes = service.routes(selected_day['value'])
                    except ValueError as exc:
                        ui.label(str(exc)).classes('text-amber-700')
                        return
                    routes = [r for r in all_routes if search['value'].lower() in (r['name'] + ' ' + r['stops'] + ' ' + r['bus'] + ' ' + r['campus']).lower()]
                    ui.label(f'{len(routes)} routes available · Times shown in college local time').classes('text-sm text-slate-500 mb-3')
                    if not routes:
                        with ui.card().classes('w-full p-8 items-center shadow-none border rounded-xl'):
                            ui.icon('directions_bus', size='48px').classes('text-teal-600')
                            ui.label('No routes to show yet').classes('text-xl font-semibold')
                            ui.label('Try another search, or ask your transport office to add routes.').classes('text-slate-500 text-center')
                    with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 gap-5'):
                        for route in routes:
                            with ui.card().classes('w-full p-5 shadow-none border border-slate-200 rounded-xl gap-3'):
                                with ui.row().classes('w-full justify-between items-center'):
                                    ui.badge(route['bus'], color='teal-1', text_color='teal-9')
                                    ui.label(route['departure']).classes('text-xl font-bold')
                                ui.label(route['name']).classes('text-xl font-semibold')
                                ui.label(route['campus']).classes('text-sm text-teal-700')
                                ui.label(route['stops']).classes('text-slate-500 min-h-12')
                                if user and selected_day['value'] == date.today().isoformat():
                                    occupancy_label = ui.label().classes('text-lg font-semibold text-teal-800')
                                    def update_occupancy(rid=route['id'], label=occupancy_label):
                                        if app.storage.user.get('user_id') != user['id']:
                                            return
                                        counts = service.occupancy(user['id'], rid)
                                        if counts:
                                            label.set_text(f"{counts['available_seats']} seats remaining · {counts['seated']}/{counts['capacity']} seated · {counts['standing']} standing")
                                        else:
                                            label.set_text('Bus route archived')
                                    update_occupancy()
                                    ui.timer(15, update_occupancy)
                                    ui.label('Self-reported occupancy; seats are released on check-out, not when GPS stops.').classes('text-xs text-slate-500')
                                with ui.row().classes('w-full justify-between items-center'):
                                    ui.label(f"{route['available']} / {route['capacity']} reservation slots left").classes('text-sm text-teal-700')
                                    def reserve(r=route):
                                        if not user:
                                            auth_dialog()
                                        else:
                                            action(lambda: service.book(user['id'], r['id'], selected_day['value']), 'Seat reserved. See My bookings for your pass.')
                                    button = ui.button('Reserve seat', icon='arrow_forward', on_click=reserve).props('unelevated')
                                    if route['available'] == 0:
                                        button.disable()
                                if selected_day['value'] == date.today().isoformat():
                                    if user:
                                        report = service.latest_report(user['id'], route['id'])
                                        if report:
                                            age = max(0, int(time.time() - report['reported_at']))
                                            ui.label(f'Last reported location · {age // 60} min {age % 60} sec ago').classes('font-medium text-teal-700')
                                            ui.label(f"GPS accuracy ±{report['accuracy']:.0f} m · Community report, not verified bus GPS").classes('text-xs text-slate-500')
                                            ui.link('View reported location on map', f"https://www.openstreetmap.org/?mlat={report['latitude']}&mlon={report['longitude']}#map=16/{report['latitude']}/{report['longitude']}", new_tab=True)
                                        else:
                                            ui.label('No recent location report. Bus status is unknown.').classes('text-sm text-slate-500')
                                    else:
                                        ui.label('Sign in to view bus location reports.').classes('text-sm text-slate-500')
                                    ui.button('I am on this bus · Check in', icon='location_on', on_click=lambda r=route: checkin_dialog(r)).props('outline')
                    if user:
                        ui.button('End my check-in', icon='location_off', on_click=end_checkin).props('flat')
                    ui.label('Open Bus map for automatically refreshed positions. Reports older than 10 minutes are hidden. No report does not mean the bus is cancelled.').classes('text-xs text-slate-500 mt-3')
                with ui.tab_panel(tracking_tab).classes('p-0'):
                    ui.label('Bus location · OpenStreetMap').classes('text-2xl font-bold')
                    if not user:
                        ui.label('Sign in to view bus locations.')
                        ui.button('Sign in to view map', on_click=auth_dialog)
                    else:
                        active_routes = service.routes(date.today().isoformat())
                        choices = {r['id']: f"{r['bus']} · {r['name']} → {r['campus']}" for r in active_routes}
                        bus_select = ui.select(choices, label='Bus code / route / campus', value=next(iter(choices), None)).classes('w-full').props('outlined')
                        map_status = ui.label('Select a bus.').classes('text-teal-700 font-medium')
                        count_label = ui.label().classes('text-sm text-slate-500')
                        ui.label('Recent community GPS reports are not independently verified. Updates refresh about every 15 seconds.').classes('text-sm text-slate-500')
                        map_state = {'map': None, 'marker': None, 'route_id': None}
                        map_container = ui.column().classes('w-full')

                        def update_map():
                            route_id = bus_select.value
                            if route_id is None:
                                map_status.set_text('No active bus routes. Ask the transport office to add one.')
                                return
                            if app.storage.user.get('user_id') != user['id']:
                                return
                            report = service.latest_report(user['id'], route_id)
                            occupancy = service.occupancy(user['id'], route_id)
                            if occupancy:
                                count_label.set_text(f"{occupancy['available_seats']} seats remaining · {occupancy['seated']}/{occupancy['capacity']} seated · {occupancy['standing']} standing · Self-reported")
                            else:
                                count_label.set_text('This bus route has been archived.')
                            if not report:
                                map_status.set_text('No recent GPS update. Bus location is unknown; check-ins may be stale.')
                                if map_state['marker']:
                                    map_state['map'].remove_layer(map_state['marker'])
                                    map_state['marker'] = None
                                return
                            age = max(0, int(time.time() - report['reported_at']))
                            freshness = 'Recent GPS report' if age < 60 else 'Updates delayed / sharing paused'
                            map_status.set_text(f"{freshness} · {age // 60} min {age % 60} sec ago · accuracy ±{report['accuracy']:.0f} m")
                            if map_state['map']:
                                point = (report['latitude'], report['longitude'])
                                if map_state['marker']:
                                    map_state['marker'].move(*point)
                                else:
                                    map_state['marker'] = map_state['map'].marker(latlng=point)
                                if map_state['route_id'] != route_id:
                                    map_state['map'].set_center(point)
                                    map_state['route_id'] = route_id

                        def load_map():
                            if map_state['map']:
                                return
                            with map_container:
                                leaflet = ui.leaflet(center=(13.0827, 80.2707), zoom=14).classes('w-full h-80 rounded-xl')
                                leaflet.clear_layers()
                                leaflet.tile_layer(url_template='https://tile.openstreetmap.org/{z}/{x}/{y}.png', options={'attribution': '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', 'maxZoom': 19})
                                map_state['map'] = leaflet
                            load_button.disable()
                            update_map()

                        ui.label('Loading the map contacts OpenStreetMap tile servers. No paid map account or API key is required.').classes('text-xs text-slate-500')
                        load_button = ui.button('Load OpenStreetMap', icon='map', on_click=load_map)
                        bus_select.on_value_change(lambda _: update_map())
                        ui.button('Refresh bus position', on_click=update_map).props('flat')
                        update_map()
                        ui.timer(15, update_map)
                with ui.tab_panel(bookings_tab).classes('p-0'):
                    ui.label('Your travel passes').classes('text-2xl font-bold mb-4')
                    if not user:
                        ui.label('Sign in to view and manage your bookings.')
                        ui.button('Sign in', on_click=auth_dialog)
                    else:
                        bookings = service.bookings(user['id'])
                        if not bookings:
                            ui.label('No bookings yet. Choose a route to reserve your first seat.').classes('text-slate-500')
                        for booking in bookings:
                            with ui.card().classes('w-full p-5 shadow-none border rounded-xl mb-3'):
                                ui.label(booking['name']).classes('text-xl font-semibold')
                                ui.label(f"{booking['day']} · {booking['departure']} · {booking['bus']}")
                                ui.label(f"Pass #{booking['id']:06d} · {user['name']}").classes('text-teal-700')
                                ui.label(booking['stops']).classes('text-slate-500')
                                if booking['day'] >= date.today().isoformat():
                                    def confirm_cancel(b=booking):
                                        with ui.dialog() as dialog, ui.card():
                                            ui.label('Cancel this seat reservation?')
                                            with ui.row():
                                                ui.button('Keep booking', on_click=dialog.close).props('flat')
                                                ui.button('Cancel booking', color='negative', on_click=lambda: (action(lambda: service.cancel(user['id'], b['id']), 'Booking cancelled.'), dialog.close()))
                                        dialog.open()
                                    ui.button('Cancel reservation', on_click=confirm_cancel).props('flat color=negative')
                if admin_tab:
                    with ui.tab_panel(admin_tab).classes('p-0'):
                        ui.label('Transport office').classes('text-2xl font-bold mb-4')
                        ui.label('Add routes and view passenger reservations. Archive a route to stop new bookings; existing passes remain visible.').classes('text-slate-500 mb-4')
                        with ui.expansion('Add a bus route', icon='add_circle').classes('w-full bg-white border rounded-xl mb-4'):
                            with ui.column().classes('w-full p-3'):
                                route_name = ui.input('Route name').classes('w-full')
                                stops = ui.input('Stops (in travel order)').classes('w-full')
                                departure = ui.input('Departure time', value='08:00').props('type=time')
                                bus = ui.input('Bus number / registration').classes('w-full')
                                campus = ui.input('Destination campus', value='Main Campus').classes('w-full')
                                capacity = ui.number('Seat capacity', value=40, min=1, max=100, precision=0)
                                ui.button('Add route', on_click=lambda: action(lambda: service.add_route(user['id'], route_name.value, stops.value, departure.value, bus.value, capacity.value, campus.value), 'Route added.'))
                        for route in service.routes(date.today().isoformat()):
                            with ui.row().classes('w-full items-center justify-between border-b py-2'):
                                ui.label(f"{route['name']} · {route['departure']} · {route['bus']}")
                                def display_qr(r=route):
                                    token = service.daily_qr(user['id'], r['id'])
                                    base = os.getenv('PUBLIC_BASE_URL') or str(ui.context.client.request.base_url)
                                    link = base.rstrip('/') + '/board?token=' + token
                                    code = qrcode.make(link, image_factory=SvgPathImage, border=4)
                                    svg = code.to_string().decode()
                                    with ui.dialog() as dialog, ui.card().classes('w-96 max-w-full p-6'):
                                        ui.label(f"Bus {r['bus']} · {date.today().isoformat()}").classes('text-xl font-bold')
                                        ui.label(f"{r['name']} → {r['campus']}")
                                        ui.html(svg).classes('w-72 max-w-full bg-white')
                                        ui.label('Display on a screen or print a new code each day. Yesterday\'s code will not work. Use numbered seats 1 to capacity.')
                                        ui.label('Set PUBLIC_BASE_URL to your deployed HTTPS address before printing; localhost cannot be opened from another phone.').classes('text-xs text-slate-500')
                                        ui.button('Download daily QR', on_click=lambda: ui.download.content(svg, f"bus-{r['id']}-{date.today().isoformat()}.svg"))
                                        ui.button('Close', on_click=dialog.close).props('flat')
                                    dialog.open()
                                ui.button('Daily boarding QR', icon='qr_code', on_click=display_qr).props('flat')
                                def archive(r=route):
                                    with ui.dialog() as dialog, ui.card():
                                        ui.label(f"Archive {r['name']}? Existing bookings are retained.")
                                        ui.button('Keep route', on_click=dialog.close).props('flat')
                                        ui.button('Archive', on_click=lambda: (action(lambda: service.archive_route(user['id'], r['id']), 'Route archived.'), dialog.close()))
                                    dialog.open()
                                ui.button('Archive', on_click=archive).props('flat color=negative')
                        ui.label('Passenger reservations').classes('text-xl font-semibold mt-6')
                        rows = service.bookings(user['id'], admin=True)
                        ui.table(columns=[{'name': key, 'label': label, 'field': key, 'sortable': True} for key, label in [('id', 'Pass'), ('day', 'Date'), ('name', 'Route'), ('departure', 'Departure'), ('student', 'Student'), ('email', 'Email')]], rows=rows, row_key='id', pagination=10).classes('w-full')
                        ui.label('Checked-in members').classes('text-xl font-semibold mt-6')
                        ui.label('Admin-only roster. A check-in is self-reported; a stale GPS update does not confirm the person is still aboard. Refresh to update this list.').classes('text-sm text-slate-500')
                        roster = service.onboard_members(user['id'])
                        for member in roster:
                            member['gps_status'] = 'No recent GPS' if not member['reported_at'] or time.time() - member['reported_at'] > 60 else 'Recent GPS'
                        ui.table(columns=[{'name': key, 'label': label, 'field': key} for key, label in [('member', 'Member'), ('bus', 'Bus code'), ('campus', 'Campus'), ('route', 'Route'), ('seating', 'Seated / standing'), ('seat_number', 'Seat'), ('gps_status', 'GPS status')]], rows=roster).classes('w-full')
                        ui.button('Refresh checked-in members', on_click=content.refresh).props('flat')
        content()
        pending = app.storage.user.get('pending_bus_token')
        if user and pending:
            try:
                pending_route = service.route_for_qr(pending)
                ui.timer(0.1, lambda: checkin_dialog(pending_route, pending), once=True)
            except ValueError:
                app.storage.user.pop('pending_bus_token', None)
                ui.notify('The scanned bus QR has expired. Scan today\'s code.', type='warning')
        ui.label('CampusRide · Contact your college transport office for service changes.').classes('text-xs text-slate-400 mt-6')


if __name__ in {'__main__', '__mp_main__'}:
    ui.run(title='CampusRide | College transport', host=os.getenv('HOST', '0.0.0.0'),
           port=int(os.getenv('PORT', '8080')), reload=False,
           native=os.getenv('NATIVE_DESKTOP') == '1',
           storage_secret=os.getenv('SESSION_SECRET') or secret_path.read_text())
