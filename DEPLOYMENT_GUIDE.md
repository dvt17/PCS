# PCS Smart Parking System — DEPLOYMENT & OPERATIONS GUIDE

## 📋 QUICK START

### 1. Installation & Setup

```bash
# Clone repository
git clone <repo-url>
cd PCS/BTL

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.\.venv\Scripts\activate
# On Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database (auto-creates on first app run)
python backend/app.py
# Or manually:
python -c "from frontend.core.database import init_db, seed_initial_data; init_db(); seed_initial_data()"

# Configure environment
cp .env.example .env
# Edit .env with your settings:
# - PCS_DB_BACKEND=mysql (or sqlite)
# - PCS_YOLO_MODEL=./best.pt
# - PCS_CHAR_MODEL=./character_detector.pt
```

### 2. Start the Application

```bash
# Development mode (Flask debug enabled)
python backend/app.py

# Production mode (Gunicorn)
gunicorn -w 4 -b 0.0.0.0:5000 backend.app:app

# Access dashboard
# Open browser: http://localhost:5000
# Login: admin / admin123 (default credentials - CHANGE in production)
```

---

## 🗄️ DATABASE INITIALIZATION

### Option A: MySQL (Recommended for Production)

```bash
# 1. Create database and user
mysql -u root -p -e "
CREATE DATABASE pcs_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'pcs_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON pcs_db.* TO 'pcs_user'@'localhost';
FLUSH PRIVILEGES;
"

# 2. The app will auto-create tables on first run, or run:
python -c "
from frontend.core.database import init_db, seed_initial_data
init_db()
seed_initial_data()
"

# 3. Verify tables
mysql -u pcs_user -p pcs_db -e "SHOW TABLES;"
```

### Option B: SQLite (Quick Development)

```bash
# SQLite is the default, auto-created on first run
# Verify database
sqlite3 frontend/data/pcs.db ".tables"
```

---

## ⚙️ CONFIGURATION

### .env File Example

```env
# Database Configuration
PCS_DB_BACKEND=sqlite
# PCS_DB_BACKEND=mysql
PCS_MYSQL_HOST=localhost
PCS_MYSQL_PORT=3306
PCS_MYSQL_USER=pcs_user
PCS_MYSQL_PASSWORD=your_secure_password
PCS_MYSQL_DATABASE=pcs_db
PCS_MYSQL_CHARSET=utf8mb4

# AI Model Configuration
PCS_YOLO_MODEL=./best.pt
PCS_CHAR_MODEL=./character_detector.pt
PCS_DEMO_MODE=False  # Set to True to use demo (no GPU needed)

# Application Configuration
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your_very_long_random_secret_key

# Payment Gateway Configuration (optional)
PAYMENT_GATEWAY_VNPAY=your_vnpay_api_key
PAYMENT_GATEWAY_MOMO=your_momo_api_key

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/pcs.log

# Parking Lot Configuration
LOT_CONFIG_PATH=./frontend/data/lot_config.json
```

### lot_config.json Example

```json
{
  "name": "PCS Parking",
  "slots": [
    {"slot_id": "A01", "zone": "A", "state": "occupied", "current_plate": "51A-12345", "notes": ""},
    {"slot_id": "A02", "zone": "A", "state": "empty", "current_plate": null, "notes": ""},
    ...
    {"slot_id": "B01", "zone": "B", "state": "occupied", "current_plate": "59B-67890", "notes": ""},
    {"slot_id": "B02", "zone": "B", "state": "empty", "current_plate": null, "notes": ""},
    ...
  ]
}
```

**Zones**:
- **Zone A**: Ô tô — 20 slots (A01–A20), giá: 15,000 VNĐ/lượt
- **Zone B**: Xe máy — 40 slots (B01–B40), giá: 5,000 VNĐ/lượt

---

## 🔐 USER & PERMISSION SETUP

### Create Initial Admin User

```python
# Interactive script: python setup_admin.py
from frontend.core.auth import AuthManager, Role
from frontend.core.database import create_user
import uuid

user_id = str(uuid.uuid4().hex[:8].upper())
username = input("Admin username: ")
password = input("Admin password: ")
full_name = input("Full name: ")

create_user(
    user_id=user_id,
    username=username,
    password_hash=AuthManager._hash(password),
    role=Role.ADMIN.value,
    full_name=full_name
)
print(f"✅ Admin user '{username}' created successfully!")
```

### Create Staff & Owner Users

```python
# Staff (Nhân viên)
create_user(
    user_id=str(uuid.uuid4().hex[:8].upper()),
    username="staff1",
    password_hash=AuthManager._hash("staff123"),
    role=Role.STAFF.value,
    full_name="Nguyễn Văn A"
)

# Owner (Chủ xe)
create_user(
    user_id=str(uuid.uuid4().hex[:8].upper()),
    username="owner1",
    password_hash=AuthManager._hash("owner_pass"),
    role=Role.OWNER.value,
    full_name="Trần Thị B"
)
```

---

## 📊 API ENDPOINTS REFERENCE

### Authentication

```bash
# Login
POST /login
Content-Type: application/x-www-form-urlencoded
username=admin&password=admin123

# Logout
GET /logout
```

### Check-In/Check-Out

```bash
# Check-in (Camera capture)
POST /api/process_frame
Content-Type: application/json
{
  "image": "data:image/jpeg;base64,..."
}
Response: {
  "success": true,
  "plate": "51A-12345",
  "confidence": 0.95,
  "vehicle_type": "car",
  "valid": true,
  "message": "Đã nhận diện biển số từ camera"
}

# Manual plate entry
POST /api/entry
Content-Type: application/json
{
  "plate": "51A-12345",
  "vehicle_type": "car"
}
Response: {
  "success": true,
  "message": "✅ 🚗 Ô tô 51A-12345 → A02 (Zone A)",
  "tx": { ... }
}

# Check-out
POST /api/exit
Content-Type: application/json
{
  "plate": "51A-12345",
  "method": "cash"
}
Response: {
  "success": true,
  "message": "Xe 51A-12345 ra — Phí: 75,000đ",
  "receipt": "..."
}

# Auto entry (OCR + suggest + enter)
POST /api/auto_entry
{
  "plate": "51A-12345",
  "vehicle_type": "car"
}
```

### Parking Lot Status

```bash
# Get lot status
GET /api/status
Response: {
  "total": 60,
  "occupied": 2,
  "available": 58,
  "occupancy_pct": 3.3,
  "revenue_today": 75000,
  "txn_count": 1,
  "zones": {
    "A": { "total": 20, "occupied": 1, "available": 19, "rate": 15000, "vehicle_type": "car", "vehicle_label": "🚗 Ô tô" },
    "B": { "total": 40, "occupied": 1, "available": 39, "rate": 5000, "vehicle_type": "motorbike", "vehicle_label": "🏍️ Xe máy" }
  }
}

# Get slot details
GET /api/slots
Response: [
  { "id": "A01", "zone": "A", "state": "occupied", "plate": "51A-12345" },
  ...
]

# Get event feed
GET /api/feed
```

### Admin Operations

```bash
# Update pricing
POST /api/admin/set_rate
{
  "zone": "A",
  "rate": 20000  # New hourly rate
}

# Manage slots
POST /api/admin/slot_action
{
  "action": "disable",
  "slot_id": "A01"
}

# Get reports
GET /api/report/today
GET /api/report/week
GET /api/report/month
Response: {
  "label": "Ngày 2024-01-01",
  "txn_count": 10,
  "total_revenue": 500000,
  "by_zone": { "A": 350000, "B": 150000 },
  "by_method": { "cash": 300000, "momo": 200000 },
  ...
}
```

---

## 🧪 TESTING

### Unit Tests

```bash
# Test OCR engine (demo mode)
python -c "
from frontend.core.ocr_engine import PlateRecognizer
rec = PlateRecognizer()
result = rec._demo_result()
print(f'Plate: {result.plate}, Confidence: {result.confidence:.0%}')
"

# Test Pricing
python -c "
from frontend.core.pricing import Pricing
from frontend.core.vehicle import VehicleType
from datetime import datetime, timedelta

engine = Pricing()
result = engine.calculate_fee_detailed(
    VehicleType.CAR,
    datetime(2024, 1, 1, 9, 0),
    datetime(2024, 1, 1, 13, 30),
    has_active_combo=False
)
print(f'Fee: {result[\"fee\"]:,} VNĐ')
"
```

---

## 📈 MONITORING & MAINTENANCE

### Database Backup

```bash
# Daily SQLite backup
0 2 * * * cp /path/to/pcs.db /backups/pcs_db_$(date +\%Y\%m\%d).db

# Daily MySQL backup (cron job)
0 2 * * * /usr/bin/mysqldump -u pcs_user -p${MYSQL_PASSWORD} pcs_db > /backups/pcs_db_$(date +\%Y\%m\%d).sql
```

### Log Analysis

```bash
# Check application logs
tail -f ./logs/pcs.log | grep ERROR

# Analyze OCR failures
grep "ocr_failed" ./logs/pcs.log | wc -l
```

---

## 🚨 TROUBLESHOOTING

### Issue: YOLO Model Not Found

```bash
# Check model files exist
ls -la best.pt character_detector.pt

# Set environment variables
export PCS_YOLO_MODEL=./best.pt
export PCS_CHAR_MODEL=./character_detector.pt

# Use demo mode (no GPU required)
export PCS_DEMO_MODE=True
```

### Issue: MySQL Connection Timeout

```bash
# Check MySQL service
sudo systemctl status mysql

# Verify credentials
mysql -u pcs_user -p pcs_db -e "SELECT 1"

# Check connection parameters in .env
cat .env | grep MYSQL
```

### Issue: Low OCR Accuracy

```python
# Increase confidence threshold in ocr_engine.py
# The system uses 3-stage fallback:
# 1. character_detector.pt (character-level detection) [PRIMARY]
# 2. EasyOCR with multi-strategy preprocessing [FALLBACK]
# 3. Full-frame EasyOCR [LAST RESORT]

# Pre-process image for better results
import cv2
image = cv2.imread(image_path)
# CLAHE equalization is already built into the pipeline
```

---

## 📅 MAINTENANCE SCHEDULE

| Task | Frequency | Owner |
|------|-----------|-------|
| Database backup | Daily (2 AM) | Admin |
| YOLO model accuracy check | Weekly | Developer |
| Log rotation | Weekly | Admin |
| Security patches | As needed | Admin |
| OCR confidence audit | Monthly | Developer |

---

## 📞 SUPPORT & ESCALATION

### Emergency Procedures

```
1. System crash: Restart Flask app
2. Database corruption: Restore from backup
3. Payment gateway down: Switch to cash-only mode
4. YOLO model failure: Fall back to demo mode (PCS_DEMO_MODE=True)
```
