"""Campus modules: permissions, energy ledgers, leave workflows and training."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


class Campus:
    PERMISSIONS = {'energy', 'leave_manager', 'training_manager'}

    def __init__(self, transport):
        self.transport = transport
        with transport.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS campus_profiles (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    academic_role TEXT NOT NULL DEFAULT 'student', industry TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS campus_permissions (
                    user_id INTEGER NOT NULL REFERENCES users(id), permission TEXT NOT NULL,
                    PRIMARY KEY(user_id,permission));
                CREATE TABLE IF NOT EXISTS energy_entries (
                    id INTEGER PRIMARY KEY, campus TEXT NOT NULL, day TEXT NOT NULL, source TEXT NOT NULL,
                    produced INTEGER NOT NULL, consumed INTEGER NOT NULL, charged INTEGER NOT NULL,
                    discharged INTEGER NOT NULL, distributed INTEGER NOT NULL, losses INTEGER NOT NULL,
                    opening INTEGER NOT NULL, closing INTEGER NOT NULL,
                    recorded_by INTEGER NOT NULL REFERENCES users(id), UNIQUE(campus,day));
                CREATE TABLE IF NOT EXISTS holidays (
                    day TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS campus_rules (
                    id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
                INSERT OR IGNORE INTO campus_rules VALUES(1,
                    'Submit leave requests for approval. Medical leave is a separate category. Contact your college office for its official attendance and documentation rules.');
                CREATE TABLE IF NOT EXISTS leave_requests (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    kind TEXT NOT NULL, start_day TEXT NOT NULL, end_day TEXT NOT NULL,
                    working_days INTEGER NOT NULL, reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', reviewed_by INTEGER REFERENCES users(id),
                    review_note TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS trainings (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL,
                    target TEXT NOT NULL, description TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS training_enrollments (
                    user_id INTEGER NOT NULL REFERENCES users(id), training_id INTEGER NOT NULL REFERENCES trainings(id),
                    status TEXT NOT NULL DEFAULT 'enrolled', PRIMARY KEY(user_id,training_id));
            ''')
            if 'destination' not in {r['name'] for r in db.execute('PRAGMA table_info(energy_entries)')}:
                db.execute("ALTER TABLE energy_entries ADD COLUMN destination TEXT NOT NULL DEFAULT ''")

    def person(self, actor_id):
        person = self.transport.user(actor_id)
        if not person:
            raise ValueError('Sign in to use campus modules.')
        with self.transport.connection() as db:
            profile = db.execute('SELECT * FROM campus_profiles WHERE user_id=?', (actor_id,)).fetchone()
        return {**person, 'academic_role': profile['academic_role'] if profile else 'student',
                'industry': profile['industry'] if profile else ''}

    def can(self, actor_id, permission):
        person = self.person(actor_id)
        with self.transport.connection() as db:
            return person['role'] == 'admin' or bool(db.execute(
                'SELECT 1 FROM campus_permissions WHERE user_id=? AND permission=?', (actor_id, permission)).fetchone())

    def require(self, actor_id, permission):
        if not self.can(actor_id, permission):
            raise ValueError('You do not have permission for this campus module.')

    def members(self, actor_id):
        self.transport.require_admin(actor_id)
        with self.transport.connection() as db:
            return [dict(row) for row in db.execute('SELECT id,name,email FROM users ORDER BY name')]

    def profile(self, actor_id, target_id):
        self.transport.require_admin(actor_id)
        person = self.person(target_id)
        with self.transport.connection() as db:
            permissions = [r[0] for r in db.execute('SELECT permission FROM campus_permissions WHERE user_id=?', (target_id,))]
        return {**person, 'permissions': permissions}

    def set_profile(self, actor_id, target_id, academic_role, industry, permissions):
        self.transport.require_admin(actor_id)
        self.person(target_id)
        if academic_role not in ('student', 'staff') or not set(permissions) <= self.PERMISSIONS:
            raise ValueError('Choose a valid role and module permissions.')
        industry = self.text(industry, 'Industry', required=False, limit=100)
        with self.transport.connection() as db:
            db.execute('INSERT INTO campus_profiles VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET academic_role=excluded.academic_role,industry=excluded.industry', (target_id, academic_role, industry))
            db.execute('DELETE FROM campus_permissions WHERE user_id=?', (target_id,))
            db.executemany('INSERT INTO campus_permissions VALUES(?,?)', [(target_id, p) for p in set(permissions)])

    @staticmethod
    def text(value, label, required=True, limit=2000):
        value = str(value or '').strip()
        if (required and not value) or len(value) > limit:
            raise ValueError(f'{label} is required and must be at most {limit} characters.' if required else f'{label} must be at most {limit} characters.')
        return value

    @staticmethod
    def day(value):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError('Enter a valid date.') from None

    @staticmethod
    def wh(value):
        try:
            number = Decimal(str(value))
            if not number.is_finite() or number < 0 or number > 1_000_000_000 or number.as_tuple().exponent < -3:
                raise ValueError()
            return int(number * 1000)
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError('Energy must be non-negative kWh, up to 3 decimal places.') from None

    def record_energy(self, actor_id, campus, day, source, produced, consumed, charged, discharged, distributed, losses, initial_storage=0, destination=''):
        self.require(actor_id, 'energy')
        campus = self.text(campus, 'Campus', limit=100)
        day = self.day(day)
        if day > date.today():
            raise ValueError('Energy readings cannot be dated in the future.')
        if source not in ('solar', 'wind', 'biogas', 'mixed', 'other'):
            raise ValueError('Choose a valid energy source.')
        values = [self.wh(v) for v in (produced, consumed, charged, discharged, distributed, losses)]
        produced, consumed, charged, discharged, distributed, losses = values
        if produced + discharged != consumed + charged + distributed + losses:
            raise ValueError('Energy must balance: production + battery discharge = consumption + battery charge + distribution + losses.')
        destination = self.text(destination, 'Distribution destination', required=distributed > 0, limit=200)
        with self.transport.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            last = db.execute('SELECT * FROM energy_entries WHERE lower(campus)=lower(?) ORDER BY day DESC LIMIT 1', (campus,)).fetchone()
            if last and day.isoformat() <= last['day']:
                raise ValueError('Add readings after the latest recorded date for this campus; historical entries cannot be overwritten.')
            opening = last['closing'] if last else self.wh(initial_storage)
            if last and self.wh(initial_storage) != 0:
                raise ValueError('Initial storage is only set on the first reading; opening storage carries forward automatically.')
            closing = opening + charged - discharged
            if closing < 0:
                raise ValueError('Battery discharge exceeds available stored energy.')
            return db.execute('INSERT INTO energy_entries(campus,day,source,produced,consumed,charged,discharged,distributed,losses,opening,closing,recorded_by,destination) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                              (last['campus'] if last else campus, day.isoformat(), source, *values, opening, closing, actor_id, destination)).lastrowid

    def energy(self, actor_id):
        self.require(actor_id, 'energy')
        with self.transport.connection() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM energy_entries ORDER BY day DESC,campus')]
        for row in rows:
            for key in ('produced', 'consumed', 'charged', 'discharged', 'distributed', 'losses', 'opening', 'closing'):
                row[key] /= 1000
        return rows

    def holidays(self, actor_id):
        self.person(actor_id)
        with self.transport.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM holidays ORDER BY day')]

    def add_holiday(self, actor_id, day, name):
        self.require(actor_id, 'leave_manager')
        day, name = self.day(day).isoformat(), self.text(name, 'Holiday name', limit=100)
        with self.transport.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM holidays WHERE day=?', (day,)).fetchone():
                raise ValueError('A holiday already exists on this date.')
            # Historical leave day counts stay as recorded; do not silently change them.
            if db.execute("SELECT 1 FROM leave_requests WHERE start_day<=? AND end_day>=? AND status IN ('pending','approved')", (day, day)).fetchone():
                raise ValueError('This date is covered by an existing leave request. Resolve the request before changing its holiday calendar.')
            db.execute('INSERT INTO holidays VALUES(?,?)', (day, name))

    def rules(self, actor_id):
        self.person(actor_id)
        with self.transport.connection() as db:
            return db.execute('SELECT body FROM campus_rules WHERE id=1').fetchone()[0]

    def set_rules(self, actor_id, body):
        self.require(actor_id, 'leave_manager')
        body = self.text(body, 'Rules', limit=10000)
        with self.transport.connection() as db:
            db.execute('UPDATE campus_rules SET body=? WHERE id=1', (body,))

    def request_leave(self, actor_id, kind, start, end, reason):
        self.person(actor_id)
        if kind not in ('regular', 'medical'):
            raise ValueError('Choose regular or medical leave.')
        start, end = self.day(start), self.day(end)
        if end < start or (end - start).days > 365:
            raise ValueError('Choose an ordered date range no longer than 366 calendar days.')
        reason = self.text(reason, 'Reason', limit=1000)
        with self.transport.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            holidays = {r[0] for r in db.execute('SELECT day FROM holidays WHERE day BETWEEN ? AND ?', (start.isoformat(), end.isoformat()))}
            days = sum((start + timedelta(days=i)).weekday() < 5 and (start + timedelta(days=i)).isoformat() not in holidays for i in range((end - start).days + 1))
            if not days:
                raise ValueError('This request contains no working days (Monday–Friday excluding holidays).')
            if db.execute("SELECT 1 FROM leave_requests WHERE user_id=? AND start_day<=? AND end_day>=? AND status IN ('pending','approved')", (actor_id, end.isoformat(), start.isoformat())).fetchone():
                raise ValueError('You already have an overlapping leave request.')
            return db.execute('INSERT INTO leave_requests(user_id,kind,start_day,end_day,working_days,reason) VALUES(?,?,?,?,?,?)', (actor_id, kind, start.isoformat(), end.isoformat(), days, reason)).lastrowid

    def leaves(self, actor_id, management=False):
        self.person(actor_id)
        if management:
            self.require(actor_id, 'leave_manager')
        with self.transport.connection() as db:
            return [dict(r) for r in db.execute('SELECT l.*,u.name AS member FROM leave_requests l JOIN users u ON u.id=l.user_id' + ('' if management else ' WHERE l.user_id=?') + ' ORDER BY l.id DESC', () if management else (actor_id,))]

    def review_leave(self, actor_id, request_id, decision, note):
        self.require(actor_id, 'leave_manager')
        if decision not in ('approved', 'rejected'):
            raise ValueError('Choose approve or reject.')
        note = self.text(note, 'Review note', limit=1000)
        with self.transport.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM leave_requests WHERE id=?', (request_id,)).fetchone()
            if not row or row['status'] != 'pending':
                raise ValueError('Only a pending request can be reviewed.')
            if row['user_id'] == actor_id:
                raise ValueError('Someone else must review your leave request.')
            db.execute('UPDATE leave_requests SET status=?,reviewed_by=?,review_note=? WHERE id=?', (decision, actor_id, note, request_id))

    def cancel_leave(self, actor_id, request_id):
        self.person(actor_id)
        with self.transport.connection() as db:
            cursor = db.execute("UPDATE leave_requests SET status='cancelled' WHERE id=? AND user_id=? AND status='pending'", (request_id, actor_id))
            if not cursor.rowcount:
                raise ValueError('Only your own pending request can be cancelled.')

    def add_training(self, actor_id, title, kind, target, description):
        self.require(actor_id, 'training_manager')
        title, target = self.text(title, 'Title', limit=150), self.text(target, 'Audience', limit=100)
        if kind not in ('role', 'industry') or (kind == 'role' and target not in ('student', 'staff', 'admin', 'all')):
            raise ValueError('Choose a valid role or industry audience.')
        description = self.text(description, 'Description')
        with self.transport.connection() as db:
            return db.execute('INSERT INTO trainings(title,kind,target,description) VALUES(?,?,?,?)', (title, kind, target, description)).lastrowid

    @staticmethod
    def eligible(person, course):
        if course['kind'] == 'industry':
            return bool(person['industry']) and person['industry'].casefold() == course['target'].casefold()
        return course['target'] == 'all' or course['target'] == person['academic_role'] or (course['target'] == 'admin' and person['role'] == 'admin')

    def trainings(self, actor_id):
        person = self.person(actor_id)
        manager = self.can(actor_id, 'training_manager')
        with self.transport.connection() as db:
            rows = [dict(r) for r in db.execute('SELECT t.*,e.status AS enrollment FROM trainings t LEFT JOIN training_enrollments e ON e.training_id=t.id AND e.user_id=? WHERE t.active=1 OR e.user_id IS NOT NULL ORDER BY t.id DESC', (actor_id,))]
        return [r for r in rows if manager or self.eligible(person, r) or r['enrollment']]

    def enroll(self, actor_id, training_id):
        person = self.person(actor_id)
        with self.transport.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            course = db.execute('SELECT * FROM trainings WHERE id=? AND active=1', (training_id,)).fetchone()
            if not course or not self.eligible(person, course):
                raise ValueError('This training is not available for your assigned role or industry.')
            if db.execute('SELECT 1 FROM training_enrollments WHERE user_id=? AND training_id=?', (actor_id, training_id)).fetchone():
                raise ValueError('You are already enrolled.')
            db.execute('INSERT INTO training_enrollments(user_id,training_id) VALUES(?,?)', (actor_id, training_id))

    def complete(self, actor_id, training_id):
        self.person(actor_id)
        with self.transport.connection() as db:
            cursor = db.execute("UPDATE training_enrollments SET status='completed' WHERE user_id=? AND training_id=? AND status='enrolled'", (actor_id, training_id))
            if not cursor.rowcount:
                raise ValueError('You need an active enrollment to mark this training complete.')

    def archive_training(self, actor_id, training_id):
        self.require(actor_id, 'training_manager')
        with self.transport.connection() as db:
            db.execute('UPDATE trainings SET active=0 WHERE id=?', (training_id,))

    def training_roster(self, actor_id):
        self.require(actor_id, 'training_manager')
        with self.transport.connection() as db:
            return [dict(r) for r in db.execute('SELECT t.title,u.name,e.status FROM training_enrollments e JOIN trainings t ON t.id=e.training_id JOIN users u ON u.id=e.user_id ORDER BY t.title,u.name')]
