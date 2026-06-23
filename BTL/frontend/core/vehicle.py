"""
vehicle.py — Vehicle data model
PCS Smart Parking System
"""

import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)




from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class VehicleType(Enum):
    CAR = "car"
    MOTORBIKE = "motorbike"
    TRUCK = "truck"


@dataclass
class Vehicle:
    plate: str
    vehicle_type: VehicleType
    owner_name: str = ""
    owner_phone: str = ""
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    slot_id: Optional[str] = None
    image_path: Optional[str] = None          # ảnh từ camera lúc vào
    ocr_confidence: float = 0.0               # độ tin cậy YOLOv8

    @property
    def is_parked(self) -> bool:
        return self.entry_time is not None and self.exit_time is None

    @property
    def duration_minutes(self) -> int:
        if not self.entry_time:
            return 0
        end = self.exit_time or datetime.now()
        return max(1, int((end - self.entry_time).total_seconds() / 60))

    @property
    def duration_hours_ceil(self) -> int:
        """Làm tròn lên theo giờ (logic tính phí)"""
        import math
        return math.ceil(self.duration_minutes / 60)

    def to_dict(self) -> dict:
        return {
            "plate": self.plate,
            "vehicle_type": self.vehicle_type.value,
            "owner_name": self.owner_name,
            "owner_phone": self.owner_phone,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "slot_id": self.slot_id,
            "image_path": self.image_path,
            "ocr_confidence": self.ocr_confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Vehicle":
        return cls(
            plate=d["plate"],
            vehicle_type=VehicleType(d["vehicle_type"]),
            owner_name=d.get("owner_name", ""),
            owner_phone=d.get("owner_phone", ""),
            entry_time=datetime.fromisoformat(d["entry_time"]) if d.get("entry_time") else None,
            exit_time=datetime.fromisoformat(d["exit_time"]) if d.get("exit_time") else None,
            slot_id=d.get("slot_id"),
            image_path=d.get("image_path"),
            ocr_confidence=d.get("ocr_confidence", 0.0),
        )
