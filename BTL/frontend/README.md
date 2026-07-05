# PCS Smart Parking — Frontend Documentation

## Tổng quan

Hệ thống quản lý bãi đỗ xe thông minh.
- **2 Zone**: Zone A (Ô tô - 20 chỗ), Zone B (Xe máy - 40 chỗ)
- **2 Loại xe**: Ô tô và Xe máy
- **3 Vai trò**: Admin, Nhân viên (Staff), Chủ xe (Owner)
- **4 Phương thức thanh toán**: Tiền mặt, MoMo, VNPAY, ZaloPay

## Cấu trúc thư mục

```
frontend/
├── core/                    # Business logic modules
│   ├── auth.py              # RBAC authentication (admin/staff/owner)
│   ├── database.py          # SQLite/MySQL data layer (6 tables)
│   ├── db_schema.py         # MySQL schema definition
│   ├── ocr_engine.py        # Dual-model AI pipeline (best.pt + character_detector.pt + EasyOCR)
│   ├── parking_lot.py       # Slot management (60 slots, 2 zones)
│   ├── payment.py           # Payment gateway (cash/momo/vnpay/zalopay)
│   ├── pricing.py           # Pricing rules (2 vehicle types)
│   ├── reports.py           # Revenue reports
│   ├── transaction.py       # Transaction ledger
│   ├── vehicle.py           # Vehicle data model (car/motorbike)
│   └── workflow.py          # Check-in/out orchestration
├── templates/               # Jinja2 HTML templates
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html       # Unified dashboard (legacy)
│   ├── admin_dashboard.html
│   ├── staff_dashboard.html
│   └── owner_dashboard.html
├── static/
│   ├── css/
│   │   └── style.css        # Cartoon brutalist stylesheet
│   ├── js/
│   │   └── app.js           # Common JS utilities
│   └── favicon.ico
└── data/
    ├── lot_config.json      # Parking lot config (60 slots)
    ├── pcs.db               # SQLite database
    └── uploads/             # Uploaded images
```

## Cấu hình Parking Lot

File `data/lot_config.json` cấu hình 60 chỗ đỗ:
- **Zone A**: A01–A20 (20 chỗ, dành cho Ô tô)
- **Zone B**: B01–B40 (40 chỗ, dành cho Xe máy)

## AI Pipeline

Hệ thống sử dụng pipeline nhận diện biển số 3 tầng:
1. **best.pt** (YOLO) → Phát hiện phương tiện + vùng biển số
2. **character_detector.pt** (YOLO fine-tuned) → Nhận dạng từng ký tự [ƯU TIÊN]
3. **EasyOCR** → Fallback với 6 chiến lược tiền xử lý

## API Endpoints

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| /api/status | GET | Trạng thái bãi đỗ |
| /api/slots | GET | Danh sách ô đỗ |
| /api/feed | GET | Sự kiện trực tiếp |
| /api/process_frame | POST | Xử lý khung hình camera |
| /api/process_image | POST | Xử lý ảnh upload |
| /api/entry | POST | Nhận xe vào |
| /api/exit | POST | Xe ra + thanh toán |
| /api/auto_entry | POST | Tự động nhận xe |
| /api/suggest_slot | POST | Gợi ý chỗ đỗ |
| /api/report/<period> | GET | Báo cáo doanh thu |
| /api/admin/set_rate | POST | Cập nhật giá |
| /api/admin/slot_action | POST | Vô hiệu/kích hoạt ô |

## Pricing

| Loại xe | Giá lượt | Combo tháng |
|---------|----------|-------------|
| 🏍️ Xe máy | 5,000 VNĐ | 150,000 VNĐ |
| 🚗 Ô tô | 15,000 VNĐ | 900,000 VNĐ |
