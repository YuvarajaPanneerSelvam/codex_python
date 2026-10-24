from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from transport import Transport


def checkin(service, user_id, route_id, *coordinates, **kwargs):
    with service.connection() as db:
        admin = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]
    token = service.daily_qr(admin, route_id)
    return service.check_in(user_id, route_id, *coordinates, qr_token=token, seat_number=kwargs.pop('seat_number', 1), **kwargs)


@pytest.fixture
def system(tmp_path):
    service = Transport(tmp_path / 'test.db')
    admin = service.register('Admin', 'admin@college.edu', 'strong-password', 'admin')
    student = service.register('Student', 'student@college.edu', 'strong-password')
    route = service.add_route(admin, 'North Campus', 'Central station → Library → Campus', '08:00', 'BUS-01', 1)
    return service, admin, student, route


def test_authentication_and_password_storage(system):
    service, _, student, _ = system
    assert service.authenticate('STUDENT@COLLEGE.EDU', 'strong-password')['id'] == student
    with service.connection() as db:
        assert db.execute('SELECT password FROM users WHERE id=?', (student,)).fetchone()[0] != 'strong-password'
    with pytest.raises(ValueError):
        service.authenticate('student@college.edu', 'wrong-password')


def test_reserve_duplicate_capacity_and_cancel(system):
    service, _, student, route = system
    day = date.today().isoformat()
    booking = service.book(student, route, day)
    assert service.routes(day)[0]['available'] == 0
    with pytest.raises(ValueError, match='already'):
        service.book(student, route, day)
    other = service.register('Other', 'other@college.edu', 'strong-password')
    with pytest.raises(ValueError, match='full'):
        service.book(other, route, day)
    with pytest.raises(ValueError, match='not found'):
        service.cancel(other, booking)
    service.cancel(student, booking)
    assert service.routes(day)[0]['available'] == 1


def test_admin_permissions_and_archive(system):
    service, admin, student, route = system
    with pytest.raises(ValueError, match='Administrator'):
        service.add_route(student, 'Unauthorized', 'A → B', '08:00', 'BUS', 10)
    with pytest.raises(ValueError, match='Administrator'):
        service.bookings(student, admin=True)
    day = date.today().isoformat()
    service.book(student, route, day)
    service.archive_route(admin, route)
    assert service.routes(day) == []
    assert len(service.bookings(student)) == 1
    with pytest.raises(ValueError, match='no longer'):
        service.book(student, route, day)


def test_concurrent_booking_does_not_oversell(system):
    service, _, student, route = system
    other = service.register('Other', 'other@college.edu', 'strong-password')
    def attempt(person):
        try:
            service.book(person, route, date.today().isoformat())
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(attempt, [student, other])) == 1


def test_invalid_date_and_route(system):
    service, admin, student, route = system
    with pytest.raises(ValueError, match='past'):
        service.book(student, route, (date.today() - timedelta(days=1)).isoformat())
    with pytest.raises(ValueError, match='valid travel date'):
        service.routes('invalid')
    with pytest.raises(ValueError, match='capacity'):
        service.add_route(admin, 'Bad', 'A → B', '99:00', 'BUS', 0)


def test_any_signed_in_person_can_report_and_withdraw(system):
    service, admin, student, route = system
    # No seat booking is required to contribute a location.
    checkin(service, student, route, 13.08, 80.27, 15)
    report = service.latest_report(admin, route)
    assert report['latitude'] == 13.08
    assert report['accuracy'] == 15
    assert set(report) == {'latitude', 'longitude', 'accuracy', 'reported_at'}
    checkin(service, admin, route, 13.09, 80.28, 20, seating='standing')
    assert service.latest_report(student, route)['latitude'] == 13.09
    service.check_out(admin)
    assert service.latest_report(admin, route)['latitude'] == 13.08
    service.check_out(student)
    assert service.latest_report(admin, route) is None


def test_report_expiry_route_switch_and_archiving(system):
    import time
    service, admin, student, route = system
    checkin(service, student, route, 13, 80, 10)
    with service.connection() as db:
        db.execute('UPDATE checkins SET reported_at=?', (time.time() - 601,))
    assert service.latest_report(admin, route) is None
    other = service.add_route(admin, 'South', 'Town → Campus', '09:00', 'BUS-02', 30)
    checkin(service, student, route, 13, 80, 10)
    checkin(service, student, other, 12, 80, 10)
    assert service.latest_report(admin, route) is None
    assert service.latest_report(admin, other) is not None
    service.archive_route(admin, other)
    assert service.latest_report(student, other) is None
    with pytest.raises(ValueError, match='no longer'):
        checkin(service, student, other, 12, 80, 10)


@pytest.mark.parametrize('lat,lon,accuracy', [(91, 80, 10), (13, -181, 10), (float('nan'), 80, 10), (13, 80, float('inf')), (13, 80, -1), (13, 80, 1001), (None, 80, 10)])
def test_invalid_report_coordinates(system, lat, lon, accuracy):
    service, _, student, route = system
    with pytest.raises(ValueError, match='valid GPS'):
        checkin(service, student, route, lat, lon, accuracy)


def test_reports_require_authentication(system):
    service, _, _, route = system
    with pytest.raises(ValueError, match='Sign in'):
        checkin(service, 9999, route, 13, 80, 10)
    with pytest.raises(ValueError, match='Sign in'):
        service.latest_report(None, route)


def test_numbered_seats_qr_and_standing(system):
    service, admin, student, route = system
    token = service.daily_qr(admin, route)
    assert token == service.daily_qr(admin, route)
    assert service.route_for_qr(token)['id'] == route
    with pytest.raises(ValueError, match='daily QR'):
        service.check_in(student, route, 13, 80, 10, seat_number=1)
    with pytest.raises(ValueError, match='daily QR'):
        service.check_in(student, route, 13, 80, 10, seat_number=1, qr_token='தவறான-code')
    service.check_in(student, route, 13, 80, 10, seat_number=1, qr_token=token)
    assert service.occupancy(admin, route) == {'capacity': 1, 'seated': 1, 'standing': 0, 'available_seats': 0}
    with pytest.raises(ValueError, match='All seats'):
        service.check_in(admin, route, 13, 80, 10, seat_number=1, qr_token=token)
    service.check_in(admin, route, 13, 80, 10, seating='standing', qr_token=token)
    assert service.occupancy(student, route)['standing'] == 1
    assert service.active_session(admin)['seat_number'] is None
    service.check_in(admin, route, 13.1, 80, 10, require_active=True)
    assert service.active_session(admin)['seating'] == 'standing'
    service.check_out(student)
    assert service.available_seats(admin, route) == [1]
    assert service.occupancy(admin, route)['available_seats'] == 1
    service.check_in(admin, route, 13, 80, 10, seat_number=1, seating='seated', qr_token=token)
    assert service.occupancy(admin, route)['standing'] == 0


def test_qr_wrong_bus_expired_and_admin_only(system):
    service, admin, student, route = system
    token = service.daily_qr(admin, route)
    other = service.add_route(admin, 'Other route', 'Town → Campus', '09:00', '342', 50, 'West Campus')
    with pytest.raises(ValueError, match='daily QR'):
        service.check_in(student, other, 13, 80, 10, seat_number=1, qr_token=token)
    with pytest.raises(ValueError, match='Administrator'):
        service.daily_qr(student, route)
    with service.connection() as db:
        db.execute('UPDATE boarding_tokens SET day=?', ((date.today() - timedelta(days=1)).isoformat(),))
    with pytest.raises(ValueError, match='expired'):
        service.route_for_qr(token)
    with pytest.raises(ValueError, match='daily QR'):
        service.check_in(student, route, 13, 80, 10, seat_number=1, qr_token=token)
    assert service.daily_qr(admin, route) != token


def test_one_seat_cannot_be_claimed_twice_concurrently(system):
    service, admin, student, route = system
    token = service.daily_qr(admin, route)
    def claim(person):
        try:
            service.check_in(person, route, 13, 80, 10, seat_number=1, qr_token=token)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(claim, [admin, student])) == 1


def test_qr_sessions_expire_next_day_and_updates_do_not_rejoin(system):
    service, admin, student, route = system
    checkin(service, student, route, 13, 80, 10)
    service.check_out(student)
    with pytest.raises(ValueError, match='ended'):
        service.check_in(student, route, 13, 80, 10, require_active=True)
    checkin(service, student, route, 13, 80, 10)
    with service.connection() as db:
        db.execute('UPDATE bus_sessions SET checkin_day=?', ((date.today() - timedelta(days=1)).isoformat(),))
    assert service.active_session(student) is None
    assert service.occupancy(admin, route)['available_seats'] == 1
    assert service.latest_report(admin, route) is None
    with pytest.raises(ValueError, match='today'):
        service.check_in(student, route, 13, 80, 10, require_active=True)


def test_duplicate_seat_and_invalid_number(system):
    service, admin, student, route = system
    bigger = service.add_route(admin, 'Big', 'A → B', '08:30', '340', 50)
    token = service.daily_qr(admin, bigger)
    service.check_in(student, bigger, 13, 80, 10, seat_number=25, qr_token=token)
    with pytest.raises(ValueError, match='already checked in'):
        service.check_in(admin, bigger, 13, 80, 10, seat_number=25, qr_token=token)
    for number in [0, 51, True, 1.5, None]:
        with pytest.raises(ValueError, match='seat number'):
            service.check_in(admin, bigger, 13, 80, 10, seat_number=number, qr_token=token)
    assert 25 not in service.available_seats(admin, bigger)
    assert 25 in service.available_seats(student, bigger)
    with pytest.raises(ValueError, match='unique bus code'):
        service.add_route(admin, 'Duplicate', 'A → B', '08:45', '340', 50)
