"""
payment.py — Cổng thanh toán (VNPAY / MoMo / ZaloPay / Tiền mặt)
PCS Smart Parking System

Tích hợp thực tế: thay _demo_request() bằng HTTP call đến API thực
"""



from __future__ import annotations

import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)


import hashlib
import random
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class GatewayType(Enum):
    CASH = "cash"
    VNPAY = "vnpay"
    MOMO = "momo"
    ZALOPAY = "zalopay"


@dataclass
class PaymentRequest:
    amount: int                    # VNĐ
    txn_ref: str                   # mã giao dịch PCS
    description: str
    gateway: GatewayType
    customer_phone: str = ""
    return_url: str = "https://pcs.local/payment/callback"


@dataclass
class PaymentResponse:
    success: bool
    gateway: GatewayType
    gateway_ref: str               # mã phía cổng TT
    amount: int
    message: str
    qr_code: Optional[str] = None  # URL QR (MoMo / ZaloPay)
    payment_url: Optional[str] = None  # redirect URL (VNPAY)


class PaymentGateway:
    """
    Lớp trừu tượng tích hợp cổng thanh toán.
    DEMO_MODE = True → mô phỏng thành công 95%, thất bại 5%
    """

    DEMO_MODE = True

    # ── API công khai ─────────────────────────────────────────────────
    def request_payment(self, req: PaymentRequest) -> PaymentResponse:
        if self.DEMO_MODE:
            return self._demo_request(req)
        method = getattr(self, f"_pay_{req.gateway.value}", None)
        if not method:
            raise NotImplementedError(f"Gateway {req.gateway.value} chưa tích hợp")
        return method(req)

    def verify_callback(self, gateway: GatewayType, params: dict) -> bool:
        """Xác minh chữ ký callback từ cổng thanh toán"""
        if self.DEMO_MODE:
            return True
        return getattr(self, f"_verify_{gateway.value}", lambda p: False)(params)

    # ── Demo ─────────────────────────────────────────────────────────
    def _demo_request(self, req: PaymentRequest) -> PaymentResponse:
        time.sleep(0.5)   # giả lập độ trễ mạng
        success = random.random() > 0.05
        gw_ref = uuid.uuid4().hex[:12].upper()
        qr = f"https://qr.demo/{req.gateway.value}/{gw_ref}" if req.gateway != GatewayType.CASH else None
        return PaymentResponse(
            success=success,
            gateway=req.gateway,
            gateway_ref=gw_ref,
            amount=req.amount,
            message="Thanh toán thành công" if success else "Giao dịch thất bại — thử lại",
            qr_code=qr,
        )

    # ── VNPAY (stub) ──────────────────────────────────────────────────
    def _pay_vnpay(self, req: PaymentRequest) -> PaymentResponse:
        # Tài liệu: https://sandbox.vnpayment.vn/apis/docs/
        SECRET = "YOUR_VNPAY_SECRET"
        params = {
            "vnp_Version": "2.1.0",
            "vnp_Command": "pay",
            "vnp_TmnCode": "YOUR_TMN_CODE",
            "vnp_Amount": str(req.amount * 100),
            "vnp_TxnRef": req.txn_ref,
            "vnp_OrderInfo": req.description,
            "vnp_ReturnUrl": req.return_url,
        }
        sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        sig = hashlib.sha512((SECRET + sorted_params).encode()).hexdigest()
        params["vnp_SecureHash"] = sig
        url = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?" + "&".join(f"{k}={v}" for k, v in params.items())
        return PaymentResponse(
            success=True, gateway=GatewayType.VNPAY,
            gateway_ref=req.txn_ref, amount=req.amount,
            message="Đang chuyển hướng đến VNPAY", payment_url=url
        )

    # ── MoMo (stub) ───────────────────────────────────────────────────
    def _pay_momo(self, req: PaymentRequest) -> PaymentResponse:
        # Tài liệu: https://developers.momo.vn/
        import json, hmac
        PARTNER_CODE = "YOUR_PARTNER_CODE"
        ACCESS_KEY = "YOUR_ACCESS_KEY"
        SECRET_KEY = "YOUR_SECRET_KEY"
        request_id = uuid.uuid4().hex
        raw = f"accessKey={ACCESS_KEY}&amount={req.amount}&orderId={req.txn_ref}&orderInfo={req.description}&partnerCode={PARTNER_CODE}&redirectUrl={req.return_url}&requestId={request_id}&requestType=captureWallet"
        sig = hmac.new(SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()
        # POST đến https://test-payment.momo.vn/v2/gateway/api/create
        return PaymentResponse(
            success=True, gateway=GatewayType.MOMO,
            gateway_ref=request_id, amount=req.amount,
            message="QR MoMo đã tạo", qr_code=f"https://test-payment.momo.vn/qr/{request_id}"
        )

    # ── Cash ──────────────────────────────────────────────────────────
    @staticmethod
    def cash_payment(amount: int, received: int) -> dict:
        change = received - amount
        if change < 0:
            return {"success": False, "message": f"Thiếu {abs(change):,}đ"}
        return {"success": True, "change": change, "message": f"Tiền thừa: {change:,}đ"}
