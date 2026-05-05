import sqlite3
import hashlib
import uuid
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'efoyta.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def hash_password(password):
    salt = "efoyta_salt_2025"
    return hashlib.sha256((password + salt).encode()).hexdigest()

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS hotels (
            id TEXT PRIMARY KEY,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            emoji TEXT DEFAULT '🏨',
            tagline TEXT DEFAULT '',
            about TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            address TEXT DEFAULT '',
            stars TEXT DEFAULT '★★★',
            price_from INTEGER DEFAULT 1000,
            plan TEXT DEFAULT 'Starter',
            subscription_status TEXT DEFAULT 'trial' CHECK(subscription_status IN ('active','expired','trial')),
            subscription_ends TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            hotel_id TEXT REFERENCES hotels(id),
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('super_admin','hotel_admin')),
            name TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            hotel_id TEXT NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'Double',
            capacity INTEGER DEFAULT 2,
            price_per_night INTEGER NOT NULL,
            available INTEGER DEFAULT 1,
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            hotel_id TEXT NOT NULL REFERENCES hotels(id),
            room_id TEXT NOT NULL REFERENCES rooms(id),
            guest_name TEXT NOT NULL,
            guest_email TEXT DEFAULT '',
            guest_phone TEXT DEFAULT '',
            check_in TEXT NOT NULL,
            check_out TEXT NOT NULL,
            nights INTEGER DEFAULT 1,
            total_price INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending','confirmed','rejected')),
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS menu_items (
            id TEXT PRIMARY KEY,
            hotel_id TEXT NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT DEFAULT '',
            price INTEGER DEFAULT 0,
            available INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_rooms_hotel ON rooms(hotel_id);
        CREATE INDEX IF NOT EXISTS idx_bookings_hotel ON bookings(hotel_id);
        CREATE INDEX IF NOT EXISTS idx_menu_hotel ON menu_items(hotel_id);
        CREATE INDEX IF NOT EXISTS idx_hotels_city ON hotels(city);
    """)

    # Check if already seeded
    existing = c.execute("SELECT COUNT(*) FROM hotels").fetchone()[0]
    if existing > 0:
        conn.commit()
        conn.close()
        return

    # ── SEED HOTELS ──
    hotels = [
        ('h1','kaffa-grand','Kaffa Grand Hotel','Jimma','☕','Where highland hospitality meets modern comfort',
         'Nestled in the heart of Jimma, we offer guests an unforgettable blend of traditional Ethiopian hospitality and contemporary amenities. Founded in 2010, we have welcomed guests from across Ethiopia and beyond with genuine warmth and impeccable service.',
         '+251 47 112 0000','info@kaffagrand.et','Jimma Town, Oromia Region, Ethiopia','★★★★',1200,'Professional','active','2025-12-31'),
        ('h2','addis-luxury','Addis Luxury Suites','Addis Ababa','🏙️','The pinnacle of Addis Ababa hospitality',
         'A premium five-star experience in the heart of the capital, with world-class amenities and impeccable service.',
         '+251 11 551 0000','hello@addisluxury.et','Bole Road, Addis Ababa, Ethiopia','★★★★★',3500,'Enterprise','active','2025-12-31'),
        ('h3','hawassa-lake','Hawassa Lakeside Resort','Hawassa','🌊','Wake up to the lake every morning',
         'Perched on the shores of Lake Hawassa with stunning views and direct lake access.',
         '+251 46 221 0000','stay@hawassalake.et','Lake Shore Road, Hawassa, Ethiopia','★★★★',1800,'Professional','active','2025-06-15'),
        ('h4','blue-nile-inn','Blue Nile Inn','Bahir Dar','🌊','Gateway to the Blue Nile Falls',
         'A comfortable inn near the famous Blue Nile Falls, perfect for nature lovers.',
         '+251 58 220 0000','info@bluenileinn.et','Near Blue Nile Falls, Bahir Dar, Ethiopia','★★★',900,'Starter','trial','2025-05-20'),
        ('h5','dira-plaza','Dire Dawa Plaza Hotel','Dire Dawa','🏨','Eastern Ethiopia\'s finest accommodation',
         'Modern comfort in the commercial heart of Dire Dawa, close to the railway station.',
         '+251 25 111 0000','contact@direplaza.et','Commercial Street, Dire Dawa, Ethiopia','★★★★',1400,'Professional','active','2025-07-01'),
        ('h6','jimma-palace','Jimma Palace Hotel','Jimma','🏰','Regal comfort in the coffee capital',
         'Historic hotel with modern luxury at the heart of Jimma city centre.',
         '+251 47 113 0000','info@jimmapalace.et','Main Square, Jimma, Ethiopia','★★★★',1600,'Professional','active','2025-08-31'),
        ('h7','ghion-hotel','Ghion Hotel Addis','Addis Ababa','🌿','A garden oasis in the capital',
         "Ethiopia's classic government hotel with beautiful gardens and a rich history.",
         '+251 11 551 4400','info@ghionhotel.et','Ras Mekonen Street, Addis Ababa, Ethiopia','★★★★',2200,'Enterprise','active','2025-12-31'),
        ('h8','sibu-lodge','Sibu Mountain Lodge','Jimma','⛰️','Off-grid serenity above Jimma',
         'Eco-lodge perched above the city with panoramic views of the Jimma highlands.',
         '+251 47 114 0000','stay@sibulodge.et','Jimma Mountain Road, Oromia, Ethiopia','★★★',750,'Starter','expired','2025-04-30'),
    ]
    for h in hotels:
        c.execute("""INSERT OR IGNORE INTO hotels
            (id,slug,name,city,emoji,tagline,about,phone,email,address,stars,price_from,plan,subscription_status,subscription_ends)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", h)

    # ── SEED USERS ──
    # super_admin: admin@efoyta.com / admin123
    # hotel_admin for kaffa-grand: kaffa@efoyta.com / hotel123
    users = [
        (str(uuid.uuid4()), None, 'admin@efoyta.com', hash_password('admin123'), 'super_admin', 'Platform Admin'),
        (str(uuid.uuid4()), 'h1', 'kaffa@efoyta.com', hash_password('hotel123'), 'hotel_admin', 'Kaffa Manager'),
        (str(uuid.uuid4()), 'h2', 'addis@efoyta.com', hash_password('hotel123'), 'hotel_admin', 'Addis Manager'),
    ]
    for u in users:
        c.execute("INSERT OR IGNORE INTO users (id,hotel_id,email,password_hash,role,name) VALUES (?,?,?,?,?,?)", u)

    # ── SEED ROOMS for kaffa-grand ──
    rooms = [
        ('r1','h1','Standard Single','Single',1,800,1,'Cosy room with garden view'),
        ('r2','h1','Deluxe Double','Double',2,1200,1,'Spacious room with mountain view'),
        ('r3','h1','Executive Suite','Suite',2,2500,0,'Premium suite with private lounge'),
        ('r4','h1','Family Room','Family',4,1800,1,'Ideal for families with children'),
        ('r5','h2','Superior King','Double',2,3500,1,'Luxurious king bed with city view'),
        ('r6','h2','Presidential Suite','Suite',4,8000,1,'Our finest suite with butler service'),
    ]
    for r in rooms:
        c.execute("INSERT OR IGNORE INTO rooms (id,hotel_id,name,type,capacity,price_per_night,available,description) VALUES (?,?,?,?,?,?,?,?)", r)

    # ── SEED BOOKINGS ──
    bookings = [
        ('b1','h1','r2','Abebe Kebede','abebe@email.com','+251911000001','2025-05-15','2025-05-18',3,3600,'confirmed'),
        ('b2','h1','r1','Sara Haile','sara@email.com','+251911000002','2025-05-20','2025-05-22',2,1600,'pending'),
        ('b3','h1','r4','Mohammed Ali','mo@email.com','+251911000003','2025-05-25','2025-05-28',3,5400,'pending'),
        ('b4','h1','r3','Tigist Bekele','tigist@email.com','+251911000004','2025-06-01','2025-06-03',2,5000,'rejected'),
        ('b5','h1','r2','Daniel Mesfin','dan@email.com','+251911000005','2025-06-10','2025-06-12',2,2400,'confirmed'),
    ]
    for b in bookings:
        c.execute("INSERT OR IGNORE INTO bookings (id,hotel_id,room_id,guest_name,guest_email,guest_phone,check_in,check_out,nights,total_price,status) VALUES (?,?,?,?,?,?,?,?,?,?,?)", b)

    # ── SEED MENU for kaffa-grand ──
    menu = [
        ('m1','h1','Injera with Doro Wot','Main Dishes','Traditional Ethiopian chicken stew',180),
        ('m2','h1','Tibs (Lamb)','Main Dishes','Pan-fried tender lamb with herbs',220),
        ('m3','h1','Vegetarian Combo','Main Dishes','Seasonal lentils, greens & salad',150),
        ('m4','h1','Sambusa','Starters','Crispy pastry with spiced filling',60),
        ('m5','h1','Avocado Juice','Beverages','Fresh local avocado',45),
        ('m6','h1','Jimma Bunna','Beverages','Traditional Ethiopian coffee ceremony',35),
        ('m7','h1','Macchiato','Beverages','Ethiopian-style espresso macchiato',25),
        ('m8','h1','Honey Cake','Desserts','Local honey and spice cake',80),
    ]
    for m in menu:
        c.execute("INSERT OR IGNORE INTO menu_items (id,hotel_id,name,category,description,price) VALUES (?,?,?,?,?,?)", m)

    conn.commit()
    conn.close()
    print("✓ Database initialized and seeded")

if __name__ == '__main__':
    init_db()
