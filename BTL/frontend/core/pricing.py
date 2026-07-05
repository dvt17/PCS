"""pricing.py — Quản lý bảng giá cho hệ thống smart parking.
Chỉ còn 2 loại xe: Ô tô và Xe máy
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

from core.vehicle import VehicleType


@dataclass
class PricingRule:
    vehicle_type: VehicleType
    pricing_type: str  # combo / non_combo
    hourly_rate: int
    daily_rate: int
    monthly_rate: int
    effective_date: datetime | None = None
    status: str = "active"

    def to_dict(self) -> dict:
        return {
            "vehicle_type": self.vehicle_type.value,
            "pricing_type": self.pricing_type,
            "hourly_rate": self.hourly_rate,
            "daily_rate": self.daily_rate,
            "monthly_rate": self.monthly_rate,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "status": self.status,
        }


class Pricing:
    def __init__(self) -> None:
        self._rules: Dict[tuple[VehicleType, str], PricingRule] = {}
        self._load_defaults()

    def _load_defaults(self) -> None:
        defaults = [
            (VehicleType.MOTORBIKE, "non_combo", 5_000, 50_000, 150_000),
            (VehicleType.MOTORBIKE, "combo", 0, 0, 150_000),
            (VehicleType.CAR, "non_combo", 15_000, 150_000, 900_000),
            (VehicleType.CAR, "combo", 0, 0, 900_000),
        ]
        for vehicle_type, pricing_type, hourly_rate, daily_rate, monthly_rate in defaults:
            self._rules[(vehicle_type, pricing_type)] = PricingRule(
                vehicle_type=vehicle_type,
                pricing_type=pricing_type,
                hourly_rate=hourly_rate,
                daily_rate=daily_rate,
                monthly_rate=monthly_rate,
                effective_date=datetime.now(),
                status="active",
            )

    def add_pricing(self, vehicle_type: VehicleType, pricing_type: str, hourly_rate: int, daily_rate: int, monthly_rate: int) -> PricingRule:
        rule = PricingRule(vehicle_type=vehicle_type, pricing_type=pricing_type, hourly_rate=hourly_rate, daily_rate=daily_rate, monthly_rate=monthly_rate, effective_date=datetime.now())
        self._rules[(vehicle_type, pricing_type)] = rule
        return rule

    def update_pricing(self, vehicle_type: VehicleType, pricing_type: str, **kwargs) -> PricingRule:
        rule = self.get_pricing(vehicle_type, pricing_type)
        for key, value in kwargs.items():
            setattr(rule, key, value)
        self._rules[(vehicle_type, pricing_type)] = rule
        return rule

    def get_pricing(self, vehicle_type: VehicleType, pricing_type: str) -> PricingRule:
        key = (vehicle_type, pricing_type)
        if key not in self._rules:
            return self._rules[(VehicleType.MOTORBIKE, "non_combo")]
        return self._rules[key]

    def calculate_price(self, vehicle_type: VehicleType, pricing_type: str, hours: int = 1) -> int:
        rule = self.get_pricing(vehicle_type, pricing_type)
        if pricing_type == "combo":
            return rule.monthly_rate
        return rule.hourly_rate * max(1, hours)

    def calculatePrice(self, vehicle_type: VehicleType, pricing_type: str, hours: int = 1) -> int:
        return self.calculate_price(vehicle_type, pricing_type, hours)

    def calculate_fee_detailed(
        self,
        vehicle_type: VehicleType,
        check_in_time: datetime,
        check_out_time: datetime,
        has_active_combo: bool = False,
        combo_expires_at: Optional[datetime] = None
    ) -> Dict:
        """
        Tính toán phí chi tiết dựa trên thời gian thực tế.
        """
        if has_active_combo and combo_expires_at:
            if datetime.now() < combo_expires_at:
                return {
                    "fee": 0,
                    "pricing_type": "combo",
                    "duration_hours": 0,
                    "duration_minutes": 0,
                    "hourly_rate": 0,
                    "reason": f"✓ Gói Combo đang hoạt động (hết hạn {combo_expires_at.strftime('%d/%m/%Y')})"
                }

        duration = check_out_time - check_in_time
        duration_minutes = int(duration.total_seconds() / 60)
        duration_hours = max(1, (duration_minutes + 59) // 60)

        fee = self.calculate_price(vehicle_type, "non_combo", duration_hours)
        rule = self.get_pricing(vehicle_type, "non_combo")
        return {
            "fee": fee,
            "pricing_type": "non_combo",
            "duration_hours": duration_hours,
            "duration_minutes": duration_minutes,
            "hourly_rate": rule.hourly_rate,
            "reason": f"{duration_hours} lượt × {rule.hourly_rate:,} VNĐ/lượt = {fee:,} VNĐ"
        }

    def list_rules(self) -> list[dict]:
        return [rule.to_dict() for rule in self._rules.values()]
