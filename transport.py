"""SQLite persistence and transport rules, independent of the user interface."""
import hashlib
import hmac
import os
import math
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path


class Transport:
    def __init__(self, path='data/transport.db'):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'student');
                CREATE TABLE IF NOT EXISTS routes (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, stops TEXT NOT NULL,
                    departure TEXT NOT NULL, bus TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity > 0),
                    active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    route_id INTEGER NOT NULL REFERENCES routes(id), day TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, route_id, day));
                CREATE TABLE IF NOT EXISTS checkins (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    route_id INTEGER NOT NULL REFERENCES routes(id),
                    latitude REAL NOT NULL, longitude REAL NOT NULL,
                    accuracy REAL NOT NULL, reported_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS checkins_route_time ON checkins(route_id, reported_at);
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def hash_password(password, salt=None):
        salt = salt or secrets.token_hex(16)
        digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return f'{salt}:{digest}'

    def register(self, name, email, password, role='student'):
        name, email = name.strip(), email.strip().lower()
        if not name or '@' not in email or '.' not in email.rsplit('@', 1)[-1]:
            raise ValueError('Enter your name and a valid email address.')
        if len(password) < 10:
            raise ValueError('Use a password with at least 10 characters.')
        if role not in ('student', 'admin'):
            raise ValueError('Invalid role.')
        try:
            with self.connection() as db:
                cursor = db.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',
                                    (name, email, self.hash_password(password), role))
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError('An account with this email already exists.') from None

    def authenticate(self, email, password):
        with self.connection() as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (email.strip().lower(),)).fetchone()
        # Spend equivalent hashing work for unknown accounts.
        stored = row['password'] if row else self.hash_password('unused-password')
        salt = stored.split(':', 1)[0]
        if hmac.compare_digest(self.hash_password(password, salt), stored) and row:
            return {key: row[key] for key in ('id', 'name', 'email', 'role')}
        raise ValueError('Email or password is incorrect.')

    def user(self, user_id):
        with self.connection() as db:
            row = db.execute('SELECT id,name,email,role FROM users WHERE id=?', (user_id,)).fetchone()
            return dict(row) if row else None

    def require_admin(self, actor_id):
        actor = self.user(actor_id)
        if not actor or actor['role'] != 'admin':
            raise ValueError('Administrator access is required.')

    def add_route(self, actor_id, name, stops, departure, bus, capacity):
        from datetime import datetime
        self.require_admin(actor_id)
        if not all(str(v).strip() for v in (name, stops, departure, bus)):
            raise ValueError('Complete every route field.')
        try:
            departure = datetime.strptime(departure, '%H:%M').strftime('%H:%M')
            capacity = int(capacity)
            if not 1 <= capacity <= 100:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Use a valid 24-hour time and capacity from 1 to 100.') from None
        with self.connection() as db:
            return db.execute('INSERT INTO routes(name,stops,departure,bus,capacity) VALUES(?,?,?,?,?)',
                              (name.strip(), stops.strip(), departure, bus.strip(), capacity)).lastrowid

    def archive_route(self, actor_id, route_id):
        self.require_admin(actor_id)
        with self.connection() as db:
            db.execute('UPDATE routes SET active=0 WHERE id=?', (route_id,))

    @staticmethod
    def valid_day(day):
        try:
            parsed = date.fromisoformat(day)
        except (ValueError, TypeError):
            raise ValueError('Choose a valid travel date.') from None
        if parsed < date.today():
            raise ValueError('Travel date cannot be in the past.')
        return parsed.isoformat()

    def routes(self, day):
        day = self.valid_day(day)
        with self.connection() as db:
            return [dict(r) for r in db.execute('''
                SELECT r.*, r.capacity - COUNT(b.id) AS available FROM routes r
                LEFT JOIN bookings b ON b.route_id=r.id AND b.day=?
                WHERE r.active=1 GROUP BY r.id ORDER BY r.departure,r.name
            ''', (day,))]

    def book(self, user_id, route_id, day):
        day = self.valid_day(day)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT id FROM users WHERE id=?', (user_id,)).fetchone():
                raise ValueError('Sign in to book a seat.')
            route = db.execute('SELECT * FROM routes WHERE id=? AND active=1', (route_id,)).fetchone()
            if not route:
                raise ValueError('This route is no longer available.')
            if db.execute('SELECT id FROM bookings WHERE user_id=? AND route_id=? AND day=?',
                          (user_id, route_id, day)).fetchone():
                raise ValueError('You already have a seat on this route for this date.')
            count = db.execute('SELECT COUNT(*) FROM bookings WHERE route_id=? AND day=?', (route_id, day)).fetchone()[0]
            if count >= route['capacity']:
                raise ValueError('This bus is full. Please choose another route or date.')
            return db.execute('INSERT INTO bookings(user_id,route_id,day) VALUES(?,?,?)',
                              (user_id, route_id, day)).lastrowid

    def bookings(self, user_id, admin=False):
        if admin:
            self.require_admin(user_id)
        with self.connection() as db:
            return [dict(r) for r in db.execute('''
                SELECT b.id,b.day,r.name,r.departure,r.bus,r.stops,u.name AS student,u.email
                FROM bookings b JOIN routes r ON r.id=b.route_id JOIN users u ON u.id=b.user_id
            ''' + ('' if admin else ' WHERE b.user_id=?') + ' ORDER BY b.day DESC,r.departure',
                () if admin else (user_id,))]

    def check_in(self, user_id, route_id, latitude, longitude, accuracy):
        """Publish one voluntary location snapshot. A person can report on one bus at a time."""
        try:
            lat, lon, accuracy = float(latitude), float(longitude), float(accuracy)
            if not all(math.isfinite(v) for v in (lat, lon, accuracy)):
                raise ValueError()
            if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= accuracy <= 1000):
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise ValueError('A valid GPS position with accuracy within 1 km is required.') from None
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT id FROM users WHERE id=?', (user_id,)).fetchone():
                raise ValueError('Sign in to check in.')
            if not db.execute('SELECT id FROM routes WHERE id=? AND active=1', (route_id,)).fetchone():
                raise ValueError('This route is no longer available.')
            db.execute('DELETE FROM checkins WHERE reported_at < ?', (time.time() - 600,))
            db.execute('''INSERT INTO checkins VALUES(?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET route_id=excluded.route_id,
                latitude=excluded.latitude, longitude=excluded.longitude,
                accuracy=excluded.accuracy, reported_at=excluded.reported_at''',
                (user_id, route_id, lat, lon, accuracy, time.time()))

    def latest_report(self, viewer_id, route_id):
        """Expose recent coordinates to signed-in users, never the reporter's identity."""
        if not self.user(viewer_id):
            raise ValueError('Sign in to view bus location reports.')
        with self.connection() as db:
            row = db.execute('''SELECT latitude,longitude,accuracy,reported_at FROM checkins
                WHERE route_id=? AND reported_at>=?
                AND EXISTS(SELECT 1 FROM routes WHERE id=? AND active=1)
                ORDER BY reported_at DESC LIMIT 1''', (route_id, time.time() - 600, route_id)).fetchone()
            return dict(row) if row else None

    def check_out(self, user_id):
        with self.connection() as db:
            db.execute('DELETE FROM checkins WHERE user_id=?', (user_id,))

    def cancel(self, user_id, booking_id):
        with self.connection() as db:
            booking = db.execute('SELECT * FROM bookings WHERE id=? AND user_id=?', (booking_id, user_id)).fetchone()
            if not booking:
                raise ValueError('Booking not found.')
            self.valid_day(booking['day'])
            db.execute('DELETE FROM bookings WHERE id=? AND user_id=?', (booking_id, user_id))


def bootstrap(service):
    """Provision an administrator only from explicitly supplied credentials."""
    email, password = os.getenv('COLLEGE_ADMIN_EMAIL'), os.getenv('COLLEGE_ADMIN_PASSWORD')
    if bool(email) != bool(password):
        raise ValueError('Set both COLLEGE_ADMIN_EMAIL and COLLEGE_ADMIN_PASSWORD.')
    if email and password:
        with service.connection() as db:
            existing = db.execute('SELECT role FROM users WHERE email=?', (email.strip().lower(),)).fetchone()
        if existing and existing['role'] != 'admin':
            raise ValueError('Admin email belongs to a student. Choose a separate admin email.')
        if not existing:
            service.register('Transport administrator', email, password, role='admin')
