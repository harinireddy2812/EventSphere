from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import sqlite3, uuid, os

app = Flask(__name__)
app.secret_key = 'eventbooking_secret_key_2024'

DB_PATH = os.path.join(os.path.dirname(__file__), 'eventbooking.db')

# ── Database setup ────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                name     TEXT NOT NULL,
                email    TEXT NOT NULL,
                role     TEXT NOT NULL DEFAULT 'user'
            );
            CREATE TABLE IF NOT EXISTS events (
                id           TEXT PRIMARY KEY,
                title        TEXT NOT NULL,
                category     TEXT NOT NULL,
                date         TEXT NOT NULL,
                time         TEXT NOT NULL,
                location     TEXT NOT NULL,
                description  TEXT NOT NULL,
                price        INTEGER NOT NULL DEFAULT 0,
                total_seats  INTEGER NOT NULL,
                booked_seats INTEGER NOT NULL DEFAULT 0,
                image_emoji  TEXT NOT NULL DEFAULT '🎉',
                organizer    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id          TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                event_id    TEXT NOT NULL,
                event_title TEXT NOT NULL,
                seats       INTEGER NOT NULL,
                total_price INTEGER NOT NULL,
                booked_at   TEXT NOT NULL
            );
        ''')
        existing = conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone()
        if not existing:
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                         ('admin','admin123','Admin User','admin@events.com','admin'))
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if count == 0:
            sample_events = [
                ('e1','Tech Summit 2025','Technology','2025-04-15','10:00',
                 'Hyderabad Convention Center',
                 'Annual technology summit featuring AI, cloud computing, and blockchain talks.',
                 999, 200, 45, '💻', 'admin'),
                ('e2','Music Fest 2025','Music','2025-05-10','18:00',
                 'Vijayawada Grounds',
                 'A night of live music featuring top indie and classical artists.',
                 499, 500, 120, '🎵', 'admin'),
                ('e3','Startup Pitching Night','Business','2025-04-28','17:00',
                 'T-Hub, Hyderabad',
                 'Watch top startups pitch to investors. Network with founders and VCs.',
                 0, 100, 60, '🚀', 'admin'),
                ('e4','Photography Workshop','Workshop','2025-04-20','09:00',
                 'Studio 7, Bangalore',
                 'Hands-on photography workshop for beginners and intermediates.',
                 1499, 30, 28, '📸', 'admin'),
            ]
            conn.executemany(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", sample_events)

def row_to_dict(row):
    return dict(row) if row else None

def get_event(event_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    return row_to_dict(row)

# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    query = request.args.get('q', '').lower()
    category = request.args.get('category', '')
    with get_db() as conn:
        if query and category:
            rows = conn.execute(
                "SELECT * FROM events WHERE (LOWER(title) LIKE ? OR LOWER(description) LIKE ?) AND category=?",
                (f'%{query}%', f'%{query}%', category)).fetchall()
        elif query:
            rows = conn.execute(
                "SELECT * FROM events WHERE LOWER(title) LIKE ? OR LOWER(description) LIKE ?",
                (f'%{query}%', f'%{query}%')).fetchall()
        elif category:
            rows = conn.execute("SELECT * FROM events WHERE category=?", (category,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM events").fetchall()
        categories = [r[0] for r in conn.execute("SELECT DISTINCT category FROM events").fetchall()]
    events = [dict(r) for r in rows]
    return render_template('index.html', events=events, categories=categories, query=query, selected_cat=category)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with get_db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        if user:
            session['user'] = user['username']
            session['role'] = user['role']
            session['name'] = user['name']
            flash('Welcome back, ' + user['name'] + '!', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        with get_db() as conn:
            existing = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
            if existing:
                flash('Username already exists.', 'error')
                return render_template('signup.html')
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                         (username, request.form['password'], request.form['name'],
                          request.form['email'], 'user'))
        session['user'] = username
        session['role'] = 'user'
        session['name'] = request.form['name']
        flash('Account created! Welcome!', 'success')
        return redirect(url_for('index'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

# ── Event Routes ──────────────────────────────────────────────────────────────
@app.route('/event/<event_id>')
def event_detail(event_id):
    event = get_event(event_id)
    if not event:
        flash('Event not found.', 'error')
        return redirect(url_for('index'))
    available = event['total_seats'] - event['booked_seats']
    user_booked = False
    if 'user' in session:
        with get_db() as conn:
            user_booked = conn.execute(
                "SELECT 1 FROM bookings WHERE username=? AND event_id=?",
                (session['user'], event_id)).fetchone() is not None
    return render_template('event_detail.html', event=event, available=available, user_booked=user_booked)

@app.route('/book/<event_id>', methods=['POST'])
def book_event(event_id):
    if 'user' not in session:
        flash('Please login to book.', 'error')
        return redirect(url_for('login'))
    event = get_event(event_id)
    if not event:
        flash('Event not found.', 'error')
        return redirect(url_for('index'))
    seats = int(request.form.get('seats', 1))
    available = event['total_seats'] - event['booked_seats']
    if seats > available:
        flash(f'Only {available} seats available.', 'error')
        return redirect(url_for('event_detail', event_id=event_id))
    with get_db() as conn:
        already = conn.execute(
            "SELECT 1 FROM bookings WHERE username=? AND event_id=?",
            (session['user'], event_id)).fetchone()
        if already:
            flash('You already booked this event.', 'error')
            return redirect(url_for('event_detail', event_id=event_id))
        booking_id = str(uuid.uuid4())[:8].upper()
        conn.execute(
            "INSERT INTO bookings VALUES (?,?,?,?,?,?,?)",
            (booking_id, session['user'], event_id, event['title'],
             seats, event['price'] * seats,
             datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.execute(
            "UPDATE events SET booked_seats = booked_seats + ? WHERE id=?",
            (seats, event_id))
    flash(f'Successfully booked {seats} seat(s) for {event["title"]}!', 'success')
    return redirect(url_for('my_bookings'))

@app.route('/my-bookings')
def my_bookings():
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT b.*, e.image_emoji, e.date, e.location
               FROM bookings b
               LEFT JOIN events e ON b.event_id = e.id
               WHERE b.username=?
               ORDER BY b.booked_at DESC''',
            (session['user'],)).fetchall()
    bookings = [dict(r) for r in rows]
    return render_template('my_bookings.html', bookings=bookings)

@app.route('/cancel/<booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        booking = conn.execute(
            "SELECT * FROM bookings WHERE id=? AND username=?",
            (booking_id, session['user'])).fetchone()
        if booking:
            conn.execute(
                "UPDATE events SET booked_seats = booked_seats - ? WHERE id=?",
                (booking['seats'], booking['event_id']))
            conn.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
            flash('Booking cancelled.', 'success')
    return redirect(url_for('my_bookings'))

# ── Admin Routes ──────────────────────────────────────────────────────────────
@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        flash('Admin access only.', 'error')
        return redirect(url_for('index'))
    with get_db() as conn:
        events   = [dict(r) for r in conn.execute("SELECT * FROM events").fetchall()]
        bookings = [dict(r) for r in conn.execute("SELECT * FROM bookings ORDER BY booked_at DESC").fetchall()]
        users    = [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]
        revenue  = conn.execute("SELECT COALESCE(SUM(total_price),0) FROM bookings").fetchone()[0]
    stats = {
        'total_events': len(events),
        'total_bookings': len(bookings),
        'total_users': len(users),
        'total_revenue': revenue
    }
    return render_template('admin.html', events=events, bookings=bookings, stats=stats, users=users)

@app.route('/admin/create-event', methods=['GET', 'POST'])
def create_event():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    if request.method == 'POST':
        new_id = str(uuid.uuid4())[:6]
        with get_db() as conn:
            conn.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_id, request.form['title'], request.form['category'],
                 request.form['date'], request.form['time'], request.form['location'],
                 request.form['description'], int(request.form['price']),
                 int(request.form['total_seats']), 0,
                 request.form.get('emoji', '🎉'), session['user']))
        flash('Event created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('create_event.html')

@app.route('/admin/delete-event/<event_id>', methods=['POST'])
def delete_event(event_id):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    with get_db() as conn:
        conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    flash('Event deleted.', 'success')
    return redirect(url_for('admin_dashboard'))

# ── Run ───────────────────────────────────────────────────────────────────────
init_db()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)