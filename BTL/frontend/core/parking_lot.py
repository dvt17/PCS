"""
parking_lot.py — ParkingSlot & ParkingLot
PCS Smart Parking System
Chỉ còn 2 khu: Zone A (Ô tô), Zone B (Xe máy)
"""

from __future__ import annotations

import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)


import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from core.vehicle import Vehicle, VehicleType


class SlotState(Enum):
    EMPTY    = "empty"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    DISABLED = "disabled"


class Zone(Enum):
    A = "A"
    B = "B"


ZONE_VEHICLE_MAP: Dict[Zone, VehicleType] = {
    Zone.A: VehicleType.CAR,
    Zone.B: VehicleType.MOTORBIKE,
}

VEHICLE_ZONE_MAP: Dict[VehicleType, Zone] = {
    VehicleType.CAR: Zone.A,
    VehicleType.MOTORBIKE: Zone.B,
}

ZONE_HOURLY_RATE: Dict[Zone, int] = {
    Zone.A: 15_000,
    Zone.B: 5_000,
}


@dataclass
class ParkingSlot:
    slot_id: str
    zone: Zone
    state: SlotState = SlotState.EMPTY
    current_plate: Optional[str] = None
    notes: str = ""

    @property
    def is_available(self) -> bool:
        return self.state == SlotState.EMPTY

    @property
    def hourly_rate(self) -> int:
        return ZONE_HOURLY_RATE[self.zone]

    def occupy(self, plate: str) -> None:
        self.state = SlotState.OCCUPIED
        self.current_plate = plate

    def release(self) -> None:
        self.state = SlotState.EMPTY
        self.current_plate = None

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "zone": self.zone.value,
            "state": self.state.value,
            "current_plate": self.current_plate,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ParkingSlot":
        return cls(
            slot_id=d["slot_id"],
            zone=Zone(d["zone"]),
            state=SlotState(d["state"]),
            current_plate=d.get("current_plate"),
            notes=d.get("notes", ""),
        )


class ParkingLot:
    def __init__(self, name: str = "PCS Parking",
                 config_path: str = None):
        self.name = name
        if config_path is None:
            config_path = os.path.join(_ROOT, "data", "lot_config.json")
        self.config_path = config_path
        self.slots: Dict[str, ParkingSlot] = {}
        self._load_or_init()

    def _load_or_init(self) -> None:
        if os.path.exists(self.config_path):
            self._load()
        else:
            self._default_layout()
            self.save()

    def _default_layout(self) -> None:
        """Mặc định: Zone A (Ô tô) = 20 slots, Zone B (Xe máy) = 40 slots"""
        layout = {Zone.A: 20, Zone.B: 40}
        for zone, count in layout.items():
            for i in range(1, count + 1):
                sid = f"{zone.value}{i:02d}"
                self.slots[sid] = ParkingSlot(slot_id=sid, zone=zone)

    def _load(self) -> None:
        with open(self.config_path, encoding="utf-8") as f:
            data = json.load(f)
        for d in data.get("slots", []):
            s = ParkingSlot.from_dict(d)
            self.slots[s.slot_id] = s
        self.name = data.get("name", self.name)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(
                {"name": self.name, "slots": [s.to_dict() for s in self.slots.values()]},
                f, ensure_ascii=False, indent=2
            )

    def available_slots(self, vehicle_type: Optional[VehicleType] = None) -> List[ParkingSlot]:
        candidates = [s for s in self.slots.values() if s.is_available]
        if vehicle_type:
            zone = VEHICLE_ZONE_MAP.get(vehicle_type)
            if zone:
                candidates = [s for s in candidates if s.zone == zone]
        return candidates

    def suggest_slot(self, vehicle_type: VehicleType) -> Optional[ParkingSlot]:
        """
        Tự động tìm chỗ trống cho loại xe tương ứng.
        Trả về chỗ trống đầu tiên (theo thứ tự ID).
        """
        available = self.available_slots(vehicle_type)
        # Sắp xếp theo slot_id để ưu tiên ô có số nhỏ
        available.sort(key=lambda s: s.slot_id)
        return available[0] if available else None

    def suggest_slot_with_info(self, vehicle_type: VehicleType) -> Optional[dict]:
        """
        Tự động tìm chỗ trống và trả về dict đầy đủ thông tin
        dùng cho frontend hiển thị thông báo.
        """
        slot = self.suggest_slot(vehicle_type)
        if not slot:
            return None
        return {
            "slot_id": slot.slot_id,
            "zone": slot.zone.value,
            "zone_label": "Zone A" if slot.zone.value == "A" else "Zone B",
            "vehicle_type": vehicle_type.value,
            "vehicle_label": vehicle_type.display_name,
            "hourly_rate": slot.hourly_rate,
        }

    def get_all_available(self) -> Dict[str, List[str]]:
        """Trả về danh sách chỗ trống theo zone"""
        result = {}
        for zone in Zone:
            result[zone.value] = [
                s.slot_id for s in self.slots.values()
                if s.zone == zone and s.is_available
            ]
        return result

    def find_by_plate(self, plate: str) -> Optional[ParkingSlot]:
        for s in self.slots.values():
            if s.current_plate == plate:
                return s
        return None

    def get_slot(self, slot_id: str) -> Optional[ParkingSlot]:
        return self.slots.get(slot_id)

    def add_slot(self, slot_id: str, zone: Zone) -> ParkingSlot:
        if slot_id in self.slots:
            raise ValueError(f"Slot {slot_id} đã tồn tại")
        s = ParkingSlot(slot_id=slot_id, zone=zone)
        self.slots[slot_id] = s
        self.save()
        return s

    def remove_slot(self, slot_id: str) -> None:
        if slot_id not in self.slots:
            raise KeyError(f"Không tìm thấy slot {slot_id}")
        if self.slots[slot_id].state == SlotState.OCCUPIED:
            raise RuntimeError("Không thể xoá ô đang có xe")
        del self.slots[slot_id]
        self.save()

    def disable_slot(self, slot_id: str) -> None:
        self.slots[slot_id].state = SlotState.DISABLED
        self.save()

    def enable_slot(self, slot_id: str) -> None:
        self.slots[slot_id].state = SlotState.EMPTY
        self.save()

    def set_rate(self, zone: Zone, rate: int) -> None:
        ZONE_HOURLY_RATE[zone] = rate

    @property
    def total_slots(self) -> int:
        return len([s for s in self.slots.values() if s.state != SlotState.DISABLED])

    @property
    def occupied_count(self) -> int:
        return len([s for s in self.slots.values() if s.state == SlotState.OCCUPIED])

    @property
    def occupancy_rate(self) -> float:
        if self.total_slots == 0:
            return 0.0
        return self.occupied_count / self.total_slots * 100

    def zone_summary(self) -> Dict[str, dict]:
        summary = {}
        for zone in Zone:
            zone_slots = [s for s in self.slots.values() if s.zone == zone]
            active = [s for s in zone_slots if s.state != SlotState.DISABLED]
            occ = [s for s in zone_slots if s.state == SlotState.OCCUPIED]
            vehicle_type = ZONE_VEHICLE_MAP[zone]
            summary[zone.value] = {
                "total": len(active),
                "occupied": len(occ),
                "available": len(active) - len(occ),
                "rate": ZONE_HOURLY_RATE[zone],
                "vehicle_type": vehicle_type.value,
                "vehicle_label": vehicle_type.display_name,
            }
        return summary
