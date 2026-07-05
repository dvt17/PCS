# PCS Smart Parking System — SYSTEM DESIGN DOCUMENT

## 📐 ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│              Frontend (Web Dashboard)                           │
│   - Admin: Config, Reports, RBAC Management                    │
│   - Staff: Live Monitoring, OCR Override, Maintenance          │
│   - Owner: Combo Management, History, Payment Integration      │
└──────────────┬──────────────────────────────────────────────────┘
               │ RESTful APIs (JSON)
┌──────────────▼──────────────────────────────────────────────────┐
│          Backend (Flask) — API Layer & Business Logic          │
│   - /api/entry  | /api/exit    | /api/payment                  │
│   - /api/report | /api/admin   | /api/status                   │
│   - /api/suggest_slot | /api/auto_entry                        │
└──────────────┬──────────────────────────────────────────────────┘
               │ Method Calls
┌──────────────▼──────────────────────────────────────────────────┐
│         Business Logic Layer (Python Core Modules)              │
│   ┌──────────────┬──────────────┬──────────────┐               │
│   │ ParkingLot   │ Transactions │ Pricing      │               │
│   │ (2 Zones)    │ (Ledger)     │ (2 loại xe)  │               │
│   └──────────────┴──────────────┴──────────────┘               │
│   ┌──────────────┬──────────────┬──────────────┐               │
│   │ Workflow     │ OCR Engine   │ Payment      │               │
│   │ (In/Out)     │ (Dual-model) │ (Gateway)    │               │
│   └──────────────┴──────────────┴──────────────┘               │
└──────────────┬──────────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
   ┌───▼────────┐  ┌───▼──────────────┐
   │ AI Module  │  │ Data Layer       │
   │────────────│  │──────────────────│
   │best.pt     │  │SQLite (Primary)  │
   │character_det│  │MySQL (Alt)      │
   │EasyOCR     │  │Query Builder    │
   └────────────┘  └──────────────────┘
```

---

## 🔄 DETAILED WORKFLOWS

### 1. CHECK-IN WORKFLOW (Xe Vào Bãi)

```
START: Vehicle arrives at entrance
│
├─ STEP 1: Image Capture (camera) OR manual plate input
│
├─ STEP 2: AI Recognition Pipeline
│  ├─ best.pt (YOLO) → vehicle type + plate bbox detection
│  ├─ character_detector.pt → character-level recognition [PRIMARY]
│  └─ EasyOCR multi-strategy → text extraction [FALLBACK]
│
├─ STEP 3: Validation (confidence >= 0.65)
│  └─ If fail → yêu cầu nhập tay
│
├─ STEP 4: Check occupancy (xe đã trong bãi?)
│
├─ STEP 5: Tự động tìm chỗ trống
│  ├─ Nếu là Ô tô → Zone A (A01-A20)
│  └─ Nếu là Xe máy → Zone B (B01-B40)
│
├─ STEP 6: Update slot state → OCCUPIED
├─ STEP 7: Create Transaction (pending)
├─ STEP 8: Log event + UI notification
│
└─ END: Return success + slot info
```

### 2. CHECK-OUT WORKFLOW (Xe Ra Khỏi Bãi)

```
START: Vehicle arrives at exit
│
├─ STEP 1: Image capture / manual plate
├─ STEP 2: AI Recognition (same pipeline)
├─ STEP 3: Find open Transaction
├─ STEP 4: Fee Calculation
│  ├─ Duration = exit_time - entry_time
│  ├─ Combo active → Fee = 0
│  └─ Non-combo → Hours × Hourly_rate
│
├─ STEP 5: Payment (CASH/MoMo/VNPAY/ZaloPay)
├─ STEP 6: Update Transaction (paid)
├─ STEP 7: Release slot → EMPTY
├─ STEP 8: Generate receipt
└─ END: Return receipt
```

---

## 💾 DATABASE SCHEMA

### 6 Tables (as implemented in database.py)

```
┌──────────────────┐
│    vehicles      │
├──────────────────┤
│ plate (PK)       │
│ vehicle_type     │  -- car / motorbike
│ owner_name       │
│ owner_phone      │
│ combo_status     │  -- active / inactive
│ combo_expire_date│
└──────────────────┘

┌──────────────────────────────┐
│      transactions            │
├──────────────────────────────┤
│ transaction_id (PK)          │
│ plate                        │
│ slot_id                      │
│ zone                         │  -- A / B
│ entry_time                   │
│ exit_time                    │
│ hourly_rate                  │
│ billed_hours                 │
│ gross_fee                    │
│ net_fee                      │
│ payment_method               │  -- cash / momo / vnpay / zalopay
│ payment_status               │  -- pending / paid / failed
└──────────────────────────────┘

┌──────────────────────┐
│     parking_log      │
├──────────────────────┤
│ id (PK, auto)        │
│ event_type           │
│ plate                │
│ slot_id              │
│ confidence           │
│ message              │
│ created_at           │
└──────────────────────┘

┌──────────────────────┐
│   image_history      │
├──────────────────────┤
│ id (PK, auto)        │
│ plate                │
│ image_path           │
│ vehicle_type         │
│ confidence           │
│ valid                │
│ created_at           │
└──────────────────────┘

┌──────────────────────┐
│      users           │
├──────────────────────┤
│ user_id (PK)         │
│ username (UNIQUE)    │
│ password_hash        │
│ role                 │  -- admin / staff / owner
│ full_name            │
│ active               │
└──────────────────────┘

┌──────────────────────┐
│  uploaded_images     │
├──────────────────────┤
│ id (PK, auto)        │
│ filename (UNIQUE)    │
│ image_data (BLOB)    │
│ plate                │
│ is_annotated         │
│ original_filename    │
│ created_at           │
└──────────────────────┘
```

---

## 💰 PRICING (2 Loại Xe)

| Loại xe | Lượt | Tháng (Combo) |
|---------|------|---------------|
| 🏍️ Xe máy | 5,000 VNĐ | 150,000 VNĐ |
| 🚗 Ô tô | 15,000 VNĐ | 900,000 VNĐ |

---

## 🔐 PERMISSION MATRIX (RBAC)

| Permission | Admin | Staff | Owner |
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

## 🎯 EXCEPTION HANDLING

### Scenario 1: OCR Confidence < 65%
- Yêu cầu nhập tay biển số
- Transaction.ManualEntryFlag = TRUE

### Scenario 2: Parking Lot Full
- Zone hết chỗ → "Bãi đỗ đầy"
- Không tạo Transaction

### Scenario 3: Vehicle Still Inside (Double Entry)
- Phát hiện xe đã có open transaction → báo lỗi

### Scenario 4: Payment Gateway Failure
- Retry hoặc chuyển sang tiền mặt
- Barrier vẫn đóng đến khi thanh toán thành công

---

## 📊 PARKING LOT CONFIG

- **Zone A**: 20 chỗ (A01–A20) — Ô tô
- **Zone B**: 40 chỗ (B01–B40) — Xe máy
- **Tổng cộng**: 60 chỗ
