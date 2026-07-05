"""
db_schema.py — MySQL Schema Initialization & Migrations
PCS Smart Parking System

Khởi tạo tất cả bảng MySQL theo chuẩn thiết kế hệ thống.
Hỗ trợ cả SQLite và MySQL backend.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional

# ─────────────────────────────────────────────────────────────────
# SCHEMA DEFINITION (COMPATIBLE WITH SQLITE & MYSQL)
# ─────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- ═════════════════════════════════════════════════════════════════
-- TABLE: Vehicles (Thông tin phương tiện)
-- Chỉ còn 2 loại: Ô tô và Xe máy
-- ═════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS Vehicles (
    LicensePlate VARCHAR(20) PRIMARY KEY COMMENT 'Biển số xe (VN format)',
    VehicleType ENUM('motorbike', 'car') 
        NOT NULL DEFAULT 'car' COMMENT 'Loại phương tiện (chỉ 2 loại)',
    OwnerName VARCHAR(100) COMMENT 'Tên chủ xe',
    OwnerPhone VARCHAR(15) COMMENT 'Số điện thoại',
    OwnerEmail VARCHAR(100) COMMENT 'Email chủ xe',
    ComboStatus ENUM('active', 'expired', 'inactive') 
        NOT NULL DEFAULT 'inactive' COMMENT 'Trạng thái combo',
    ComboExpireDate DATETIME COMMENT 'Ngày hết hạn combo',
    FirstRegistered DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    LastSeen DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    IsBlacklisted BOOLEAN DEFAULT FALSE,
    Notes TEXT,
    INDEX idx_vehicle_type (VehicleType),
    INDEX idx_combo_status (ComboStatus),
    INDEX idx_last_seen (LastSeen)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ═════════════════════════════════════════════════════════════════
-- TABLE: Slots (Chỗ đỗ xe)
-- ═════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS Slots (
    SlotID VARCHAR(10) PRIMARY KEY COMMENT 'ID chỗ đỗ (A1, A2, B1, ...)',
    Zone ENUM('A', 'B') NOT NULL COMMENT 'Zone A=Ô tô, Zone B=Xe máy',
    Status ENUM('empty', 'occupied', 'reserved', 'disabled') 
        NOT NULL DEFAULT 'empty' COMMENT 'Trạng thái',
    CurrentPlate VARCHAR(20) COMMENT 'Biển số xe đang đỗ',
    LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    DisabledReason VARCHAR(255) COMMENT 'Lý do nếu bị vô hiệu',
    DisabledSince DATETIME COMMENT 'Thời gian bắt đầu vô hiệu',
    FOREIGN KEY (CurrentPlate) REFERENCES Vehicles(LicensePlate) ON DELETE SET NULL,
    INDEX idx_zone (Zone),
    INDEX idx_status (Status),
    INDEX idx_current_plate (CurrentPlate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ═════════════════════════════════════════════════════════════════
-- TABLE: Pricing (Bảng giá)
-- ═════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS Pricing (
    PricingID INT AUTO_INCREMENT PRIMARY KEY,
    VehicleType ENUM('motorbike', 'car') 
        NOT NULL COMMENT 'motorbike=Xe máy, car=Ô tô',
    PricingType ENUM('combo', 'non_combo') NOT NULL,
    HourlyRate INT COMMENT 'Giá theo lượt (VNĐ)',
    MonthlyRate INT COMMENT 'Giá theo tháng (VNĐ)',
    EffectiveDate DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ExpiryDate DATETIME COMMENT 'NULL if still active',
    Active BOOLEAN NOT NULL DEFAULT TRUE,
    CreatedBy VARCHAR(36) COMMENT 'User ID who created this',
    LastModified DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_pricing (VehicleType, PricingType, EffectiveDate, ExpiryDate),
    INDEX idx_vehicle_type (VehicleType),
    INDEX idx_pricing_type (PricingType),
    INDEX idx_active (Active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ═════════════════════════════════════════════════════════════════
-- TABLE: Transactions (Giao dịch đỗ xe)
-- ═════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS Transactions (
    TransactionID VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    LicensePlate VARCHAR(20) NOT NULL,
    VehicleType ENUM('motorbike', 'car') 
        NOT NULL COMMENT 'motorbike=Xe máy, car=Ô tô',
    SlotID VARCHAR(10) COMMENT 'Chỗ đỗ được phân bổ',
    PricingID INT COMMENT 'Bảng giá áp dụng',
    PricingType ENUM('combo', 'non_combo') NOT NULL,
    CheckInTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CheckOutTime DATETIME COMMENT 'NULL if still parked',
    DurationMinutes INT COMMENT 'Thời gian lưu (phút)',
    Fee INT DEFAULT 0 COMMENT 'Phí (VNĐ)',
    PaymentStatus ENUM('pending', 'completed', 'failed', 'refunded') 
        NOT NULL DEFAULT 'pending',
    PaymentMethod ENUM('cash', 'momo', 'vnpay', 'zalopay', 'combo') 
        COMMENT 'Phương thức thanh toán',
    EntryImagePath VARCHAR(255) COMMENT 'Đường dẫn ảnh vào',
    ExitImagePath VARCHAR(255) COMMENT 'Đường dẫn ảnh ra',
    EntryOCRConfidence FLOAT COMMENT 'Độ tin cậy OCR khi vào',
    ExitOCRConfidence FLOAT COMMENT 'Độ tin cậy OCR khi ra',
    ManualEntryFlag BOOLEAN DEFAULT FALSE COMMENT 'Nhập tay?',
    ManualExitFlag BOOLEAN DEFAULT FALSE,
    Notes TEXT,
    FOREIGN KEY (LicensePlate) REFERENCES Vehicles(LicensePlate),
    FOREIGN KEY (SlotID) REFERENCES Slots(SlotID) ON DELETE SET NULL,
    FOREIGN KEY (PricingID) REFERENCES Pricing(PricingID),
    INDEX idx_license_plate (LicensePlate),
    INDEX idx_check_in_time (CheckInTime),
    INDEX idx_check_out_time (CheckOutTime),
    INDEX idx_payment_status (PaymentStatus),
    INDEX idx_slot_id (SlotID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ═════════════════════════════════════════════════════════════════
-- TABLE: OCRHistory (Lịch sử nhận diện)
-- ═════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS OCRHistory (
    HistoryID INT AUTO_INCREMENT PRIMARY KEY,
    ImagePath VARCHAR(255) NOT NULL,
    Timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    DetectedPlate VARCHAR(20) COMMENT 'Biển số được nhận diện',
    Confidence FLOAT NOT NULL COMMENT '0.0-1.0',
    RawText VARCHAR(255) COMMENT 'Text thô trước khi chuẩn hóa',
    IsValid BOOLEAN NOT NULL DEFAULT FALSE,
    VehicleType ENUM('motorbike', 'car'),
    Status ENUM('success', 'partial_fail', 'manual_input_required') 
        NOT NULL DEFAULT 'success',
    BboxData VARCHAR(255) COMMENT 'Bounding box coordinates (x1,y1,x2,y2)',
    OperatorInterventionID INT COMMENT 'Reference to user intervention',
    INDEX idx_timestamp (Timestamp),
    INDEX idx_confidence (Confidence),
    INDEX idx_detected_plate (DetectedPlate),
    INDEX idx_status (Status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ═════════════════════════════════════════════════════════════════
-- TABLE: Users (Người dùng hệ thống)
-- ═════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS Users (
    UserID VARCHAR(36) PRIMARY KEY COMMENT 'UUID',
    Username VARCHAR(50) NOT NULL UNIQUE,
    PasswordHash VARCHAR(255) NOT NULL,
    FullName VARCHAR(100),
    Email VARCHAR(100),
    Role ENUM('admin', 'operator', 'owner') NOT NULL DEFAULT 'operator',
    LastLogin DATETIME,
    Active BOOLEAN NOT NULL DEFAULT TRUE,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_username (Username),
    INDEX idx_role (Role),
    INDEX idx_active (Active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ═════════════════════════════════════════════════════════════════
-- TABLE: Events (Sự kiện hệ thống)
-- ═════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS Events (
    EventID INT AUTO_INCREMENT PRIMARY KEY,
    EventType ENUM('checkin', 'checkout', 'error', 'maintenance', 'alert') 
        NOT NULL,
    Plate VARCHAR(20) COMMENT 'Liên quan đến xe nào',
    SlotID VARCHAR(10) COMMENT 'Chỗ đỗ liên quan',
    EventTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Message TEXT NOT NULL,
    Severity ENUM('info', 'warning', 'error', 'critical') NOT NULL,
    TransactionID VARCHAR(36) COMMENT 'Liên kết đến giao dịch',
    UserID VARCHAR(36) COMMENT 'Người xử lý',
    FOREIGN KEY (TransactionID) REFERENCES Transactions(TransactionID),
    FOREIGN KEY (UserID) REFERENCES Users(UserID),
    INDEX idx_event_type (EventType),
    INDEX idx_event_time (EventTime),
    INDEX idx_severity (Severity),
    INDEX idx_plate (Plate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ═════════════════════════════════════════════════════════════════
-- TABLE: DailyReport (Báo cáo hàng ngày - cache)
-- ═════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS DailyReport (
    ReportDate DATE PRIMARY KEY,
    TotalCheckIns INT DEFAULT 0,
    TotalCheckOuts INT DEFAULT 0,
    TotalRevenue BIGINT DEFAULT 0 COMMENT 'VNĐ',
    AverageOccupancy FLOAT DEFAULT 0 COMMENT '0.0-1.0',
    PeakHour VARCHAR(5) COMMENT 'e.g., 09-10',
    MostUsedSlot VARCHAR(10),
    LastUpdated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_date (ReportDate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# ─────────────────────────────────────────────────────────────────
# SQLITE COMPATIBLE VERSION (Simplified Schema)
# ─────────────────────────────────────────────────────────────────

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS Vehicles (
    LicensePlate TEXT PRIMARY KEY,
    VehicleType TEXT DEFAULT 'motorbike',
    OwnerName TEXT,
    OwnerPhone TEXT,
    ComboStatus TEXT DEFAULT 'inactive',
    ComboExpireDate TEXT,
    FirstRegistered TEXT DEFAULT CURRENT_TIMESTAMP,
    LastSeen TEXT DEFAULT CURRENT_TIMESTAMP,
    IsBlacklisted INTEGER DEFAULT 0,
    Notes TEXT
);

CREATE TABLE IF NOT EXISTS Slots (
    SlotID TEXT PRIMARY KEY,
    Zone TEXT NOT NULL,
    Status TEXT DEFAULT 'empty',
    CurrentPlate TEXT,
    LastUpdated TEXT DEFAULT CURRENT_TIMESTAMP,
    DisabledReason TEXT,
    DisabledSince TEXT,
    FOREIGN KEY (CurrentPlate) REFERENCES Vehicles(LicensePlate)
);

CREATE TABLE IF NOT EXISTS Pricing (
    PricingID INTEGER PRIMARY KEY AUTOINCREMENT,
    VehicleType TEXT NOT NULL,
    PricingType TEXT NOT NULL,
    HourlyRate INTEGER,
    MonthlyRate INTEGER,
    EffectiveDate TEXT DEFAULT CURRENT_TIMESTAMP,
    ExpiryDate TEXT,
    Active INTEGER DEFAULT 1,
    CreatedBy TEXT,
    LastModified TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Transactions (
    TransactionID TEXT PRIMARY KEY,
    LicensePlate TEXT NOT NULL,
    VehicleType TEXT NOT NULL,
    SlotID TEXT,
    PricingID INTEGER,
    PricingType TEXT NOT NULL,
    CheckInTime TEXT DEFAULT CURRENT_TIMESTAMP,
    CheckOutTime TEXT,
    DurationMinutes INTEGER,
    Fee INTEGER DEFAULT 0,
    PaymentStatus TEXT DEFAULT 'pending',
    PaymentMethod TEXT,
    EntryImagePath TEXT,
    ExitImagePath TEXT,
    EntryOCRConfidence REAL,
    ExitOCRConfidence REAL,
    ManualEntryFlag INTEGER DEFAULT 0,
    ManualExitFlag INTEGER DEFAULT 0,
    Notes TEXT,
    FOREIGN KEY (LicensePlate) REFERENCES Vehicles(LicensePlate),
    FOREIGN KEY (SlotID) REFERENCES Slots(SlotID),
    FOREIGN KEY (PricingID) REFERENCES Pricing(PricingID)
);

CREATE TABLE IF NOT EXISTS OCRHistory (
    HistoryID INTEGER PRIMARY KEY AUTOINCREMENT,
    ImagePath TEXT NOT NULL,
    Timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    DetectedPlate TEXT,
    Confidence REAL NOT NULL,
    RawText TEXT,
    IsValid INTEGER DEFAULT 0,
    VehicleType TEXT,
    Status TEXT DEFAULT 'success',
    BboxData TEXT
);

CREATE TABLE IF NOT EXISTS Users (
    UserID TEXT PRIMARY KEY,
    Username TEXT UNIQUE NOT NULL,
    PasswordHash TEXT NOT NULL,
    FullName TEXT,
    Email TEXT,
    Role TEXT DEFAULT 'operator',
    LastLogin TEXT,
    Active INTEGER DEFAULT 1,
    CreatedAt TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Events (
    EventID INTEGER PRIMARY KEY AUTOINCREMENT,
    EventType TEXT NOT NULL,
    Plate TEXT,
    SlotID TEXT,
    EventTime TEXT DEFAULT CURRENT_TIMESTAMP,
    Message TEXT NOT NULL,
    Severity TEXT NOT NULL,
    TransactionID TEXT,
    UserID TEXT,
    FOREIGN KEY (TransactionID) REFERENCES Transactions(TransactionID),
    FOREIGN KEY (UserID) REFERENCES Users(UserID)
);

CREATE TABLE IF NOT EXISTS DailyReport (
    ReportDate TEXT PRIMARY KEY,
    TotalCheckIns INTEGER DEFAULT 0,
    TotalCheckOuts INTEGER DEFAULT 0,
    TotalRevenue INTEGER DEFAULT 0,
    AverageOccupancy REAL DEFAULT 0,
    PeakHour TEXT,
    MostUsedSlot TEXT,
    LastUpdated TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ═ INDEXES FOR SQLITE ═
CREATE INDEX IF NOT EXISTS idx_vehicles_type ON Vehicles(VehicleType);
CREATE INDEX IF NOT EXISTS idx_slots_zone ON Slots(Zone);
CREATE INDEX IF NOT EXISTS idx_slots_status ON Slots(Status);
CREATE INDEX IF NOT EXISTS idx_txn_plate ON Transactions(LicensePlate);
CREATE INDEX IF NOT EXISTS idx_txn_checkin ON Transactions(CheckInTime);
CREATE INDEX IF NOT EXISTS idx_ocr_plate ON OCRHistory(DetectedPlate);
CREATE INDEX IF NOT EXISTS idx_ocr_time ON OCRHistory(Timestamp);
CREATE INDEX IF NOT EXISTS idx_users_role ON Users(Role);
CREATE INDEX IF NOT EXISTS idx_events_type ON Events(EventType);
CREATE INDEX IF NOT EXISTS idx_events_time ON Events(EventTime);
"""

# ─────────────────────────────────────────────────────────────────
# DEFAULT PRICING DATA
# ─────────────────────────────────────────────────────────────────

DEFAULT_PRICING = [
    # Motorbike
    {'vehicle_type': 'motorbike', 'pricing_type': 'non_combo', 'hourly': 5000, 'monthly': None},
    {'vehicle_type': 'motorbike', 'pricing_type': 'combo', 'hourly': None, 'monthly': 150000},
    # Car (only 2 types: car and motorbike)
    {'vehicle_type': 'car', 'pricing_type': 'non_combo', 'hourly': 15000, 'monthly': None},
    {'vehicle_type': 'car', 'pricing_type': 'combo', 'hourly': None, 'monthly': 900000},
]

# ─────────────────────────────────────────────────────────────────
# SLOT CONFIGURATION — chỉ 2 zone: A (Ô tô) và B (Xe máy)
# ─────────────────────────────────────────────────────────────────

DEFAULT_SLOTS = {
    'A': 20,  # Zone A: 20 chỗ (Ô tô)
    'B': 40,  # Zone B: 40 chỗ (Xe máy)
}


def init_schema(db_backend: str = 'sqlite', db_path: Optional[str] = None) -> None:
    """Khởi tạo schema database."""
    if db_backend == 'sqlite':
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'pcs.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute('PRAGMA foreign_keys=ON')
        for statement in SCHEMA_SQLITE.split(';'):
            if statement.strip():
                conn.execute(statement)
        conn.commit()
        conn.close()
        print(f"[DB] SQLite schema initialized: {db_path}")
    else:
        print("[DB] MySQL schema initialization requires manual execution.")
        print("[DB] SQL statements available in SCHEMA_SQL constant.")


if __name__ == '__main__':
    # Test: Khởi tạo SQLite
    init_schema('sqlite')
    print("[DB] Schema initialized successfully!")
