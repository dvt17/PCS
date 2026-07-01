# PCS Smart Parking System — SYSTEM DESIGN DOCUMENT

## 📐 ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│              Frontend (Web Dashboard + Mobile App)              │
│   - Admin: Config, Reports, RBAC Management                    │
│   - Operator: Live Monitoring, OCR Override, Maintenance       │
│   - Owner: Combo Management, History, Payment Integration      │
└──────────────┬──────────────────────────────────────────────────┘
               │ RESTful APIs (JSON)
┌──────────────▼──────────────────────────────────────────────────┐
│          Backend (Flask) — API Layer & Business Logic          │
│   - /api/checkin   | /api/checkout  | /api/payment            │
│   - /api/reports   | /api/admin     | /api/config             │
│   - /api/ocr       | /api/slots     | /api/pricing             │
└──────────────┬──────────────────────────────────────────────────┘
               │ Method Calls
┌──────────────▼──────────────────────────────────────────────────┐
│         Business Logic Layer (Python Core Modules)              │
│   ┌──────────────┬──────────────┬──────────────┐               │
│   │ ParkingLot   │ Transactions │ Pricing      │               │
│   │ (Slot Mgmt)  │ (Ledger)     │ (Fee Calc)   │               │
│   └──────────────┴──────────────┴──────────────┘               │
│   ┌──────────────┬──────────────┬──────────────┐               │
│   │ Workflow     │ OCR Engine   │ Payment      │               │
│   │ (Check In/Out) (AI Pipeline) (Gateway)    │               │
│   └──────────────┴──────────────┴──────────────┘               │
└──────────────┬──────────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
   ┌───▼────────┐  ┌───▼──────────────┐
   │ AI Module  │  │ Data Layer       │
   │────────────│  │──────────────────│
   │YOLOv8      │  │MySQL (Primary)   │
   │EasyOCR     │  │SQLite (Fallback) │
   │Vehicle Det │  │ORM/Query Builder │
   │Plate Det   │  │Cache Layer       │
   │OCR Text    │  │──────────────────│
   └────────────┘  └──────────────────┘
```

---

## 🔄 DETAILED WORKFLOWS

### 1. CHECK-IN WORKFLOW (Xe Vào Bãi)

```
START: Vehicle arrives at entrance
│
├─ STEP 1: Image Capture
│  ├─ Camera captures vehicle frame → save to disk
│  ├─ Timestamp: check_in_time = NOW()
│  └─ Image Path: /uploads/checkin_<uuid>_<timestamp>.jpg
│
├─ STEP 2: AI Recognition Pipeline
│  ├─ Module A: Vehicle Detection (YOLOv8)
│  │  └─ Output: bbox_vehicle, vehicle_confidence, vehicle_type_hint
│  ├─ Module B: License Plate Detection (YOLOv8 fine-tuned)
│  │  └─ Output: bbox_plate, plate_confidence
│  ├─ Module C: OCR (EasyOCR)
│  │  └─ Output: raw_text, character_confidence
│  └─ Normalization: normalize_plate(raw_text) → plate
│
├─ STEP 3: Validation
│  ├─ IF confidence < 70%:
│  │  ├─ Flag: manual_input_required = TRUE
│  │  ├─ Event: {"type": "ocr_failed", "severity": "warning"}
│  │  └─ UI: Show to Operator for manual input
│  ├─ Else:
│  │  └─ Continue to STEP 4
│
├─ STEP 4: Database Query
│  ├─ Query: SELECT * FROM Vehicles WHERE LicensePlate = ?
│  ├─ Found?
│  │  ├─ YES: Load existing vehicle_info
│  │  │  ├─ Check ComboStatus (active/expired/inactive)
│  │  │  ├─ Check BlackList
│  │  │  └─ Update LastSeen = NOW()
│  │  └─ NO: Insert new vehicle record
│
├─ STEP 5: Occupancy Check
│  ├─ Query: SELECT * FROM Transactions WHERE CheckOutTime IS NULL 
│  │                                  AND LicensePlate = ?
│  ├─ IF found (vehicle already inside):
│  │  └─ Return ERROR: "Biển số {plate} đã đỗ tại {slot_id}"
│  └─ ELSE: Continue to STEP 6
│
├─ STEP 6: Slot Allocation
│  ├─ Get VehicleType from OCR or Vehicle record
│  ├─ Query available slots for zone matching VehicleType
│  │  ├─ Zone A: Ô tô dưới 7 chỗ
│  │  ├─ Zone B: Xe máy
│  │  └─ Zone C: Ô tô 7-16 chỗ
│  ├─ Algorithm: Find best_slot (prefer closest to exit, then random)
│  ├─ IF no available slots:
│  │  ├─ Event: {"type": "lot_full", "zone": "A"}
│  │  └─ Return ERROR: "Bãi đỗ đầy"
│  └─ ELSE: best_slot = allocated_slot
│
├─ STEP 7: Update Parking Lot State
│  ├─ UPDATE Slots SET Status='occupied', CurrentPlate=? WHERE SlotID=?
│  └─ Cache Update: lot_state['A1'] = {status: 'occupied', plate: '51A-12345'}
│
├─ STEP 8: Create Transaction Record
│  ├─ INSERT INTO Transactions:
│  │  ├─ TransactionID = UUID()
│  │  ├─ LicensePlate = plate
│  │  ├─ VehicleType = detected_vehicle_type
│  │  ├─ SlotID = allocated_slot.id
│  │  ├─ CheckInTime = NOW()
│  │  ├─ CheckOutTime = NULL (still inside)
│  │  ├─ PricingType = 'combo' if ComboActive else 'non_combo'
│  │  ├─ EntryImagePath = image_path
│  │  ├─ EntryOCRConfidence = ocr_confidence
│  │  └─ ManualEntryFlag = FALSE (or TRUE if manual input)
│
├─ STEP 9: Log Event
│  ├─ INSERT INTO Events:
│  │  ├─ EventType = 'checkin'
│  │  ├─ Plate = plate
│  │  ├─ SlotID = allocated_slot.id
│  │  ├─ Message = "Xe 51A-12345 vào ô A5"
│  │  ├─ Severity = 'info'
│  │  └─ Timestamp = NOW()
│
├─ STEP 10: Barrier Control & UI Response
│  ├─ Emit Event: {"vehicle_entered", plate, slot_id, zone}
│  ├─ UI: Show green confirmation "Xe vào thành công"
│  ├─ Display: "Gợi ý: Ô đỗ {slot_id} - Zone {zone} - {distance}m"
│  └─ Barrier: OPEN (for 5 seconds)
│
└─ END: Return {success: TRUE, message, transaction_id}

---

### PSEUDOCODE: Check-In Method

```python
def process_entry(
    image_path: str,
    manual_plate: str = "",
    vehicle_type: VehicleType = None,
    staff_id: str = ""
) -> Tuple[bool, str, Transaction]:
    
    # Step 1-3: OCR & Validation
    if manual_plate:
        plate = manual_plate
        confidence = 0.99  # Manual input = high confidence
        manual_entry_flag = True
    else:
        ocr_result = recognizer.analyze_frame(image_path)
        plate = ocr_result.plate
        confidence = ocr_result.confidence
        manual_entry_flag = False
    
    if confidence < 0.70 and not manual_plate:
        log_event("ocr_failed", plate=plate, confidence=confidence)
        return False, "OCR thất bại — cần nhập tay", None
    
    # Step 4-5: Occupancy Check
    existing_txn = db.get_open_transaction(plate)
    if existing_txn:
        return False, f"Biển số {plate} đã đỗ tại {existing_txn.slot_id}", None
    
    vehicle_info = db.get_vehicle(plate)
    if not vehicle_info:
        db.insert_vehicle(plate, vehicle_type)
    
    # Step 6: Slot Allocation
    available_slots = db.get_available_slots(zone_for(vehicle_type))
    if not available_slots:
        log_event("lot_full", zone=zone_for(vehicle_type).name)
        return False, f"Bãi đỗ đầy", None
    
    allocated_slot = choose_best_slot(available_slots)
    
    # Step 7-8: Update & Create Transaction
    db.update_slot(allocated_slot.id, status='occupied', current_plate=plate)
    
    pricing_type = "combo" if is_combo_active(plate) else "non_combo"
    txn = Transaction(
        transaction_id=uuid4(),
        license_plate=plate,
        vehicle_type=vehicle_type,
        slot_id=allocated_slot.id,
        check_in_time=datetime.now(),
        pricing_type=pricing_type,
        entry_image_path=image_path,
        entry_ocr_confidence=confidence,
        manual_entry_flag=manual_entry_flag
    )
    db.save_transaction(txn)
    
    # Step 9-10: Log & Emit
    log_event("checkin", plate=plate, slot_id=allocated_slot.id, confidence=confidence)
    emit_event("vehicle_entered", {
        "plate": plate,
        "slot_id": allocated_slot.id,
        "zone": allocated_slot.zone,
        "timestamp": datetime.now().isoformat()
    })
    
    return True, f"Xe {plate} vào ô {allocated_slot.id}", txn
```
```

---

### 2. CHECK-OUT WORKFLOW (Xe Ra Khỏi Bãi)

```
START: Vehicle arrives at exit camera
│
├─ STEP 1: Image Capture
│  └─ Same as check-in (capture frame, save, timestamp)
│
├─ STEP 2-3: AI Recognition (same as check-in)
│
├─ STEP 4: Find Open Transaction
│  ├─ Query: SELECT * FROM Transactions 
│  │         WHERE LicensePlate = ? AND CheckOutTime IS NULL
│  ├─ IF found:
│  │  └─ Load transaction (has check_in_time, slot_id, pricing_type, etc.)
│  └─ ELSE:
│  │  └─ Return ERROR: "Không tìm thấy giao dịch mở"
│
├─ STEP 5: Load Pricing Configuration
│  ├─ Get VehicleType from Transaction
│  ├─ Get ComboStatus from Vehicles table
│  └─ Determine PricingType (already set in check-in)
│
├─ STEP 6: Fee Calculation
│  ├─ Duration = check_out_time - check_in_time
│  ├─ IF ComboStatus = 'active' AND ComboExpireDate > TODAY:
│  │  └─ Fee = 0 (免费)
│  ├─ ELSE:
│  │  ├─ Pricing Rule = get_pricing(vehicle_type, 'non_combo')
│  │  ├─ Hours = ceil(Duration / 60) minutes
│  │  └─ Fee = Hours × Pricing Rule.hourly_rate
│  │
│  └─ Example Calculation:
│     Vehicle Type: ô tô dưới 7 chỗ (car_under_7)
│     Check-in: 09:00 → Check-out: 13:30 (4.5 hours)
│     Hours billed: ceil(4.5) = 5 lượt
│     Hourly rate: 30,000 VNĐ/lượt
│     Fee: 5 × 30,000 = 150,000 VNĐ
│
├─ STEP 7: Payment Processing
│  ├─ IF Fee = 0 (Combo):
│  │  └─ Skip payment gateway, mark as 'completed'
│  ├─ ELSE (Non-Combo):
│  │  ├─ Call Payment Gateway (CASH, MoMo, VNPAY, ZaloPay)
│  │  ├─ Wait for Payment Response:
│  │  │  ├─ Success: Payment Confirmed
│  │  │  └─ Failed: Retry or Manual Override
│  │
│  └─ IF Payment Failed:
│     ├─ Event: {"type": "payment_failed", "severity": "error"}
│     ├─ Barrier: STAY CLOSED
│     ├─ UI: Alert to Operator
│     └─ Return ERROR with retry option
│
├─ STEP 8: Update Transaction Record
│  ├─ UPDATE Transactions SET
│  │  ├─ CheckOutTime = NOW()
│  │  ├─ DurationMinutes = DIFF(check_in, check_out)
│  │  ├─ Fee = calculated_fee
│  │  ├─ PaymentStatus = 'completed'
│  │  ├─ PaymentMethod = payment_gateway_used
│  │  ├─ ExitImagePath = image_path
│  │  ├─ ExitOCRConfidence = confidence
│  │  └─ ManualExitFlag = FALSE (or TRUE if manual)
│
├─ STEP 9: Update Slot Status
│  ├─ UPDATE Slots SET
│  │  ├─ Status = 'empty'
│  │  ├─ CurrentPlate = NULL
│  │  └─ LastUpdated = NOW()
│
├─ STEP 10: Generate Receipt
│  ├─ Receipt Format:
│  │  ┌─────────────────────────────┐
│  │  │    PCS SMART PARKING        │
│  │  │                             │
│  │  │ Biển số: 51A-12345          │
│  │  │ Ô đỗ: A5                    │
│  │  │ Giờ vào: 09:00 (01/01/2024) │
│  │  │ Giờ ra: 13:30 (01/01/2024)  │
│  │  │ Thời gian: 4h 30min (5 lượt) │
│  │  │ Giá: 30,000 VNĐ/lượt        │
│  │  │ Phí: 150,000 VNĐ             │
│  │  │ Thanh toán: Tiền mặt        │
│  │  │ Cảm ơn bạn!                 │
│  │  └─────────────────────────────┘
│
├─ STEP 11: Log Event & Barrier Control
│  ├─ INSERT INTO Events:
│  │  ├─ EventType = 'checkout'
│  │  ├─ Message = "Xe 51A-12345 ra khỏi ô A5 - Phí: 150,000 VNĐ"
│  │  └─ Severity = 'info'
│  ├─ Emit Event: {"vehicle_exited", plate, slot_id, fee, method}
│  ├─ UI: Display Receipt
│  └─ Barrier: OPEN (for 5 seconds)
│
└─ END: Return {success: TRUE, message, transaction_with_fee}
```

---

## 💾 DATABASE SCHEMA IMPLEMENTATION

### ER Diagram

```
┌──────────────────┐
│    Vehicles      │
├──────────────────┤
│ LicensePlate (PK)│ ◄────────┐
│ VehicleType      │          │
│ OwnerName        │          │
│ ComboStatus      │          │  FK
│ ComboExpireDate  │          │
│ FirstRegistered  │          │
│ LastSeen         │          │
└──────────────────┘          │
                              │
┌──────────────────┐          │
│     Slots        │          │
├──────────────────┤          │
│ SlotID (PK)      │          │
│ Zone             │          │
│ Status           │          │
│ CurrentPlate  ───┼──────────┘
│ LastUpdated      │
└──────────────────┘
        ▲
        │
        │ FK
        │
┌──────────────────────────────┐
│      Transactions            │
├──────────────────────────────┤
│ TransactionID (PK, UUID)     │
│ LicensePlate (FK→Vehicles)   │
│ VehicleType                  │
│ SlotID (FK→Slots)            │
│ PricingID (FK→Pricing)       │
│ CheckInTime                  │
│ CheckOutTime                 │
│ DurationMinutes              │
│ Fee                          │
│ PaymentStatus                │
│ PaymentMethod                │
│ EntryImagePath               │
│ ExitImagePath                │
│ ManualEntryFlag              │
│ ManualExitFlag               │
└──────────────────────────────┘
        ▲
        │ FK
        │
┌──────────────────────────────┐
│      Pricing                 │
├──────────────────────────────┤
│ PricingID (PK)               │
│ VehicleType                  │
│ PricingType (combo/non_combo)│
│ HourlyRate                   │
│ MonthlyRate                  │
│ EffectiveDate                │
│ Active                       │
└──────────────────────────────┘

┌──────────────────────────────┐
│      OCRHistory              │
├──────────────────────────────┤
│ HistoryID (PK)               │
│ ImagePath                    │
│ Timestamp                    │
│ DetectedPlate                │
│ Confidence                   │
│ IsValid                      │
│ Status                       │
└──────────────────────────────┘

┌──────────────────────────────┐
│      Users                   │
├──────────────────────────────┤
│ UserID (PK, UUID)            │
│ Username (UNIQUE)            │
│ PasswordHash                 │
│ Role (admin/operator/owner)  │
│ Active                       │
│ CreatedAt                    │
└──────────────────────────────┘

┌──────────────────────────────┐
│      Events                  │
├──────────────────────────────┤
│ EventID (PK)                 │
│ EventType                    │
│ Plate                        │
│ SlotID                       │
│ EventTime                    │
│ Message                      │
│ Severity                     │
│ TransactionID (FK)           │
│ UserID (FK)                  │
└──────────────────────────────┘
```

---

### SQL Queries for Key Operations

```sql
-- 1. Find available slots in zone A
SELECT * FROM Slots 
WHERE Zone = 'A' AND Status = 'empty' 
ORDER BY LastUpdated ASC 
LIMIT 10;

-- 2. Get open transaction for a plate
SELECT * FROM Transactions 
WHERE LicensePlate = ? AND CheckOutTime IS NULL 
LIMIT 1;

-- 3. Calculate occupancy for today
SELECT 
    Zone,
    COUNT(*) as total_slots,
    SUM(CASE WHEN Status = 'occupied' THEN 1 ELSE 0 END) as occupied,
    ROUND(100.0 * SUM(CASE WHEN Status = 'occupied' THEN 1 ELSE 0 END) / COUNT(*), 1) as occupancy_pct
FROM Slots
GROUP BY Zone;

-- 4. Daily revenue report
SELECT 
    DATE(CheckOutTime) as report_date,
    COUNT(*) as total_transactions,
    SUM(CASE WHEN PaymentStatus = 'completed' THEN Fee ELSE 0 END) as total_revenue,
    COUNT(DISTINCT LicensePlate) as unique_vehicles,
    AVG(CASE WHEN PaymentStatus = 'completed' THEN Fee ELSE 0 END) as avg_fee
FROM Transactions
WHERE CheckOutTime >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY DATE(CheckOutTime)
ORDER BY report_date DESC;

-- 5. Top slots by usage (peak traffic analysis)
SELECT 
    SlotID,
    Zone,
    COUNT(*) as usage_count,
    AVG(DurationMinutes) as avg_duration
FROM Transactions
WHERE CheckOutTime >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY SlotID
ORDER BY usage_count DESC
LIMIT 10;

-- 6. Vehicles with active combo
SELECT 
    LicensePlate,
    VehicleType,
    ComboExpireDate,
    DATEDIFF(ComboExpireDate, CURDATE()) as days_remaining
FROM Vehicles
WHERE ComboStatus = 'active' AND ComboExpireDate > CURDATE()
ORDER BY ComboExpireDate ASC;
```

---

## 🎯 EXCEPTION HANDLING SCENARIOS

### Scenario 1: OCR Confidence < 70%

```
Event Flow:
1. OCR returns confidence = 0.45
2. System: Flags as manual_input_required
3. UI: Displays "⚠ Không nhận diện được. Nhân viên: Nhập biển số tay"
4. Operator: Types "51A-12345" manually
5. System: Treats as manual_entry_flag=TRUE (override)
6. Continues check-in workflow with manual_plate parameter

Database Impact:
- OCRHistory.Status = 'manual_input_required'
- Transactions.ManualEntryFlag = TRUE
- Events.Severity = 'warning'
```

### Scenario 2: Parking Lot Full

```
Event Flow:
1. All slots in Zone A occupied
2. Vehicle arrives (car_under_7)
3. System: No available slots found
4. UI: "❌ Bãi đỗ đầy. Vui lòng quay lại sau"
5. Operator: May enable "reserved" slot or turn vehicle away

Database Impact:
- Events.EventType = 'lot_full'
- Events.Severity = 'critical'
- No Transaction created
- Lot.occupancy_rate = 100%
```

### Scenario 3: Vehicle Still Inside (Double Entry)

```
Event Flow:
1. Same plate captured at entry camera again
2. System: Finds open transaction for this plate
3. Returns ERROR: "Biển số 51A-12345 đã đỗ tại A5"
4. Operator: Investigates (vehicle might not have exited properly)

Resolution:
- Operator manually marks transaction as completed
- Updates slot status to 'empty'
- Allows new check-in for same plate
```

### Scenario 4: Payment Gateway Failure

```
Event Flow:
1. Check-out initiated, fee = 150,000 VNĐ
2. Payment Gateway (VNPAY) times out
3. System: PaymentStatus = 'pending'
4. UI: "⚠ Thanh toán thất bại. Thử lại?"
5. Operator: Retry payment or process manually

Options:
a) Retry payment (automatic retry after 30 seconds)
b) Accept cash instead of VNPAY
c) Mark as paid_manually (requires operator authorization)
d) Hold vehicle (barrier stays closed) until payment confirmed
```

---

## 🔐 PERMISSION MATRIX (RBAC)

| Permission | Admin | Operator | Owner |
|---|---|---|---|
| checkin | ✅ | ✅ | ❌ |
| checkout | ✅ | ✅ | ❌ |
| manual:ocr | ✅ | ✅ | ❌ |
| manage:slots | ✅ | ❌ | ❌ |
| config:pricing | ✅ | ❌ | ❌ |
| config:lot | ✅ | ❌ | ❌ |
| view:dashboard | ✅ | ✅ | ❌ |
| view:reports | ✅ | ✅ | ❌ |
| manage:users | ✅ | ❌ | ❌ |
| view:my_combo | ✅ | ❌ | ✅ |
| renew:combo | ✅ | ❌ | ✅ |
| view:history | ✅ | ✅ | ✅ |

---

## 📊 MONITORING & LOGGING

### Log Levels

```
INFO: Normal checkin/checkout
- "[INFO] [2024-01-01 09:00:15] Xe 51A-12345 vào ô A5 (Zone A)"

WARNING: OCR issues, manual input
- "[WARN] [2024-01-01 09:05:00] OCR confidence=0.45 - manual input required for plate 51A-?????

ERROR: Payment failure, slot full
- "[ERROR] [2024-01-01 13:30:45] Payment failed for TXN#uuid-123 - VNPAY timeout"

CRITICAL: System alerts
- "[CRIT] [2024-01-01 14:00:00] Lot full (Zone A occupancy = 100%)"
```

---

## 🚀 DEPLOYMENT CHECKLIST

- [ ] MySQL database initialized with schema
- [ ] Environment variables configured (.env or secrets)
- [ ] YOLO models downloaded and verified
- [ ] EasyOCR cached (first run is slow)
- [ ] Payment gateway credentials set up
- [ ] RBAC roles and users seeded
- [ ] Default pricing loaded into database
- [ ] Parking lot configuration (zones, slots) finalized
- [ ] SSL/TLS certificates configured
- [ ] Rate limiting enabled on APIs
- [ ] Logging and monitoring set up (ELK, Splunk, etc.)
- [ ] Load testing and stress testing completed
- [ ] Backup strategy defined (daily MySQL dumps)
- [ ] Disaster recovery plan in place

---

## 📝 NEXT STEPS

1. **Database Migration**: Generate Alembic migrations for schema versioning
2. **API Optimization**: Add caching layer (Redis) for frequent queries
3. **Mobile App**: Develop iOS/Android app for vehicle owners
4. **Analytics Dashboard**: Real-time occupancy heatmaps, revenue trends
5. **Predictive Maintenance**: Alert for YOLO model drift, OCR accuracy degradation
6. **Multi-Location Support**: Extend system to manage multiple parking lots
7. **Integration**: Connect with city traffic management systems
8. **Internationalization**: Support for multiple languages and currencies

