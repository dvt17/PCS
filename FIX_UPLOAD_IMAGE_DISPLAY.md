# Fix: Hiển thị ảnh đã xử lý (Annotated Image) sau khi tải ảnh lên

## Vấn đề
- Chức năng tải ảnh lên và xử lý bãi đỗ xe hoạt động, nhưng ảnh đã xử lý (có khung biển số) không hiển thị trên trang web
- Chỉ có thông tin biển số được hiển thị, nhưng ảnh với annotation (khung biển số + ký tự) không show lên

## Nguyên nhân
1. **Backend không trả về dữ liệu ảnh đã xử lý**: Hai API endpoint (`/api/process_image` và `/api/process_frame`) xử lý ảnh nhưng không trả về ảnh đã xử lý (annotated image) trong JSON response
2. **Database lưu ảnh nhưng không trả về**: Ảnh annotated được lưu vào database nhưng response chỉ trả về thông tin metadata (plate, confidence, etc.)
3. **Frontend đợi dữ liệu không có**: Frontend code mong đợi `annotated_b64` hoặc `image_b64` trong response nhưng backend không cung cấp

## Giải pháp

### 1. Sửa `/api/process_image` endpoint (backend/app.py)
- Thêm query database để lấy ảnh annotated đã lưu
- Encode ảnh thành base64 và đưa vào response
- Trả về `annotated_b64` trong JSON response

### 2. Sửa `/api/process_frame` endpoint (backend/app.py)
- Tương tự `/api/process_image`, thêm trả về `annotated_b64`
- Nếu không có annotated, fallback trả về `image_b64` (ảnh gốc)

### 3. Cập nhật Frontend (templates/dashboard.html)
- Sửa hàm `showAnnotatedResult()` để xử lý `image_b64` từ `/api/process_frame`
- Ưu tiên hiển thị: `annotated_b64` > `image_b64` > blob từ upload > annotated_path

## Kết quả
- ✅ API `/api/process_image` giờ trả về `annotated_b64`
- ✅ API `/api/process_frame` trả về `annotated_b64` (hoặc `image_b64` nếu không có)
- ✅ Frontend hiển thị ảnh đã xử lý trên trang dashboard
- ✅ Ảnh hiển thị ngay sau khi tải ảnh lên và xử lý xong

## Files đã sửa
1. `backend/app.py`
   - Sửa `/api/process_image` endpoint
   - Sửa `/api/process_frame` endpoint

2. `frontend/templates/dashboard.html`
   - Sửa hàm `showAnnotatedResult()`
