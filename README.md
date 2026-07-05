# PCS Smart Parking System

Hệ thống quản lý bãi đỗ xe thông minh sử dụng AI nhận diện biển số (YOLO + Character Detection + EasyOCR).

## Tính năng chính

- **Nhận diện biển số tự động** — `best.pt` phát hiện phương tiện & biển số, `character_detector.pt` nhận dạng từng ký tự, EasyOCR fallback
- **Quản lý bãi đỗ** — 2 zone riêng biệt: Zone A (Ô tô - 20 chỗ), Zone B (Xe máy - 40 chỗ)
- **Tự động gợi ý chỗ đỗ** — Sau khi OCR thành công, hệ thống tự tìm chỗ trống phù hợp
- **Tính phí thông minh** — Hỗ trợ combo/tháng và tính theo lượt
- **Đa vai trò** — Admin / Nhân viên / Chủ xe với phân quyền RBAC
- **Đa phương thức thanh toán** — Tiền mặt, MoMo, VNPAY, ZaloPay
- **Báo cáo doanh thu** — Theo ngày/tuần/tháng, thống kê zone, top ô đỗ
- **Camera AI trực tiếp** — Chụp ảnh từ camera trình duyệt hoặc tải ảnh lên
- **Mô phỏng tự động** — Tự động sinh xe vào/ra để kiểm thử

## Công nghệ

- **Backend**: Python Flask
- **Frontend**: HTML + CSS (Cartoon Brutalist) + Vanilla JS
- **AI**: Ultralytics YOLO (`best.pt`), Character Detector (`character_detector.pt`), EasyOCR
- **Database**: SQLite (dev) / MySQL (production)
- **Biểu đồ**: Chart.js

## Cài đặt & Chạy

```bash
# Clone repo
git clone <repo-url>
cd PCS/BTL

# Tạo virtual environment
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

# Cài dependencies
pip install -r requirements.txt

# Chạy ứng dụng
python backend/app.py

# Mở trình duyệt tại http://localhost:5000
```

## Tài khoản mặc định

| Vai trò | Username | Password |
|---------|----------|----------|
| Admin | admin | admin123 |
| Nhân viên | staff1 | staff123 |
| Chủ xe | owner | owner123 |

## Cấu trúc thư mục

```
PCS/BTL/
├── backend/
│   └── app.py                 # Flask entry point + API routes
├── frontend/
│   ├── core/                   # Business logic modules
│   │   ├── auth.py             # RBAC authentication
│   │   ├── database.py         # SQLite/MySQL data layer
│   │   ├── ocr_engine.py       # AI OCR pipeline (Dual-model)
│   │   ├── parking_lot.py      # Slot management (2 zones)
│   │   ├── payment.py          # Payment gateway integration
│   │   ├── pricing.py          # Pricing rules engine
│   │   ├── reports.py          # Revenue reports
│   │   ├── transaction.py      # Transaction ledger
│   │   ├── vehicle.py          # Vehicle data model (2 types)
│   │   └── workflow.py         # Check-in/out orchestration
│   ├── templates/              # Jinja2 HTML templates
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── dashboard.html      # Unified dashboard (legacy)
│   │   ├── admin_dashboard.html
│   │   ├── staff_dashboard.html
│   │   └── owner_dashboard.html
│   ├── static/
│   │   ├── css/style.css       # Cartoon brutalist stylesheet
│   │   ├── js/app.js           # Common JS utilities
│   │   └── favicon.ico
│   └── data/
│       ├── lot_config.json     # Parking lot layout (60 slots)
│       ├── pcs.db              # SQLite database
│       └── uploads/            # Uploaded images
├── best.pt                     # YOLO model (vehicle + plate detection)
├── character_detector.pt       # Character recognition model
├── requirements.txt
└── .env.example
```

## API Endpoints

### Authentication
- `GET /login` — Trang đăng nhập
- `POST /login` — Đăng nhập
- `GET /register` — Trang đăng ký
- `POST /register` — Đăng ký tài khoản
- `GET /logout` — Đăng xuất

### Dashboard & Status
- `GET /` — Dashboard theo vai trò
- `GET /dashboard` — Dashboard hợp nhất (legacy)
- `GET /api/status` — Trạng thái bãi đỗ
- `GET /api/slots` — Danh sách ô đỗ
- `GET /api/feed` — Sự kiện trực tiếp
- `GET /api/last_transaction` — Giao dịch gần nhất

### OCR & Image Processing
- `POST /api/process_frame` — Xử lý khung hình từ camera
- `POST /api/process_image` — Xử lý ảnh upload
- `GET /api/annotated/<filename>` — Phục vụ ảnh annotation
- `GET /api/image_history/<plate>` — Lịch sử nhận diện
- `GET /api/recent_history` — Lịch sử gần đây
- `POST /api/ocr_demo` — OCR demo (mô phỏng)

### Parking Operations
- `POST /api/suggest_slot` — Gợi ý chỗ đỗ
- `POST /api/auto_entry` — Tự động nhận xe (OCR + gợi ý + vào)
- `POST /api/entry` — Nhận xe vào (manual plate)
- `POST /api/exit` — Xe ra + thanh toán
- `POST /api/simulate_entry` — Mô phỏng xe vào
- `POST /api/simulate_exit` — Mô phỏng xe ra

### Owner
- `GET /api/my_vehicles` — Xe của tôi
- `GET /api/my_transactions` — Giao dịch của tôi
- `POST /api/my_payment` — Thanh toán online

### Reports & Admin
- `GET /api/report/<period>` — Báo cáo (today/week/month)
- `GET /api/top_slots` — Top ô đỗ
- `POST /api/admin/set_rate` — Cập nhật giá đỗ
- `POST /api/admin/slot_action` — Vô hiệu/kích hoạt ô đỗ
- `GET /api/admin/users` — Danh sách tài khoản

## License

PCS Smart Parking System — Bài tập lớn ITS
