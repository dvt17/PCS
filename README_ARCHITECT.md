# PCS Smart Parking System — ARCHITECT REVIEW

## 🏗️ PROJECT STATUS

Dưới đây là báo cáo chi tiết về toàn bộ hệ thống Smart Parking.

---

## 📚 DOCUMENTS

### 1️⃣ **SYSTEM_DESIGN.md** — Thiết kế hệ thống chi tiết
**Vị trí**: `PCS/SYSTEM_DESIGN.md`

### 2️⃣ **AI_PIPELINE.md** — Chi tiết AI Vision Pipeline
**Vị trí**: `PCS/BTL/AI_PIPELINE.md`

### 3️⃣ **DEPLOYMENT_GUIDE.md** — Hướng dẫn triển khai & vận hành
**Vị trí**: `PCS/DEPLOYMENT_GUIDE.md`

---

## 🗄️ DATABASE SCHEMA

### **database.py** — Script khởi tạo (SQLite + MySQL)
```
✅ 6 bảng chính:
  1. vehicles        (License Plate PK, 2 loại: car/motorbike)
  2. transactions    (Complete transaction lifecycle)
  3. parking_log     (System event logging)
  4. image_history   (Recognition audit trail)
  5. users           (RBAC - admin/staff/owner)
  6. uploaded_images (Image storage in DB)

✅ MySQL compatible (với fallback SQLite)
✅ Full indexes & foreign keys
```

**Vị trí**: `frontend/core/database.py`

---

## 💰 PRICING ENGINE

### **pricing.py** — Công cụ tính toán phí (2 loại xe)
```python
✅ Bảng giá mặc định:
  - Xe máy: 5,000 VNĐ/lượt | 150,000 VNĐ/tháng
  - Ô tô: 15,000 VNĐ/lượt | 900,000 VNĐ/tháng

✅ Logic tính toán:
  - Nếu có Combo đang hoạt động → Phí = 0
  - Nếu Combo hết hạn → Áp dụng bảng giá non-combo
  - Tính phí = Hours × Hourly_rate (tối thiểu 1 lượt)
```

**Vị trí**: `frontend/core/pricing.py`

---

## 🎬 WORKFLOW LOGIC

### Check-In Workflow
```
1. Chụp ảnh / nhập plate
2. AI nhận diện (best.pt + character_detector.pt + EasyOCR)
3. Kiểm tra độ tin cậy (confidence >= 0.65?)
4. Kiểm tra trạng thái xe (đã đỗ rồi?)
5. Tìm ô đỗ trống theo loại xe (Zone A = Ô tô, Zone B = Xe máy)
6. Cập nhật trạng thái Slot
7. Tạo Transaction record
8. Lưu log sự kiện
9. Hiển thị kết quả UI + thông báo vị trí đỗ
```

### Check-Out Workflow
```
1. Chụp ảnh / nhập plate
2. AI nhận diện biển số
3. Tìm Transaction đang mở
4. Tải Pricing Config
5. Tính phí (Combo hoặc non-combo)
6. Xử lý thanh toán (CASH/MoMo/VNPAY/ZaloPay)
7. Cập nhật Transaction (check_out_time, fee)
8. Giải phóng Slot
9. Return receipt & success
```

---

## 🔐 RBAC PERMISSION MODEL

### 3 Roles

| Permission | Admin | Nhân viên (Staff) | Chủ xe (Owner) |
|---|---|---|---|
| checkin | ✅ | ✅ | ❌ |
| checkout | ✅ | ✅ | ❌ |
| manage_slots | ✅ | ❌ | ❌ |
| config_lot | ✅ | ❌ | ❌ |
| view_reports | ✅ | ❌ | ❌ |
| manage_users | ✅ | ❌ | ❌ |
| view_status | ✅ | ✅ | ✅ |
| view_own_history | ❌ | ❌ | ✅ |

---

## 🤖 AI VISION PIPELINE

### Dual-Model Architecture
```
Input Frame
    ↓
┌─────────────────────────────────────┐
│ Model 1: best.pt (YOLO)             │
│ - Vehicle Detection (car/motorbike) │
│ - License Plate Detection (region)  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Model 2: character_detector.pt      │
│ [PRIMARY]                           │
│ - Character-level detection         │
│ - Sorts left-to-right → plate text  │
└─────────────────────────────────────┘
    ↓ (fallback nếu confidence thấp)
┌─────────────────────────────────────┐
│ EasyOCR Multi-Strategy [FALLBACK]   │
│ - CLAHE + Adaptive Threshold + OTSU │
│ - Full-frame OCR (last resort)      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Post-Processing: Normalize & Validate│
│ plate="51A-12345", valid=true       │
└─────────────────────────────────────┘
```

---

## 📋 CONFIGURATION FILES

### **.env.example** — Comprehensive Configuration
```
✅ Database config (MySQL/SQLite)
✅ AI Model paths (best.pt, character_detector.pt) & demo mode
✅ Flask configuration
✅ Payment gateway credentials
✅ Parking lot config path
✅ Logging & monitoring
✅ OCR confidence thresholds
✅ Security settings
```

**Vị trí**: `PCS/BTL/.env.example`

---

## 📁 PROJECT STRUCTURE

```
PCS/BTL/
├── backend/
│   ├── app.py (Flask entry point)
│   └── (API routes & logic)
├── frontend/
│   ├── core/
│   │   ├── database.py (Data layer)
│   │   ├── db_schema.py (MySQL schema)
│   │   ├── pricing.py (2 vehicle types)
│   │   ├── ocr_engine.py (Dual-model pipeline)
│   │   ├── workflow.py (Check-in/out logic)
│   │   ├── auth.py (RBAC - admin/staff/owner)
│   │   ├── parking_lot.py (2 zones)
│   │   └── ...
│   ├── templates/
│   │   └── (4 role-based dashboards)
│   ├── static/
│   │   └── (CSS, JS, favicon)
│   └── data/
│       ├── lot_config.json (60 slots)
│       └── uploads/ (OCR images)
├── best.pt (YOLO model)
├── character_detector.pt (Character model)
├── requirements.txt
├── .env.example
├── SYSTEM_DESIGN.md
├── DEPLOYMENT_GUIDE.md
├── AI_PIPELINE.md
└── README.md
```

---

## ✨ KEY POINTS

✅ **2 Zones**: Zone A (Ô tô - 20 chỗ), Zone B (Xe máy - 40 chỗ)
✅ **2 Vehicle Types**: Chỉ còn Ô tô và Xe máy
✅ **Dual-model AI**: best.pt + character_detector.pt + EasyOCR fallback
✅ **3 Roles**: Admin, Staff (Nhân viên), Owner (Chủ xe)
✅ **Pricing**: 15,000đ/lượt (Ô tô), 5,000đ/lượt (Xe máy)
✅ **6 Database Tables**: vehicles, transactions, parking_log, image_history, users, uploaded_images
