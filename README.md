# EVRP Realtime — Montoya 2017 mở rộng

Dự án Python cho bài toán điều độ xe điện giao hàng (EVRP) **realtime** dựa trên bộ
dữ liệu Montoya et al. (2017), có **sạc phi tuyến**, **giới hạn công suất trạm** và
**giá điện theo khung giờ (TOU)**. Hàm mục tiêu:

$$\min F = w_1(\text{di chuyển} + \text{chờ} + \text{sạc}) + w_2\,\text{chi phí điện TOU}
+ w_3\,\text{suy hao pin}$$

Dự án triển khai và so sánh ba phương pháp:

1. **Baseline** — Greedy chèn khách hàng + **Quy hoạch động** cho chiến lược sạc
   (sạc bao nhiêu, tại trạm nào) khi thứ tự khách hàng đã cố định.
2. **GA thuần** — Genetic Algorithm độc lập, không có VNS.
3. **Hybrid GA-VNS** — GA kết hợp Variable Neighborhood Search.

Xem phân tích kết quả tại [`REPORT.md`](REPORT.md).

---

## 1. Cài đặt

Yêu cầu **Python 3.10+**. Lõi thuật toán chỉ dùng thư viện chuẩn; `matplotlib` và
`pytest` chỉ cần cho biểu đồ và kiểm thử.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 2. Sinh dataset cải tiến

Đặt XML gốc Montoya trong `data/montoya-et-al-2017/` (đã có sẵn 120 instance).
Sinh dataset tự chứa (release time, giới hạn trạm, TOU, tham số hao pin) vào
`data/enhanced/`:

```bash
python -m evrp prepare --data data/montoya-et-al-2017 --out data/enhanced --config configs/default.json
```

Ba bổ sung so với Montoya gốc:
- **Realtime**: một tỷ lệ khách hàng có `release_hours > 0`.
- **Giới hạn công suất trạm**: `ports` (số cổng) và `power_kw` (tổng công suất).
- **TOU**: biểu giá 4 khung/ngày, lặp mỗi 24h.

## 3. Sử dụng CLI

```bash
# Liệt kê instance
python -m evrp list --data data/enhanced

# Chạy 1 instance: greedy | ga | ga_vns ; static | dynamic
python -m evrp run --instance tc0c10s2ct1 --algorithm ga_vns --mode static --seed 42 \
    --config configs/comparison.json --output results/run

# Benchmark nhiều instance/seed/thuật toán -> comparison.csv + statistics.csv
python -m evrp benchmark --instances tc0c10s2ct1 tc1c10s2ct4 \
    --algorithms greedy ga ga_vns --seeds 42 43 44 --mode static \
    --config configs/comparison.json --output results/benchmark

# Thí nghiệm độ phức tạp theo quy mô
python -m evrp complexity --sizes 10 20 40 80 --algorithms greedy ga ga_vns \
    --seeds 42 43 --mode static --config configs/quick.json \
    --greedy-budget 120 --meta-budget 15 --output results/complexity
```

Script thí nghiệm:

```bash
python -m experiments.comparison --seeds 42 43 44 --mode static --config configs/comparison.json
python -m experiments.complexity --sizes 10 20 40 80 --config configs/quick.json
python -m experiments.approximation --sizes 4 5 6 --config configs/approximation.json
python -m experiments.plots --output results/report
```

Trên Windows nên đặt `$env:PYTHONIOENCODING='utf-8'` để in tiếng Việt đúng.

## 4. Cấu trúc mã nguồn

| Đường dẫn | Trách nhiệm |
|---|---|
| `evrp/domain.py` | Node, Curve, Instance, VehicleState, Action, RoutePlan, Solution |
| `evrp/config.py` | Cấu hình (trọng số, TOU, hao pin, tham số DP/GA) + kiểm tra |
| `evrp/io/montoya.py` | Đọc XML Montoya gốc (namespace, Wh→kWh) |
| `evrp/io/enhance.py` | Sinh dataset cải tiến + đọc lại |
| `evrp/io/results.py` | Ghi JSON kết quả, `comparison.csv`, `statistics.csv` |
| `evrp/charging/model.py` | Sạc phi tuyến, sự kiện sạc sâu/xả cạn |
| `evrp/charging/tariff.py` | Tích phân chi phí TOU (kể cả qua nửa đêm) |
| `evrp/charging/calendar.py` | Lịch đặt cổng + giới hạn tổng công suất trạm |
| `evrp/algorithms/charging_dp.py` | DP/A* cho chiến lược sạc, thứ tự khách cố định |
| `evrp/algorithms/ranking.py` | Pareto: dominance, non-dominated sort, crowding distance (NSGA-II) |
| `evrp/algorithms/evaluator.py` | Đánh giá đội xe dùng chung, đặt lịch theo ID xe |
| `evrp/algorithms/greedy.py` | Baseline chèn tham lam |
| `evrp/algorithms/ga.py` | Lõi GA (thuần và bật/tắt VNS), gene trạm, chọn lọc Pareto |
| `evrp/algorithms/ga_vns.py` | GA thuần và Hybrid GA-VNS |
| `evrp/simulation.py` | Mô phỏng rolling-horizon: release đơn + tái tối ưu chu kỳ |
| `evrp/cli.py` | Lệnh `list/prepare/run/benchmark/complexity` |
| `experiments/` | Thí nghiệm độ phức tạp, so sánh, tỷ số xấp xỉ, vẽ biểu đồ |
| `configs/` | Kịch bản JSON (`default`, `quick`, `benchmark`, `comparison`) |
| `tests/` | Kiểm thử đầu vào, sạc, thuật toán, mô phỏng |
| `data/enhanced/` | Dataset cải tiến (sinh tự động) |
| `results/` | Đầu ra thí nghiệm |

## 5. Mô hình realtime

Chế độ `dynamic` chia thời gian thành các **epoch** (`replan_interval_hours`).
Tại mỗi epoch: công bố đơn có `release ≤ now`; neo trạng thái mỗi xe; tái tối ưu
các đơn đã công bố chưa phục vụ; thực thi các hành động đã bắt đầu; đơn chưa phục
vụ được thử lại ở epoch sau. Chế độ `static` đặt mọi release = 0 để đo thuần chất
lượng định tuyến/sạc.

## 6. Kiểm thử

```bash
python -m pip install pytest
python -m pytest -q
```

## 7. Biểu đồ và tập Pareto

- `results/report/complexity.png` — thời gian và số lần gọi DP theo quy mô.
- `results/report/comparison.png` — F trung bình theo thuật toán và instance.
- `results/report/approximation.png` — tỉ số xấp xỉ `F/OPT` so với ngưỡng α.
- `results/report/pareto.png` — mặt trước Pareto: đánh đổi Thời gian – Điện – Hao pin.
- `results/comparison/pareto.csv` — điểm non-dominated thô (dữ liệu cho hình Pareto).

Vẽ tất cả: `python -m experiments.plots --output results/report`.

## 8. Chọn lọc GA: scalar vs Pareto

GA hỗ trợ hai cơ chế chọn lọc (cấu hình `pareto_selection`, CLI `--selection`):

- `pareto` (mặc định) — NSGA-II: non-dominated sorting + crowding distance trên vector
  `(đơn chưa phục vụ, T, điện, hao pin)`; xuất tập front ra `pareto.csv`.
- `scalar` — xếp hạng vô hướng `F` cũ (tái lập số liệu cũ).

Ngoài ra `use_station_genes` bật/tắt gene trạm sạc trong nhiễm sắc thể.