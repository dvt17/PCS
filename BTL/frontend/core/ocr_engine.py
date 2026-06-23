"""
ocr_engine.py — Nhận diện biển số (YOLOv8 + EasyOCR)
PCS Smart Parking System

Chạy thực tế: cài ultralytics + easyocr + opencv-python
Chế độ DEMO : mô phỏng kết quả mà không cần GPU/camera
"""



from __future__ import annotations

import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)


import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

# ── Cờ môi trường ────────────────────────────────────────────────────
DEMO_MODE = True   # đặt False khi có camera thực

try:
    import cv2
    import easyocr
    from ultralytics import YOLO
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

VN_PLATE_PATTERN = re.compile(r"^\d{2}[A-Z]{1,2}-\d{4,5}$")

DEMO_PLATES = [
    "51A-12345", "59B-67890", "43C-11111", "30D-22222",
    "51F-33333", "92G-44444", "62H-55555", "74K-66666",
    "51L-77777", "88M-88888", "20P-00001", "61R-34343",
]


@dataclass
class OCRResult:
    plate: str
    confidence: float          # 0.0 – 1.0
    raw_text: str              # văn bản thô trước khi chuẩn hoá
    bbox: Optional[Tuple] = None
    image_path: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def is_valid(self) -> bool:
        return bool(VN_PLATE_PATTERN.match(self.plate)) and self.confidence >= 0.70

    @property
    def needs_manual(self) -> bool:
        return not self.is_valid

    def __str__(self) -> str:
        status = "✓ HỢP LỆ" if self.is_valid else "⚠ CẦN NHẬP TAY"
        return f"[OCR] {self.plate} | conf={self.confidence:.0%} | {status}"


class PlateRecognizer:
    """
    Pipeline: Camera → YOLOv8 detect → crop → EasyOCR → chuẩn hoá biển số VN
    """

    def __init__(self, model_path: str = "models/yolov8_plate.pt", lang: str = "vi"):
        self.model_path = model_path
        self.lang = lang
        self._yolo = None
        self._ocr = None
        self._demo = DEMO_MODE or not DEPS_AVAILABLE

        if not self._demo:
            self._load_models()

    def _load_models(self) -> None:
        print("[OCR] Đang tải YOLOv8...")
        self._yolo = YOLO(self.model_path)
        print("[OCR] Đang tải EasyOCR...")
        self._ocr = easyocr.Reader(["vi", "en"], gpu=False)
        print("[OCR] Sẵn sàng.")

    # ── API chính ────────────────────────────────────────────────────
    def recognize_from_frame(self, frame) -> OCRResult:
        """Nhận frame từ camera (numpy array), trả về OCRResult"""
        if self._demo:
            return self._demo_result()
        return self._real_recognize(frame)

    def recognize_from_file(self, image_path: str) -> OCRResult:
        """Nhận diện từ file ảnh"""
        if self._demo:
            return self._demo_result(image_path=image_path)
        if not DEPS_AVAILABLE:
            return self._demo_result(image_path=image_path)
        frame = cv2.imread(image_path)
        if frame is None:
            return OCRResult(plate="", confidence=0.0, raw_text="", image_path=image_path)
        return self._real_recognize(frame, image_path=image_path)

    # ── Xử lý thực tế ────────────────────────────────────────────────
    def _real_recognize(self, frame, image_path: str = None) -> OCRResult:
        # Bước 1: YOLOv8 phát hiện vùng biển số
        results = self._yolo(frame, conf=0.5, verbose=False)
        if not results or not results[0].boxes:
            return OCRResult(plate="", confidence=0.0, raw_text="[Không phát hiện biển số]")

        box = results[0].boxes[0]
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        yolo_conf = float(box.conf[0])
        crop = frame[y1:y2, x1:x2]

        # Bước 2: EasyOCR đọc ký tự
        ocr_results = self._ocr.readtext(crop, detail=1)
        if not ocr_results:
            return OCRResult(plate="", confidence=yolo_conf * 0.5, raw_text="[OCR trống]", bbox=(x1,y1,x2,y2))

        raw = " ".join(r[1] for r in ocr_results)
        conf = yolo_conf * float(ocr_results[0][2])
        plate = self._normalize(raw)
        return OCRResult(plate=plate, confidence=conf, raw_text=raw, bbox=(x1,y1,x2,y2), image_path=image_path)

    # ── Demo mô phỏng ────────────────────────────────────────────────
    def _demo_result(self, image_path: str = None) -> OCRResult:
        time.sleep(0.3)   # giả lập độ trễ xử lý
        plate = random.choice(DEMO_PLATES)
        # Thỉnh thoảng mô phỏng OCR kém → cần nhập tay
        if random.random() < 0.08:
            raw = plate.replace("-", "").lower()
            conf = round(random.uniform(0.40, 0.68), 2)
        else:
            raw = plate
            conf = round(random.uniform(0.88, 0.99), 2)
        normalized = self._normalize(raw)
        return OCRResult(plate=normalized, confidence=conf, raw_text=raw, image_path=image_path)

    # ── Chuẩn hoá ────────────────────────────────────────────────────
    @staticmethod
    def _normalize(raw: str) -> str:
        """Chuyển văn bản thô → định dạng biển số VN: 51A-12345"""
        cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
        # Thử khớp 2 số + 1-2 chữ + 4-5 số
        m = re.match(r"(\d{2})([A-Z]{1,2})(\d{4,5})", cleaned)
        if m:
            return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
        return cleaned

    @staticmethod
    def manual_entry(plate_input: str) -> OCRResult:
        """Nhân viên nhập tay khi OCR thất bại"""
        plate = PlateRecognizer._normalize(plate_input)
        return OCRResult(plate=plate, confidence=1.0, raw_text=f"[MANUAL] {plate_input}")
