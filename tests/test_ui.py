"""Full browser journeys using an isolated database and server."""
import os
import base64
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from transport import Transport
from campus import Campus
from datetime import date, timedelta


def test_desktop_and_mobile_journeys(tmp_path):
    playwright = pytest.importorskip('playwright.sync_api')
    chromium = os.getenv('CHROMIUM_PATH', '/usr/bin/chromium')
    if not Path(chromium).exists():
        pytest.skip('System Chromium unavailable')
    root = Path(__file__).resolve().parents[1]
    service = Transport(tmp_path / 'transport.db')
    password = secrets.token_urlsafe(20)
    admin = service.register('Administrator', 'admin@college.edu', password, 'admin')
    service.register('Test Student', 'student@college.edu', password)
    modules = Campus(service)
    modules.add_training(admin, 'Python foundations', 'role', 'student', 'Build practical Python skills.')
    service.add_route(admin, 'North Campus Express', 'Central Station → Library → Campus', '08:00', 'BUS-01', 2)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    environment = {**os.environ, 'TRANSPORT_DB': service.path, 'PORT': str(port), 'HOST': '127.0.0.1', 'COLLEGE_NAME': 'Example College'}
    for key in ('COLLEGE_ADMIN_EMAIL', 'COLLEGE_ADMIN_PASSWORD', 'NATIVE_DESKTOP', 'PYTEST_CURRENT_TEST', 'PYTEST_VERSION'):
        environment.pop(key, None)
    with (tmp_path / 'server.log').open('w+') as log:
        process = subprocess.Popen([sys.executable, str(root / 'app.py')], cwd=tmp_path, env=environment, stdout=log, stderr=log)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base + '/health', timeout=1) as response:
                        assert response.status == 200
                    break
                except OSError:
                    if process.poll() is not None:
                        log.seek(0)
                        pytest.fail(log.read())
                    time.sleep(0.1)
            else:
                pytest.fail('Server did not become ready')
            with playwright.sync_playwright() as p:
                browser = p.chromium.launch(executable_path=chromium, headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.set_default_timeout(10000)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                # Tile transport is mocked so this integration test does not load
                # community tile servers or depend on external network access.
                tile = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jVxkAAAAASUVORK5CYII=')
                page.route('https://tile.openstreetmap.org/**', lambda route: route.fulfill(status=200, content_type='image/png', body=tile))
                page.goto(base)
                playwright.expect(page.get_by_text('North Campus Express', exact=True)).to_be_visible()
                page.get_by_role('button', name='Student / admin sign in').click()
                page.get_by_label('College email', exact=True).fill('student@college.edu')
                page.get_by_label('Password', exact=True).fill(password)
                page.get_by_role('button', name='Sign in', exact=True).click()
                playwright.expect(page.get_by_text('Test Student', exact=True)).to_be_visible()
                page.context.grant_permissions(['geolocation'], origin=base)
                page.context.set_geolocation({'latitude': 13.08, 'longitude': 80.27, 'accuracy': 15})
                page.goto(base + '/board?token=' + service.daily_qr(admin, 1))
                page.get_by_role('button', name='Start sharing bus location').click()
                playwright.expect(page.get_by_text('Last reported location', exact=False)).to_be_visible()
                playwright.expect(page.get_by_role('link', name='View reported location on map')).to_have_attribute('href', 'https://www.openstreetmap.org/?mlat=13.08&mlon=80.27#map=16/13.08/80.27')
                playwright.expect(page.get_by_text('1 seats remaining · 1/2 seated · 0 standing', exact=True)).to_be_visible()
                page.get_by_role('tab', name='Bus map', exact=False).click()
                page.get_by_role('button', name='Load OpenStreetMap', exact=True).click()
                playwright.expect(page.locator('.leaflet-marker-icon')).to_be_visible()
                playwright.expect(page.locator('.leaflet-control-attribution')).to_contain_text('OpenStreetMap')
                initial = service.latest_report(admin, 1)['reported_at']
                page.context.set_geolocation({'latitude': 13.09, 'longitude': 80.28, 'accuracy': 12})
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    latest = service.latest_report(admin, 1)
                    if latest['reported_at'] > initial and latest['latitude'] == 13.09:
                        break
                    page.wait_for_timeout(200)
                else:
                    pytest.fail('Foreground GPS did not update automatically')
                page.get_by_role('button', name='Refresh bus position', exact=True).click()
                playwright.expect(page.get_by_text('Recent GPS report', exact=False)).to_be_visible()
                page.get_by_role('tab', name='Routes & schedules', exact=False).click()
                page.get_by_role('button', name='End my check-in').click()
                playwright.expect(page.get_by_text('No recent location report.', exact=False)).to_be_visible()
                page.get_by_role('button', name='Reserve seat').click()
                page.get_by_role('tab', name='My bookings').click()
                playwright.expect(page.get_by_text('Pass #000001', exact=False)).to_be_visible()
                page.get_by_role('button', name='Cancel reservation').click()
                page.get_by_role('button', name='Cancel booking', exact=True).click()
                playwright.expect(page.get_by_text('No bookings yet.', exact=False)).to_be_visible()
                page.get_by_role('button', name='Campus modules', exact=True).click()
                playwright.expect(page.get_by_role('tab', name='Energy', exact=False)).to_have_count(0)
                page.get_by_text('Request leave', exact=True).click()
                leave_day = (date.today() + timedelta(days=(7 - date.today().weekday()) % 7)).isoformat()
                page.get_by_label('Leave start date', exact=True).fill(leave_day)
                page.get_by_label('Leave end date', exact=True).fill(leave_day)
                page.get_by_label('Leave reason', exact=True).fill('Personal appointment')
                page.get_by_role('button', name='Submit leave request', exact=True).click()
                playwright.expect(page.get_by_role('cell', name='pending', exact=True)).to_be_visible()
                page.get_by_role('tab', name='Training', exact=False).click()
                page.get_by_role('button', name='Enroll in training', exact=True).click()
                page.get_by_role('button', name='Mark training complete', exact=True).click()
                playwright.expect(page.get_by_text('completed', exact=True)).to_be_visible()
                page.get_by_role('button', name='Back to transport', exact=True).click()
                page.get_by_role('button', name='Sign out').click()
                page.get_by_role('button', name='Student / admin sign in').click()
                page.get_by_label('College email', exact=True).fill('admin@college.edu')
                page.get_by_label('Password', exact=True).fill(password)
                page.get_by_role('button', name='Sign in', exact=True).click()
                page.get_by_role('tab', name='Administration', exact=False).click()
                page.get_by_role('button', name='Daily boarding QR', exact=True).click()
                playwright.expect(page.get_by_role('button', name='Download daily QR', exact=True)).to_be_visible()
                playwright.expect(page.locator('[role=dialog] svg')).to_be_visible()
                page.get_by_role('button', name='Close', exact=True).click()
                page.get_by_text('Add a bus route', exact=True).click()
                page.get_by_label('Route name', exact=True).fill('South Campus')
                page.get_by_label('Stops (in travel order)', exact=True).fill('Town → Campus')
                page.get_by_label('Bus number / registration', exact=True).fill('BUS-02')
                page.get_by_role('button', name='Add route', exact=True).click()
                playwright.expect(page.get_by_text('South Campus · 08:00 · BUS-02', exact=True)).to_be_visible()
                page.set_viewport_size({'width': 390, 'height': 844})
                page.get_by_role('tab', name='Routes & schedules', exact=False).click()
                playwright.expect(page.get_by_text('South Campus', exact=True)).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(tmp_path / 'mobile.png'), full_page=True)
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.get_by_role('button', name='Campus modules', exact=True).click()
                page.get_by_label('Review note for request 1', exact=True).fill('Approved for the appointment')
                page.get_by_role('button', name='Approve #1', exact=True).click()
                playwright.expect(page.get_by_text('#1 · Test Student · regular · approved', exact=True)).to_be_visible()
                page.get_by_role('tab', name='Energy', exact=False).click()
                page.get_by_text('Record energy reading', exact=True).click()
                page.get_by_label('Produced kWh', exact=True).fill('100')
                page.get_by_label('Consumed kWh', exact=True).fill('60')
                page.get_by_label('Battery charged kWh', exact=True).fill('30')
                page.get_by_label('Distributed / exported kWh', exact=True).fill('10')
                page.get_by_label('Distribution destination (building / grid)', exact=True).fill('Library')
                page.get_by_role('button', name='Save energy reading', exact=True).click()
                playwright.expect(page.get_by_text('30 kWh stored', exact=True)).to_be_visible()
                page.get_by_role('tab', name='Access', exact=False).click()
                page.get_by_label('Member', exact=True).click()
                page.get_by_text('Test Student · student@college.edu', exact=True).click()
                page.get_by_role('button', name='Edit member access', exact=True).click()
                page.get_by_role('checkbox', name='Energy access', exact=True).click()
                playwright.expect(page.get_by_role('checkbox', name='Energy access', exact=True)).to_be_checked()
                page.get_by_role('button', name='Save member access', exact=True).click()
                playwright.expect(page.get_by_role('button', name='Save member access', exact=True)).not_to_be_visible()
                assert modules.can(service.authenticate('student@college.edu', password)['id'], 'energy')
                page.get_by_role('tab', name='Compute', exact=False).click()
                playwright.expect(page.get_by_text('Requirements pending', exact=True)).to_be_visible()
                assert not errors
                browser.close()
        finally:
            process.terminate()
            process.wait(timeout=10)
