from datetime import date, timedelta

import pytest
from campus import Campus
from transport import Transport


@pytest.fixture
def system(tmp_path):
    transport = Transport(tmp_path / 'campus.db')
    admin = transport.register('Admin', 'admin@college.edu', 'strong-password', 'admin')
    student = transport.register('Student', 'student@college.edu', 'strong-password')
    staff = transport.register('Staff', 'staff@college.edu', 'strong-password')
    campus = Campus(transport)
    campus.set_profile(admin, staff, 'staff', 'manufacturing', [])
    return campus, admin, student, staff


def test_permissions_are_enforced_by_services(system):
    campus, admin, student, staff = system
    with pytest.raises(ValueError, match='permission'):
        campus.energy(student)
    with pytest.raises(ValueError, match='Administrator'):
        campus.set_profile(student, student, 'staff', 'IT', ['energy'])
    campus.set_profile(admin, staff, 'staff', 'manufacturing', ['energy'])
    assert campus.energy(staff) == []
    with pytest.raises(ValueError, match='permission'):
        campus.training_roster(staff)
    campus.set_profile(admin, staff, 'staff', 'manufacturing', [])
    with pytest.raises(ValueError, match='permission'):
        campus.energy(staff)
    with pytest.raises(ValueError, match='Sign in'):
        campus.holidays(None)


def test_energy_balances_storage_and_append_only_dates(system):
    campus, admin, student, _ = system
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    campus.record_energy(admin, 'Main', yesterday, 'solar', 100, 60, 30, 0, 10, 0, destination='Grid')
    campus.record_energy(admin, 'main', date.today().isoformat(), 'mixed', 50, 50, 0, 10, 10, 0, destination='Grid')
    readings = campus.energy(admin)
    assert readings[0]['opening'] == 30
    assert readings[0]['closing'] == 20
    assert readings[0]['campus'] == 'Main'
    with pytest.raises(ValueError, match='latest'):
        campus.record_energy(admin, 'Main', yesterday, 'solar', 0, 0, 0, 0, 0, 0)
    with pytest.raises(ValueError, match='balance'):
        campus.record_energy(admin, 'West', yesterday, 'solar', 100, 20, 0, 0, 0, 0)
    with pytest.raises(ValueError, match='available stored'):
        campus.record_energy(admin, 'West', yesterday, 'solar', 0, 10, 0, 10, 0, 0)
    with pytest.raises(ValueError, match='permission'):
        campus.record_energy(student, 'West', yesterday, 'solar', 0, 0, 0, 0, 0, 0)
    campus.record_energy(admin, 'Battery', yesterday, 'solar', '0.001', 0, '0.001', 0, 0, 0, initial_storage='0.123')
    battery = next(r for r in campus.energy(admin) if r['campus'] == 'Battery')
    assert battery['closing'] == 0.124


@pytest.mark.parametrize('value', [-1, 'NaN', 'Infinity', '0.0001', None])
def test_invalid_energy_values_rejected(system, value):
    campus, admin, _, _ = system
    with pytest.raises(ValueError, match='Energy must'):
        campus.record_energy(admin, 'Main', date.today().isoformat(), 'solar', value, 0, 0, 0, 0, 0)


def monday():
    day = date.today()
    return day + timedelta(days=(7 - day.weekday()) % 7)


def test_leave_holidays_medical_privacy_review_and_overlap(system):
    campus, admin, student, staff = system
    start = monday()
    campus.add_holiday(admin, start.isoformat(), 'College holiday')
    request = campus.request_leave(student, 'medical', start.isoformat(), (start + timedelta(days=2)).isoformat(), 'Medical appointment')
    assert campus.leaves(student)[0]['working_days'] == 2
    assert campus.leaves(staff) == []
    with pytest.raises(ValueError, match='permission'):
        campus.leaves(staff, management=True)
    with pytest.raises(ValueError, match='overlapping'):
        campus.request_leave(student, 'regular', start.isoformat(), (start + timedelta(days=3)).isoformat(), 'Duplicate')
    with pytest.raises(ValueError, match='Only your own'):
        campus.cancel_leave(staff, request)
    with pytest.raises(ValueError, match='existing leave'):
        campus.add_holiday(admin, (start + timedelta(days=1)).isoformat(), 'New holiday')
    with pytest.raises(ValueError, match='permission'):
        campus.review_leave(staff, request, 'approved', 'Not authorized')
    campus.review_leave(admin, request, 'approved', 'Approved by college office')
    assert campus.leaves(student)[0]['review_note'] == 'Approved by college office'
    with pytest.raises(ValueError, match='pending'):
        campus.review_leave(admin, request, 'rejected', 'Second review')
    with pytest.raises(ValueError, match='Only your own'):
        campus.cancel_leave(student, request)


def test_leave_self_approval_cancel_rules_and_nonworking_dates(system):
    campus, admin, student, _ = system
    start = monday().isoformat()
    request = campus.request_leave(admin, 'regular', start, start, 'Personal')
    with pytest.raises(ValueError, match='Someone else'):
        campus.review_leave(admin, request, 'approved', 'Self')
    own = campus.request_leave(student, 'regular', start, start, 'Personal')
    campus.cancel_leave(student, own)
    assert campus.leaves(student)[0]['status'] == 'cancelled'
    weekend = (monday() + timedelta(days=5)).isoformat()
    with pytest.raises(ValueError, match='no working days'):
        campus.request_leave(student, 'regular', weekend, weekend, 'Weekend')
    with pytest.raises(ValueError, match='permission'):
        campus.set_rules(student, 'Unapproved rules')
    campus.set_rules(admin, 'Medical leave needs college office approval.')
    assert 'Medical leave' in campus.rules(student)


def test_role_and_industry_training_eligibility_progress_and_roster(system):
    campus, admin, student, staff = system
    course = campus.add_training(admin, 'Student induction', 'role', 'student', 'An introduction.')
    industry = campus.add_training(admin, 'Factory safety', 'industry', 'manufacturing', 'Industrial safety.')
    assert [r['id'] for r in campus.trainings(student)] == [course]
    assert [r['id'] for r in campus.trainings(staff)] == [industry]
    with pytest.raises(ValueError, match='not available'):
        campus.enroll(student, industry)
    campus.enroll(student, course)
    with pytest.raises(ValueError, match='already enrolled'):
        campus.enroll(student, course)
    with pytest.raises(ValueError, match='active enrollment'):
        campus.complete(staff, course)
    campus.complete(student, course)
    assert campus.training_roster(admin)[0]['status'] == 'completed'
    campus.archive_training(admin, course)
    assert campus.trainings(student)[0]['enrollment'] == 'completed'
    with pytest.raises(ValueError, match='not available'):
        campus.enroll(staff, course)
    campus.enroll(staff, industry)
    with pytest.raises(ValueError, match='permission'):
        campus.training_roster(student)


def test_initialization_preserves_existing_records(system):
    campus, admin, student, _ = system
    day = monday().isoformat()
    campus.request_leave(student, 'regular', day, day, 'Personal')
    again = Campus(campus.transport)
    assert len(again.leaves(student)) == 1
    assert campus.transport.user(student)['name'] == 'Student'
