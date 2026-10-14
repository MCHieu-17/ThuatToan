# Benchmarks

Hướng dẫn cài đặt và chạy benchmark cho 3 thuật toán `greedy`, `ga`, `ga_vns`
trên bộ dữ liệu Montoya et al. 2017 (120 instance EVRP).

## 1. Cài đặt thư viện

Yêu cầu: **Python 3.10+**.

Các thuật toán lõi chỉ dùng thư viện chuẩn của Python. Chỉ cần cài thêm
`matplotlib` để vẽ biểu đồ (và `pytest` nếu muốn chạy test):

```bash
# (khuyến nghị) tạo môi trường ảo
python3 -m venv .venv
source .venv/bin/activate

# cài các thư viện cần thiết
pip install -r requirements.txt
```

Nếu chỉ muốn phần tối thiểu để vẽ biểu đồ:

```bash
pip install matplotlib
```

Kiểm tra đã cài đúng bằng cách chạy lệnh trợ giúp:

```bash
python3 -m evrp --help
```

## 2. Hướng dẫn chạy benchmark

Có sẵn 3 script trong `benchmarks/`, mỗi script chia nhỏ công việc thành từng
tổ hợp `(instance, algorithm, seed)` và chạy song song nhiều tiến trình để tận
dụng tối đa số nhân CPU.

| Script | Bộ instance | Số instance |
|---|---|---|
| `benchmarks/run_all_120.sh` | Toàn bộ Montoya | 120 |
| `benchmarks/run_subset_26.sh` | Bộ con đại diện | 26 |
| `benchmarks/run_by_size.sh` | Theo kích thước 10/20/40/80/160/320 khách | 12 |

### Lệnh chạy

Chạy từ thư mục gốc của repo:

```bash
# Toàn bộ 120 instance (nặng, có thể mất hàng chục giờ)
bash benchmarks/run_all_120.sh

# Bộ con 26 instance đại diện (khuyến nghị cho báo cáo đồ án)
bash benchmarks/run_subset_26.sh

# Theo kích thước để phân tích scaling
bash benchmarks/run_by_size.sh
```

### Tùy chỉnh qua biến môi trường

Các script nhận cấu hình qua biến môi trường, không cần sửa code:

```bash
# đổi config, số seed, số tiến trình song song
JOBS=12 SEEDS="42 43" CONFIG=configs/benchmark.json bash benchmarks/run_subset_26.sh

# chạy chế độ tĩnh thay vì động
MODE=static bash benchmarks/run_by_size.sh

# chỉ chạy 2 thuật toán
ALGORITHMS="greedy ga_vns" bash benchmarks/run_subset_26.sh
```

Các biến hỗ trợ:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `JOBS` | số nhân CPU (`nproc`) | Số tiến trình chạy song song |
| `SEEDS` | `42 43` (`42 43 44` cho all_120) | Danh sách seed |
| `CONFIG` | `configs/benchmark.json` | File cấu hình |
| `ALGORITHMS` | `greedy ga ga_vns` | Thuật toán cần chạy |
| `MODE` | `dynamic` | `dynamic` hoặc `static` |
| `DATA` | `data/montoya-et-al-2017` | Thư mục dữ liệu |
| `OUT` | `results/benchmark_*` | Thư mục kết quả |

Khi chạy xong, script in ra tổng thời gian chạy (giây) ở dòng cuối:

```
done -> results/benchmark_subset26
total time: 1832s
```

### Nơi lưu kết quả

Mỗi script ghi vào một thư mục riêng dưới `results/`:

| Script | Thư mục kết quả |
|---|---|
| `run_all_120.sh` | `results/benchmark_all120/` |
| `run_subset_26.sh` | `results/benchmark_subset26/` |
| `run_by_size.sh` | `results/benchmark_by_size/` |

Trong mỗi thư mục có:

- `*.json` — kết quả thô của từng lần chạy (một file mỗi tổ hợp).
- `comparison.csv` — bảng từng lần chạy với đầy đủ chỉ số (F, T, điện năng, suy giảm pin, thời gian chạy, số label DP...).
- `statistics.csv` — thống kê gộp theo `(instance, mode, algorithm)`: trung bình, độ lệch chuẩn.
- `pareto.csv` — các điểm trên mặt Pareto.

## 3. Hướng dẫn tạo visualization

Script `benchmarks/visualization.py` đọc `comparison.csv` (hoặc `statistics.csv`)
từ thư mục kết quả và sinh biểu đồ cột + linechart.

```bash
python3 benchmarks/visualization.py results/benchmark_subset26
```

Chỉ định thư mục xuất ảnh khác (mặc định xuất ngay trong thư mục kết quả):

```bash
python3 benchmarks/visualization.py results/benchmark_by_size --output reports/figures
```

### Nơi lưu kết quả

Biểu đồ được ghi vào thư mục kết quả (hoặc thư mục `--output`):

- `bars_F.png` — biểu đồ cột F trung bình theo kích thước.
- `bars_served.png` — biểu đồ cột tỉ lệ khách được phục vụ.
- `bars_runtime.png` — biểu đồ cột thời gian chạy.
- `line_F.png` — linechart F theo kích thước.
- `line_scaling.png` — linechart thời gian chạy theo kích thước (thang log).
- `line_labels.png` — linechart số label DP theo kích thước (thang log).
- `summary_by_size.csv` — bảng tổng hợp số liệu dùng để vẽ.

## Quy trình đầy đủ (ví dụ)

```bash
# 1. cài đặt
pip install -r requirements.txt

# 2. chạy benchmark bộ 26 instance
JOBS=12 SEEDS="42 43" bash benchmarks/run_subset_26.sh

# 3. vẽ biểu đồ
python3 benchmarks/visualization.py results/benchmark_subset26
```

Kết quả nằm trong `results/benchmark_subset26/`.
