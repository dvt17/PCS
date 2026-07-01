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
.\.venv\Scripts\Activate.ps1
# On Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download YOLO models (one-time setup)
python -c "from ultralytics import YOLO; YOLO('yolo26n.pt')"

# Initialize database
python frontend/core/db_schema.py

# Configure environment
cp .env.example .env
# Edit .env with your settings:
# - PCS_DB_BACKEND=mysql (or sqlite)
# - PCS_MYSQL_HOST=localhost
# - PCS_MYSQL_PORT=3306
# - PCS_MYSQL_USER=pcs_user
# - PCS_MYSQL_PASSWORD=secure_password
# - PCS_MYSQL_DATABASE=pcs_db
# - PCS_YOLO_MODEL=./yolo26n.pt
```

### 2. Start the Application

```bash
# Development mode (Flask debug enabled)
python backend/app.py

# Production mode (Gunicorn)
gunicorn -w 4 -b 0.0.0.0:5000 backend.app:app

# Access dashboard
# Open browser: http://localhost:5000
# Login: admin/admin (default credentials - CHANGE in production)
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

# 2. Execute schema SQL
mysql -u pcs_user -p pcs_db < frontend/core/db_schema.py

# 3. Load seed data
python -c "
from frontend.core.database import init_db, seed_initial_data
init_db()
seed_initial_data()
"

# 4. Verify tables
mysql -u pcs_user -p pcs_db -e "SHOW TABLES;"
```

### Option B: SQLite (Quick Development)

```bash
# SQLite is the default, auto-created on first run
python -c "
from frontend.core.db_schema import init_schema
init_schema('sqlite')
"

# Verify database
sqlite3 frontend/data/pcs.db ".tables"
```

---

## ⚙️ CONFIGURATION

### .env File Example

```env
# Database Configuration
PCS_DB_BACKEND=mysql
PCS_MYSQL_HOST=localhost
PCS_MYSQL_PORT=3306
PCS_MYSQL_USER=pcs_user
PCS_MYSQL_PASSWORD=your_secure_password
PCS_MYSQL_DATABASE=pcs_db
PCS_MYSQL_CHARSET=utf8mb4

# AI Model Configuration
PCS_YOLO_MODEL=./yolo26n.pt
PCS_DEMO_MODE=False  # Set to True to use demo (no GPU needed)

# Application Configuration
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your_very_long_random_secret_key

# Payment Gateway Configuration
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
  "name": "PCS Smart Parking - Downtown",
  "location": "123 Main Street, City",
  "zones": {
    "A": {
      "name": "Cars (< 7 seats)",
      "vehicle_types": ["car_under_7"],
      "slots": 20,
      "default_rate": 30000
    },
    "B": {
      "name": "Motorcycles",
      "vehicle_types": ["motorbike", "electric_bike"],
      "slots": 40,
      "default_rate": 5000
    },
    "C": {
      "name": "Trucks (7-16 seats)",
      "vehicle_types": ["car_7_16"],
      "slots": 10,
      "default_rate": 40000
    }
  },
  "operating_hours": {
    "start": "06:00",
    "end": "22:00"
  },
  "barrier_config": {
    "entry_port": "/dev/ttyUSB0",
    "exit_port": "/dev/ttyUSB1",
    "open_duration_seconds": 5
  }
}
```

---

## 🔐 USER & PERMISSION SETUP

### Create Initial Admin User

```python
# Interactive script: python setup_admin.py
from frontend.core.auth import AuthManager, Role
from frontend.core.database import create_user
import uuid

user_id = str(uuid.uuid4())
username = input("Admin username: ")
password = input("Admin password: ")
full_name = input("Full name: ")

create_user(
    user_id=user_id,
    username=username,
    password_hash=AuthManager.hash_password(password),
    role=Role.ADMIN.value,
    full_name=full_name
)
print(f"✅ Admin user '{username}' created successfully!")
```

### Create Operator & Owner Users

```python
# Operator (Staff)
create_user(
    username="operator1",
    password_hash=AuthManager.hash_password("operator_pass"),
    role=Role.OPERATOR.value,
    full_name="Nguyễn Văn A"
)

# Owner (Vehicle Owner - for mobile app login)
create_user(
    username="owner1",
    password_hash=AuthManager.hash_password("owner_pass"),
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
Content-Type: application/json
{
  "username": "admin",
  "password": "admin"
}
Response: {
  "success": true,
  "user_id": "uuid",
  "role": "admin",
  "token": "jwt_token"
}

# Logout
GET /logout
```

### Check-In/Check-Out

```bash
# Check-in (Camera capture)
POST /api/process_frame
Content-Type: application/json
{
  "image": "data:image/jpeg;base64,..."  # Base64 encoded frame
}
Response: {
  "success": true,
  "plate": "51A-12345",
  "confidence": 0.95,
  "vehicle_type": "car_under_7",
  "valid": true,
  "slot_id": "A5",
  "message": "Xe vào ô A5 thành công"
}

# Manual plate entry (Operator override)
POST /api/manual_entry
{
  "plate": "51A-12345",
  "vehicle_type": "car_under_7",
  "operation": "checkin"
}

# Check-out
POST /api/process_image
Content-Type: multipart/form-data
file: <image_file>
Response: {
  "success": true,
  "plate": "51A-12345",
  "fee": 150000,
  "duration_hours": 5,
  "message": "Tính phí thành công"
}

# Get transaction status
GET /api/transaction/{transaction_id}
Response: {
  "transaction_id": "uuid",
  "plate": "51A-12345",
  "check_in_time": "2024-01-01T09:00:00",
  "check_out_time": "2024-01-01T13:30:00",
  "duration": "4h 30min",
  "fee": 150000,
  "payment_status": "completed",
  "slot_id": "A5"
}
```

### Parking Lot Status

```bash
# Get lot status
GET /api/status
Response: {
  "total": 70,
  "occupied": 45,
  "available": 25,
  "occupancy_pct": 64.3,
  "revenue_today": 2500000,
  "zones": {
    "A": { "total": 20, "occupied": 15, "available": 5 },
    "B": { "total": 40, "occupied": 25, "available": 15 },
    "C": { "total": 10, "occupied": 5, "available": 5 }
  }
}

# Get slot details
GET /api/slots
Response: [
  {
    "id": "A1",
    "zone": "A",
    "status": "occupied",
    "plate": "51A-12345"
  },
  ...
]

# Get history
GET /api/recent_history
GET /api/image_history/{plate}
```

### Admin Operations

```bash
# Update pricing
POST /api/admin/set_rate
{
  "zone": "A",
  "rate": 35000  # New hourly rate
}

# Manage slots
POST /api/admin/slot_action
{
  "action": "disable",  # disable | enable | reset
  "slot_id": "A1",
  "reason": "Maintenance"
}

# Get reports
GET /api/report/today
GET /api/report/week
GET /api/report/month
Response: {
  "total_checkins": 120,
  "total_checkouts": 118,
  "total_revenue": 5000000,
  "average_occupancy": 72.5,
  "peak_hour": "09-10",
  "top_slots": [...]
}
```

---

## 🧪 TESTING

### Unit Tests

```bash
# Run unit tests
pytest tests/unit/ -v

# Test OCR engine
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
    VehicleType.CAR_UNDER_7,
    datetime(2024, 1, 1, 9, 0),
    datetime(2024, 1, 1, 13, 30),
    has_active_combo=False
)
print(f'Fee: {result[\"fee\"]:,} VNĐ')
"
```

### Integration Tests

```bash
# Full workflow test
python tests/integration/test_checkin_checkout.py

# Load testing
ab -n 1000 -c 100 http://localhost:5000/api/status

# Stress test with concurrent vehicles
python tests/load/stress_test.py
```

---

## 📈 MONITORING & MAINTENANCE

### Health Check Endpoint

```bash
GET /api/health
Response: {
  "status": "healthy",
  "db": "connected",
  "yolo": "ready",
  "timestamp": "2024-01-01T12:00:00"
}
```

### Database Backup

```bash
# Daily MySQL backup (cron job)
0 2 * * * /usr/bin/mysqldump -u pcs_user -p${MYSQL_PASSWORD} pcs_db > /backups/pcs_db_$(date +\%Y\%m\%d).sql

# Restore from backup
mysql -u pcs_user -p pcs_db < /backups/pcs_db_20240101.sql
```

### Log Analysis

```bash
# Check error logs
tail -f ./logs/pcs.log | grep ERROR

# Analyze OCR failures
grep "ocr_failed" ./logs/pcs.log | wc -l

# Peak hour analysis
grep "checkin" ./logs/pcs.log | awk '{print $1}' | sort | uniq -c
```

### Performance Monitoring

```bash
# Monitor API response times
# Use APM tools: NewRelic, DataDog, Splunk
# Example: Create custom metric in backend
from time import time
start = time()
result = recognize_plate(image)
duration = time() - start
log_metric("ocr.recognition_time", duration)
```

---

## 🚨 TROUBLESHOOTING

### Issue: YOLO Model Not Found

```bash
# Solution 1: Download manually
python -c "from ultralytics import YOLO; YOLO('yolo26n.pt')"

# Solution 2: Set environment variable
export PCS_YOLO_MODEL=/full/path/to/yolo26n.pt

# Solution 3: Use demo mode (no GPU required)
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
# Increase confidence threshold
CONFIDENCE_THRESHOLD = 0.85  # Instead of 0.70

# Use higher quality YOLO model
# Download yolov8m.pt or yolov8l.pt for better accuracy
# Trade-off: slower inference

# Pre-process image
import cv2
image = cv2.imread(image_path)
image = cv2.equalizeHist(image)  # Improve contrast
result = recognizer.analyze_frame(image)
```

### Issue: Payment Gateway Failures

```python
# Implement retry logic
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

for attempt in range(MAX_RETRIES):
    try:
        response = payment_gateway.request_payment(request)
        if response.success:
            break
    except Exception as e:
        if attempt < MAX_RETRIES - 1:
            sleep(RETRY_DELAY)
        else:
            raise
```

---

## 📞 SUPPORT & ESCALATION

### Emergency Procedures

```
1. Barrier stuck: Manual override key location [SPECIFY]
2. System crash: Restart sequence [SPECIFY]
3. Database corruption: Use latest backup from [SPECIFY]
4. Payment gateway down: Use cash-only mode, mark manual later
5. YOLO model failure: Fall back to EasyOCR only mode
```

### Contact Information

- **Technical Support**: support@pcs-parking.local
- **On-call Engineer**: +84-xxx-xxx-xxxx
- **Database Admin**: dba@pcs-parking.local

---

## 📅 MAINTENANCE SCHEDULE

| Task | Frequency | Owner |
|------|-----------|-------|
| Database backup | Daily (2 AM) | DBAdmin |
| YOLO model accuracy check | Weekly | ML Engineer |
| Log rotation | Weekly | SysAdmin |
| Security patches | As needed | SecTeam |
| Barrier maintenance | Monthly | Maintenance |
| OCR confidence audit | Monthly | QA |
| Disaster recovery drill | Quarterly | All |

