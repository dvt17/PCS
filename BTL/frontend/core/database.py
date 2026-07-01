"""
database.py — Lưu trữ dữ liệu (SQLite mặc định, có thể chuyển sang MySQL)
PCS Smart Parking System
"""

import hashlib
import os
import sqlite3
import sys
import uuid
from typing import List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import pymysql
except Exception:
    pymysql = None

try:
    import mysql.connector as mysql_connector
except Exception:
    mysql_connector = None

DB_PATH = os.path.join(_ROOT, "data", "pcs.db")
DB_BACKEND = os.getenv("PCS_DB_BACKEND", "sqlite").strip().lower()
MYSQL_HOST = os.getenv("PCS_MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("PCS_MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("PCS_MYSQL_USER", "")
MYSQL_PASSWORD = os.getenv("PCS_MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("PCS_MYSQL_DATABASE", "")
MYSQL_CHARSET = os.getenv("PCS_MYSQL_CHARSET", "utf8mb4")


def get_db_backend() -> str:
    if DB_BACKEND == "mysql" and _mysql_available():
        return "mysql"
    return "sqlite"


def _mysql_available() -> bool:
    return bool(MYSQL_USER and MYSQL_DATABASE and (pymysql or mysql_connector))


def _connect():
    backend = get_db_backend()
    if backend == "mysql":
        if pymysql:
            conn = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
                charset=MYSQL_CHARSET,
                autocommit=True,
            )
            return conn
        if mysql_connector:
            conn = mysql_connector.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
                charset=MYSQL_CHARSET,
            )
            conn.autocommit = True
            return conn

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return dict(row)
    return dict(zip([c[0] for c in row.cursor.description], row))


def _fetch_all(cursor) -> List[dict]:
    columns = [c[0] for c in cursor.description] if cursor.description else []
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _execute(conn, sql: str, params: tuple = ()):
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return cursor


def _row_count(conn, table_name: str) -> int:
    backend = get_db_backend()
    if backend == "mysql":
        cursor = _execute(conn, f"SELECT COUNT(*) as total FROM {table_name}")
    else:
        cursor = _execute(conn, f"SELECT COUNT(*) as total FROM {table_name}")
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def seed_initial_data() -> None:
    placeholder = "%s" if get_db_backend() == "mysql" else "?"
    insert_vehicle_sql = f"INSERT INTO vehicles(plate, vehicle_type, owner_name, owner_phone, combo_status, combo_expire_date) VALUES({','.join([placeholder]*6)})"
    insert_history_sql = f"INSERT INTO image_history(plate, image_path, vehicle_type, confidence, valid) VALUES({','.join([placeholder]*5)})"
    with _connect() as con:
        if _row_count(con, 'users') == 0:
            create_user(uuid.uuid4().hex[:8].upper(), 'admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'admin', 'Quản trị viên')
            create_user(uuid.uuid4().hex[:8].upper(), 'staff1', hashlib.sha256('staff123'.encode()).hexdigest(), 'staff', 'Nhân viên 1')
            create_user(uuid.uuid4().hex[:8].upper(), 'owner', hashlib.sha256('owner123'.encode()).hexdigest(), 'owner', 'Chủ xe Nguyễn Văn A')
        if _row_count(con, 'vehicles') == 0:
            _execute(con, insert_vehicle_sql, ('51A-12345', 'car_under_7', 'Nguyễn Văn A', '0901234567', 'active', ''))
            _execute(con, insert_vehicle_sql, ('59B-67890', 'motorbike', 'Trần Thị B', '0912345678', 'inactive', ''))
            _execute(con, insert_vehicle_sql, ('51L-77777', 'car_under_7', 'Chủ xe Nguyễn Văn A', '0988777666', 'inactive', ''))
        if _row_count(con, 'image_history') == 0:
            _execute(con, insert_history_sql, ('51A-12345', 'sample-51A-12345.jpg', 'car_under_7', 0.95, 1))
            _execute(con, insert_history_sql, ('59B-67890', 'sample-59B-67890.jpg', 'motorbike', 0.88, 1))
        con.commit()


def init_db() -> None:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        statements = [
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                plate VARCHAR(20) PRIMARY KEY,
                vehicle_type VARCHAR(50) NOT NULL,
                owner_name VARCHAR(100) DEFAULT '',
                owner_phone VARCHAR(30) DEFAULT '',
                combo_status VARCHAR(20) DEFAULT 'inactive',
                combo_expire_date VARCHAR(20) DEFAULT '',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id VARCHAR(50) PRIMARY KEY,
                plate VARCHAR(20) NOT NULL,
                slot_id VARCHAR(20) NOT NULL,
                zone VARCHAR(10) NOT NULL,
                entry_time VARCHAR(30) NOT NULL,
                exit_time VARCHAR(30),
                hourly_rate INT NOT NULL,
                billed_hours INT,
                gross_fee INT,
                discount_pct DOUBLE DEFAULT 0,
                net_fee INT,
                payment_method VARCHAR(20) DEFAULT 'cash',
                payment_status VARCHAR(20) DEFAULT 'pending',
                staff_id VARCHAR(50) DEFAULT '',
                notes TEXT DEFAULT ''
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS parking_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                event_type VARCHAR(50) NOT NULL,
                plate VARCHAR(20),
                slot_id VARCHAR(20),
                confidence DOUBLE,
                image_path VARCHAR(255),
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS image_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                plate VARCHAR(20) NOT NULL,
                image_path VARCHAR(255) NOT NULL,
                vehicle_type VARCHAR(50),
                confidence DOUBLE,
                valid INT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(50) PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL,
                full_name VARCHAR(100) DEFAULT '',
                active INT DEFAULT 1
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS uploaded_images (
                id INT AUTO_INCREMENT PRIMARY KEY,
                filename VARCHAR(255) NOT NULL UNIQUE,
                image_data LONGBLOB NOT NULL,
                plate VARCHAR(20) DEFAULT '',
                is_annotated INT DEFAULT 0,
                original_filename VARCHAR(255) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_filename (filename),
                INDEX idx_plate (plate)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        ]
        for statement in statements:
            _execute(con, statement)
    else:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS vehicles (
            plate             TEXT PRIMARY KEY,
            vehicle_type      TEXT NOT NULL,
            owner_name        TEXT DEFAULT '',
            owner_phone       TEXT DEFAULT '',
            combo_status      TEXT DEFAULT 'inactive',
            combo_expire_date TEXT DEFAULT '',
            registered_at     TEXT DEFAULT (datetime('now','localtime'))
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

        CREATE TABLE IF NOT EXISTS image_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            plate         TEXT NOT NULL,
            image_path    TEXT NOT NULL,
            vehicle_type  TEXT,
            confidence    REAL,
            valid         INTEGER DEFAULT 1,
            created_at    TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id       TEXT PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL,
            full_name     TEXT DEFAULT '',
            active        INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS uploaded_images (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            filename          TEXT NOT NULL UNIQUE,
            image_data        BLOB NOT NULL,
            plate             TEXT DEFAULT '',
            is_annotated      INTEGER DEFAULT 0,
            original_filename TEXT DEFAULT '',
            created_at        TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_txn_plate ON transactions(plate);
        CREATE INDEX IF NOT EXISTS idx_txn_date  ON transactions(exit_time);
        CREATE INDEX IF NOT EXISTS idx_log_plate ON parking_log(plate);
        CREATE INDEX IF NOT EXISTS idx_img_filename ON uploaded_images(filename);
        """)
    con.close()


def upsert_vehicle(
    plate: str,
    vehicle_type: str,
    owner_name: str = "",
    owner_phone: str = "",
    combo_status: str = "inactive",
    combo_expire_date: str = "",
) -> None:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        _execute(
            con,
            """
            INSERT INTO vehicles(plate, vehicle_type, owner_name, owner_phone, combo_status, combo_expire_date)
            VALUES(%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                vehicle_type=VALUES(vehicle_type),
                owner_name=VALUES(owner_name),
                owner_phone=VALUES(owner_phone),
                combo_status=VALUES(combo_status),
                combo_expire_date=VALUES(combo_expire_date)
            """,
            (plate, vehicle_type, owner_name, owner_phone, combo_status, combo_expire_date),
        )
    else:
        _execute(
            con,
            """
            INSERT INTO vehicles(plate, vehicle_type, owner_name, owner_phone, combo_status, combo_expire_date)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(plate) DO UPDATE SET
                vehicle_type=excluded.vehicle_type,
                owner_name=excluded.owner_name,
                owner_phone=excluded.owner_phone,
                combo_status=excluded.combo_status,
                combo_expire_date=excluded.combo_expire_date
            """,
            (plate, vehicle_type, owner_name, owner_phone, combo_status, combo_expire_date),
        )
    con.close()


def get_vehicle(plate: str) -> Optional[dict]:
    con = _connect()
    cursor = _execute(con, "SELECT * FROM vehicles WHERE plate=?", (plate,)) if get_db_backend() == "sqlite" else _execute(con, "SELECT * FROM vehicles WHERE plate=%s", (plate,))
    row = cursor.fetchone()
    con.close()
    return _row_to_dict(row) if row else None


def set_vehicle_combo(plate: str, combo_status: str, combo_expire_date: str = "") -> None:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        _execute(con, "UPDATE vehicles SET combo_status=%s, combo_expire_date=%s WHERE plate=%s", (combo_status, combo_expire_date, plate))
    else:
        _execute(con, "UPDATE vehicles SET combo_status=?, combo_expire_date=? WHERE plate=?", (combo_status, combo_expire_date, plate))
    con.close()


def save_transaction(txn_dict: dict) -> None:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        _execute(
            con,
            """
            INSERT INTO transactions
            (transaction_id, plate, slot_id, zone, entry_time, exit_time,
             hourly_rate, billed_hours, gross_fee, discount_pct, net_fee,
             payment_method, payment_status, staff_id, notes)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                plate=VALUES(plate), slot_id=VALUES(slot_id), zone=VALUES(zone), entry_time=VALUES(entry_time),
                exit_time=VALUES(exit_time), hourly_rate=VALUES(hourly_rate), billed_hours=VALUES(billed_hours),
                gross_fee=VALUES(gross_fee), discount_pct=VALUES(discount_pct), net_fee=VALUES(net_fee),
                payment_method=VALUES(payment_method), payment_status=VALUES(payment_status), staff_id=VALUES(staff_id), notes=VALUES(notes)
            """,
            tuple(txn_dict.values()),
        )
    else:
        _execute(
            con,
            """
            INSERT OR REPLACE INTO transactions
            (transaction_id, plate, slot_id, zone, entry_time, exit_time,
             hourly_rate, billed_hours, gross_fee, discount_pct, net_fee,
             payment_method, payment_status, staff_id, notes)
            VALUES(:transaction_id,:plate,:slot_id,:zone,:entry_time,:exit_time,
                   :hourly_rate,:billed_hours,:gross_fee,:discount_pct,:net_fee,
                   :payment_method,:payment_status,:staff_id,:notes)
            """,
            txn_dict,
        )
    con.close()


def get_open_transaction(plate: str) -> Optional[dict]:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        cursor = _execute(con, "SELECT * FROM transactions WHERE plate=%s AND payment_status='pending' ORDER BY entry_time DESC LIMIT 1", (plate,))
    else:
        cursor = _execute(con, "SELECT * FROM transactions WHERE plate=? AND payment_status='pending' ORDER BY entry_time DESC LIMIT 1", (plate,))
    row = cursor.fetchone()
    con.close()
    return _row_to_dict(row) if row else None


def query_transactions(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    zone: Optional[str] = None,
    status: str = "paid"
) -> List[dict]:
    con = _connect()
    backend = get_db_backend()
    sql = "SELECT * FROM transactions WHERE payment_status=%s" if backend == "mysql" else "SELECT * FROM transactions WHERE payment_status=?"
    params: list = [status]
    if date_from:
        sql += " AND exit_time >= %s" if backend == "mysql" else " AND exit_time >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND exit_time <= %s" if backend == "mysql" else " AND exit_time <= ?"
        params.append(date_to + " 23:59:59")
    if zone:
        sql += " AND zone=%s" if backend == "mysql" else " AND zone=?"
        params.append(zone)
    sql += " ORDER BY exit_time DESC"
    cursor = _execute(con, sql, tuple(params))
    rows = _fetch_all(cursor)
    con.close()
    return rows


def revenue_summary(period: str = "today") -> dict:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        if period == "today":
            date_filter = "DATE(exit_time) = CURDATE()"
        elif period == "week":
            date_filter = "exit_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
        else:
            date_filter = "exit_time >= DATE_FORMAT(CURDATE(), '%Y-%m-01')"
    else:
        if period == "today":
            date_filter = "date(exit_time,'localtime') = date('now','localtime')"
        elif period == "week":
            date_filter = "exit_time >= date('now','-7 days','localtime')"
        else:
            date_filter = "exit_time >= date('now','start of month','localtime')"
    cursor = _execute(con, f"""
        SELECT COUNT(*) as txn_count,
               COALESCE(SUM(net_fee),0) as total_revenue,
               COALESCE(AVG(net_fee),0) as avg_fee,
               COALESCE(MAX(net_fee),0) as max_fee
        FROM transactions
        WHERE payment_status='paid' AND {date_filter}
    """)
    row = cursor.fetchone()
    con.close()
    return _row_to_dict(row) if row else {}


def busiest_slots(top: int = 5) -> List[dict]:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        cursor = _execute(con, """
            SELECT slot_id, COUNT(*) as uses, SUM(net_fee) as revenue
            FROM transactions WHERE payment_status='paid'
            GROUP BY slot_id ORDER BY uses DESC LIMIT %s
        """, (top,))
    else:
        cursor = _execute(con, """
            SELECT slot_id, COUNT(*) as uses, SUM(net_fee) as revenue
            FROM transactions WHERE payment_status='paid'
            GROUP BY slot_id ORDER BY uses DESC LIMIT ?
        """, (top,))
    rows = _fetch_all(cursor)
    con.close()
    return rows


def log_event(event_type: str, plate: str = "", slot_id: str = "",
              confidence: float = 0.0, image_path: str = "", message: str = "") -> None:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        _execute(con, "INSERT INTO parking_log(event_type, plate, slot_id, confidence, image_path, message) VALUES(%s,%s,%s,%s,%s,%s)", (event_type, plate, slot_id, confidence, image_path, message))
    else:
        _execute(con, "INSERT INTO parking_log(event_type, plate, slot_id, confidence, image_path, message) VALUES(?,?,?,?,?,?)", (event_type, plate, slot_id, confidence, image_path, message))
    con.close()


def recent_log(limit: int = 50) -> List[dict]:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        cursor = _execute(con, "SELECT * FROM parking_log ORDER BY created_at DESC LIMIT %s", (limit,))
    else:
        cursor = _execute(con, "SELECT * FROM parking_log ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = _fetch_all(cursor)
    con.close()
    return rows


def save_image_history(plate: str, image_path: str, vehicle_type: str = "", confidence: float = 0.0, valid: int = 1) -> None:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        _execute(con, "INSERT INTO image_history(plate, image_path, vehicle_type, confidence, valid) VALUES(%s,%s,%s,%s,%s)", (plate, image_path, vehicle_type, confidence, valid))
    else:
        _execute(con, "INSERT INTO image_history(plate, image_path, vehicle_type, confidence, valid) VALUES(?,?,?,?,?)", (plate, image_path, vehicle_type, confidence, valid))
    con.close()


def get_image_history(plate: str) -> List[dict]:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        cursor = _execute(con, "SELECT * FROM image_history WHERE plate=%s ORDER BY created_at DESC LIMIT 20", (plate,))
    else:
        cursor = _execute(con, "SELECT * FROM image_history WHERE plate=? ORDER BY created_at DESC LIMIT 20", (plate,))
    rows = _fetch_all(cursor)
    con.close()
    return rows


def get_recent_image_history(limit: int = 10) -> List[dict]:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        cursor = _execute(con, "SELECT * FROM image_history ORDER BY created_at DESC LIMIT %s", (limit,))
    else:
        cursor = _execute(con, "SELECT * FROM image_history ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = _fetch_all(cursor)
    con.close()
    return rows


def create_user(user_id: str, username: str, password_hash: str, role: str, full_name: str = "") -> None:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        _execute(con, "INSERT INTO users(user_id, username, password_hash, role, full_name) VALUES(%s,%s,%s,%s,%s)", (user_id, username, password_hash, role, full_name))
    else:
        _execute(con, "INSERT INTO users(user_id, username, password_hash, role, full_name) VALUES(?,?,?,?,?)", (user_id, username, password_hash, role, full_name))
    con.commit()
    con.close()


def user_exists(username: str) -> bool:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        cursor = _execute(con, "SELECT 1 FROM users WHERE username=%s AND active=1 LIMIT 1", (username,))
    else:
        cursor = _execute(con, "SELECT 1 FROM users WHERE username=? AND active=1 LIMIT 1", (username,))
    exists = cursor.fetchone() is not None
    con.close()
    return exists


def get_user_by_username(username: str) -> Optional[dict]:
    con = _connect()
    backend = get_db_backend()
    if backend == "mysql":
        cursor = _execute(con, "SELECT * FROM users WHERE username=%s AND active=1", (username,))
    else:
        cursor = _execute(con, "SELECT * FROM users WHERE username=? AND active=1", (username,))
    row = cursor.fetchone()
    con.close()
    return _row_to_dict(row) if row else None


# ═══════════════════════════════════════════════════════════════════
# IMAGE STORAGE — Lưu ảnh trong DB thay vì filesystem
# ═══════════════════════════════════════════════════════════════════

def save_image_to_db(filename: str, image_data: bytes, plate: str = "",
                     is_annotated: int = 0, original_filename: str = "") -> None:
    """Lưu ảnh vào database (BLOB) thay vì ghi ra filesystem."""
    con = _connect()
    backend = get_db_backend()
    placeholder = "%s" if backend == "mysql" else "?"
    sql = f"""
        INSERT OR REPLACE INTO uploaded_images
        (filename, image_data, plate, is_annotated, original_filename)
        VALUES({','.join([placeholder]*5)})
    """
    _execute(con, sql, (filename, image_data, plate, is_annotated, original_filename))
    con.commit()
    con.close()


def get_image_from_db(filename: str) -> Optional[bytes]:
    """Lấy ảnh từ database theo filename. Trả về None nếu không tìm thấy."""
    con = _connect()
    backend = get_db_backend()
    placeholder = "%s" if backend == "mysql" else "?"
    cursor = _execute(con, f"SELECT image_data FROM uploaded_images WHERE filename={placeholder}", (filename,))
    row = cursor.fetchone()
    con.close()
    if row and row[0]:
        return row[0] if isinstance(row[0], bytes) else bytes(row[0])
    return None


def image_exists_in_db(filename: str) -> bool:
    """Kiểm tra ảnh đã tồn tại trong database chưa."""
    con = _connect()
    backend = get_db_backend()
    placeholder = "%s" if backend == "mysql" else "?"
    cursor = _execute(con, f"SELECT 1 FROM uploaded_images WHERE filename={placeholder}", (filename,))
    exists = cursor.fetchone() is not None
    con.close()
    return exists


def delete_image_from_db(filename: str) -> None:
    """Xoá ảnh khỏi database."""
    con = _connect()
    backend = get_db_backend()
    placeholder = "%s" if backend == "mysql" else "?"
    _execute(con, f"DELETE FROM uploaded_images WHERE filename={placeholder}", (filename,))
    con.commit()
    con.close()
