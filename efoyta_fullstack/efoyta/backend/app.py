#!/usr/bin/env python3
"""
efoyta.com — Flask Backend
Serves the frontend HTML and provides REST API endpoints.
"""

from flask import Flask, request, jsonify, make_response, send_from_directory, send_file
import jwt
import sqlite3
import hashlib
import uuid
import os
import json
from datetime import datetime, timedelta
from functools import wraps
from db import get_db, hash_password, init_db

# ─── CONFIG ───
SECRET_KEY = os.environ.get('JWT_SECRET', 'efoyta_jwt_secret_change_in_production_2025')
TOKEN_EXP_HOURS = 24
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'public')

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')

# ─── CORS (manual since flask-cors unavailable) ───
@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin', '')
    response.headers['Access-Control-Allow-Origin'] = origin or '*'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PATCH,DELETE,OPTIONS'
    return response

@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options(path):
    return '', 204

# ─── AUTH HELPERS ───
def make_token(user_id, role, hotel_id):
    payload = {
        'sub': user_id,
        'role': role,
        'hotel_id': hotel_id,
        'exp': datetime.utcnow() + timedelta(hours=TOKEN_EXP_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def decode_token(token):
    return jwt.decode(token, SECRET_KEY, algorithms=['HS256'])

def get_token_from_request():
    # Check Authorization header first
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    # Fallback to cookie
    return request.cookies.get('efoyta_token')

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({'error': 'Authentication required'}), 401
        try:
            payload = decode_token(token)
            request.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def require_super_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({'error': 'Authentication required'}), 401
        try:
            payload = decode_token(token)
            if payload.get('role') != 'super_admin':
                return jsonify({'error': 'Super admin access required'}), 403
            request.user = payload
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def require_hotel_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({'error': 'Authentication required'}), 401
        try:
            payload = decode_token(token)
            if payload.get('role') not in ('hotel_admin', 'super_admin'):
                return jsonify({'error': 'Hotel admin access required'}), 403
            request.user = payload
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def assert_hotel_access(hotel_id):
    """Ensure current user can access this hotel's data."""
    user = request.user
    if user.get('role') == 'super_admin':
        return True
    if user.get('hotel_id') != hotel_id:
        return False
    return True

def row_to_dict(row):
    if row is None:
        return None
    return dict(row)

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ─── SERVE FRONTEND ───
@app.route('/')
def index():
    return send_file(os.path.join(FRONTEND_DIR, 'index.html'))

# ─── AUTH ROUTES ───

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    db = get_db()
    user = row_to_dict(db.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone())
    db.close()

    if not user or user['password_hash'] != hash_password(password):
        return jsonify({'error': 'Invalid email or password'}), 401

    token = make_token(user['id'], user['role'], user['hotel_id'])

    resp = make_response(jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'role': user['role'],
            'hotel_id': user['hotel_id'],
            'name': user['name']
        }
    }))
    resp.set_cookie('efoyta_token', token, httponly=True, samesite='Lax',
                    max_age=TOKEN_EXP_HOURS * 3600)
    return resp

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    resp = make_response(jsonify({'ok': True}))
    resp.delete_cookie('efoyta_token')
    return resp

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def me():
    db = get_db()
    user = row_to_dict(db.execute(
        "SELECT id,email,role,hotel_id,name FROM users WHERE id=?",
        (request.user['sub'],)
    ).fetchone())
    db.close()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user)

# ─── PUBLIC HOTEL ROUTES ───

@app.route('/api/hotels', methods=['GET'])
def get_hotels():
    city = request.args.get('city', '')
    search = request.args.get('q', '').lower()
    db = get_db()
    query = "SELECT * FROM hotels WHERE subscription_status != 'expired' AND is_active=1"
    params = []
    if city and city != 'all':
        query += " AND city=?"
        params.append(city)
    if search:
        query += " AND (LOWER(name) LIKE ? OR LOWER(city) LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
    query += " ORDER BY CASE subscription_status WHEN 'active' THEN 0 WHEN 'trial' THEN 1 ELSE 2 END, name"
    hotels = rows_to_list(db.execute(query, params).fetchall())
    db.close()
    return jsonify(hotels)

@app.route('/api/hotels/<slug>', methods=['GET'])
def get_hotel(slug):
    db = get_db()
    hotel = row_to_dict(db.execute(
        "SELECT * FROM hotels WHERE slug=? AND is_active=1", (slug,)
    ).fetchone())
    db.close()
    if not hotel:
        return jsonify({'error': 'Hotel not found'}), 404
    return jsonify(hotel)

@app.route('/api/hotels/<slug>/rooms', methods=['GET'])
def get_hotel_rooms(slug):
    db = get_db()
    hotel = row_to_dict(db.execute("SELECT id FROM hotels WHERE slug=?", (slug,)).fetchone())
    if not hotel:
        db.close()
        return jsonify({'error': 'Hotel not found'}), 404
    rooms = rows_to_list(db.execute(
        "SELECT * FROM rooms WHERE hotel_id=? ORDER BY price_per_night", (hotel['id'],)
    ).fetchall())
    db.close()
    return jsonify(rooms)

@app.route('/api/hotels/<slug>/menu', methods=['GET'])
def get_hotel_menu(slug):
    db = get_db()
    hotel = row_to_dict(db.execute("SELECT id FROM hotels WHERE slug=?", (slug,)).fetchone())
    if not hotel:
        db.close()
        return jsonify({'error': 'Hotel not found'}), 404
    items = rows_to_list(db.execute(
        "SELECT * FROM menu_items WHERE hotel_id=? AND available=1 ORDER BY category, name",
        (hotel['id'],)
    ).fetchall())
    db.close()
    return jsonify(items)

@app.route('/api/hotels/<slug>/bookings', methods=['POST'])
def create_booking(slug):
    db = get_db()
    hotel = row_to_dict(db.execute(
        "SELECT * FROM hotels WHERE slug=? AND is_active=1", (slug,)
    ).fetchone())
    if not hotel:
        db.close()
        return jsonify({'error': 'Hotel not found'}), 404

    data = request.get_json() or {}
    room_id = data.get('room_id', '')
    guest_name = data.get('guest_name', '').strip()
    guest_email = data.get('guest_email', '').strip()
    guest_phone = data.get('guest_phone', '').strip()
    check_in = data.get('check_in', '')
    check_out = data.get('check_out', '')

    if not all([room_id, guest_name, check_in, check_out]):
        db.close()
        return jsonify({'error': 'Missing required fields'}), 400

    room = row_to_dict(db.execute(
        "SELECT * FROM rooms WHERE id=? AND hotel_id=?", (room_id, hotel['id'])
    ).fetchone())
    if not room:
        db.close()
        return jsonify({'error': 'Room not found'}), 404
    if not room['available']:
        db.close()
        return jsonify({'error': 'Room is not available'}), 400

    try:
        ci = datetime.strptime(check_in, '%Y-%m-%d')
        co = datetime.strptime(check_out, '%Y-%m-%d')
        nights = max(1, (co - ci).days)
    except ValueError:
        db.close()
        return jsonify({'error': 'Invalid dates'}), 400

    total = nights * room['price_per_night']
    booking_id = 'b' + str(uuid.uuid4())[:8]

    db.execute("""INSERT INTO bookings
        (id,hotel_id,room_id,guest_name,guest_email,guest_phone,check_in,check_out,nights,total_price,status)
        VALUES (?,?,?,?,?,?,?,?,?,?,'pending')""",
        (booking_id, hotel['id'], room_id, guest_name, guest_email, guest_phone,
         check_in, check_out, nights, total))
    db.commit()
    booking = row_to_dict(db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone())
    db.close()
    return jsonify(booking), 201

# ─── HOTEL ADMIN ROUTES ───

@app.route('/api/admin/hotel', methods=['GET'])
@require_hotel_admin
def admin_get_hotel():
    hotel_id = request.user.get('hotel_id')
    if not hotel_id:
        return jsonify({'error': 'No hotel assigned'}), 400
    db = get_db()
    hotel = row_to_dict(db.execute("SELECT * FROM hotels WHERE id=?", (hotel_id,)).fetchone())
    db.close()
    return jsonify(hotel)

@app.route('/api/admin/hotel', methods=['PATCH'])
@require_hotel_admin
def admin_update_hotel():
    hotel_id = request.user.get('hotel_id')
    if not hotel_id and request.user.get('role') != 'super_admin':
        return jsonify({'error': 'No hotel assigned'}), 400

    data = request.get_json() or {}
    fields = ['name','tagline','about','phone','email','address','city','stars','price_from']
    updates = {k: data[k] for k in fields if k in data}
    if not updates:
        return jsonify({'error': 'No fields to update'}), 400

    set_clause = ', '.join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [hotel_id]
    db = get_db()
    db.execute(f"UPDATE hotels SET {set_clause} WHERE id=?", values)
    db.commit()
    hotel = row_to_dict(db.execute("SELECT * FROM hotels WHERE id=?", (hotel_id,)).fetchone())
    db.close()
    return jsonify(hotel)

@app.route('/api/admin/dashboard', methods=['GET'])
@require_hotel_admin
def admin_dashboard():
    hotel_id = request.user.get('hotel_id')
    db = get_db()
    rooms_count = db.execute("SELECT COUNT(*) FROM rooms WHERE hotel_id=?", (hotel_id,)).fetchone()[0]
    pending = db.execute("SELECT COUNT(*) FROM bookings WHERE hotel_id=? AND status='pending'", (hotel_id,)).fetchone()[0]
    menu_count = db.execute("SELECT COUNT(*) FROM menu_items WHERE hotel_id=?", (hotel_id,)).fetchone()[0]
    total_bk = db.execute("SELECT COUNT(*) FROM bookings WHERE hotel_id=?", (hotel_id,)).fetchone()[0]
    recent_bk = rows_to_list(db.execute(
        """SELECT b.*, r.name as room_name FROM bookings b
           LEFT JOIN rooms r ON b.room_id=r.id
           WHERE b.hotel_id=? ORDER BY b.created_at DESC LIMIT 5""",
        (hotel_id,)
    ).fetchall())
    db.close()
    return jsonify({
        'rooms': rooms_count, 'pending': pending,
        'menu_items': menu_count, 'total_bookings': total_bk,
        'recent_bookings': recent_bk
    })

# ─── ROOMS ADMIN ───

@app.route('/api/admin/rooms', methods=['GET'])
@require_hotel_admin
def admin_get_rooms():
    hotel_id = request.user.get('hotel_id')
    db = get_db()
    rooms = rows_to_list(db.execute(
        "SELECT * FROM rooms WHERE hotel_id=? ORDER BY created_at", (hotel_id,)
    ).fetchall())
    db.close()
    return jsonify(rooms)

@app.route('/api/admin/rooms', methods=['POST'])
@require_hotel_admin
def admin_add_room():
    hotel_id = request.user.get('hotel_id')
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Room name required'}), 400

    room_id = 'r' + str(uuid.uuid4())[:8]
    db = get_db()
    db.execute("""INSERT INTO rooms (id,hotel_id,name,type,capacity,price_per_night,available,description)
                  VALUES (?,?,?,?,?,?,1,?)""",
        (room_id, hotel_id, name,
         data.get('type', 'Double'),
         int(data.get('capacity', 2)),
         int(data.get('price_per_night', 1000)),
         data.get('description', '')))
    db.commit()
    room = row_to_dict(db.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone())
    db.close()
    return jsonify(room), 201

@app.route('/api/admin/rooms/<room_id>', methods=['PATCH'])
@require_hotel_admin
def admin_update_room(room_id):
    hotel_id = request.user.get('hotel_id')
    db = get_db()
    room = row_to_dict(db.execute(
        "SELECT * FROM rooms WHERE id=? AND hotel_id=?", (room_id, hotel_id)
    ).fetchone())
    if not room:
        db.close()
        return jsonify({'error': 'Room not found'}), 404

    data = request.get_json() or {}
    fields = ['name','type','capacity','price_per_night','available','description']
    updates = {k: data[k] for k in fields if k in data}
    if not updates:
        db.close()
        return jsonify({'error': 'Nothing to update'}), 400

    set_clause = ', '.join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [room_id, hotel_id]
    db.execute(f"UPDATE rooms SET {set_clause} WHERE id=? AND hotel_id=?", values)
    db.commit()
    room = row_to_dict(db.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone())
    db.close()
    return jsonify(room)

@app.route('/api/admin/rooms/<room_id>', methods=['DELETE'])
@require_hotel_admin
def admin_delete_room(room_id):
    hotel_id = request.user.get('hotel_id')
    db = get_db()
    result = db.execute(
        "DELETE FROM rooms WHERE id=? AND hotel_id=?", (room_id, hotel_id)
    )
    db.commit()
    db.close()
    if result.rowcount == 0:
        return jsonify({'error': 'Room not found'}), 404
    return jsonify({'ok': True})

# ─── BOOKINGS ADMIN ───

@app.route('/api/admin/bookings', methods=['GET'])
@require_hotel_admin
def admin_get_bookings():
    hotel_id = request.user.get('hotel_id')
    status = request.args.get('status', '')
    db = get_db()
    query = """SELECT b.*, r.name as room_name FROM bookings b
               LEFT JOIN rooms r ON b.room_id=r.id
               WHERE b.hotel_id=?"""
    params = [hotel_id]
    if status and status != 'all':
        query += " AND b.status=?"
        params.append(status)
    query += " ORDER BY b.created_at DESC"
    bookings = rows_to_list(db.execute(query, params).fetchall())
    db.close()
    return jsonify(bookings)

@app.route('/api/admin/bookings/<booking_id>', methods=['PATCH'])
@require_hotel_admin
def admin_update_booking(booking_id):
    hotel_id = request.user.get('hotel_id')
    data = request.get_json() or {}
    status = data.get('status')
    if status not in ('confirmed', 'rejected', 'pending'):
        return jsonify({'error': 'Invalid status'}), 400

    db = get_db()
    result = db.execute(
        "UPDATE bookings SET status=? WHERE id=? AND hotel_id=?",
        (status, booking_id, hotel_id)
    )
    db.commit()
    if result.rowcount == 0:
        db.close()
        return jsonify({'error': 'Booking not found'}), 404
    booking = row_to_dict(db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone())
    db.close()
    return jsonify(booking)

# ─── MENU ADMIN ───

@app.route('/api/admin/menu', methods=['GET'])
@require_hotel_admin
def admin_get_menu():
    hotel_id = request.user.get('hotel_id')
    db = get_db()
    items = rows_to_list(db.execute(
        "SELECT * FROM menu_items WHERE hotel_id=? ORDER BY category, name", (hotel_id,)
    ).fetchall())
    db.close()
    return jsonify(items)

@app.route('/api/admin/menu', methods=['POST'])
@require_hotel_admin
def admin_add_menu():
    hotel_id = request.user.get('hotel_id')
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Item name required'}), 400

    item_id = 'm' + str(uuid.uuid4())[:8]
    db = get_db()
    db.execute("""INSERT INTO menu_items (id,hotel_id,name,category,description,price,available)
                  VALUES (?,?,?,?,?,?,1)""",
        (item_id, hotel_id, name,
         data.get('category', 'Main Dishes'),
         data.get('description', ''),
         int(data.get('price', 0))))
    db.commit()
    item = row_to_dict(db.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone())
    db.close()
    return jsonify(item), 201

@app.route('/api/admin/menu/<item_id>', methods=['DELETE'])
@require_hotel_admin
def admin_delete_menu(item_id):
    hotel_id = request.user.get('hotel_id')
    db = get_db()
    result = db.execute(
        "DELETE FROM menu_items WHERE id=? AND hotel_id=?", (item_id, hotel_id)
    )
    db.commit()
    db.close()
    if result.rowcount == 0:
        return jsonify({'error': 'Item not found'}), 404
    return jsonify({'ok': True})

# ─── SUPER ADMIN ROUTES ───

@app.route('/api/superadmin/stats', methods=['GET'])
@require_super_admin
def sa_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM hotels").fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM hotels WHERE subscription_status='active'").fetchone()[0]
    trial = db.execute("SELECT COUNT(*) FROM hotels WHERE subscription_status='trial'").fetchone()[0]
    expired = db.execute("SELECT COUNT(*) FROM hotels WHERE subscription_status='expired'").fetchone()[0]
    total_bk = db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    db.close()
    return jsonify({'total_hotels': total, 'active': active, 'trial': trial,
                    'expired': expired, 'total_bookings': total_bk})

@app.route('/api/superadmin/hotels', methods=['GET'])
@require_super_admin
def sa_get_hotels():
    db = get_db()
    hotels = rows_to_list(db.execute("""
        SELECT h.*, 
               (SELECT COUNT(*) FROM rooms r WHERE r.hotel_id=h.id) as rooms_count,
               (SELECT COUNT(*) FROM bookings b WHERE b.hotel_id=h.id) as bookings_count
        FROM hotels h ORDER BY h.created_at DESC
    """).fetchall())
    db.close()
    return jsonify(hotels)

@app.route('/api/superadmin/hotels', methods=['POST'])
@require_super_admin
def sa_create_hotel():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    city = data.get('city', '').strip()
    admin_email = data.get('admin_email', '').strip().lower()
    plan = data.get('plan', 'Starter')

    if not all([name, city, admin_email]):
        return jsonify({'error': 'Name, city, and admin email are required'}), 400

    slug = name.lower()
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')

    hotel_id = 'h' + str(uuid.uuid4())[:8]
    trial_end = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')

    db = get_db()
    # Check slug uniqueness
    existing_slug = db.execute("SELECT id FROM hotels WHERE slug=?", (slug,)).fetchone()
    if existing_slug:
        slug = slug + '-' + hotel_id[:4]

    db.execute("""INSERT INTO hotels
        (id,slug,name,city,tagline,about,plan,subscription_status,subscription_ends)
        VALUES (?,?,?,?,?,?,?,'trial',?)""",
        (hotel_id, slug, name, city, f'Welcome to {name}', f'{name} is located in {city}, Ethiopia.',
         plan, trial_end))

    # Create admin user
    user_id = str(uuid.uuid4())
    temp_pass = 'hotel123'
    db.execute("""INSERT INTO users (id,hotel_id,email,password_hash,role,name)
                  VALUES (?,?,?,?,'hotel_admin',?)""",
        (user_id, hotel_id, admin_email, hash_password(temp_pass), name + ' Admin'))

    db.commit()
    hotel = row_to_dict(db.execute("SELECT * FROM hotels WHERE id=?", (hotel_id,)).fetchone())
    db.close()

    return jsonify({**hotel, 'admin_email': admin_email, 'temp_password': temp_pass}), 201

@app.route('/api/superadmin/hotels/<hotel_id>/subscription', methods=['PATCH'])
@require_super_admin
def sa_update_subscription(hotel_id):
    data = request.get_json() or {}
    status = data.get('status')
    if status not in ('active', 'expired', 'trial'):
        return jsonify({'error': 'Invalid status'}), 400

    ends = data.get('ends', (datetime.utcnow() + timedelta(days=365)).strftime('%Y-%m-%d'))

    db = get_db()
    db.execute(
        "UPDATE hotels SET subscription_status=?, subscription_ends=? WHERE id=?",
        (status, ends, hotel_id)
    )
    db.commit()
    hotel = row_to_dict(db.execute("SELECT * FROM hotels WHERE id=?", (hotel_id,)).fetchone())
    db.close()
    if not hotel:
        return jsonify({'error': 'Hotel not found'}), 404
    return jsonify(hotel)

@app.route('/api/superadmin/hotels/<hotel_id>', methods=['DELETE'])
@require_super_admin
def sa_delete_hotel(hotel_id):
    db = get_db()
    db.execute("DELETE FROM hotels WHERE id=?", (hotel_id,))
    db.commit()
    db.close()
    return jsonify({'ok': True})

# ─── START ───
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print(f"""
╔══════════════════════════════════════════╗
║  efoyta.com backend running              ║
║  http://localhost:{port}                    ║
║                                          ║
║  Login credentials:                      ║
║  Super Admin: admin@efoyta.com / admin123║
║  Hotel Admin: kaffa@efoyta.com / hotel123║
╚══════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=port, debug=False)
