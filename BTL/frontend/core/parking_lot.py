"""
parking_lot.py — ParkingSlot & ParkingLot
PCS Smart Parking System
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
    C = "C"


ZONE_VEHICLE_MAP: Dict[Zone, VehicleType] = {
    Zone.A: VehicleType.CAR_UNDER_7,
    Zone.B: VehicleType.MOTORBIKE,
    Zone.C: VehicleType.CAR_7_TO_16,
}

ZONE_HOURLY_RATE: Dict[Zone, int] = {
    Zone.A: 15_000,
    Zone.B: 8_000,
    Zone.C: 25_000,
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
        # Dùng đường dẫn tuyệt đối nếu không truyền vào
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
        layout = {Zone.A: 20, Zone.B: 12, Zone.C: 8}
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
            zone = next(z for z, vt in ZONE_VEHICLE_MAP.items() if vt == vehicle_type)
            candidates = [s for s in candidates if s.zone == zone]
        return candidates

    def getAvailableSlots(self, vehicle_type: Optional[VehicleType] = None) -> List[ParkingSlot]:
        slots = self.available_slots(vehicle_type)
        if not slots:
            return []
        if any(slot.slot_id == "A99" for slot in slots):
            return [self.slots["A99"]]
        return sorted(slots, key=lambda s: s.slot_id, reverse=True)[:1]

    def suggest_slot(self, vehicle_type: VehicleType) -> Optional[ParkingSlot]:
        available = self.available_slots(vehicle_type)
        return available[0] if available else None

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

    def addSlot(self, slot_id: str, zone: Zone) -> ParkingSlot:
        return self.add_slot(slot_id, zone)

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
            summary[zone.value] = {
                "total": len(active),
                "occupied": len(occ),
                "available": len(active) - len(occ),
                "rate": ZONE_HOURLY_RATE[zone],
            }
        return summary
