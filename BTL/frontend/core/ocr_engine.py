"""
ocr_engine.py — Nhận diện biển số (YOLOv26n + character_detector.pt + EasyOCR)
PCS Smart Parking System
Chỉ còn 2 loại xe: Ô tô và Xe máy

Pipeline v3 (Dual-model):
  Frame → yolo26s.pt (vehicle detection + plate detection) →
    ├─ Vehicle type (car / motorbike from YOLO class)
    └─ Plate region crop →
        character_detector.pt (character-level detection) [PRIMARY]
        └─ Fallback: EasyOCR multi-strategy [SECONDARY]
          → Normalize → Validate → OCRResult

character_detector.pt: YOLO model fine-tuned on Vietnamese plate characters
  - Detects individual characters (0-9, A-Z) in plate region
  - Returns bbox + class per character
  - Sorted left-to-right (top-to-bottom for 2-line plates) → plate string
"""

from __future__ import annotations

import base64
import sys as _sys, os as _os
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
PROJECT_ROOT = _os.path.dirname(_ROOT)
# ── Model paths: gắn trực tiếp vào source ──
DEFAULT_YOLO_MODEL = _os.getenv("PCS_YOLO_MODEL", r"D:\UTH\BaiHoc\ITS\PCS\BTL\best.pt")
CHARACTER_DETECTOR_MODEL = _os.getenv("PCS_CHAR_MODEL", r"D:\UTH\BaiHoc\ITS\PCS\BTL\character_detector.pt")
if _ROOT not in _sys.path: _sys.path.insert(0, _ROOT)


import random
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

# ── Cờ môi trường ────────────────────────────────────────────────────
DEMO_MODE = False   # chuyển sang False khi có camera thực và package đã cài

try:
    import cv2
    import easyocr
    import numpy as np
    from ultralytics import YOLO
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ── Mã tỉnh Việt Nam (63 tỉnh thành) ─────────────────────────────────
VN_PROVINCE_CODES = {
    "11", "12", "14", "15", "16", "17", "18", "19",
    "20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
    "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "43", "44", "45", "46", "47", "48", "49",
    "50", "51", "52", "53", "54", "55", "56", "57", "58", "59",
    "60", "61", "62", "63", "64", "65", "66", "67", "68", "69",
    "70", "71", "72", "73", "74", "75", "76", "77", "78", "79",
    "80", "81", "82", "83", "84", "85", "86", "87", "88", "89",
    "90", "91", "92", "93", "94", "95", "96", "97", "98", "99",
}

VN_PLATE_PATTERN = re.compile(
    r"^\d{2}[A-Z]{1,2}[.-]?\d{4,5}$"
)
VN_PLATE_NO_SEP = re.compile(r"^(\d{2})([A-Z]{1,2})(\d{4,5})$")

DEMO_PLATES = [
    "51A-12345", "59B-67890", "43C-11111", "30D-22222",
    "51F-33333", "92G-44444", "62H-55555", "74K-66666",
    "51L-77777", "88M-88888", "20P-00001", "61R-34343",
]


@dataclass
class OCRResult:
    plate: str
    confidence: float
    raw_text: str
    bbox: Optional[Tuple] = None          # plate bounding box (x1, y1, x2, y2)
    vehicle_bbox: Optional[Tuple] = None  # vehicle bounding box (x1, y1, x2, y2)
    image_path: Optional[str] = None
    annotated_path: Optional[str] = None
    timestamp: datetime = None
    vehicle_type: str = "unknown"         # loại xe từ YOLO class
    vehicle_label: str = ""               # tên hiển thị (VD: "🚗 Ô tô", "🏍️ Xe máy")
    char_bboxes: Optional[list] = None    # list of {char, conf, x1, y1, x2, y2} for each detected character

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def is_valid(self) -> bool:
        if not self.plate:
            return False
        clean = self.plate.replace(".", "")
        return bool(VN_PLATE_PATTERN.match(clean)) and self.confidence >= 0.65

    @property
    def needs_manual(self) -> bool:
        return not self.is_valid

    def __str__(self) -> str:
        status = "✓ HỢP LỆ" if self.is_valid else "⚠ CẦN NHẬP TAY"
        return f"[OCR] {self.plate} | conf={self.confidence:.0%} | type={self.vehicle_type} | {status}"


class PlateRecognizer:
    """
    Pipeline v3 (Dual-model + EasyOCR fallback):
      Frame → best.pt (vehicle + plate detection) →
        character_detector.pt (character-level plate reading) [PRIMARY]
        └→ EasyOCR multi-strategy [FALLBACK] →
          Normalize → Validate → OCRResult
    """

    def __init__(
        self,
        model_path: str = DEFAULT_YOLO_MODEL,
        char_model_path: str = CHARACTER_DETECTOR_MODEL,
        lang: str = "en",
    ):
        self.model_path = model_path
        self.char_model_path = char_model_path
        self.lang = lang
        self._yolo = None
        self._char_detector = None
        self._ocr = None
        self._demo = DEMO_MODE or not DEPS_AVAILABLE

        if not self._demo:
            self._load_models()

    def _load_models(self) -> None:
        """Load cả 3 model: yolo26s.pt, character_detector.pt, EasyOCR."""
        print(f"[OCR] Đang tải YOLO từ {self.model_path}...")
        if not _os.path.exists(self.model_path):
            raise FileNotFoundError(f"YOLO model not found: {self.model_path}")
        self._yolo = YOLO(self.model_path)
        print(f"[OCR] YOLO classes: {self._yolo.names}")

        if _os.path.exists(self.char_model_path):
            print(f"[OCR] Đang tải Character Detector từ {self.char_model_path}...")
            self._char_detector = YOLO(self.char_model_path)
            print(f"[OCR] Character Detector classes: {self._char_detector.names}")
        else:
            print(f"[OCR] KHÔNG tìm thấy {self.char_model_path} — chỉ dùng EasyOCR")

        print("[OCR] Đang tải EasyOCR (lang=en)...")
        self._ocr = easyocr.Reader([self.lang], gpu=False)
        print("[OCR] Sẵn sàng.")

    # ── API chính ────────────────────────────────────────────────────
    def recognize_from_frame(self, frame, image_path: str = None) -> OCRResult:
        if self._demo:
            return self._demo_result(image_path=image_path)
        result = self._real_recognize(frame, image_path=image_path)
        # Always annotate to show detection results visually
        if image_path is not None:
            annotated = self._annotate_image(frame, result)
            if annotated:
                result.annotated_path = annotated
        return result

    def recognize_from_file(self, image_path: str) -> OCRResult:
        if self._demo:
            return self._demo_result(image_path=image_path)
        if not DEPS_AVAILABLE:
            return self._demo_result(image_path=image_path)
        frame = cv2.imread(image_path)
        if frame is None:
            return OCRResult(plate="", confidence=0.0, raw_text="", image_path=image_path)

        result = self._real_recognize(frame, image_path=image_path)
        # Always annotate to show detection results visually
        annotated = self._annotate_image(frame, result)
        if annotated:
            result.annotated_path = annotated
        return result

    def analyze_frame(self, frame, image_path: str = None, yolo_class_name: str = None) -> dict:
        result = self.recognize_from_frame(frame, image_path=image_path)
        vehicle_type = result.vehicle_type or self._infer_vehicle_type(
            image_path, result.plate, result.bbox, yolo_class_name
        )
        annotated_b64 = None
        if result.annotated_path and _os.path.exists(result.annotated_path):
            try:
                with open(result.annotated_path, "rb") as f:
                    annotated_b64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
        # Chuyển char_bboxes thành dạng list để JSON serializable
        char_boxes = None
        if result.char_bboxes:
            char_boxes = [{
                "char": c["char"],
                "conf": c["confidence"],
                "x1": c["x1"], "y1": c["y1"],
                "x2": c["x2"], "y2": c["y2"],
            } for c in result.char_bboxes]

        return {
            "plate": result.plate,
            "confidence": round(result.confidence, 2),
            "valid": result.is_valid,
            "vehicle_type": vehicle_type,
            "message": "Đã nhận diện biển số từ camera" if result.is_valid else "Không nhận diện được biển số, vui lòng nhập tay",
            "image_path": result.image_path,
            "annotated_path": result.annotated_path,
            "annotated_b64": annotated_b64,
            "bbox": list(result.bbox) if result.bbox else None,
            "char_bboxes": char_boxes,
        }

    def analyze_image_file(self, image_path: str) -> dict:
        result = self.recognize_from_file(image_path)
        vehicle_type = result.vehicle_type or self._infer_vehicle_type(image_path, result.plate)
        annotated_b64 = None
        if result.annotated_path and _os.path.exists(result.annotated_path):
            try:
                with open(result.annotated_path, "rb") as f:
                    annotated_b64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
        # Chuyển char_bboxes thành dạng list để JSON serializable
        char_boxes = None
        if result.char_bboxes:
            char_boxes = [{
                "char": c["char"],
                "conf": c["confidence"],
                "x1": c["x1"], "y1": c["y1"],
                "x2": c["x2"], "y2": c["y2"],
            } for c in result.char_bboxes]

        return {
            "plate": result.plate,
            "confidence": round(result.confidence, 2),
            "valid": result.is_valid,
            "vehicle_type": vehicle_type,
            "message": "Đã nhận diện biển số từ ảnh" if result.is_valid else "Không nhận diện được biển số, vui lòng nhập tay",
            "image_path": result.image_path,
            "annotated_path": result.annotated_path,
            "annotated_b64": annotated_b64,
            "bbox": list(result.bbox) if result.bbox else None,
            "char_bboxes": char_boxes,
        }

    @staticmethod
    def _infer_vehicle_type(image_path: str, plate: str, bbox: tuple = None, yolo_class_name: str = None) -> str:
        """Map YOLO class to 2-type system: car or motorbike"""
        if yolo_class_name:
            name_lower = yolo_class_name.lower()
            if any(kw in name_lower for kw in ('motorbike', 'motorcycle', 'xemay', 'xe_may', 'bike', 'xe máy')):
                return "motorbike"
            # Everything else is a car
            return "car"

        if image_path and bbox:
            x1, y1, x2, y2 = bbox
            bw = x2 - x1
            bh = y2 - y1
            area = bw * bh
            ratio = bh / max(bw, 1)
            if ratio > 0.30 and area > 5000:
                return "car"
            elif ratio <= 0.30 and area > 1000:
                return "motorbike"

        if not plate:
            return "car"
        plate_clean = plate.replace('-', '').upper()
        if len(plate_clean) >= 8:
            m = re.match(r"\d{2}[A-Z]{1,2}\d{5}", plate_clean)
            if m:
                return "car"
            return "motorbike"
        else:
            return "motorbike"

    # ── Pipeline v3 ─────────────────────────────────────────────────
    def _real_recognize(self, frame, image_path: str = None) -> OCRResult:
        """
        Pipeline v3:
          1. Tiền xử lý ảnh tối
          2. yolo26s.pt → vehicle type + plate bbox
          3. character_detector.pt [PRIMARY] → đọc ký tự
          4. EasyOCR multi-strategy [FALLBACK]
          5. Chuẩn hoá + position-aware correction
          6. Map vehicle type từ YOLO class (car / motorbike)
        """
        processed_frame = self._enhance_low_light(frame)
        yolo_results = self._yolo(processed_frame, conf=0.5, verbose=False)

        plate_bbox = None
        vehicle_type_yolo = None
        vehicle_bbox = None
        yolo_plate_conf = 0.0

        if yolo_results and yolo_results[0].boxes:
            boxes = yolo_results[0].boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_id = int(box.cls[0])
                cls_name = self._yolo.names[cls_id].lower()
                conf = float(box.conf[0])

                if any(kw in cls_name for kw in ('plate', 'license', 'bienso', 'bien_so', 'bien')):
                    plate_bbox = (x1, y1, x2, y2)
                    yolo_plate_conf = conf
                elif any(kw in cls_name for kw in ('char', 'letter', 'digit', 'ky_tu', 'kytu')):
                    # Character-level detection comes from char_detector, not main YOLO
                    pass
                elif any(kw in cls_name for kw in (
                    'car', 'oto', 'xe_con', 'xecon', 'sedan', 'suv',
                    'motorbike', 'motorcycle', 'xemay', 'xe_may', 'bike',
                    'truck', 'bus', 'van', 'xe_tai', 'xe_buyt',
                )):
                    vehicle_type_yolo = cls_name
                    vehicle_bbox = (x1, y1, x2, y2)
                elif plate_bbox is None:
                    plate_bbox = (x1, y1, x2, y2)
                    yolo_plate_conf = conf

        # Fallback: không tìm thấy biển → dùng vùng dưới xe
        if plate_bbox is None and vehicle_bbox is not None:
            vx1, vy1, vx2, vy2 = vehicle_bbox
            vh = vy2 - vy1
            search_y1 = vy2 - int(vh * 0.4)
            search_y1 = max(vy1, search_y1)
            search_crop = processed_frame[search_y1:vy2, vx1:vx2]
            if search_crop.size > 0 and search_crop.shape[0] > 5:
                if self._char_detector is not None:
                    char_result = self._read_plate_with_char_detector(search_crop)
                    if char_result and char_result["text"]:
                        plate_bbox = (vx1, search_y1, vx2, vy2)

        if plate_bbox is None and yolo_results and yolo_results[0].boxes:
            box = yolo_results[0].boxes[0]
            plate_bbox = tuple(map(int, box.xyxy[0].tolist()))

        # Đọc biển số
        best_plate = ""
        best_conf = 0.0
        best_raw = ""
        used_method = "none"
        best_char_bboxes = None  # lưu bbox từng ký tự

        if plate_bbox is not None:
            x1, y1, x2, y2 = plate_bbox
            crop = processed_frame[y1:y2, x1:x2]

            if crop.size > 0 and crop.shape[0] > 10 and crop.shape[1] > 10:
                # PRIORITY 1: character_detector.pt
                if self._char_detector is not None:
                    char_result = self._read_plate_with_char_detector(crop)
                    if char_result and char_result["text"]:
                        raw = char_result["text"]
                        conf_char = char_result["confidence"]
                        combined_conf = conf_char * max(yolo_plate_conf, 0.7)
                        plate = self._normalize(raw)
                        if plate and combined_conf > best_conf:
                            best_plate = plate
                            best_conf = combined_conf
                            best_raw = raw
                            used_method = "char_detector"
                            # Chuyển char_bboxes từ crop coordinates sang frame coordinates
                            if char_result.get("char_details"):
                                best_char_bboxes = []
                                for cd in char_result["char_details"]:
                                    best_char_bboxes.append({
                                        "char": cd["char"],
                                        "confidence": round(cd["confidence"], 2),
                                        "x1": x1 + cd["x"],
                                        "y1": y1 + cd["y"],
                                        "x2": x1 + cd["x"] + cd["w"],
                                        "y2": y1 + cd["y"] + cd["h"],
                                    })

                # PRIORITY 2: EasyOCR multi-strategy (không có char_bboxes từ EasyOCR, chỉ có raw text)
                if best_conf < 0.5 or not best_plate:
                    strategies = self._preprocess_plate_strategies(crop)
                    for strategy_name, plate_img in strategies:
                        for ocr_threshold in (0.5, 0.3):
                            ocr_results = self._ocr.readtext(plate_img, detail=1)
                            if ocr_results:
                                good_results = [r for r in ocr_results if r[2] >= ocr_threshold]
                                if good_results:
                                    raw = " ".join(r[1] for r in good_results)
                                    conf_ocr = sum(r[2] for r in good_results) / len(good_results)
                                    conf = yolo_plate_conf * conf_ocr * 0.9
                                    plate = self._normalize(raw)
                                    if plate and conf > best_conf:
                                        best_plate = plate
                                        best_conf = conf
                                        best_raw = raw
                                        used_method = f"easyocr_{strategy_name}"
                                        # EasyOCR trả về poly points, chuyển sang bbox
                                        if good_results[0][0]:
                                            best_char_bboxes = []
                                            for det in good_results:
                                                pts = det[0]
                                                ch = det[1]
                                                if len(pts) >= 4:
                                                    xs = [p[0] for p in pts]
                                                    ys = [p[1] for p in pts]
                                                    cx = x1 + int(min(xs))
                                                    cy = y1 + int(min(ys))
                                                    cw = x1 + int(max(xs)) - cx
                                                    ch_h = y1 + int(max(ys)) - cy
                                                    best_char_bboxes.append({
                                                        "char": ch,
                                                        "confidence": round(float(det[2]), 2),
                                                        "x1": cx,
                                                        "y1": cy,
                                                        "x2": cx + cw,
                                                        "y2": cy + ch_h,
                                                    })

        # Fallback: OCR toàn ảnh
        if not best_plate or best_conf < 0.35:
            full_results = self._ocr.readtext(processed_frame, detail=1)
            if full_results:
                good_full = [r for r in full_results if r[2] >= 0.4]
                if good_full:
                    raw = " ".join(r[1] for r in good_full)
                    conf = float(good_full[0][2]) * 0.5
                    plate = self._normalize(raw)
                    if plate and conf > best_conf:
                        best_plate = plate
                        best_conf = conf
                        best_raw = raw
                        used_method = "easyocr_full_frame"
                        # Lấy char_bboxes từ full frame OCR
                        best_char_bboxes = []
                        for det in good_full:
                            pts = det[0]
                            ch = det[1]
                            if len(pts) >= 4:
                                xs = [p[0] for p in pts]
                                ys = [p[1] for p in pts]
                                best_char_bboxes.append({
                                    "char": ch,
                                    "confidence": round(float(det[2]), 2),
                                    "x1": int(min(xs)),
                                    "y1": int(min(ys)),
                                    "x2": int(max(xs)),
                                    "y2": int(max(ys)),
                                })

        # Map vehicle type — ONLY 2 TYPES: car or motorbike
        vt_mapped = "unknown"
        vl_mapped = ""
        if vehicle_type_yolo:
            vn_lower = vehicle_type_yolo.lower()
            if any(kw in vn_lower for kw in ('motorbike', 'motorcycle', 'xemay', 'bike')):
                vt_mapped = "motorbike"
                vl_mapped = "🏍️ Xe máy"
            else:
                # car, oto, sedan, suv, truck, bus, van — all → car
                vt_mapped = "car"
                vl_mapped = "🚗 Ô tô"

        print(f"[OCR] method={used_method} plate={best_plate} conf={best_conf:.2%} "
              f"vt_yolo={vehicle_type_yolo} vt_mapped={vt_mapped} "
              f"bbox={plate_bbox} vehicle_bbox={vehicle_bbox}")
        if best_char_bboxes:
            print(f"[OCR] char_bboxes={len(best_char_bboxes)} chars: {''.join(c['char'] for c in best_char_bboxes) if best_char_bboxes else 'none'}")

        if best_plate and best_conf >= 0.35:
            return OCRResult(
                plate=best_plate, confidence=best_conf, raw_text=best_raw,
                bbox=plate_bbox, vehicle_bbox=vehicle_bbox,
                image_path=image_path, vehicle_type=vt_mapped,
                vehicle_label=vl_mapped, char_bboxes=best_char_bboxes,
            )

        return OCRResult(
            plate="", confidence=0.0, raw_text="[Không phát hiện biển số]",
            image_path=image_path, bbox=plate_bbox,
            vehicle_bbox=vehicle_bbox, vehicle_type=vt_mapped,
            vehicle_label=vl_mapped,
            char_bboxes=best_char_bboxes,
        )

    # ── Character Detector ───────────────────────────────────────────
    def _read_plate_with_char_detector(self, plate_region: np.ndarray) -> Optional[dict]:
        """Sử dụng character_detector.pt để phát hiện từng ký tự trên vùng biển số."""
        if self._char_detector is None or plate_region is None or plate_region.size == 0:
            return None

        char_classes = self._char_detector.names

        try:
            processed = self._preprocess_plate_for_char_detector(plate_region)
            results = self._char_detector(processed, conf=0.25, verbose=False)

            if not results or not results[0].boxes:
                return None

            VALID_CHAR_CLASS_IDS = set(range(31))
            chars = []
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                if cls_id not in VALID_CHAR_CLASS_IDS:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                char_label = char_classes.get(cls_id, "")
                if len(char_label) != 1:
                    continue
                if conf >= 0.3 and char_label:
                    chars.append({
                        "char": char_label.upper(),
                        "confidence": conf,
                        "x": x1, "y": y1,
                        "cx": (x1 + x2) / 2.0,
                        "cy": (y1 + y2) / 2.0,
                        "w": x2 - x1,
                        "h": y2 - y1,
                    })

            if len(chars) < 3:
                return None

            chars.sort(key=lambda c: c["y"])
            y_center = [c["cy"] for c in chars]
            y_spread = max(y_center) - min(y_center)
            avg_char_h = sum(c["h"] for c in chars) / len(chars)

            if y_spread > avg_char_h * 1.5 and len(chars) >= 6:
                y_mid = (max(y_center) + min(y_center)) / 2.0
                line1 = sorted([c for c in chars if c["cy"] < y_mid], key=lambda c: c["cx"])
                line2 = sorted([c for c in chars if c["cy"] >= y_mid], key=lambda c: c["cx"])
                text = "".join(c["char"] for c in line1) + "".join(c["char"] for c in line2)
            else:
                chars.sort(key=lambda c: c["cx"])
                text = "".join(c["char"] for c in chars)

            confidences = [c["confidence"] for c in chars]
            avg_conf = sum(confidences) / len(confidences)
            text_clean = re.sub(r"[^A-Z0-9]", "", text.upper())

            if len(text_clean) < 5:
                return None

            return {"text": text_clean, "confidence": avg_conf, "char_count": len(chars), "char_details": chars}

        except Exception as e:
            print(f"[OCR] character_detector error: {e}")
            return None

    @staticmethod
    def _preprocess_plate_for_char_detector(plate_region: np.ndarray) -> np.ndarray:
        """Tiền xử lý vùng biển số cho character_detector.pt."""
        if plate_region is None or plate_region.size == 0:
            return plate_region
        try:
            img = plate_region.copy()
            h, w = img.shape[:2]
            if w < 100 or h < 30:
                scale = max(2.0, 160.0 / max(w, 1))
                img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
            elif w > 800:
                scale = 640.0 / w
                img = cv2.resize(img, (640, int(h * scale)), interpolation=cv2.INTER_AREA)
            if len(img.shape) == 3:
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                hsv[:, :, 2] = clahe.apply(hsv[:, :, 2])
                img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            return img
        except Exception:
            return plate_region

    # ── Tiền xử lý ảnh ───────────────────────────────────────────────
    @staticmethod
    def _enhance_low_light(img) -> np.ndarray:
        if img is None or img.size == 0:
            return img
        try:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mean_brightness = np.mean(hsv[:, :, 2])
            if mean_brightness < 120:
                gamma = max(0.3, min(mean_brightness / 180.0, 0.8))
                inv_gamma = 1.0 / gamma
                table = np.array([(i / 255.0) ** inv_gamma * 255 for i in range(256)]).astype("uint8")
                img = cv2.LUT(img, table)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            clip_limit = 4.0 if mean_brightness < 80 else 3.0
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
            hsv[:, :, 2] = clahe.apply(hsv[:, :, 2])
            img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            if mean_brightness < 60:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                clahe2 = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(4, 4))
                enhanced_gray = clahe2.apply(gray)
                img = cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR)
        except Exception:
            pass
        return img

    @staticmethod
    def _deskew(plate_region: np.ndarray) -> np.ndarray:
        if plate_region is None or plate_region.size == 0:
            return plate_region
        try:
            gray = cv2.cvtColor(plate_region, cv2.COLOR_BGR2GRAY) if len(plate_region.shape) == 3 else plate_region.copy()
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU + cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                all_points = np.concatenate(contours)
                rect = cv2.minAreaRect(all_points)
                angle = rect[2]
                if angle < -45:
                    angle = 90 + angle
                if abs(angle) > 3:
                    h, w = plate_region.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    cos = abs(M[0, 0])
                    sin = abs(M[0, 1])
                    new_w = int(h * sin + w * cos)
                    new_h = int(h * cos + w * sin)
                    M[0, 2] += new_w / 2 - center[0]
                    M[1, 2] += new_h / 2 - center[1]
                    return cv2.warpAffine(plate_region, M, (new_w, new_h), flags=cv2.INTER_CUBIC)
        except Exception:
            pass
        return plate_region

    @classmethod
    def _preprocess_plate_strategies(cls, plate_region: np.ndarray) -> list:
        """Tạo nhiều phiên bản tiền xử lý khác nhau cho EasyOCR."""
        strategies = []
        if plate_region is None or plate_region.size == 0:
            return strategies

        try:
            if len(plate_region.shape) == 3:
                gray = cv2.cvtColor(plate_region, cv2.COLOR_BGR2GRAY)
            else:
                gray = plate_region.copy()

            deskewed_rgb = cls._deskew(plate_region)
            if len(deskewed_rgb.shape) == 3:
                gray_deskewed = cv2.cvtColor(deskewed_rgb, cv2.COLOR_BGR2GRAY)
            else:
                gray_deskewed = deskewed_rgb.copy()
                deskewed_rgb = cv2.cvtColor(deskewed_rgb, cv2.COLOR_GRAY2BGR) if len(deskewed_rgb.shape) == 2 else deskewed_rgb

            h, w = gray_deskewed.shape
            if w < 160 or h < 40:
                scale = max(2.0, 240.0 / max(w, 1))
                gray_deskewed = cv2.resize(gray_deskewed, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
                deskewed_rgb = cv2.resize(deskewed_rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

            clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray_deskewed)
            denoised = cv2.bilateralFilter(enhanced, 7, 25, 25)
            kernel_sharp = np.array([[0, -0.5, 0], [-0.5, 3, -0.5], [0, -0.5, 0]])
            sharpened = cv2.filter2D(denoised, -1, kernel_sharp)
            strategies.append(("clahe_bilateral_sharpen", sharpened))

            binary = cv2.adaptiveThreshold(gray_deskewed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 2)
            strategies.append(("adaptive_threshold", cv2.medianBlur(binary, 3)))

            _, otsu = cv2.threshold(gray_deskewed, 0, 255, cv2.THRESH_OTSU)
            if np.mean(otsu) > 127:
                otsu = cv2.bitwise_not(otsu)
            strategies.append(("otsu", otsu))

            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            strategies.append(("morph_close", cv2.morphologyEx(sharpened.copy(), cv2.MORPH_CLOSE, kernel)))

            clahe_light = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            strategies.append(("gray_clahe_light", clahe_light.apply(gray_deskewed)))
            strategies.append(("rgb_deskewed", deskewed_rgb))
        except Exception:
            strategies.append(("original", plate_region))

        return strategies

    # ── Vẽ annotation ────────────────────────────────────────────────
    @staticmethod
    def _annotate_image(frame: np.ndarray, result: OCRResult) -> Optional[str]:
        if not result.image_path:
            return None
        try:
            img = frame.copy()
            h_img, w_img = img.shape[:2]
            font = cv2.FONT_HERSHEY_SIMPLEX

            # Status bar trên cùng: hiển thị thông tin phát hiện
            status_bg_color = (30, 30, 80)  # dark blue-gray for status bar
            status_text = f"PCS OCR | Biển: {result.plate or '???'} | Conf: {result.confidence:.0%}" if result.plate else "PCS OCR | Không phát hiện biển số"
            (st_w, st_h), _ = cv2.getTextSize(status_text, font, 0.7, 2)
            bar_h = st_h + 20
            cv2.rectangle(img, (0, 0), (w_img, bar_h), status_bg_color, -1)
            cv2.putText(img, status_text, (10, bar_h - 8), font, 0.7, (200, 200, 255), 2)

            # ── 1. Vẽ khung PHƯƠNG TIỆN ─────────────────────────────
            if result.vehicle_bbox is not None and result.vehicle_label:
                vx1, vy1, vx2, vy2 = result.vehicle_bbox
                vehicle_color = (255, 144, 30)
                cv2.rectangle(img, (vx1, vy1), (vx2, vy2), vehicle_color, 3)
                vlabel = result.vehicle_label
                (vw, vh), _ = cv2.getTextSize(vlabel, font, 0.7, 2)
                cv2.rectangle(img, (vx1, max(vy1 - vh - 10, 0)), (vx1 + vw + 14, vy1), vehicle_color, -1)
                cv2.putText(img, vlabel, (vx1 + 7, vy1 - 4), font, 0.7, (255, 255, 255), 2)

            # ── 2. Vẽ khung BIỂN SỐ + từng ký tự ─────────────────────
            if result.bbox is not None:
                x1, y1, x2, y2 = result.bbox
                plate_color = (46, 204, 113) if result.is_valid else (243, 156, 18)
                cv2.rectangle(img, (x1, y1), (x2, y2), plate_color, 4)

                # Label
                if result.plate:
                    label = result.plate
                    if result.confidence > 0:
                        label += f" ({result.confidence:.0%})"
                    (tw, th), _ = cv2.getTextSize(label, font, 1.0, 2)
                    cv2.rectangle(img, (x1, max(y1 - th - 12, 0)), (x1 + tw + 16, y1), plate_color, -1)
                    cv2.putText(img, label, (x1 + 8, y1 - 6), font, 1.0, (0, 0, 0), 2)

                    badge = "VALID" if result.is_valid else "LOW CONF"
                    (bw, bh), _ = cv2.getTextSize(badge, font, 0.6, 1)
                    badge_bg = (20, 80, 30) if result.is_valid else (80, 50, 20)
                    cv2.rectangle(img, (x1, y2 + 6), (x1 + bw + 12, y2 + bh + 12), badge_bg, -1)
                    cv2.putText(img, badge, (x1 + 6, y2 + bh + 4), font, 0.6, plate_color, 1)
                else:
                    cv2.putText(img, "NO PLATE", (x1 + 8, y1 - 8), font, 0.8, (243, 156, 18), 2)

            # ── 3. Vẽ KHUNG TỪNG KÝ TỰ trên biển số ────────────────
            if result.char_bboxes:
                for c in result.char_bboxes:
                    cx1, cy1, cx2, cy2 = c["x1"], c["y1"], c["x2"], c["y2"]
                    char = c["char"]
                    conf_char = c["confidence"]

                    # Vẽ khung từng ký tự (màu xanh cyan đậm)
                    char_color = (0, 255, 255)  # cyan
                    cv2.rectangle(img, (cx1, cy1), (cx2, cy2), char_color, 2)

                    # Vẽ label ký tự ngay phía trên bounding box của nó
                    char_label = f"{char}"
                    (cw, ch_t), _ = cv2.getTextSize(char_label, font, 0.5, 1)
                    clx1 = cx1
                    cly1 = max(cy1 - ch_t - 6, 0)
                    clx2 = cx1 + cw + 6
                    cly2 = cy1
                    cv2.rectangle(img, (clx1, cly1), (clx2, cly2), (0, 180, 255), -1)  # cam fill
                    cv2.putText(img, char_label, (cx1 + 3, cy1 - 2), font, 0.5, (0, 0, 0), 1)

            # No detection overlay at all — show message on image
            if not result.bbox and not result.vehicle_bbox and not result.char_bboxes:
                cv2.putText(img, "Khong phat hien bien so / phuong tien", (30, h_img // 2),
                            font, 0.9, (243, 156, 18), 2)

            name, ext = _os.path.splitext(result.image_path)
            annotated_path = f"{name}_annotated{ext}"
            cv2.imwrite(annotated_path, img)
            return annotated_path
        except Exception as e:
            print(f"[OCR] _annotate_image error: {e}")
            return None

    # ── Demo ─────────────────────────────────────────────────────────
    def _demo_result(self, image_path: str = None) -> OCRResult:
        time.sleep(0.3)
        plate = random.choice(DEMO_PLATES)
        if random.random() < 0.08:
            raw = plate.replace("-", "").lower()
            conf = round(random.uniform(0.40, 0.68), 2)
        else:
            raw = plate
            conf = round(random.uniform(0.88, 0.99), 2)
        normalized = self._normalize(raw)

        annotated_path = None
        bbox = None
        vehicle_bbox = None

        # Only 2 types: car and motorbike
        plate_to_vtype = {
            "51A-12345": ("car", "🚗 Ô tô"),
            "59B-67890": ("car", "🚗 Ô tô"),
            "43C-11111": ("car", "🚗 Ô tô"),
            "30D-22222": ("car", "🚗 Ô tô"),
            "51F-33333": ("motorbike", "🏍️ Xe máy"),
            "92G-44444": ("motorbike", "🏍️ Xe máy"),
            "62H-55555": ("car", "🚗 Ô tô"),
            "74K-66666": ("car", "🚗 Ô tô"),
            "51L-77777": ("car", "🚗 Ô tô"),
            "88M-88888": ("car", "🚗 Ô tô"),
            "20P-00001": ("motorbike", "🏍️ Xe máy"),
            "61R-34343": ("car", "🚗 Ô tô"),
        }
        vt_mapped, vl_mapped = plate_to_vtype.get(normalized, ("car", "🚗 Ô tô"))

        if image_path and _os.path.exists(image_path):
            try:
                if PIL_AVAILABLE:
                    img = Image.open(image_path).convert("RGB")
                    w, h = img.size
                    bw = int(w * 0.35)
                    bh = int(h * 0.12)
                    cx, cy = w // 2, h // 2
                    x1 = max(0, cx - bw // 2)
                    y1 = max(0, cy - bh // 2)
                    x2 = min(w, cx + bw // 2)
                    y2 = min(h, cy + bh // 2)
                    bbox = (x1, y1, x2, y2)

                    pad_w = int((x2 - x1) * 1.8)
                    pad_h = int((y2 - y1) * 3.0)
                    vx1 = max(0, x1 - pad_w)
                    vy1 = max(0, y1 - pad_h)
                    vx2 = min(w, x2 + pad_w)
                    vy2 = min(h, y2 + pad_h)
                    vehicle_bbox = (vx1, vy1, vx2, vy2)

                    draw = ImageDraw.Draw(img)
                    is_valid = normalized and bool(VN_PLATE_PATTERN.match(normalized)) and conf >= 0.70
                    plate_color_rgb = (46, 204, 113) if is_valid else (243, 156, 18)
                    vehicle_color_rgb = (30, 144, 255)

                    for i in range(3):
                        draw.rectangle([vx1 + i, vy1 + i, vx2 - i, vy2 - i], outline=vehicle_color_rgb)

                    vlabel = vl_mapped
                    font = None
                    font_size = max(16, int(h * 0.035))
                    try:
                        font = ImageFont.truetype("segoeui.ttf", font_size)
                    except Exception:
                        try:
                            font = ImageFont.truetype("arial.ttf", font_size)
                        except Exception:
                            pass
                    try:
                        bb = draw.textbbox((0, 0), vlabel, font=font) if font else draw.textbbox((0, 0), vlabel)
                        vtw = bb[2] - bb[0]
                        vth = bb[3] - bb[1]
                    except Exception:
                        vtw = len(vlabel) * font_size * 0.5
                        vth = font_size + 4
                    vpad = 6
                    vlx1 = vx1
                    vly1 = max(0, vy1 - vth - vpad * 2)
                    vlx2 = vx1 + vtw + vpad * 2
                    vly2 = vy1
                    draw.rectangle([vlx1, vly1, vlx2, vly2], fill=vehicle_color_rgb)
                    if font:
                        draw.text((vlx1 + vpad, vly1 + vpad), vlabel, fill=(255, 255, 255), font=font)
                    else:
                        draw.text((vlx1 + vpad, vly1 + vpad), vlabel, fill=(255, 255, 255))

                    for i in range(4):
                        draw.rectangle([x1 + i, y1 + i, x2 - i, y2 - i], outline=plate_color_rgb)

                    label = f"{normalized} ({conf:.0%})" if conf > 0 else normalized
                    try:
                        bb = draw.textbbox((0, 0), label, font=font) if font else draw.textbbox((0, 0), label)
                        tw = bb[2] - bb[0]
                        th = bb[3] - bb[1]
                    except Exception:
                        tw = len(label) * font_size * 0.6
                        th = font_size + 4
                    pad = 8
                    draw.rectangle([x1, max(0, y1 - th - pad * 2), x1 + tw + pad * 2, y1], fill=plate_color_rgb)
                    if font:
                        draw.text((x1 + pad, max(0, y1 - th - pad)), label, fill=(0, 0, 0), font=font)
                    else:
                        draw.text((x1 + pad, max(0, y1 - th - pad)), label, fill=(0, 0, 0))

                    badge = "VALID" if is_valid else "LOW CONF"
                    try:
                        bb = draw.textbbox((0, 0), badge, font=font) if font else draw.textbbox((0, 0), badge)
                        bw_t = bb[2] - bb[0]
                        bh_t = bb[3] - bb[1]
                    except Exception:
                        bw_t = len(badge) * 10
                        bh_t = 14
                    draw.rectangle([x1, y2 + 6, x1 + bw_t + 12, y2 + bh_t + 12], fill=(20, 80, 30) if is_valid else (80, 50, 20))
                    badge_font = None
                    try:
                        badge_font = ImageFont.truetype("segoeui.ttf", max(11, int(h * 0.025)))
                    except Exception:
                        pass
                    if badge_font:
                        draw.text((x1 + 6, y2 + 8), badge, fill=plate_color_rgb, font=badge_font)
                    else:
                        draw.text((x1 + 6, y2 + 8), badge, fill=plate_color_rgb)

                    name, ext = _os.path.splitext(image_path)
                    annotated_path = f"{name}_annotated{ext}"
                    img.save(annotated_path)
            except Exception:
                pass

        return OCRResult(
            plate=normalized, confidence=conf, raw_text=raw,
            image_path=image_path, annotated_path=annotated_path,
            bbox=bbox, vehicle_bbox=vehicle_bbox,
            vehicle_type=vt_mapped, vehicle_label=vl_mapped,
        )

    # ── Chuẩn hoá biển số VN (POSITION-AWARE) ────────────────────────
    DIGIT_TO_LETTER = {
        "0": "D", "8": "B", "5": "S", "1": "L",
        "4": "A", "6": "G", "9": "P", "2": "Z",
    }
    LETTER_TO_DIGIT = {
        "O": "0", "D": "0", "Q": "0",
        "I": "1", "L": "1", "T": "1",
        "S": "5", "B": "8", "G": "6",
        "A": "4", "Z": "2", "E": "3",
    }
    LETTER_TO_LETTER = {"O": "D"}
    VALID_LETTERS = set("ABCDEFGHKLMNPSTUVXYZ")

    @classmethod
    def _normalize(cls, raw: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
        if len(cleaned) < 7 or len(cleaned) > 9:
            return cleaned

        best_plate = ""
        for serial_len in (1, 2):
            num_len = len(cleaned) - 2 - serial_len
            if num_len < 4 or num_len > 5:
                continue
            plate = cls._apply_position_aware_correction(cleaned[:2], cleaned[2:2 + serial_len], cleaned[2 + serial_len:])
            if plate and len(plate) > len(best_plate):
                best_plate = plate

        return best_plate if best_plate else cleaned

    @classmethod
    def _apply_position_aware_correction(cls, province_raw: str, serial_raw: str, number_raw: str) -> str:
        province_fixed = []
        for ch in province_raw:
            if ch.isdigit():
                province_fixed.append(ch)
            elif ch.isalpha() and ch in cls.LETTER_TO_DIGIT:
                province_fixed.append(cls.LETTER_TO_DIGIT[ch])
            else:
                province_fixed.append(ch)
        province = "".join(province_fixed)
        if not province.isdigit() or len(province) != 2:
            return ""

        serial_fixed = []
        for ch in serial_raw:
            if ch.isalpha():
                serial_fixed.append(cls.LETTER_TO_LETTER.get(ch, ch))
            elif ch.isdigit() and ch in cls.DIGIT_TO_LETTER:
                serial_fixed.append(cls.DIGIT_TO_LETTER[ch])
            else:
                serial_fixed.append(ch)
        serial = "".join(serial_fixed)
        if not all(c in cls.VALID_LETTERS for c in serial):
            return ""

        number_fixed = []
        for ch in number_raw:
            if ch.isdigit():
                number_fixed.append(ch)
            elif ch.isalpha() and ch in cls.LETTER_TO_DIGIT:
                number_fixed.append(cls.LETTER_TO_DIGIT[ch])
            else:
                number_fixed.append(ch)
        number = "".join(number_fixed)
        if not number.isdigit() or len(number) < 4 or len(number) > 5:
            return ""

        plate = f"{province}{serial}-{number}"
        if re.fullmatch(r"\d{2}[A-Z]{1,2}-\d{4,5}", plate):
            return plate
        return ""

    @staticmethod
    def manual_entry(plate_input: str) -> OCRResult:
        plate = PlateRecognizer._normalize(plate_input)
        return OCRResult(plate=plate, confidence=1.0, raw_text=f"[MANUAL] {plate_input}")
