from __future__ import annotations

import base64
import os
import sys
import uuid
from datetime import datetime, date
from typing import Any, Dict, List

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT, "frontend")
if FRONTEND_DIR not in sys.path:
    sys.path.insert(0, FRONTEND_DIR)

from core.auth import AuthManager, Role, User
from core.database import (
    get_image_from_db,
    get_image_history,
    get_open_transaction,
    get_recent_image_history,
    get_vehicle,
    image_exists_in_db,
    init_db,
    log_event,
    query_transactions,
    recent_log,
    revenue_summary,
    save_image_history,
    save_image_to_db,
    save_transaction,
    seed_initial_data,
    upsert_vehicle,
)
from core.ocr_engine import PlateRecognizer
from core.parking_lot import ParkingLot, Zone, VEHICLE_ZONE_MAP
from core.payment import GatewayType, PaymentGateway
from core.reports import ReportEngine
from core.transaction import PaymentMethod, TransactionLedger
from core.vehicle import Vehicle, VehicleType
from core.workflow import ParkingWorkflow

try:
    import numpy as np
except Exception:
    np = None

try:
    import cv2
except Exception:
    cv2 = None

app = Flask(__name__, template_folder=os.path.join(FRONTEND_DIR, "templates"), static_folder=os.path.join(FRONTEND_DIR, "static"))
app.secret_key = "pcs-smart-parking-demo"
app.config["EVENT_FEED"] = []
app.config["LAST_PLATE"] = ""
app.config["UPLOAD_FOLDER"] = os.path.join(FRONTEND_DIR, "data", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

init_db()
seed_initial_data()

lot = ParkingLot(config_path=os.path.join(FRONTEND_DIR, "data", "lot_config.json"))
ledger = TransactionLedger()
recognizer = PlateRecognizer()
gateway = PaymentGateway()
report_engine = ReportEngine()


def emit_event(event: str, payload: Dict[str, Any]) -> None:
    feed = app.config.setdefault("EVENT_FEED", [])
    feed.append({"event": event, "payload": payload, "time": datetime.now().strftime("%H:%M:%S")})
    if len(feed) > 30:
        feed.pop(0)
    plate = payload.get("plate", "")
    if plate:
        log_event(event, plate=plate, image_path=str(payload.get("image_path", "")), message=str(payload.get("message", "")))


workflow = ParkingWorkflow(lot, ledger, recognizer=recognizer, gateway=gateway, on_event=emit_event)


def _convert_numpy_types(obj: Any) -> Any:
    """Convert numpy types to native Python types for JSON serialization."""
    if np is not None:
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    if isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_numpy_types(v) for v in obj]
    return obj


def current_user() -> Dict[str, Any] | None:
    return session.get("user")


def require_login():
    if not current_user():
        return redirect(url_for("login"))
    return None


def require_permission(action: str):
    user = current_user()
    if not user:
        return jsonify({"error": "unauthorized", "message": "Chưa đăng nhập"}), 401
    try:
        role = Role(user.get("role"))
    except Exception:
        return jsonify({"error": "forbidden", "message": "Quyền không hợp lệ"}), 403
    if not User(user_id=user.get("user_id", ""), username=user.get("username", ""), role=role, full_name=user.get("full_name", "")).can(action):
        return jsonify({"error": "forbidden", "message": "Không có quyền truy cập"}), 403
    return None


# ─── ROLE-SPECIFIC TEMPLATE MAP ─────────────────────────────────────
ROLE_TEMPLATE = {
    Role.ADMIN: "admin_dashboard.html",
    Role.STAFF: "staff_dashboard.html",
    Role.OWNER: "owner_dashboard.html",
}


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = AuthManager.login(username, password)
        if user:
            session["user"] = {
                "user_id": user.user_id,
                "username": user.username,
                "role": user.role.value,
                "full_name": user.full_name,
            }
            return redirect(url_for("index"))
        error = "Tên đăng nhập hoặc mật khẩu không đúng"
    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = ""
    success = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        full_name = request.form.get("full_name", "").strip()
        role_str = request.form.get("role", "owner").strip()

        if not username or not password:
            error = "Vui lòng nhập đầy đủ thông tin"
        elif len(password) < 4:
            error = "Mật khẩu phải có ít nhất 4 ký tự"
        elif role_str not in ("staff", "owner"):
            error = "Vai trò không hợp lệ"
        else:
            from core.database import user_exists
            if user_exists(username):
                error = f"Tên đăng nhập '{username}' đã tồn tại"
            else:
                role = Role.STAFF if role_str == "staff" else Role.OWNER
                AuthManager.register(username, password, role, full_name)
                success = "Đăng ký thành công! Vui lòng đăng nhập."

    return render_template("register.html", error=error, success=success)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET"])
def index():
    guard = require_login()
    if guard is not None:
        return guard
    u = current_user()
    role = Role(u["role"])
    template = ROLE_TEMPLATE.get(role, "admin_dashboard.html")
    return render_template(template, username=u["username"], full_name=u.get("full_name", ""), role=role.value)


@app.route("/dashboard", methods=["GET"])
def dashboard_view():
    """Legacy unified dashboard — accessible by all roles for testing."""
    guard = require_login()
    if guard is not None:
        return guard
    u = current_user()
    return render_template("dashboard.html", username=u["username"], full_name=u.get("full_name", ""), role=Role(u["role"]).value)


# ─── API: STATUS (all roles) ─────────────────────────────────────────
@app.route("/api/status")
def api_status():
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401
    summary = revenue_summary("today")
    return jsonify({
        "total": lot.total_slots,
        "occupied": lot.occupied_count,
        "available": lot.total_slots - lot.occupied_count,
        "occupancy_pct": round(lot.occupancy_rate, 1),
        "revenue_today": int(summary.get("total_revenue", 0) or 0),
        "txn_count": int(summary.get("txn_count", 0) or 0),
        "zones": lot.zone_summary(),
    })


@app.route("/api/slots")
def api_slots():
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401
    slots = []
    for slot in sorted(lot.slots.values(), key=lambda s: s.slot_id):
        slots.append({
            "id": slot.slot_id,
            "zone": slot.zone.value,
            "state": slot.state.value,
            "plate": slot.current_plate,
        })
    return jsonify(slots)


@app.route("/api/feed")
def api_feed():
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(list(reversed(app.config.get("EVENT_FEED", []))))


@app.route("/api/last_transaction")
def api_last_transaction():
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401
    if ledger._records:
        txn = ledger._records[-1]
        return jsonify({
            "plate": txn.plate,
            "slot_id": txn.slot_id,
            "entry": txn.entry_time.strftime("%H:%M %d/%m"),
            "exit": txn.exit_time.strftime("%H:%M %d/%m") if txn.exit_time else "—",
            "hours": txn.billed_hours,
            "method": txn.payment_method.value,
            "fee": txn.net_fee,
        })
    return jsonify({})


# ─── API: OCR ────────────────────────────────────────────────────────
@app.route("/api/ocr_demo", methods=["POST"])
def api_ocr_demo():
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401
    result = recognizer._demo_result()
    return jsonify({"plate": result.plate, "confidence": result.confidence, "valid": result.is_valid})


@app.route("/api/process_frame", methods=["POST"])
def api_process_frame():
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    image_data = payload.get("image") or payload.get("frame")
    if not image_data:
        return jsonify({"success": False, "message": "Thiếu dữ liệu khung hình"}), 400

    if "," in image_data:
        _, encoded = image_data.split(",", 1)
    else:
        encoded = image_data

    try:
        image_bytes = base64.b64decode(encoded)
    except Exception:
        return jsonify({"success": False, "message": "Dữ liệu ảnh không hợp lệ"}), 400

    ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    tmp_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    if cv2 is not None and np is not None:
        array = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if frame is not None:
            cv2.imwrite(tmp_path, frame)
            result = recognizer.analyze_frame(frame, image_path=tmp_path)
        else:
            result = {"plate": "", "confidence": 0.0, "valid": False, "vehicle_type": "unknown", "message": "Không đọc được khung hình", "image_path": tmp_path, "bbox": None}
    else:
        with open(tmp_path, "wb") as fh:
            fh.write(image_bytes)
        result = {"plate": "", "confidence": 0.0, "valid": False, "vehicle_type": "unknown", "message": "Camera đang chạy ở chế độ demo", "image_path": tmp_path, "bbox": None}

    # Lưu ảnh gốc vào DB
    save_image_to_db(filename, image_bytes, plate=result.get("plate", ""), is_annotated=0, original_filename="camera_frame.jpg")

    # Lưu ảnh annotated vào DB nếu có
    ann_path = result.get("annotated_path", "")
    if ann_path and os.path.exists(ann_path):
        with open(ann_path, "rb") as f:
            ann_bytes = f.read()
        ann_filename = os.path.basename(ann_path)
        save_image_to_db(ann_filename, ann_bytes, plate=result.get("plate", ""), is_annotated=1, original_filename=filename)
        os.remove(ann_path)

    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    plate = result.get("plate", "") or ""
    save_image_history(plate, filename, result.get("vehicle_type", ""), result.get("confidence", 0.0), 1 if result.get("valid") else 0)
    result["plate"] = plate
    result["success"] = True
    result["message"] = result.get("message", "Đã xử lý khung hình") + f" | Ảnh lưu tại {filename}"

    # Trả về ảnh đã xử lý (annotated) nếu có, nếu không trả về ảnh gốc
    ann_found = False
    from core.database import _connect, _execute
    con = _connect()
    backend_type = "sqlite"
    try:
        backend_type = __import__('os').environ.get('PCS_DB_BACKEND', 'sqlite').strip().lower()
    except Exception:
        pass
    placeholder = "%s" if backend_type == "mysql" else "?"
    
    # Tìm ảnh đã xử lý (annotated)
    cursor = _execute(con, f"SELECT image_data FROM uploaded_images WHERE is_annotated=1 AND original_filename={placeholder} ORDER BY filename DESC LIMIT 1", (filename,))
    ann_row = cursor.fetchone()
    if ann_row and ann_row[0]:
        ann_data = ann_row[0] if isinstance(ann_row[0], bytes) else bytes(ann_row[0])
        result["annotated_b64"] = base64.b64encode(ann_data).decode("utf-8")
        ann_found = True
    
    # Nếu không có ảnh annotated, trả về ảnh gốc
    if not ann_found:
        cursor = _execute(con, f"SELECT image_data FROM uploaded_images WHERE is_annotated=0 AND filename={placeholder}", (filename,))
        orig_row = cursor.fetchone()
        if orig_row and orig_row[0]:
            orig_data = orig_row[0] if isinstance(orig_row[0], bytes) else bytes(orig_row[0])
            result["image_b64"] = base64.b64encode(orig_data).decode("utf-8")
    
    con.close()
    return jsonify(_convert_numpy_types(result))


@app.route("/api/annotated/<filename>")
def api_annotated_image(filename: str):
    """Phục vụ ảnh đã vẽ annotation (bbox + label) — lấy từ DB"""
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401
    from flask import send_file
    import io
    data = get_image_from_db(filename)
    if data:
        mimetype = 'image/png' if filename.lower().endswith('.png') else 'image/jpeg'
        return send_file(io.BytesIO(data), mimetype=mimetype)
    image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(image_path):
        return send_file(image_path, mimetype='image/jpeg')
    return jsonify({"error": "not_found"}), 404


@app.route("/api/process_image", methods=["POST"])
def api_process_image():
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401

    if "image" not in request.files or not request.files["image"].filename:
        return jsonify({"success": False, "message": "Vui lòng chọn ảnh"}), 400

    image_file = request.files["image"]
    ext = os.path.splitext(image_file.filename)[1] or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    tmp_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    image_file.save(tmp_path)

    with open(tmp_path, "rb") as f:
        orig_bytes = f.read()

    save_image_to_db(filename, orig_bytes, plate="", is_annotated=0, original_filename=image_file.filename)

    result = recognizer.analyze_image_file(tmp_path)

    # Lưu ảnh annotated vào DB nếu có
    ann_path = result.get("annotated_path", "")
    if ann_path and os.path.exists(ann_path):
        with open(ann_path, "rb") as f:
            ann_bytes = f.read()
        ann_filename = os.path.basename(ann_path)
        save_image_to_db(ann_filename, ann_bytes, plate=result.get("plate", ""), is_annotated=1, original_filename=filename)
        os.remove(ann_path)

    plate = result.get("plate", "") or ""
    save_image_history(plate, filename, result.get("vehicle_type", ""), result.get("confidence", 0.0), 1 if result.get("valid") else 0)
    result["plate"] = plate
    result["success"] = True

    # Cập nhật plate cho ảnh gốc đã lưu
    if plate:
        from core.database import _connect, _execute
        con = _connect()
        backend_type = "sqlite"
        try:
            backend_type = __import__('os').environ.get('PCS_DB_BACKEND', 'sqlite').strip().lower()
        except Exception:
            pass
        if backend_type == "mysql":
            _execute(con, "UPDATE uploaded_images SET plate=%s WHERE filename=%s", (plate, filename))
        else:
            _execute(con, "UPDATE uploaded_images SET plate=? WHERE filename=?", (plate, filename))
        con.close()

    # Trả về ảnh đã xử lý (annotated) nếu có, nếu không thì trả về ảnh gốc
    from core.database import _connect, _execute
    con = _connect()
    backend_type = "sqlite"
    try:
        backend_type = __import__('os').environ.get('PCS_DB_BACKEND', 'sqlite').strip().lower()
    except Exception:
        pass
    placeholder = "%s" if backend_type == "mysql" else "?"
    cursor = _execute(con, f"SELECT filename, image_data FROM uploaded_images WHERE is_annotated=1 AND original_filename={placeholder} ORDER BY filename DESC LIMIT 1", (filename,))
    ann_row = cursor.fetchone()
    
    if ann_row:
        ann_filename, ann_data = ann_row
        if ann_data:
            result["annotated_b64"] = base64.b64encode(ann_data).decode("utf-8")
            result["annotated_filename"] = ann_filename
        con.close()
    else:
        # Fallback: trả về ảnh gốc đã upload
        cursor = _execute(con, f"SELECT image_data FROM uploaded_images WHERE is_annotated=0 AND filename={placeholder}", (filename,))
        orig_row = cursor.fetchone()
        con.close()
        if orig_row and orig_row[0]:
            orig_data = orig_row[0] if isinstance(orig_row[0], bytes) else bytes(orig_row[0])
            result["image_b64"] = base64.b64encode(orig_data).decode("utf-8")

    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    return jsonify(_convert_numpy_types(result))


@app.route("/api/image_history/<plate>")
def api_image_history(plate: str):
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_image_history(plate.upper()))


@app.route("/api/recent_history")
def api_recent_history():
    guard = require_login()
    if guard is not None:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_recent_image_history())


# ─── API: SUGGEST SLOT (auto assignment) ────────────────────────────
@app.route("/api/suggest_slot", methods=["POST"])
def api_suggest_slot():
    """
    Nhận plate + vehicle_type → kiểm tra xe chưa vào → tìm chỗ trống
    → trả về thông tin slot được gợi ý + thông báo.
    Dùng cho chức năng auto-slot-sau-OCR.
    """
    guard = require_permission("checkin")
    if guard is not None:
        return guard
    payload = request.get_json(silent=True) or {}
    plate = (payload.get("plate") or "").strip().upper()
    vehicle_type = payload.get("vehicle_type") or "car"
    
    if not plate:
        return jsonify({"success": False, "message": "Thiếu biển số xe"}), 400

    # Only 2 types: car or motorbike
    if vehicle_type == "motorbike":
        vehicle_type_enum = VehicleType.MOTORBIKE
    else:
        vehicle_type_enum = VehicleType.CAR

    # Check if already parked
    existing_slot = lot.find_by_plate(plate)
    if existing_slot:
        return jsonify({
            "success": False,
            "plate": plate,
            "vehicle_type": vehicle_type_enum.value,
            "has_slot": True,
            "suggested_slot": {
                "slot_id": existing_slot.slot_id,
                "zone": existing_slot.zone.value,
                "zone_label": "Zone A" if existing_slot.zone.value == "A" else "Zone B",
            },
            "message": f"⚠️ Xe {plate} đã đỗ tại {existing_slot.slot_id}"
        })

    # Find available slot
    slot_info = lot.suggest_slot_with_info(vehicle_type_enum)
    if not slot_info:
        zone = vehicle_type_enum.display_name
        return jsonify({
            "success": False,
            "plate": plate,
            "vehicle_type": vehicle_type_enum.value,
            "has_slot": False,
            "suggested_slot": None,
            "message": f"❌ Bãi đỗ đầy ({zone})"
        })

    return jsonify({
        "success": True,
        "plate": plate,
        "vehicle_type": vehicle_type_enum.value,
        "vehicle_label": vehicle_type_enum.display_name,
        "has_slot": True,
        "suggested_slot": slot_info,
        "message": f"✅ {vehicle_type_enum.display_name} {plate} → {slot_info['zone_label']} · {slot_info['slot_id']}"
    })


@app.route("/api/auto_entry", methods=["POST"])
def api_auto_entry():
    """
    Tự động: Detect → Tìm chỗ → Nhận xe vào → Thông báo
    Chỉ cần plate + vehicle_type. Tự động chọn slot trống.
    """
    guard = require_permission("checkin")
    if guard is not None:
        return guard
    payload = request.get_json(silent=True) or {}
    plate = (payload.get("plate") or "").strip().upper()
    vehicle_type = payload.get("vehicle_type") or "car"
    
    if not plate:
        return jsonify({"success": False, "message": "Thiếu biển số xe"}), 400

    if vehicle_type == "motorbike":
        vehicle_type_enum = VehicleType.MOTORBIKE
    else:
        vehicle_type_enum = VehicleType.CAR

    ok, message, txn = workflow.process_entry(image_path="", manual_plate=plate, vehicle_type=vehicle_type_enum)
    if ok and txn:
        app.config["LAST_PLATE"] = txn.plate
    return jsonify({"success": ok, "message": message, "tx": txn.to_dict() if txn else None})


# ─── API: ENTRY / EXIT ───────────────────────────────────────────────
@app.route("/api/simulate_entry", methods=["POST"])
def api_simulate_entry():
    guard = require_permission("checkin")
    if guard is not None:
        return guard
    ok, message, txn = workflow.process_entry(image_path="")
    if ok and txn:
        app.config["LAST_PLATE"] = txn.plate
    return jsonify({"success": ok, "message": message})


@app.route("/api/simulate_exit", methods=["POST"])
def api_simulate_exit():
    guard = require_permission("checkout")
    if guard is not None:
        return guard
    plate = app.config.get("LAST_PLATE") or "51A-12345"
    ok, message, txn = workflow.process_exit(image_path="", manual_plate=plate, payment_method=GatewayType.CASH)
    return jsonify({"success": ok, "message": message, "receipt": txn.receipt_text() if txn else None})


@app.route("/api/entry", methods=["POST"])
def api_entry():
    guard = require_permission("checkin")
    if guard is not None:
        return guard
    payload = request.get_json(silent=True) or {}
    plate = (payload.get("plate") or "").strip().upper()
    vehicle_type = payload.get("vehicle_type") or "car"
    # Only 2 types: car or motorbike
    if vehicle_type == "motorbike":
        vehicle_type_enum = VehicleType.MOTORBIKE
    else:
        vehicle_type_enum = VehicleType.CAR
    ok, message, txn = workflow.process_entry(image_path="", manual_plate=plate, vehicle_type=vehicle_type_enum)
    if ok and txn:
        app.config["LAST_PLATE"] = txn.plate
    return jsonify({"success": ok, "message": message, "tx": txn.to_dict() if txn else None})


@app.route("/api/exit", methods=["POST"])
def api_exit():
    guard = require_permission("checkout")
    if guard is not None:
        return guard
    payload = request.get_json(silent=True) or {}
    plate = (payload.get("plate") or "").strip().upper()
    method = payload.get("method") or "cash"
    gateway_type = GatewayType(method) if method in {m.value for m in GatewayType} else GatewayType.CASH
    ok, message, txn = workflow.process_exit(image_path="", manual_plate=plate, payment_method=gateway_type)
    receipt = txn.receipt_text() if txn else None

    return jsonify({"success": ok, "message": message, "receipt": receipt})


# ─── API: OWNER ──────────────────────────────────────────────────────
@app.route("/api/my_vehicles")
def api_my_vehicles():
    guard = require_permission("view_own_history")
    if guard is not None:
        return guard
    u = current_user()
    sample_plates = {"staff1": "51A-12345", "owner": "51L-77777"}
    plate = sample_plates.get(u["username"], "51A-12345")
    vehicle = get_vehicle(plate)
    return jsonify(vehicle or {"plate": plate, "vehicle_type": "car", "owner_name": u.get("full_name", "")})


@app.route("/api/my_transactions")
def api_my_transactions():
    guard = require_permission("view_own_history")
    if guard is not None:
        return guard
    u = current_user()
    sample_plates = {"staff1": "51A-12345", "owner": "51L-77777"}
    plate = sample_plates.get(u["username"], "51A-12345")
    txns = query_transactions()
    my_txns = [t for t in txns if t.get("plate") == plate][:20]
    return jsonify(my_txns)


@app.route("/api/my_payment", methods=["POST"])
def api_my_payment():
    guard = require_permission("view_own_history")
    if guard is not None:
        return guard
    payload = request.get_json(silent=True) or {}
    plate = (payload.get("plate") or "").strip().upper()
    method = payload.get("method") or "momo"
    gateway_type = GatewayType(method) if method in {m.value for m in GatewayType} else GatewayType.MOMO
    ok, message, txn = workflow.process_exit(image_path="", manual_plate=plate, payment_method=gateway_type)
    return jsonify({"success": ok, "message": message, "receipt": txn.receipt_text() if txn else None})


# ─── API: REPORTS ────────────────────────────────────────────────────
@app.route("/api/report/<period>")
def api_report(period: str):
    guard = require_permission("view_reports")
    if guard is not None:
        return guard
    if period == "today":
        report = report_engine.daily_report()
    elif period == "week":
        report = report_engine.weekly_report()
    else:
        report = report_engine.monthly_report()
    report["occupancy_trend"] = report_engine.occupancy_over_time(lot.total_slots, 7)
    return jsonify(report)


@app.route("/api/top_slots")
def api_top_slots():
    guard = require_permission("view_reports")
    if guard is not None:
        return guard
    return jsonify(report_engine.top_slots(5))


# ─── API: ADMIN ──────────────────────────────────────────────────────
@app.route("/api/admin/set_rate", methods=["POST"])
def api_admin_set_rate():
    guard = require_permission("config_lot")
    if guard is not None:
        return guard
    payload = request.get_json(silent=True) or {}
    zone = payload.get("zone", "A")
    rate = int(payload.get("rate", 0))
    if zone == "A":
        lot.set_rate(Zone.A, rate)
    elif zone == "B":
        lot.set_rate(Zone.B, rate)
    return jsonify({"success": True, "message": "Đã cập nhật giá"})


@app.route("/api/admin/slot_action", methods=["POST"])
def api_admin_slot_action():
    guard = require_permission("manage_slots")
    if guard is not None:
        return guard
    payload = request.get_json(silent=True) or {}
    action = payload.get("action")
    slot_id = payload.get("slot_id")
    if action == "disable":
        lot.disable_slot(slot_id)
    elif action == "enable":
        lot.enable_slot(slot_id)
    return jsonify({"success": True, "message": "Đã cập nhật ô đỗ"})


@app.route("/api/admin/users")
def api_admin_users():
    guard = require_permission("manage_users")
    if guard is not None:
        return guard
    from core.database import _connect, _fetch_all
    con = _connect()
    backend = "sqlite"
    cursor = con.cursor()
    cursor.execute("SELECT user_id, username, role, full_name, active FROM users ORDER BY role, username")
    rows = _fetch_all(cursor)
    con.close()
    return jsonify(rows)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
