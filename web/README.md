# EVRP Visual Lab

Trang demo chạy trên máy cá nhân để trực quan hoá thuật toán EVRP thời gian thực. Giao diện
React/Next.js ở cổng **3000**, API FastAPI ở cổng **8000**. FastAPI gọi trực tiếp mã `evrp` ở
thư mục gốc. Không có cơ sở dữ liệu; job đang chạy và kết quả gần đây nằm trong bộ nhớ và sẽ mất
khi khởi động lại backend.

Giao diện gồm ba tab: **Mô phỏng** (phát lại tuyến, pin, sạc theo đồng hồ mô phỏng), **So sánh**
(`greedy` / `ga` / `ga_vns` trên cùng điều kiện) và **Giải thích thuật toán** (thứ tự khách, ví dụ
lai ghép/đột biến/VNS và chứng minh xấp xỉ). Chi tiết bộ dữ liệu và thuật toán xem
[README gốc](../README.md).

## 1. Yêu cầu

- **Python 3.11+**, **Node.js 20.9+**;
- tệp `data/raw/montoya-et-al-2017.zip` của dự án (bộ Montoya E-VRP-NL, xem mục 1 của
  [README gốc](../README.md#1-bộ-dữ-liệu-dataset)).

## 2. Khởi động trang web

Chạy hai server ở hai terminal, đều từ **thư mục gốc dự án**.

### Terminal 1 — Backend FastAPI (cổng 8000)

```bash
python -m pip install -r web/backend/requirements.txt
python -m uvicorn web.backend.app:app --reload --host 127.0.0.1 --port 8000
```

Kiểm tra nhanh backend: mở <http://127.0.0.1:8000/api/health> (phải trả về `{"ok": true, ...}`).

### Terminal 2 — Frontend Next.js (cổng 3000)

```bash
cd web/frontend
npm ci
npm run dev
```

Mở **<http://127.0.0.1:3000>**.

### Ghi chú cấu hình

- Nếu backend chạy ở địa chỉ khác, đặt biến `EVRP_API_ORIGIN` **trước khi chạy Next.js**, ví dụ:
  `EVRP_API_ORIGIN=http://127.0.0.1:9000 npm run dev`.
- Next.js chuyển tiếp `/api/*` sang FastAPI (xem `next.config.mjs`), nên **không cần cấu hình CORS**
  cho demo cục bộ.

## 3. Kiểm tra

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s web/backend/tests -v
cd web/frontend && npm run typecheck && npm run build
```

Nếu máy có Brave hoặc trình duyệt Chromium, sau khi hai server đã chạy có thể kiểm tra luồng giao
diện bằng:

```bash
cd web/frontend && npm run smoke
```

Đặt `BROWSER_EXECUTABLE` nếu trình duyệt nằm ở đường dẫn khác (mặc định `/usr/bin/brave-browser`).

## 4. API

| Endpoint | Mô tả |
|---|---|
| `GET /api/health` | Trạng thái backend, ZIP và `summary.csv` có sẵn hay không |
| `GET /api/instances` | Danh sách 9 benchmark kèm số khách, số trạm |
| `GET /api/instances/{name}` | Toạ độ nút, danh sách khách/trạm, thông số xe, đường cong sạc và biểu giá TOU |
| `POST /api/runs` | Tạo job mô phỏng (bất đồng bộ), trả về `id` |
| `GET /api/runs/{id}` | Trạng thái `running`/`complete`/`failed`, tiến độ, kết quả và snapshot lập tuyến |
| `GET /api/experiments` | Các dòng CSV thí nghiệm; lọc bằng `instance` và `dynamic_ratio` |
| `GET /api/proof/{name}` | Hành trình TSP đặc biệt, cạnh MST và đối chiếu Held–Karp khi ≤ 15 khách |

Ví dụ tạo job:

```json
POST /api/runs
{"instance": "tc0c10s2cf1", "dynamic_ratio": 0.5, "seed": 0, "seconds": 0.1, "methods": ["ga_vns"]}
```

Ràng buộc tham số:

- `dynamic_ratio`: `0`, `0.5` hoặc `1`;
- `seconds`: `0.1`, `0.5` hoặc `2.0` (áp dụng cho **mỗi lần** xuất hiện đơn);
- `methods`: một hoặc cả ba trong `greedy`, `ga`, `ga_vns` (không lặp);
- backend xử lý **mỗi lúc một lượt chạy**; gọi khi đang bận sẽ trả `409`.

Mọi giá điện là đơn vị tương đối. Chỉ số hao mòn pin chỉ là proxy, không phải tuổi thọ pin được
hiệu chuẩn. Benchmark gốc không có thời điểm đơn xuất hiện hoặc giá TOU; chúng được sinh từ seed và
giả định của dự án.

## 5. Cách trình bày trong 5 phút

1. **Đơn đến dần:** chọn kịch bản 10 khách, bấm **Chạy mô phỏng** rồi **▶**. Bấm các dấu xanh trên
   thanh thời gian để xem khách mới xuất hiện và tuyến dự kiến đổi. Chọn một xe để xem mức pin.
2. **Sạc và giá điện:** chọn kịch bản 20 khách, seed 0. Tua tới khoảng giờ 3–4; xe ghé trạm sạc
   trong khung giá cao 2–5 giờ. Đồ thị sạc là đường cong gốc của benchmark, giá điện là mô phỏng.
3. **So sánh:** vào tab **So sánh** để xem trung bình thí nghiệm hiện có; bấm **Chạy cả 3** để tạo
   so sánh cùng instance, seed, tỷ lệ đơn động và ngân sách. Ba chỉ số mục tiêu được trình bày tách biệt.
4. **Giải thích:** vào tab **Giải thích thuật toán** khi đã chạy GA+VNS để thấy thứ tự khách, ví dụ
   lai ghép/đột biến/VNS và điểm tốt nhất qua thế hệ. Phần chứng minh tỷ lệ 2 chỉ dành cho TSP tĩnh
   đặc biệt, không phải EVRP đầy đủ.

Các lượt chạy 40 khách hoặc ngân sách 2 giây có thể mất nhiều thời gian vì ngân sách áp dụng cho
**mỗi lần** xuất hiện đơn. Giao diện hiển thị tiến độ khi backend tính xong rồi mới phát lại thời
gian mô phỏng.