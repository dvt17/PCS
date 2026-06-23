"""
database.py — Lưu trữ dữ liệu (SQLite)
PCS Smart Parking System
"""

import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)



import sqlite3
import os
from datetime import datetime
from typing import List, Optional

# Đường dẫn DB động theo vị trí project
DB_PATH = os.path.join(_ROOT, "data", "pcs.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db() -> None:
    con = _connect()
    with con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS vehicles (
            plate         TEXT PRIMARY KEY,
            vehicle_type  TEXT NOT NULL,
            owner_name    TEXT DEFAULT '',
            owner_phone   TEXT DEFAULT '',
            registered_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id  TEXT PRIMARY KEY,
            plate           TEXT NOT NULL,
            slot_id         TEXT NOT NULL,
            zone            TEXT NOT NULL,
            entry_time      TEXT NOT NULL,
            exit_time       TEXT,
            hourly_rate     INTEGER NOT NULL,
            billed_hours    INTEGER,
            gross_fee       INTEGER,
            discount_pct    REAL DEFAULT 0,
            net_fee         INTEGER,
            payment_method  TEXT DEFAULT 'cash',
            payment_status  TEXT DEFAULT 'pending',
            staff_id        TEXT DEFAULT '',
            notes           TEXT DEFAULT '',
            FOREIGN KEY(plate) REFERENCES vehicles(plate)
        );

        CREATE TABLE IF NOT EXISTS parking_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            plate       TEXT,
            slot_id     TEXT,
            confidence  REAL,
            image_path  TEXT,
            message     TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id       TEXT PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL,
            full_name     TEXT DEFAULT '',
            active        INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_txn_plate ON transactions(plate);
        CREATE INDEX IF NOT EXISTS idx_txn_date  ON transactions(exit_time);
        CREATE INDEX IF NOT EXISTS idx_log_plate ON parking_log(plate);
        """)
    con.close()


def upsert_vehicle(plate: str, vehicle_type: str, owner_name: str = "", owner_phone: str = "") -> None:
    con = _connect()
    with con:
        con.execute("""
            INSERT INTO vehicles(plate, vehicle_type, owner_name, owner_phone)
            VALUES(?,?,?,?)
            ON CONFLICT(plate) DO UPDATE SET
                vehicle_type=excluded.vehicle_type,
                owner_name=excluded.owner_name,
                owner_phone=excluded.owner_phone
        """, (plate, vehicle_type, owner_name, owner_phone))
    con.close()


def get_vehicle(plate: str) -> Optional[dict]:
    con = _connect()
    row = con.execute("SELECT * FROM vehicles WHERE plate=?", (plate,)).fetchone()
    con.close()
    return dict(row) if row else None


def save_transaction(txn_dict: dict) -> None:
    con = _connect()
    with con:
        con.execute("""
            INSERT OR REPLACE INTO transactions
            (transaction_id, plate, slot_id, zone, entry_time, exit_time,
             hourly_rate, billed_hours, gross_fee, discount_pct, net_fee,
             payment_method, payment_status, staff_id, notes)
            VALUES(:transaction_id,:plate,:slot_id,:zone,:entry_time,:exit_time,
                   :hourly_rate,:billed_hours,:gross_fee,:discount_pct,:net_fee,
                   :payment_method,:payment_status,:staff_id,:notes)
        """, txn_dict)
    con.close()


def get_open_transaction(plate: str) -> Optional[dict]:
    con = _connect()
    row = con.execute(
        "SELECT * FROM transactions WHERE plate=? AND payment_status='pending' ORDER BY entry_time DESC LIMIT 1",
        (plate,)
    ).fetchone()
    con.close()
    return dict(row) if row else None


def query_transactions(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    zone: Optional[str] = None,
    status: str = "paid"
) -> List[dict]:
    con = _connect()
    sql = "SELECT * FROM transactions WHERE payment_status=?"
    params: list = [status]
    if date_from:
        sql += " AND exit_time >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND exit_time <= ?"
        params.append(date_to + " 23:59:59")
    if zone:
        sql += " AND zone=?"
        params.append(zone)
    sql += " ORDER BY exit_time DESC"
    rows = con.execute(sql, params).fetchall()
    con.close()
    return [dict(r) for r in rows]


def revenue_summary(period: str = "today") -> dict:
    con = _connect()
    if period == "today":
        date_filter = "date(exit_time,'localtime') = date('now','localtime')"
    elif period == "week":
        date_filter = "exit_time >= date('now','-7 days','localtime')"
    else:
        date_filter = "exit_time >= date('now','start of month','localtime')"
    row = con.execute(f"""
        SELECT COUNT(*) as txn_count,
               COALESCE(SUM(net_fee),0) as total_revenue,
               COALESCE(AVG(net_fee),0) as avg_fee,
               COALESCE(MAX(net_fee),0) as max_fee
        FROM transactions
        WHERE payment_status='paid' AND {date_filter}
    """).fetchone()
    con.close()
    return dict(row) if row else {}


def busiest_slots(top: int = 5) -> List[dict]:
    con = _connect()
    rows = con.execute("""
        SELECT slot_id, COUNT(*) as uses, SUM(net_fee) as revenue
        FROM transactions WHERE payment_status='paid'
        GROUP BY slot_id ORDER BY uses DESC LIMIT ?
    """, (top,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def log_event(event_type: str, plate: str = "", slot_id: str = "",
              confidence: float = 0.0, image_path: str = "", message: str = "") -> None:
    con = _connect()
    with con:
        con.execute("""
            INSERT INTO parking_log(event_type, plate, slot_id, confidence, image_path, message)
            VALUES(?,?,?,?,?,?)
        """, (event_type, plate, slot_id, confidence, image_path, message))
    con.close()


def recent_log(limit: int = 50) -> List[dict]:
    con = _connect()
    rows = con.execute(
        "SELECT * FROM parking_log ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def create_user(user_id: str, username: str, password_hash: str, role: str, full_name: str = "") -> None:
    con = _connect()
    with con:
        con.execute("""
            INSERT INTO users(user_id, username, password_hash, role, full_name)
            VALUES(?,?,?,?,?)
        """, (user_id, username, password_hash, role, full_name))
    con.close()


def get_user_by_username(username: str) -> Optional[dict]:
    con = _connect()
    row = con.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
    con.close()
    return dict(row) if row else None
