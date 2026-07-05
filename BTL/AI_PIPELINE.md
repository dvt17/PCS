# PCS Smart Parking — AI VISION PIPELINE (v3)

## 🎯 OVERVIEW

The AI Vision Pipeline processes incoming vehicle frames through a dual-model architecture:

1. **best.pt** (YOLO) → Vehicle detection + License plate detection (region)
2. **character_detector.pt** (YOLO fine-tuned on characters) → Character-level recognition [PRIMARY]
3. **EasyOCR** → Multi-strategy text extraction [FALLBACK]

Each module outputs confidence scores and intermediate results for fallback handling.

---

## 📐 PIPELINE ARCHITECTURE

```
Input Frame (any size)
        │
        ▼
┌─────────────────────────────────────────────────┐
│  MODEL 1: best.pt (YOLO)                       │
│  ──────────────────────────────────────────────│
│  Model: Ultralytics YOLO (fine-tuned)         │
│  Task: Vehicle + License Plate detection      │
│  Output:                                        │
│   - vehicle_bbox: [x1, y1, x2, y2]           │
│   - vehicle_type_yolo: "car" | "motorbike"    │
│   - plate_bbox: [x1, y1, x2, y2]             │
│   - yolo_plate_conf: 0.0-1.0                  │
│   - cropped_plate: plate_region_image         │
└─────────────────────────────────────────────────┘
        │
        ▼ (cropped_plate)
┌─────────────────────────────────────────────────┐
│  MODEL 2: character_detector.pt [PRIMARY]      │
│  ──────────────────────────────────────────────│
│  Model: YOLO fine-tuned on VN plate characters │
│  Task: Character-level detection (0-9, A-Z)   │
│  Output:                                        │
│   - char_bboxes: [{char, confidence, x,y,w,h}] │
│   - sorted left-to-right (top-to-bottom for   │
│     multi-line plates)                         │
│   - text: "51A12345"                          │
│   - confidence: avg(char_confidences)         │
└─────────────────────────────────────────────────┘
        │
        ▼ (fallback if confidence < 0.5)
┌─────────────────────────────────────────────────┐
│  MODEL 3: EasyOCR Multi-Strategy [FALLBACK]    │
│  ──────────────────────────────────────────────│
│  Strategies applied to plate region:           │
│   1. CLAHE + bilateral + sharpen              │
│   2. Adaptive threshold                       │
│   3. OTSU binary                              │
│   4. Morphological close                      │
│   5. Gray + CLAHE light                       │
│   6. RGB deskewed                             │
│  Output: raw_text + confidence last resort    │
│  Full-frame OCR if plate OCR fails            │
└─────────────────────────────────────────────────┘
        │
        ▼ (raw_text)
┌─────────────────────────────────────────────────┐
│  POST-PROCESSING: Normalization                 │
│  ──────────────────────────────────────────────│
│  - Position-aware correction:                  │
│    Province (2 digits) → Serial (1-2 letters)  │
│      → Number (4-5 digits)                     │
│  - Common OCR mistake mapping:                 │
│    O→0, l→1, I→1, Z→2, S→5, etc.             │
│  - Format: "51A12345" → "51A-12345"           │
│  - Validate: ^\d{2}[A-Z]{1,2}-\d{4,5}$        │
└─────────────────────────────────────────────────┘
        │
        ▼
Output OCRResult:
{
  plate: "51A-12345",
  confidence: 0.94,
  raw_text: "51A12345",
  bbox: [x1, y1, x2, y2],
  vehicle_bbox: [x1, y1, x2, y2],
  is_valid: true,
  vehicle_type: "car" | "motorbike",
  vehicle_label: "🚗 Ô tô" | "🏍️ Xe máy",
  char_bboxes: [{char, confidence, x1, y1, x2, y2}, ...]
}
```

---

## 🔍 MODULE SPECIFICATIONS

### Module 1: Vehicle + Plate Detection (best.pt)

```python
class PlateRecognizer:
    """
    Uses best.pt (YOLO) to detect both vehicles and license plates.
    Classes:
      - car, oto, sedan, suv, truck, bus, van → mapped to "car"
      - motorbike, motorcycle, xemay, bike → mapped to "motorbike"
      - plate, license, bienso → plate bbox
    """

    def __init__(self, model_path="best.pt", char_model_path="character_detector.pt"):
        self._yolo = YOLO(model_path)       # best.pt
        self._char_detector = YOLO(char_model_path)  # character_detector.pt
        self._ocr = easyocr.Reader(["en"])

    def _real_recognize(self, frame) -> OCRResult:
        """
        1. Run YOLO on frame → get vehicle_type + plate_bbox
        2. Crop plate region
        3. Run character_detector.pt [PRIMARY]
        4. Fallback: EasyOCR multi-strategy
        5. Normalize plate → Validate
        6. Map vehicle_type to car/motorbike
        """
```

### Module 2: Character Detector (character_detector.pt)

```python
def _read_plate_with_char_detector(self, plate_region) -> dict:
    """
    Uses character_detector.pt (YOLO fine-tuned on 31 classes: 0-9, A-Z).
    Steps:
      1. Preprocess plate (CLAHE + resize)
      2. Run YOLO inference (conf=0.25)
      3. Filter valid character classes (0-30)
      4. Sort left-to-right (top-to-bottom for 2-line plates)
      5. Return combined text + confidence

    Returns: {
      "text": "51A12345",
      "confidence": 0.92,
      "char_count": 8,
      "char_details": [{char, confidence, x, y, w, h}, ...]
    }
    """
```

### Module 3: EasyOCR Multi-Strategy (Fallback)

```python
@classmethod
def _preprocess_plate_strategies(cls, plate_region) -> list:
    """
    Generate multiple pre-processed versions for EasyOCR:
      1. clahe_bilateral_sharpen — CLAHE + bilateral filter + sharpen
      2. adaptive_threshold — adaptive Gaussian + median blur
      3. otsu — OTSU binary (inverted if needed)
      4. morph_close — CLAHE + morphological close
      5. gray_clahe_light — light CLAHE on grayscale
      6. rgb_deskewed — deskewed RGB
    Each strategy is tried with 2 OCR confidence thresholds (0.5, 0.3).
    """
```

### Post-Processing: Normalization

```python
@classmethod
def _normalize(cls, raw: str) -> str:
    """
    Position-aware correction:
      Province: map letters to digits (O→0, I→1, etc.)
      Serial:   map digits to letters (0→D, 8→B, etc.)
      Number:   map letters to digits

    Tries both serial lengths (1 and 2 letters):
      "51A12345" → province="51" serial="A" number="12345"
      "51AB12345" → province="51" serial="AB" number="12345"
    Returns: "51A-12345"
    """
```

---

## 🎯 CONFIDENCE THRESHOLDS & DECISION LOGIC

```python
# Decision Matrix:
┌────────────────┬──────────────────┬────────────────┬─────────────────┐
│ Confidence     │ Format Valid      │ Decision       │ Action          │
├────────────────┼──────────────────┼────────────────┼─────────────────┤
│ >= 0.85        │ YES              │ AUTO_ACCEPT    │ Process auto    │
│ 0.65-0.84      │ YES              │ AUTO_ACCEPT    │ Still process   │
│ < 0.65         │ YES              │ MANUAL_INPUT   │ Need manual     │
│ Any            │ NO               │ MANUAL_INPUT   │ Need operator   │
└────────────────┴──────────────────┴────────────────┴─────────────────┘
```

---

## ⚡ PERFORMANCE

| Module | Model | Time (ms) |
|--------|-------|----------|
| Vehicle + Plate Detection | best.pt (YOLO) | ~150 |
| Character Detection | character_detector.pt | ~120 |
| EasyOCR Fallback | EasyOCR | ~800 |
| **TOTAL (best case)** | - | **~270ms** |
| **TOTAL (fallback)** | - | **~1050ms** |

---

## 🔧 FALLBACK HIERARCHY

```python
1. [PRIMARY] character_detector.pt on cropped plate
   └── If confidence < 0.5 or no characters:
2. [FALLBACK] EasyOCR on cropped plate (6 strategies)
   └── If no plate bbox found:
3. [LAST RESORT] Full-frame EasyOCR
   └── If all fail:
4. [MANUAL] Return empty result → operator manual input
```
