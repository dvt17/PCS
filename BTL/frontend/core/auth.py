"""
auth.py — Xác thực & phân quyền (Admin / Nhân viên / Chủ xe)
PCS Smart Parking System
"""



from __future__ import annotations

import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)


import hashlib
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.database import create_user, get_user_by_username, init_db


class Role(Enum):
    ADMIN = "admin"
    STAFF = "staff"
    OWNER = "owner"


@dataclass
class User:
    user_id: str
    username: str
    role: Role
    full_name: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_staff(self) -> bool:
        return self.role in (Role.ADMIN, Role.STAFF)

    def can(self, action: str) -> bool:
        permissions = {
            Role.ADMIN:  {"config_lot", "manage_slots", "view_reports", "checkin", "checkout", "manage_users"},
            Role.STAFF:  {"checkin", "checkout", "view_status"},
            Role.OWNER:  {"view_status", "view_own_history"},
        }
        return action in permissions.get(self.role, set())


class AuthManager:
    _current_user: Optional[User] = None

    @staticmethod
    def _hash(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    # ── Đăng ký ───────────────────────────────────────────────────────
    @classmethod
    def register(cls, username: str, password: str, role: Role, full_name: str = "") -> User:
        user_id = uuid.uuid4().hex[:8].upper()
        create_user(user_id, username, cls._hash(password), role.value, full_name)
        return User(user_id=user_id, username=username, role=role, full_name=full_name)

    # ── Đăng nhập ─────────────────────────────────────────────────────
    @classmethod
    def login(cls, username: str, password: str) -> Optional[User]:
        row = get_user_by_username(username)
        if not row:
            return None
        if row["password_hash"] != cls._hash(password):
            return None
        user = User(
            user_id=row["user_id"],
            username=row["username"],
            role=Role(row["role"]),
            full_name=row.get("full_name", ""),
        )
        cls._current_user = user
        return user

    @classmethod
    def logout(cls) -> None:
        cls._current_user = None

    @classmethod
    def current_user(cls) -> Optional[User]:
        return cls._current_user

    @classmethod
    def require(cls, action: str) -> User:
        u = cls._current_user
        if not u:
            raise PermissionError("Chưa đăng nhập")
        if not u.can(action):
            raise PermissionError(f"Tài khoản '{u.username}' không có quyền: {action}")
        return u


def seed_default_users() -> None:
    """Tạo tài khoản mặc định nếu chưa có"""
    defaults = [
        ("admin", "admin123", Role.ADMIN, "Quản trị viên"),
        ("staff1", "staff123", Role.STAFF, "Nhân viên 1"),
    ]
    for username, password, role, name in defaults:
        try:
            AuthManager.register(username, password, role, name)
            print(f"[Auth] Tạo tài khoản: {username} / {role.value}")
        except Exception:
            pass   # đã tồn tại
