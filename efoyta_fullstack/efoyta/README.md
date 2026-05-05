# efoyta.com — Hotel SaaS Platform

A fully functional multi-tenant hotel booking and management SaaS platform.

## Architecture

```
efoyta/
├── backend/
│   ├── app.py        — Flask REST API (all routes)
│   ├── db.py         — SQLite database + seed data
│   └── efoyta.db     — SQLite database (auto-created on first run)
├── frontend/
│   └── public/
│       └── index.html — Single-page app (served by Flask)
├── requirements.txt
├── Procfile           — For Railway/Heroku
└── render.yaml        — For Render.com
```

## Demo Credentials

| Role | Email | Password |
|------|-------|----------|
| Super Admin | admin@efoyta.com | admin123 |
| Hotel Admin (Kaffa Grand) | kaffa@efoyta.com | hotel123 |
| Hotel Admin (Addis Luxury) | addis@efoyta.com | hotel123 |

## Local Development

```bash
# Install dependencies
pip install flask PyJWT gunicorn

# Run development server
cd backend
python app.py

# Open http://localhost:5000
```

## Deploy to Render.com (Free, Recommended)

1. Push this folder to a GitHub repository
2. Go to https://render.com → New → Web Service
3. Connect your GitHub repo
4. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --chdir backend app:app --bind 0.0.0.0:$PORT`
   - **Environment:** Python 3
5. Add environment variable: `JWT_SECRET` = any random string
6. Click Deploy

## Deploy to Railway.app

1. Push to GitHub
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Select your repo — Railway auto-detects the `railway.toml`
4. Add `JWT_SECRET` environment variable
5. Deploy

## API Endpoints

### Public
- `GET /api/hotels` — List hotels (filter: `?city=Jimma&q=search`)
- `GET /api/hotels/:slug` — Hotel details
- `GET /api/hotels/:slug/rooms` — Hotel rooms
- `GET /api/hotels/:slug/menu` — Hotel menu
- `POST /api/hotels/:slug/bookings` — Create booking

### Auth
- `POST /api/auth/login` — Login → returns JWT
- `POST /api/auth/logout` — Logout
- `GET /api/auth/me` — Current user (requires JWT)

### Hotel Admin (JWT required, hotel_admin role)
- `GET /api/admin/hotel` — Get own hotel info
- `PATCH /api/admin/hotel` — Update hotel info
- `GET /api/admin/dashboard` — Dashboard stats
- `GET /api/admin/rooms` — List rooms
- `POST /api/admin/rooms` — Add room
- `PATCH /api/admin/rooms/:id` — Update room (toggle availability)
- `DELETE /api/admin/rooms/:id` — Delete room
- `GET /api/admin/bookings` — List bookings (filter: `?status=pending`)
- `PATCH /api/admin/bookings/:id` — Approve/reject booking
- `GET /api/admin/menu` — List menu items
- `POST /api/admin/menu` — Add menu item
- `DELETE /api/admin/menu/:id` — Delete menu item

### Super Admin (JWT required, super_admin role)
- `GET /api/superadmin/stats` — Platform stats
- `GET /api/superadmin/hotels` — All hotels with room/booking counts
- `POST /api/superadmin/hotels` — Create hotel + admin user
- `PATCH /api/superadmin/hotels/:id/subscription` — Update subscription status
- `DELETE /api/superadmin/hotels/:id` — Delete hotel

## Security

- JWT tokens expire after 24 hours
- All admin routes require valid JWT
- Hotel admins can ONLY access their own hotel's data (enforced server-side on every request)
- Super admin has full platform access
- Passwords hashed with SHA-256 + salt (upgrade to bcrypt for production)

## Production Checklist

- [ ] Change `JWT_SECRET` to a long random string
- [ ] Switch to PostgreSQL (replace sqlite3 with psycopg2 + SQLAlchemy)
- [ ] Use real bcrypt for passwords (`pip install bcrypt`)
- [ ] Add HTTPS (handled by Render/Railway automatically)
- [ ] Set up Cloudinary for image uploads
- [ ] Integrate Chapa for payments
- [ ] Add rate limiting on auth endpoints
