"""Full browser journeys using an isolated database and server."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from transport import Transport


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
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base)
                playwright.expect(page.get_by_text('North Campus Express', exact=True)).to_be_visible()
                page.get_by_role('button', name='Student / admin sign in').click()
                page.get_by_label('College email', exact=True).fill('student@college.edu')
                page.get_by_label('Password', exact=True).fill(password)
                page.get_by_role('button', name='Sign in', exact=True).click()
                playwright.expect(page.get_by_text('Test Student', exact=True)).to_be_visible()
                page.context.grant_permissions(['geolocation'], origin=base)
                page.context.set_geolocation({'latitude': 13.08, 'longitude': 80.27, 'accuracy': 15})
                page.get_by_role('button', name='I am on this bus · Check in').click()
                page.get_by_role('button', name='Share my current location').click()
                playwright.expect(page.get_by_text('Last reported location', exact=False)).to_be_visible()
                playwright.expect(page.get_by_role('link', name='View reported location on map')).to_have_attribute('href', 'https://www.openstreetmap.org/?mlat=13.08&mlon=80.27#map=16/13.08/80.27')
                page.get_by_role('button', name='End my check-in').click()
                playwright.expect(page.get_by_text('No recent location report.', exact=False)).to_be_visible()
                page.get_by_role('button', name='Reserve seat').click()
                page.get_by_role('tab', name='My bookings').click()
                playwright.expect(page.get_by_text('Pass #000001', exact=False)).to_be_visible()
                page.get_by_role('button', name='Cancel reservation').click()
                page.get_by_role('button', name='Cancel booking', exact=True).click()
                playwright.expect(page.get_by_text('No bookings yet.', exact=False)).to_be_visible()
                page.get_by_role('button', name='Sign out').click()
                page.get_by_role('button', name='Student / admin sign in').click()
                page.get_by_label('College email', exact=True).fill('admin@college.edu')
                page.get_by_label('Password', exact=True).fill(password)
                page.get_by_role('button', name='Sign in', exact=True).click()
                page.get_by_role('tab', name='Administration', exact=False).click()
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
                assert not errors
                browser.close()
        finally:
            process.terminate()
            process.wait(timeout=10)
