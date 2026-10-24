from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from transport import Transport


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
