# EVRP thời gian thực: GA + VNS bằng Python

Bản cài đặt nhỏ, chạy lại được, cho bài toán điều độ xe giao hàng điện (Electric Vehicle
Routing Problem, EVRP) khi đơn mới xuất hiện dần. Dự án so sánh ba phương pháp `greedy`,
`ga` và `ga_vns` trên bộ benchmark chuẩn, tối ưu đồng thời ba mục tiêu: thời gian vận hành,
chi phí điện và chỉ số hao mòn pin (đại diện). Dữ liệu gốc là bộ **Montoya et al., E-VRP-NL**;
thuật toán chỉ dùng thư viện chuẩn Python.

---

## 1. Bộ dữ liệu (dataset)

### 1.1. Nguồn

- Bộ dữ liệu: **Montoya et al. (2016), "Instances for the Electric Vehicle Routing Problem
  with Non-linear Charging Functions" (E-VRP-NL)**.
- Gồm **120 instance XML**, công bố tại VRP-REP:
  <https://www.vrp-rep.org/datasets/item/2016-0020.html>.
- Bản ZIP chính thức tải trực tiếp:
  <https://www.vrp-rep.org/datasets/download/montoya-et-al-2017.zip>.
- Dự án đặt ZIP tại `data/raw/montoya-et-al-2017.zip` và **đọc trực tiếp từng XML trong ZIP**,
  không chỉnh sửa dữ liệu benchmark.

### 1.2. Quy ước đặt tên

Mỗi instance có tên `tcAcBsCcDE`, trong đó:

| Ký hiệu | Ý nghĩa |
|---|---|
| `A` | Cách đặt khách: `0` phân bố đều, `1` thành cụm, `2` hỗn hợp |
| `B` | Số khách hàng |
| `C` | Số trạm sạc (charging station, CS) |
| `D` | Cách đặt trạm: `t` theo heuristic p-median, `f` ngẫu nhiên |
| `E` | Chỉ số instance cho mỗi tổ hợp tham số (`0`–`4`) |

Ví dụ `tc0c10s2cf1` = khách phân bố đều, 10 khách, 2 trạm sạc đặt ngẫu nhiên, instance số 1.

### 1.3. Thành phần một tệp XML

Mỗi XML gồm ba khối:

- **`<network>/<nodes>`** — các nút mạng:
  - `type=0`: kho (depot), `type=1`: khách hàng, `type=2`: trạm sạc;
  - toạ độ `cx`, `cy` tính bằng **km**, khoảng cách Euclid chính xác tới 14 chữ số thập phân;
  - nút trạm sạc có thẻ `<custom><cs_type>` nhận `slow`, `normal` hoặc `fast`.
- **`<fleet>/<vehicle_profile>`** — một loại xe điện duy nhất cho cả 120 instance:
  - `speed_factor`: tốc độ (km/h);
  - `consumption_rate`: mức tiêu thụ năng lượng (Wh/km);
  - `battery_capacity`: dung lượng pin (Wh);
  - `max_travel_time`: giới hạn thời gian một tuyến (giờ);
  - `charging_functions`: hàm sạc **phi tuyến** dạng đa đoạn cho từng `cs_type`,
    mỗi điểm là cặp `(<battery_level> Wh, <charging_time> h)`.
- **`<requests>/<request>`** — mỗi khách có một `service_time` (giờ).

### 1.4. Ví dụ cụ thể: `tc0c10s2cf1`

| Thuộc tính | Giá trị |
|---|---|
| Toạ độ kho | (77.59, 78.35) km |
| Khách hàng | 10 (node 1–10), mỗi khách `service_time = 0.5` h |
| Trạm sạc | 2 (node 11, 12), loại `fast` |
| Pin tối đa | 16 000 Wh |
| Tiêu thụ | 125 Wh/km |
| Tốc độ | 40 km/h |
| Thời gian tuyến tối đa | 10 h |
| Đường cong sạc `fast` | (0 Wh, 0 h) → (13 600 Wh, 0.31 h) → (15 200 Wh, 0.39 h) → (16 000 Wh, 0.51 h) |

Đường cong cho thấy phần pin cuối (80 % → 100 %) sạc chậm hơn rõ rệt, đúng đặc trưng sạc
phi tuyến mà bài toán yêu cầu.

### 1.5. Chín instance dự án sử dụng

Dự án chọn **9 instance** đại diện cho 3 cách phân bố khách × số khách 10 / 20 / 40:

| Instance | Khách | Trạm | Loại đường cong sạc |
|---|---:|---:|---|
| `tc0c10s2cf1` | 10 | 2 | fast |
| `tc1c10s2cf2` | 10 | 2 | fast, slow |
| `tc2c10s2cf0` | 10 | 2 | normal, slow |
| `tc0c20s3cf2` | 20 | 3 | fast |
| `tc1c20s3cf1` | 20 | 3 | fast, slow |
| `tc2c20s3cf0` | 20 | 3 | fast, normal |
| `tc0c40s5cf0` | 40 | 5 | fast, normal, slow |
| `tc1c40s5cf1` | 40 | 5 | normal, slow |
| `tc2c40s5cf2` | 40 | 5 | normal, slow |

Tất cả dùng chung thông số xe: pin 16 000 Wh, tiêu thụ 125 Wh/km, tốc độ 40 km/h, tuyến tối đa 10 h.

### 1.6. Phần mở rộng mô phỏng (không có trong benchmark)

Benchmark gốc chỉ mô tả bài toán **tĩnh** (mọi đơn biết trước) và không có giá điện. Dự án thêm
các thành phần sau để minh hoạ EVRP **thời gian thực**; chúng được sinh từ seed và lưu cùng kết quả:

- **Thời điểm đơn xuất hiện** (`make_releases`): `dynamic_ratio` khách có mặt tại thời điểm 0,
  phần còn lại sinh đều trong nửa đầu giới hạn thời gian tuyến.
- **Giá điện theo khung giờ TOU**: đơn vị tương đối/kWh — giờ 0–2: **1**, giờ 2–5: **3**,
  sau giờ 5: **1.5**; lặp lại mỗi 24 giờ. Chi phí một lần sạc được chia chính xác tại ranh giới giá.
- **Chỉ số hao mòn pin** (đại diện): kWh sạc từ mức pin ≥ 80 % cộng kWh xả dưới 20 %.
  Đây **không** phải mô hình tuổi thọ pin được hiệu chuẩn.

---

## 2. Thuật toán

### 2.1. Tên và ý tưởng

Thuật toán chính là **Genetic Algorithm kết hợp Variable Neighborhood Search (GA + VNS)**,
đối chiếu với hai baseline:

- `greedy` — chỉ dùng nghiệm tham lam (láng giềng gần nhất) làm nghiệm ban đầu;
- `ga` — chỉ chạy tiến hoá, không có bước cải thiện VNS;
- `ga_vns` — GA có VNS lắc và tìm kiếm cục bộ trên cá thể tốt nhất ở mỗi thế hệ.

### 2.2. Biểu diễn và bộ giải mã

- **Nhiễm sắc thể** là một **hoán vị các khách chưa giao** (thứ tự ghé thăm), không kèm thông tin
  phân tuyến hay lịch sạc.
- **`decode`** tách hoán vị thành các tuyến khả thi: ưu tiên xe đang có theo thời điểm sẵn sàng,
  chỉ mở xe mới khi cần. Với mỗi khách, nếu thêm vào tuyến hiện tại không khả thi thì thử xe khác,
  cuối cùng mới ghi vào `unserved`.
- **`plan_route` → `go_to` → `station_path`** kiểm tra tính khả thi năng lượng: chèn các lần sạc
  một phần cần thiết, chọn đường vòng qua trạm **ngắn nhất** (Dijkstra trên trạm), và giữ dự trữ
  tối thiểu 10 % pin hoặc đủ để thoát khỏi khách tới kho/trạm gần nhất.
- Sau khi rời kho, pin được coi là đầy; năng lượng nạp tại kho được tính chi phí theo giờ xuất phát
  nhưng không thêm thời gian sạc (benchmark không có thông số này).

### 2.3. Tham số GA

| Thành phần | Giá trị |
|---|---|
| Quần thể | 30 cá thể |
| Số thế hệ tối đa | 40 |
| Lai ghép | Order Crossover (OX), xác suất 80 % |
| Đột biến | 20 % (một trong ba lân cận relocate / swap / reverse) |
| Chọn lọc | Tournament kích thước 3 |
| Elitism | Giữ 2 cá thể tốt nhất |
| Cache | Lưu nghiệm đã giải mã theo thứ tự để tránh tính lặp |

### 2.4. VNS

GA+VNS lấy cá thể tốt nhất và lắc theo bán kính `k = 0,1,2` tương ứng ba lân cận:

1. `relocate` — chuyển một khách sang vị trí khác;
2. `swap` — đổi chỗ hai khách;
3. `reverse` — đảo một đoạn (2-opt trên thứ tự).

Sau mỗi lần lắc là một vòng leo đồi cục bộ nhỏ; nếu tìm được nghiệm tốt hơn thì quay lại `k = 0`,
ngược lại tăng `k`. Số lần thử mỗi thế hệ bị chặn để tuân thủ ngân sách thời gian.

### 2.5. Hàm mục tiêu

Với mỗi lần lập lại tuyến, điểm của nghiệm là:

```
score = 10000 × (#đơn không giao được)
      + 0.5 × thời_gian   / max(thời_gian_tham_lam, 1)
      + 0.3 × chi_phí     / max(chi_phí_tham_lam, 1)
      + 0.2 × hao_mòn     / max(hao_mòn_tham_lam, 1)
```

Các đại lượng được chuẩn hoá theo chính nghiệm tham lam trong lần lập kế hoạch đó để cân bằng
độ lớn giữa ba mục tiêu. Phạt `10000` mỗi đơn không giao đảm bảo ưu tiên phục vụ đủ đơn.
Thời gian vận hành là tổng giờ lái, phục vụ và sạc; **không** cộng thời gian chờ đơn mới.

### 2.6. Mô phỏng trực tuyến

Tại mỗi thời điểm có đơn mới, thuật toán lập lại kế hoạch cho các đơn chưa giao: xe đang chạy
**giữ nguyên chặng đang thực hiện** (`advance`), phần còn lại được tối ưu lại. Seed được lưu để
tái lập. Ngân sách `--seconds` áp dụng **cho từng lần xuất hiện đơn** và là cố gắng tuân thủ:
một thế hệ GA đang xử lý có thể làm thời gian thực vượt nhẹ.

### 2.7. Độ phức tạp

| Thành phần | Độ phức tạp |
|---|---|
| Giải mã một nhiễm sắc thể (`decode`) | đa thức; chi phối bởi Dijkstra `station_path` trên `|S|` trạm cho từng chặng, xấp xỉ `O(n² · (|S|+1)² log(|S|+1))` với `n` khách |
| GA | `O(E · decode)`, `E` = số nghiệm được đánh giá; bị chặn bởi ngân sách `seconds` |
| Held–Karp (TSP chính xác, ≤ 15 khách) | thời gian `O(n² · 2ⁿ)`, bộ nhớ `O(n · 2ⁿ)` |
| MST nhân đôi (Prim + DFS) | `O(V²)` cho `V = n + 1` nút |

### 2.8. Ngưỡng xấp xỉ cho trường hợp đặc biệt

Lệnh `proof` chứng minh **tỷ lệ xấp xỉ 2** cho một trường hợp đặc biệt: một xe, mọi đơn biết
trước, không cần sạc và tối thiểu quãng đường Euclid (tức TSP metric tĩnh). Gọi `MST` là độ dài
cây khung nhỏ nhất và `OPT` là hành trình tối ưu:

1. Một hành trình tối ưu, khi bỏ một cạnh, chứa một cây khung ⇒ `MST ≤ OPT`.
2. Nhân đôi mọi cạnh của cây được một hành trình dài `2 × MST`.
3. Đi tắt các đỉnh lặp không làm tăng độ dài nhờ bất đẳng thức tam giác ⇒ `ALG ≤ 2 × MST`.

Vậy `ALG ≤ 2 × MST ≤ 2 × OPT`. Với instance 10 khách, nghiệm còn được đối chiếu với TSP tối ưu
bằng quy hoạch động **Held–Karp**.

> **Quan trọng:** bảo đảm tỷ lệ 2 **chỉ** áp dụng cho TSP tĩnh đặc biệt nêu trên. Không suy rộng
> sang GA+VNS hoặc EVRP đầy đủ (nhiều xe, sạc phi tuyến, đơn động).

### 2.9. Kết quả benchmark

Kết quả đầy đủ nằm trong `results/experiment/` (bảng `report.md`, `summary.csv` và các biểu đồ
`runtime.png`, `evaluation_cost.png`, `objectives.png`). Cấu hình hiện có: **162 lượt chạy**
= 9 instance × 6 kịch bản (một tĩnh + năm seed động) × 3 phương pháp, ngân sách **0.1 giây**
mỗi lần tái lập tuyến. Dưới đây là trích đoạn kịch bản **50 % đơn động** (trung bình nhiều seed):

| Khách | Phương pháp | Giao được | Giờ vận hành | Chi phí điện | Hao mòn (kWh) | Trung vị (s) | P95 (s) |
|---:|---|---:|---:|---:|---:|---:|---:|
| 10 | `greedy` | 10/10 | 46.55 | 342.53 | 62.08 | 0.000 | 0.000 |
| 10 | `ga` | 10/10 | 30.60 | 195.97 | 38.92 | 0.020 | 0.038 |
| 10 | `ga_vns` | 10/10 | 30.78 | 194.98 | 39.02 | 0.033 | 0.061 |
| 20 | `greedy` | 20/20 | 74.95 | 552.61 | 99.10 | 0.001 | 0.001 |
| 20 | `ga` | 20/20 | 55.74 | 360.80 | 69.95 | 0.095 | 0.105 |
| 20 | `ga_vns` | 20/20 | 56.86 | 365.15 | 71.39 | 0.101 | 0.105 |
| 40 | `greedy` | 40/40 | 163.65 | 1199.41 | 201.34 | 0.001 | 0.002 |
| 40 | `ga` | 40/40 | 128.92 | 852.71 | 155.61 | 0.110 | 0.124 |
| 40 | `ga_vns` | 40/40 | 129.33 | 867.37 | 155.83 | 0.104 | 0.119 |

Nhận xét nhanh: GA cải thiện rõ so với tham lam trên cả ba mục tiêu (ví dụ 40 khách: giờ vận hành
163.65 → 128.92, chi phí 1199 → 853). Với ngân sách 0.1 giây, `ga` và `ga_vns` gần tương đương;
hiệu ứng của VNS cần kiểm chứng lại với ngân sách 2 giây. Thời gian lập tuyến phụ thuộc máy tính
và ngân sách đã chọn, nên hãy chạy lại trên máy dùng để báo cáo.

---

## 3. Cài đặt và chạy CLI

Yêu cầu **Python 3.11+**. Thuật toán chỉ dùng thư viện chuẩn; vẽ biểu đồ cần `matplotlib`.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v

python -m evrp run --instance tc0c10s2cf1 --method ga_vns --seed 0 --dynamic-ratio 0.5
python -m evrp proof --instance tc0c10s2cf1
```

Lệnh `run` ghi lịch xuất hiện đơn, tuyến xe, từng chặng di chuyển/sạc và số đo vào
`results/run.json`. Ba phương pháp: `greedy`, `ga`, `ga_vns`.

Chạy thí nghiệm trên 9 bài toán (3 phân bố × 10/20/40 khách), một kịch bản tĩnh và năm seed động:

```bash
python -m evrp experiment --seconds 2 --seeds 5
python -m evrp report
```

Kiểm tra nhanh: `python -m evrp experiment --limit-instances 1 --seeds 1 --seconds 0.1`.
Lệnh `experiment` tạo `summary.csv` và `scenarios.json`; lệnh `report` tạo `report.md` và các
biểu đồ. CSV có thời gian trung vị/P95, số lần đánh giá nghiệm và ba mục tiêu để đánh giá độ phức
tạp thực nghiệm. Biểu đồ `evaluation_cost.png` cho thấy chi phí đánh giá một nghiệm khi số khách
tăng, tránh đọc nhầm đường thời gian bị chặn bởi ngân sách. Khi so sánh chất lượng, dùng cùng
`scenarios.json`, seed và ngân sách cho cả ba phương pháp.

Nếu thiếu ZIP, tải từ [trang benchmark](https://www.vrp-rep.org/datasets/item/2016-0020.html)
hoặc [liên kết tải trực tiếp](https://www.vrp-rep.org/datasets/download/montoya-et-al-2017.zip)
và đặt tại `data/raw/montoya-et-al-2017.zip`.

---

## 4. Trang web trực quan

Thư mục `web/` có giao diện Next.js và API FastAPI để phát lại tuyến xe, xem pin/sạc/giá điện,
so sánh ba phương pháp và giải thích chứng minh xấp xỉ. Hướng dẫn khởi động chi tiết ở
[web/README.md](web/README.md).

---

## 5. Giới hạn cần nêu trong báo cáo

Dữ liệu gốc không chứa thời điểm đơn xuất hiện, giá TOU, dữ liệu suy hao pin hoặc giới hạn công
suất dùng chung ở trạm; các thành phần tương ứng trong mã là **giả định nghiên cứu có thể tái lập**.
Heuristic sạc chọn đường ngắn nhất và mức sạc vừa đủ, nên GA chủ yếu tối ưu thứ tự và phân tuyến
khách; nó không tối ưu độc lập lịch sạc. Không mô phỏng hàng đợi hoặc chia sẻ công suất giữa xe
tại trạm. Cần báo cáo trung thực tỷ lệ phục vụ, thời gian tính và seed, không gọi chỉ số hao mòn
là tuổi thọ pin thực.