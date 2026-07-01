"""
workflow.py — Điều phối luồng vào / ra xe
PCS Smart Parking System
"""



from __future__ import annotations

import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)


from datetime import datetime
from typing import Callable, Optional, Tuple

from core.database import (get_open_transaction, get_vehicle, log_event, save_transaction,
                            upsert_vehicle)
from core.ocr_engine import OCRResult, PlateRecognizer
from core.parking_lot import ParkingLot, ZONE_VEHICLE_MAP
from core.payment import GatewayType, PaymentGateway, PaymentRequest, PaymentResponse
from core.pricing import Pricing
from core.transaction import PaymentMethod, Transaction, TransactionLedger
from core.vehicle import Vehicle, VehicleType


EventCallback = Callable[[str, dict], None]   # (event_name, payload)


class ParkingWorkflow:
    """
    Điều phối toàn bộ luồng nghiệp vụ:
      Entry : Camera → OCR → So sánh DB → Mở barrier → Cập nhật slot
      Exit  : Camera → OCR → Tính phí → Thanh toán → Mở barrier → Giải phóng slot
    """

    def __init__(
        self,
        lot: ParkingLot,
        ledger: TransactionLedger,
        recognizer: Optional[PlateRecognizer] = None,
        gateway: Optional[PaymentGateway] = None,
        on_event: Optional[EventCallback] = None,
    ) -> None:
        self.lot = lot
        self.ledger = ledger
        self.recognizer = recognizer or PlateRecognizer()
        self.gateway = gateway or PaymentGateway()
        self.pricing = Pricing()
        self._on_event = on_event or (lambda e, p: None)

    def _emit(self, event: str, **payload) -> None:
        self._on_event(event, payload)

    def _has_active_combo(self, plate: str) -> bool:
        vehicle = get_vehicle(plate)
        if not vehicle:
            return False
        combo_status = vehicle.get("combo_status", "inactive")
        expire_date = vehicle.get("combo_expire_date", "")
        if combo_status != "active" or not expire_date:
            return False
        try:
            return datetime.strptime(expire_date, "%Y-%m-%d") >= datetime.now().date()
        except ValueError:
            return False

    def _pricing_type_for(self, plate: str, vehicle_type: VehicleType) -> str:
        if self._has_active_combo(plate):
            return "combo"
        return "non_combo"

    @staticmethod
    def _resolve_vehicle_type(ocr: OCRResult, override: Optional[VehicleType] = None) -> VehicleType:
        """
        Xác định loại xe theo thứ tự ưu tiên:
          1. Override từ người dùng (nếu có)
          2. vehicle_type từ YOLO pipeline (OCRResult.vehicle_type)
          3. Tra cứu DB nếu xe đã tồn tại
          4. Fallback: CAR_UNDER_7
        """
        if override is not None:
            return override

        # Từ OCR pipeline (YOLO class name → VehicleType)
        vt_str = ocr.vehicle_type if hasattr(ocr, 'vehicle_type') and ocr.vehicle_type else ""
        if vt_str and vt_str != "unknown":
            try:
                return VehicleType(vt_str)
            except (ValueError, TypeError):
                pass

        # Từ DB
        vehicle = get_vehicle(ocr.plate) if ocr.plate else None
        if vehicle and vehicle.get("vehicle_type"):
            try:
                return VehicleType(vehicle["vehicle_type"])
            except (ValueError, TypeError):
                pass

        return VehicleType.CAR_UNDER_7

    # ═══════════════════════════════════════════════════════════════════
    # ENTRY
    # ═══════════════════════════════════════════════════════════════════
    def process_entry(
        self,
        image_path: str = "",
        manual_plate: str = "",
        vehicle_type: Optional[VehicleType] = None,
        staff_id: str = "",
    ) -> Tuple[bool, str, Optional[Transaction]]:
        """
        Trả về (success, message, transaction).
        vehicle_type: nếu None sẽ tự động xác định từ YOLO pipeline hoặc DB.
        """
        # 1. Nhận diện biển số
        if manual_plate:
            ocr: OCRResult = PlateRecognizer.manual_entry(manual_plate)
            log_event("manual", plate=ocr.plate, message="Nhập tay bởi nhân viên", image_path=image_path)
        else:
            ocr = self.recognizer.recognize_from_file(image_path) if image_path else self.recognizer._demo_result()
            log_event("entry_ocr", plate=ocr.plate, confidence=ocr.confidence, image_path=image_path,
                      message=f"vehicle_type={ocr.vehicle_type}" if hasattr(ocr, 'vehicle_type') and ocr.vehicle_type else "")

        if not ocr.is_valid:
            self._emit("ocr_failed", plate=ocr.raw_text, confidence=ocr.confidence)
            return False, f"OCR thất bại (conf={ocr.confidence:.0%}) — cần nhập tay", None

        plate = ocr.plate

        # 2. Kiểm tra xe đã trong bãi
        existing_slot = self.lot.find_by_plate(plate)
        if existing_slot:
            return False, f"Biển số {plate} đã đỗ tại {existing_slot.slot_id}", None

        # 3. Xác định loại xe (tự động từ YOLO nếu không override)
        vtype = self._resolve_vehicle_type(ocr, vehicle_type)
        suggested = self.lot.suggest_slot(vtype)
        if not suggested:
            self._emit("lot_full", vehicle_type=vtype.value)
            return False, f"Bãi đỗ đầy (zone {[z for z,v in ZONE_VEHICLE_MAP.items() if v==vtype][0].value})", None

        # 4. Lưu xe vào DB
        upsert_vehicle(plate, vtype.value)

        # 5. Cập nhật slot
        suggested.occupy(plate)
        self.lot.save()

        # 6. Tạo giao dịch
        pricing_type = self._pricing_type_for(plate, vtype)
        rule = self.pricing.get_pricing(vtype, pricing_type)
        txn = Transaction(
            plate=plate,
            slot_id=suggested.slot_id,
            zone=suggested.zone.value,
            entry_time=datetime.now(),
            hourly_rate=rule.hourly_rate,
            staff_id=staff_id,
        )
        txn.notes = f"vehicle_type={vtype.value};pricing_type={pricing_type}"
        self.ledger.add(txn)
        save_transaction(txn.to_dict())
        log_event("entry", plate=plate, slot_id=suggested.slot_id, confidence=ocr.confidence, image_path=image_path)

        self._emit("vehicle_entered", plate=plate, slot_id=suggested.slot_id, zone=suggested.zone.value)
        msg = f"Xe {plate} vào ô {suggested.slot_id} (Zone {suggested.zone.value})"
        return True, msg, txn

    # ═══════════════════════════════════════════════════════════════════
    # EXIT
    # ═══════════════════════════════════════════════════════════════════
    def process_exit(
        self,
        image_path: str = "",
        manual_plate: str = "",
        payment_method: GatewayType = GatewayType.CASH,
        cash_received: int = 0,
        discount_pct: float = 0.0,
        staff_id: str = "",
    ) -> Tuple[bool, str, Optional[Transaction]]:
        """
        Trả về (success, message, transaction_with_fee).
        """
        # 1. Nhận diện biển số
        if manual_plate:
            ocr = PlateRecognizer.manual_entry(manual_plate)
        else:
            ocr = self.recognizer.recognize_from_file(image_path) if image_path else self.recognizer._demo_result()

        if not ocr.is_valid:
            return False, "OCR thất bại — cần nhập tay", None

        plate = ocr.plate

        # 2. Tìm giao dịch đang mở
        txn = self.ledger.get_by_plate(plate)
        if not txn:
            # Thử lấy từ DB (sau khi khởi động lại)
            db_txn = get_open_transaction(plate)
            if db_txn:
                txn = Transaction.from_dict(db_txn)
                self.ledger.add(txn)
            else:
                return False, f"Không tìm thấy giao dịch mở cho biển số {plate}", None

        vehicle_type = VehicleType(get_vehicle(plate).get("vehicle_type", "car_under_7")) if get_vehicle(plate) else VehicleType.CAR_UNDER_7
        pricing_type = self._pricing_type_for(plate, vehicle_type)
        rule = self.pricing.get_pricing(vehicle_type, pricing_type)
        txn.hourly_rate = rule.hourly_rate if pricing_type == "non_combo" else 0
        txn.discount_pct = discount_pct
        txn.staff_id = staff_id
        txn.notes = f"vehicle_type={vehicle_type.value};pricing_type={pricing_type}"

        # 3. Thanh toán
        if pricing_type == "combo":
            pay_resp = PaymentResponse(success=True, gateway=payment_method, gateway_ref="combo", amount=0, message="Combo còn hạn")
        else:
            pay_req = PaymentRequest(
                amount=txn.net_fee,
                txn_ref=txn.transaction_id,
                description=f"Phí đỗ xe {plate} — {txn.billed_hours}h",
                gateway=payment_method,
            )
            pay_resp = self.gateway.request_payment(pay_req)
        if not pay_resp.success:
            txn.fail()
            save_transaction(txn.to_dict())
            return False, f"Thanh toán thất bại: {pay_resp.message}", txn

        # 4. Hoàn tất giao dịch
        method_map = {
            GatewayType.CASH: PaymentMethod.CASH,
            GatewayType.VNPAY: PaymentMethod.VNPAY,
            GatewayType.MOMO: PaymentMethod.MOMO,
            GatewayType.ZALOPAY: PaymentMethod.ZALOPAY,
        }
        fee = txn.complete(method_map[payment_method])
        save_transaction(txn.to_dict())

        # 5. Giải phóng slot
        slot = self.lot.find_by_plate(plate)
        if slot:
            slot.release()
            self.lot.save()

        log_event("exit", plate=plate, slot_id=txn.slot_id, image_path=image_path, message=f"Thu: {fee:,}đ")
        self._emit("vehicle_exited", plate=plate, slot_id=txn.slot_id, fee=fee, method=payment_method.value)
        return True, f"Xe {plate} ra — Phí: {fee:,}đ", txn
