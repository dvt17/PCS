"""
reports.py — Báo cáo & thống kê doanh thu
PCS Smart Parking System
"""



from __future__ import annotations

import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)


from datetime import datetime, timedelta
from typing import Dict, List

from core.database import busiest_slots, query_transactions, revenue_summary


class ReportEngine:
    """
    Tạo báo cáo theo kỳ: ngày / tuần / tháng
    Xuất text, dict (cho UI), hoặc CSV
    """

    # ── Doanh thu ─────────────────────────────────────────────────────
    def daily_report(self, date: str = None) -> dict:
        """date: 'YYYY-MM-DD', mặc định hôm nay"""
        date = date or datetime.now().strftime("%Y-%m-%d")
        rows = query_transactions(date_from=date, date_to=date)
        return self._summarise(rows, f"Ngày {date}")

    def weekly_report(self) -> dict:
        today = datetime.now().date()
        start = (today - timedelta(days=6)).isoformat()
        rows = query_transactions(date_from=start)
        return self._summarise(rows, f"7 ngày (từ {start})")

    def monthly_report(self, year: int = None, month: int = None) -> dict:
        now = datetime.now()
        year = year or now.year
        month = month or now.month
        start = f"{year}-{month:02d}-01"
        # Ngày cuối tháng
        if month == 12:
            end = f"{year+1}-01-01"
        else:
            end = f"{year}-{month+1:02d}-01"
        rows = query_transactions(date_from=start, date_to=end)
        return self._summarise(rows, f"Tháng {month:02d}/{year}")

    def _summarise(self, rows: List[dict], label: str) -> dict:
        if not rows:
            return {"label": label, "txn_count": 0, "total_revenue": 0, "by_zone": {}, "by_method": {}, "rows": []}
        total = sum(r["net_fee"] or 0 for r in rows)
        by_zone: Dict[str, int] = {}
        by_method: Dict[str, int] = {}
        for r in rows:
            by_zone[r["zone"]] = by_zone.get(r["zone"], 0) + (r["net_fee"] or 0)
            by_method[r["payment_method"]] = by_method.get(r["payment_method"], 0) + (r["net_fee"] or 0)
        return {
            "label": label,
            "txn_count": len(rows),
            "total_revenue": total,
            "avg_fee": int(total / len(rows)),
            "by_zone": by_zone,
            "by_method": by_method,
            "rows": rows,
        }

    # ── Tỷ lệ lấp đầy ────────────────────────────────────────────────
    def occupancy_over_time(self, total_slots: int, days: int = 7) -> List[dict]:
        """Tỷ lệ lấp đầy mỗi ngày (dựa trên số lượt xe/ngày so với tổng slot)"""
        result = []
        for i in range(days, 0, -1):
            day = (datetime.now().date() - timedelta(days=i - 1)).isoformat()
            rows = query_transactions(date_from=day, date_to=day)
            pct = min(100, round(len(rows) / max(total_slots, 1) * 100, 1)) if rows else 0
            result.append({"date": day, "txn_count": len(rows), "occupancy_pct": pct})
        return result

    # ── Thống kê ô đỗ ────────────────────────────────────────────────
    def top_slots(self, top: int = 10) -> List[dict]:
        return busiest_slots(top)

    # ── Xuất CSV ──────────────────────────────────────────────────────
    def export_csv(self, rows: List[dict], filepath: str) -> str:
        import csv, os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        if not rows:
            return filepath
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return filepath

    # ── In báo cáo text ───────────────────────────────────────────────
    def print_report(self, report: dict) -> None:
        print(f"\n{'═'*40}")
        print(f"  BÁO CÁO: {report['label']}")
        print(f"{'═'*40}")
        print(f"  Số giao dịch : {report['txn_count']:,}")
        print(f"  Doanh thu    : {report['total_revenue']:,}đ")
        if report.get("avg_fee"):
            print(f"  Phí TB/lượt  : {report['avg_fee']:,}đ")
        if report.get("by_zone"):
            print("\n  Theo Zone:")
            for z, v in sorted(report["by_zone"].items()):
                print(f"    Zone {z}: {v:,}đ")
        if report.get("by_method"):
            print("\n  Theo phương thức:")
            for m, v in sorted(report["by_method"].items()):
                print(f"    {m.upper():10s}: {v:,}đ")
        print(f"{'─'*40}\n")
