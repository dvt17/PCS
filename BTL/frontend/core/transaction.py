"""
transaction.py — Tính phí & quản lý giao dịch
PCS Smart Parking System
"""



from __future__ import annotations

import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)


import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class PaymentMethod(Enum):
    CASH = "cash"
    VNPAY = "vnpay"
    MOMO = "momo"
    ZALOPAY = "zalopay"


class PaymentStatus(Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass
class Transaction:
    plate: str
    slot_id: str
    zone: str
    entry_time: datetime
    hourly_rate: int                              # đồng/giờ
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    exit_time: Optional[datetime] = None
    payment_method: PaymentMethod = PaymentMethod.CASH
    payment_status: PaymentStatus = PaymentStatus.PENDING
    staff_id: str = ""
    discount_pct: float = 0.0                    # % giảm giá (0–100)
    notes: str = ""

    # ── Tính phí ──────────────────────────────────────────────────────
    @property
    def duration_minutes(self) -> int:
        end = self.exit_time or datetime.now()
        return max(1, int((end - self.entry_time).total_seconds() / 60))

    @property
    def billed_hours(self) -> int:
        """Làm tròn lên theo giờ"""
        return math.ceil(self.duration_minutes / 60)

    @property
    def gross_fee(self) -> int:
        return self.billed_hours * self.hourly_rate

    @property
    def discount_amount(self) -> int:
        return int(self.gross_fee * self.discount_pct / 100)

    @property
    def net_fee(self) -> int:
        return self.gross_fee - self.discount_amount

    # ── Hoàn tất giao dịch ────────────────────────────────────────────
    def complete(self, method: PaymentMethod, exit_time: Optional[datetime] = None) -> int:
        self.exit_time = exit_time or datetime.now()
        self.payment_method = method
        self.payment_status = PaymentStatus.PAID
        return self.net_fee

    def fail(self) -> None:
        self.payment_status = PaymentStatus.FAILED

    # ── Serialisation ─────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "plate": self.plate,
            "slot_id": self.slot_id,
            "zone": self.zone,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "hourly_rate": self.hourly_rate,
            "billed_hours": self.billed_hours,
            "gross_fee": self.gross_fee,
            "discount_pct": self.discount_pct,
            "net_fee": self.net_fee,
            "payment_method": self.payment_method.value,
            "payment_status": self.payment_status.value,
            "staff_id": self.staff_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Transaction":
        t = cls(
            plate=d["plate"],
            slot_id=d["slot_id"],
            zone=d["zone"],
            entry_time=datetime.fromisoformat(d["entry_time"]),
            hourly_rate=d["hourly_rate"],
            transaction_id=d["transaction_id"],
            payment_method=PaymentMethod(d["payment_method"]),
            payment_status=PaymentStatus(d["payment_status"]),
            staff_id=d.get("staff_id", ""),
            discount_pct=d.get("discount_pct", 0.0),
            notes=d.get("notes", ""),
        )
        if d.get("exit_time"):
            t.exit_time = datetime.fromisoformat(d["exit_time"])
        return t

    def receipt_text(self) -> str:
        line = "─" * 36
        return (
            f"\n{'PCS SMART PARKING':^36}\n{line}\n"
            f"Mã GD  : {self.transaction_id}\n"
            f"Biển số: {self.plate}\n"
            f"Ô đỗ   : {self.slot_id} (Zone {self.zone})\n"
            f"Vào    : {self.entry_time.strftime('%d/%m/%Y %H:%M')}\n"
            f"Ra     : {self.exit_time.strftime('%d/%m/%Y %H:%M') if self.exit_time else '—'}\n"
            f"TG đỗ  : {self.billed_hours} giờ ({self.duration_minutes} phút)\n"
            f"Đơn giá: {self.hourly_rate:,}đ/giờ\n"
            f"Thành tiền: {self.gross_fee:,}đ\n"
            + (f"Giảm giá  : -{self.discount_amount:,}đ ({self.discount_pct:.0f}%)\n" if self.discount_pct else "")
            + f"{'─'*36}\n"
            f"TỔNG CỘNG : {self.net_fee:,}đ\n"
            f"Thanh toán: {self.payment_method.value.upper()}\n"
            f"{line}\n"
            f"{'Cảm ơn quý khách!':^36}\n"
        )


class TransactionLedger:
    """
    Danh sách giao dịch trong phiên — sẽ được persist qua database.py.
    """

    def __init__(self) -> None:
        self._records: List[Transaction] = []

    def add(self, txn: Transaction) -> None:
        self._records.append(txn)

    def get_by_plate(self, plate: str) -> Optional[Transaction]:
        for t in reversed(self._records):
            if t.plate == plate and t.payment_status == PaymentStatus.PENDING:
                return t
        return None

    def get_by_id(self, txn_id: str) -> Optional[Transaction]:
        return next((t for t in self._records if t.transaction_id == txn_id), None)

    def paid_records(self) -> List[Transaction]:
        return [t for t in self._records if t.payment_status == PaymentStatus.PAID]

    # ── Báo cáo doanh thu ────────────────────────────────────────────
    def revenue_today(self) -> int:
        today = datetime.now().date()
        return sum(t.net_fee for t in self.paid_records() if t.exit_time and t.exit_time.date() == today)

    def revenue_by_day(self) -> dict:
        result: dict = {}
        for t in self.paid_records():
            if t.exit_time:
                day = t.exit_time.strftime("%Y-%m-%d")
                result[day] = result.get(day, 0) + t.net_fee
        return dict(sorted(result.items()))

    def revenue_by_zone(self) -> dict:
        result: dict = {}
        for t in self.paid_records():
            result[t.zone] = result.get(t.zone, 0) + t.net_fee
        return result

    def busiest_slots(self, top: int = 5) -> List[tuple]:
        from collections import Counter
        c = Counter(t.slot_id for t in self.paid_records())
        return c.most_common(top)

    def total_revenue(self) -> int:
        return sum(t.net_fee for t in self.paid_records())

    def to_list(self) -> list:
        return [t.to_dict() for t in self._records]
