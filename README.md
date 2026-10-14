# Realtime EVRP — Giao hàng bằng xe điện (Montoya et al. 2017)

Đồ án xây dựng một **lab mô phỏng bài toán định tuyến xe điện có sạc (EVRP)** trên
bộ dữ liệu Montoya et al. 2017, kèm **ba thuật toán** (`greedy`, `ga`, `ga_vns`)
và một **pipeline benchmark + visualization** để so sánh chúng.

Điểm khác biệt cốt lõi của đồ án so với dữ liệu gốc Montoya:

- **Đơn hàng realtime**: một phần khách xuất hiện theo thời gian (`release_hours`),
  không phải tất cả đều sẵn sàng từ đầu.
- **Trạm sạc có giới hạn công suất** (số cổng + tổng kW dùng chung).
- **Giá điện theo khung giờ (TOU)** và **chi phí suy giảm pin**.
- **Hàm sạc phi tuyến** dạng piecewise-linear.

Các cải tiến này được mô tả chi tiết trong [`ENHANCE_DATASET.md`](ENHANCE_DATASET.md).

---

## 1. Kiến trúc mã nguồn

```
evrp/
  domain.py          # Node, Instance, Curve, Action, RoutePlan, Solution
  config.py          # Config: TOU, degradation, fleet, tham so DP/GA
  metrics.py         # dinh nghia F + cac bo dem thao tac
  simulation.py      # mo phong rolling-horizon (realtime)
  algorithms/
    greedy.py        # baseline: chen tham lam chi phi nho nhat
    ga.py            # engine GA (thuan) + che do Pareto/scalar
    ga_vns.py        # GA lai VNS
    evaluator.py     # routes -> charging plans -> F (dung chung)
    charging_dp.py   # DP/A* quyet dinh sac (label-setting)
    ranking.py       # non-dominated sort + crowding distance
  charging/
    model.py         # mo hinh sac phi tuyen + suy giam pin
    calendar.py      # dat cho cong/cong suat tram sac
    tariff.py        # chi phi dien theo TOU
  io/
    montoya.py       # doc XML goc (quy doi Wh -> kWh)
    enhance.py       # sinh dataset enhanced JSON
    results.py       # ghi JSON + comparison/statistics/pareto CSV
  cli.py             # list / prepare / run / benchmark / complexity
benchmarks/          # script chay song song + visualization
configs/benchmark.json
data/montoya-et-al-2017/   # 120 XML goc
data/enhanced/             # 120 JSON da cai tien
```

---

## 2. Ba thuật toán và cách chúng hoạt động

Cả ba thuật toán dùng chung một "hợp đồng" gọi là **FleetEvaluator**: nhận vào
`routes` (mỗi xe một danh sách khách) và trả về một `Solution`. Bên trong
evaluator, mỗi xe được giải bài toán con **quyết định sạc** bằng một
**dynamic program label-setting (A*)** (`charging_dp.py`). Vì vậy khác biệt giữa
ba thuật toán nằm ở **cách tạo/duyệt các phương án phân tuyến**, không nằm ở mô
hình vật lý.

Trạng thái của một **phiên mô phỏng** (rolling-horizon, `simulation.py`):
tại các mốc thời gian cách nhau `replan_interval_hours`, solver chỉ thấy các đơn
đã `release` và chưa phục vụ, tái tối ưu từ trạng thái hiện tại của từng xe, rồi
chỉ thực thi các hành động bắt đầu trước `epoch_end`; phần còn lại bị bỏ và lên
lịch lại ở epoch sau.

### Hàm mục tiêu F

Mọi thuật toán đều tối ưu (giảm dần) giá trị:

```
F = w_time * (drive + wait + charge)
  + w_electricity * electricity
  + w_degradation * degradation
```

- `service` (thời gian phục vụ) **không** tính vào F (nó vẫn đẩy đồng hồ xe).
- `electricity` là tiền điện (tính theo TOU), `degradation` là chi phí sự cố
  sạc sâu / xả sâu.

**Thứ tự ưu tiên là "phục vụ nhiều khách trước, giảm F sau"**, được mã hoá trong
`Solution.rank = (không khả thi?, số khách chưa phục vụ, F)`. Nghĩa là một
phương án phục vụ nhiều khách hơn **luôn** tốt hơn, kể cả khi F cao hơn. Điều
này quan trọng khi đọc kết quả benchmark (xem mục 4).

### 2.1. `greedy` — baseline chèn tham lam

`greedy_insert` (`evrp/algorithms/greedy.py`):

1. Xuất phát từ lời giải rỗng, xét khách theo thứ tự ưu tiên
   `(release_hours, khoảng cách từ depot, id)`.
2. Với mỗi khách còn lại, thử **mọi vị trí chèn vào mọi xe**. Một ứng viên chỉ
   giải lại **xe bị thay đổi** (các xe khác giữ nguyên), rồi được xếp hạng:
   - **non-regressing**: giữ tất cả khách đã phục vụ trước đó → ưu tiên, chọn F
     cục bộ nhỏ nhất.
   - **fallback**: ít nhất vẫn phục vụ được khách mới và không giảm số khách đã
     phục vụ.
3. Ứng viên được **xác nhận bằng một đánh giá toàn fleet thật** (tối đa
   `CONFIRM_LIMIT = 6` ứng viên rẻ nhất) trước khi nhận, để không đánh rơi khách
   do hiệu ứng dây chuyền giữa các xe.

Không có ngẫu nhiên → **cùng một instance luôn cho cùng kết quả**, bất kể seed.

### 2.2. `ga` — giải thuật di truyền thuần

`run_pure_ga` → `run_ga(use_vns=False)` (`evrp/algorithms/ga.py`):

- **Nhiễm sắc thể (Chromosome)**: `order` (thứ tự khách), `vehicles` (mỗi khách
  thuộc xe nào), và `stations` (gen gợi ý trạm sạc cho mỗi khách, `-1` = không
  gợi ý). Gen trạm chỉ là **hint** truyền xuống DP — DP vẫn tự tối ưu công suất,
  mức sạc mục tiêu và công suất đặt trước.
- **Khởi tạo**: lấy `greedy_insert` (dùng 60% ngân sách thời gian) làm hạt
  giống, rồi sinh thêm cá thể ngẫu nhiên / đột biến cho đủ `population`.
- **Lai ghép (crossover)**: lai OX (order crossover) trên thứ tự khách; gen xe và
  gen trạm thừa kế ngẫu nhiên 50/50 từ bố/mẹ.
- **Đột biến (mutate)**: 50% hoán vị hai gen; nếu có pool trạm thì 30% đổi gen
  trạm; ngược lại đổi xe cho một khách.
- **Chọn lọc**: tuỳ `pareto_selection`:
  - `true` (mặc định) → **NSGA-II**: non-dominated sort + crowding distance,
    `_evolve_pareto`.
  - `false` → **scalar**: sắp xếp theo `rank`, tournament 3, elitism.
- **Dừng** khi hết `generations` hoặc hết `solver_budget_seconds`.

Hàm `_export_front` xuất **mặt Pareto** của thế hệ cuối, nhưng chỉ giữ các nghiệm
có **số khách chưa phục vụ nhỏ nhất** — loại bỏ các nghiệm "phục vụ ít cho kịp
thời gian".

### 2.3. `ga_vns` — GA lai tìm kiếm lân cận biến đổi (VNS)

`run_ga_vns` → `run_ga(use_vns=True)`. Dùng **đúng engine GA ở trên**, chỉ thêm
bước VNS ở đầu mỗi thế hệ (`_apply_vns`, `neighbor`):

- 4 lân cận xoay vòng:
  - `0` — **relocate**: chuyển 1 khách sang xe khác.
  - `1` — **swap**: đổi chỗ 1 khách giữa hai xe.
  - `2` — **2-opt/reverse**: đảo một đoạn trong tuyến một xe.
  - `3` — **charge-adjust**: đổi trạm sạc ưu tiên của một chặng (nếu bật
    `use_station_genes`).
- Chạy tối đa `vns_iterations` lần; chỉ nhận lân cận nếu `rank` tốt hơn; nếu
  không cải thiện thì tăng số hiệu lân cận (đa dạng hoá).

GA-VNS thường đạt F tốt hơn GA thuần nhưng chậm hơn, vì mỗi bước VNS là một lần
đánh giá fleet đầy đủ.

### 2.4. Bài toán con sạc (`charging_dp.py`) — dùng chung cho cả ba

Cho một tuyến cố định (thứ tự khách đã biết), DP quyết định:

- Có chèn trạm sạc vào giữa các chặng không, và chèn trạm nào.
- Nạp tới mức SoC nào (target) và đặt trước công suất bao nhiêu
  (`power_fractions`).
- Tôn trọng `max_station_hops`, `candidate_stations`, `reserve_soc`,
  công suất rảnh của trạm (`StationCalendar`), và release time của khách.
- Trả `optimal` / `search_limit` / `no_path`. `search_limit` **không** phải bằng
  chứng bất khả thi — chỉ là đã chạm giới hạn `max_labels`/`dp_budget_seconds`.

---

## 3. Cách chạy benchmark

> **Dataset mặc định:** benchmark chạy trên bộ **đã cải tiến** `data/enhanced/`
> (JSON). Muốn chạy trên XML gốc, đặt `DATA=data/montoya-et-al-2017` — nhưng khi
> đó sẽ **mất** release times, giới hạn cổng sạc, TOU và degradation (chúng chỉ
> có trong bản enhanced).

Cài đặt (Python 3.10+):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # chỉ cần matplotlib; lõi dùng stdlib
```

### Chạy một instance đơn lẻ

```bash
python3 -m evrp run --data data/enhanced --instance tc0c10s2cf1 \
    --algorithm ga_vns --mode dynamic --seed 42 --output results/run
```

### Chạy benchmark hàng loạt

Ba script trong `benchmarks/` chia công việc thành từng tổ hợp
`(instance, algorithm, seed)` và chạy **song song** bằng `xargs -P`:

| Script | Bộ instance | Số instance | Thư mục kết quả |
|---|---|---|---|
| `run_all_120.sh` | Toàn bộ Montoya | 120 | `results/benchmark_all120/` |
| `run_subset_26.sh` | Bộ con đại diện | 26 | `results/benchmark_subset26/` |
| `run_by_size.sh` | Theo kích thước 10/20/40/80/160/320 | 12 | `results/benchmark_by_size/` |

```bash
bash benchmarks/run_subset_26.sh      # khuyến nghị cho báo cáo
bash benchmarks/run_by_size.sh        # để phân tích scaling
bash benchmarks/run_all_120.sh        # nặng, có thể mất hàng chục giờ
```

Tùy chỉnh qua biến môi trường:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `JOBS` | `nproc` | Số tiến trình song song |
| `SEEDS` | `42 43` (`42 43 44` cho all_120) | Danh sách seed |
| `CONFIG` | `configs/benchmark.json` | File cấu hình |
| `ALGORITHMS` | `greedy ga ga_vns` | Thuật toán cần chạy |
| `MODE` | `dynamic` | `dynamic` (realtime) hoặc `static` (tất cả khách có từ đầu) |
| `SELECTION` | `pareto` | `pareto` (NSGA-II) hoặc `scalar` (chỉ GA) |
| `DATA` | `data/enhanced` | Thư mục dữ liệu |
| `OUT` | `results/benchmark_*` | Thư mục kết quả |

Ví dụ:

```bash
JOBS=12 SEEDS="42 43" ALGORITHMS="greedy ga_vns" bash benchmarks/run_subset_26.sh
MODE=static bash benchmarks/run_by_size.sh
```

Script in **tổng thời gian chạy** ở dòng cuối:

```
done -> results/benchmark_subset26
total time: 1832s
```

### File kết quả

Mỗi script chạy `python3 -m evrp run` cho từng tổ hợp, ghi một `*.json`, rồi gọi
`benchmarks/collect_results.py` để gom lại (không chạy lại thuật toán):

- `*.json` — kết quả thô đầy đủ của từng lần chạy (metrics, counters, actions,
  pareto_front, config).
- `comparison.csv` — **một dòng mỗi lần chạy** với đầy đủ chỉ số:
  `served`, `total`, `complete`, `F`, `T`, `drive`, `wait`, `charge`,
  `electricity`, `degradation`, `deep_charge`, `deep_discharge`, `makespan`,
  `runtime_seconds`, `replans`, `dp_calls`, `labels_expanded`, `evaluations`,
  `insertion_candidates`.
- `statistics.csv` — gộp theo `(instance, mode, algorithm)`: `served_mean`,
  `F_mean`, `F_std`, `runtime_mean`, ...
- `pareto.csv` — hợp các điểm trên mặt Pareto của mọi lần chạy.

---

## 4. Cách đọc kết quả cho đúng

Đây là phần **dễ hiểu sai nhất**. Có vài điểm bắt buộc phải nhớ:

### 4.1. `F` là **chi phí tổng**, không phải chi phí trên mỗi khách

F = tổng chi phí thời gian + điện + suy giảm của **toàn bộ hành động đã thực
thi**. Vì vậy khi một thuật toán phục vụ **nhiều khách hơn**, F **tăng lên là
chuyện bình thường** (thêm chuyến, thêm thời gian, thêm điện). **Không được kết
luận "F cao hơn = tệ hơn"** khi số khách phục vụ khác nhau.

→ **Luôn đọc `served / total` (hoặc `served_ratio`) song song với `F`.** Một
thuật toán chỉ thực sự trội khi nó phục vụ **ít nhất** bằng đối thủ **và** F thấp
hơn ở cùng mức phục vụ.

### 4.2. Không thuật toán nào phục vụ đủ 100% khách

Trên bộ enhanced, **kể cả instance 10 khách cũng chỉ đạt ~8/10** (`complete_runs
= 0` ở mọi tổ hợp). Đây là hành vi thật của code + ràng buộc (T max_travel_time,
cửa sổ release, pin, trạm giới hạn), **không phải bug**. Vì vậy `statistics.csv`
để `F_mean` trống khi không có nghiệm nào `complete`. Khi báo cáo:

- Dùng cột `served` / `total` để mô tả mức phục vụ thực tế.
- Dùng `complete_runs` để biết có bao nhiêu lần chạy đạt 100%.

### 4.3. `mode`

- `static`: mọi khách `release = 0`, solver chỉ replan một lần cho cả horizon →
  F thấp hơn, phục vụ thường tốt hơn. Dùng để so sánh thuần tuý chất lượng
  tuyến.
- `dynamic`: đúng bài toán realtime, solver replan mỗi `replan_interval_hours`.

**Chỉ so sánh kết quả cùng `mode`.**

### 4.4. Các chỉ số vận hành (chi phí tính toán)

- `runtime_seconds` — tổng thời gian mô phỏng (gồm mọi lần replan).
- `dp_calls` — số lần gọi DP sạc.
- `labels_expanded` — số nhãn A* mở rộng (thước đo độ khó bài toán sạc).
- `evaluations` — số lần đánh giá một phương án fleet.
- `insertion_candidates` — số ứng viên chèn đã thử (chủ yếu của greedy).

Thường thấy: `greedy` chạy **nhanh nhất** nhưng F kém hơn; `ga_vns` chậm nhất
nhưng chất lượng tốt nhất khi còn ngân sách.

---

## 5. Cách chạy visualization

```bash
python3 benchmarks/visualization.py results/benchmark_subset26
python3 benchmarks/visualization.py results/benchmark_by_size --output reports/figures
```

Script đọc `comparison.csv` (ưu tiên) hoặc `statistics.csv`, gom nhóm theo
`(kích thước instance, algorithm)`, và xuất:

| File | Nội dung |
|---|---|
| `bars_F.png` | F trung bình theo kích thước (3 thuật toán) |
| `bars_served.png` | Tỉ lệ khách phục vụ theo kích thước |
| `bars_runtime.png` | Thời gian chạy theo kích thước |
| `line_F.png` | Linechart F theo kích thước |
| `line_scaling.png` | Linechart thời gian chạy theo kích thước (thang log) |
| `line_labels.png` | Linechart số nhãn DP theo kích thước (thang log) |
| `summary_by_size.csv` | Bảng tổng hợp dùng để vẽ |

Kích thước instance được suy ra từ tên file `tcAcBsCcDE`: **B** là số khách
(tự động đọc, không cần cấu hình). `summary_by_size.csv` chứa:

| Cột | Ý nghĩa |
|---|---|
| `size` | Số khách |
| `algorithm` | Tên thuật toán |
| `runs` | Số lần chạy |
| `complete_runs` | Số lần phục vụ đủ 100% (thường = 0) |
| `F` | F trung bình |
| `served_ratio` | Tỉ lệ khách phục vụ trung bình (0–1) |
| `served_over_total` | Dạng `"X.X/Y"` ví dụ `8.0/10`, `46.0/80` |
| `runtime` | Thời gian chạy trung bình (giây) |
| `labels` / `dp_calls` / `evaluations` | Chỉ số vận hành trung bình |

> Khi đọc `bars_F.png`/`line_F.png` hãy nhớ **đọc kèm `served_over_total`**:
> F tăng theo kích thước là do phục vụ nhiều khách hơn, không phải do thuật toán
> tệ đi (xem mục 4.1).

---

## 6. Giải thích siêu tham số trong `configs/benchmark.json`

File này là **cấu hình duy nhất** dùng cho benchmark. Nó vừa điều khiển việc
sinh dataset enhanced, vừa điều khiển mô phỏng và thuật toán.

### 6.1. Nhóm seed & fleet

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `seed` | `42` | Seed gốc. Dùng cho `random` khi sinh dataset (reproducible) và là mặc định cho GA khi không truyền `--seed`. Cùng seed ⇒ cùng dataset và cùng kết quả tất định cho greedy. |
| `vehicles` | `0` | `0` = để code **tự ước lượng fleet** từ hình học. Nếu `> 0` thì dùng đúng số đó, ghi đè ước lượng. |
| `customers_per_vehicle` | `5` | Tỉ lệ khách/xe **mục tiêu** khi ước lượng fleet (không phải ràng buộc cứng). |
| `min_vehicles` | `2` | Sàn số xe, tránh instance nhỏ ước lượng ra 1 xe. |
| `fleet_clustering_discount` | `1.0` | Hệ số chiết khấu thời gian di chuyển khi khách gần nhau (ước lượng fleet). `1.0` = không chiết khấu. |
| `fleet_time_utilization` | `0.75` | Một xe không vượt quá **75%** horizon. Vì khách Montoya rất xa nhau, một chuyến đi-về có thể đã chiếm phần lớn ngày, nên đây là ràng buộc chính thay vì tỉ lệ khách/xe. |

Fleet ước lượng theo **khối lượng thời gian**: mỗi khách đóng góp
`đi-về depot + service_time`; số xe tối thiểu để tổng thời gian đó nằm trong
`fleet_time_utilization * horizon` mỗi xe. Ví dụ 10 khách → 4–7 xe, 320 khách →
122–169 xe tuỳ địa lý.

### 6.2. Nhóm đơn hàng realtime

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `dynamic_fraction` | `0.5` | 50% khách được coi là "động" (có `release_hours > 0`). |
| `release_until_fraction` | `0.35` | Các đơn động rải đều trong `[0, 0.35 * horizon]`. Với horizon 10h → đơn động xuất hiện trong ~3.5h đầu. |
| `start_clock_hour` | `8.0` | Giờ tường lúc bắt đầu mô phỏng (8:00). Dùng để tra giá TOU: giờ mô phỏng `t` ↔ giờ tường `8 + t`. |
| `horizon_factor` | `1.0` | Hệ số nhân lên horizon gốc (`max_travel_time`). `1.0` = giữ nguyên. |

### 6.3. Nhóm trạm sạc (`stations_by_type`)

Mỗi loại trạm có 3 thông số: `ports` (số cổng sạc đồng thời), `power_kw` (tổng
công suất trạm dùng chung), `charger_kw` (công suất tối đa mỗi trụ).

```json
"fast":   {"ports": 2, "power_kw": 50.0, "charger_kw": 44.0}
"normal": {"ports": 2, "power_kw": 22.0, "charger_kw": 22.0}
"slow":   {"ports": 1, "power_kw": 7.0,  "charger_kw": 7.0}
```

- `fast` nạp nhanh nhất nhưng cũng "ngốn" công suất trạm; `slow` chỉ 7 kW.
- Ràng buộc cả **số cổng** và **tổng kW tức thời** được `StationCalendar` kiểm
  tra khi đặt chỗ; trạm đầy thì DP phải chọn trạm khác hoặc chờ.

### 6.4. Nhóm giá điện TOU (`tou`)

```json
[ {0-9h: 0.12}, {9-12h: 0.25}, {12-17h: 0.45}, {17-24h: 0.18} ]
```

Đơn vị: tiền/kWh. Các khung **phủ liên tục [0, 24]** và phải kết thúc ở 24 (code
validate điều này). Giá cao điểm 12–17h (0.45) khuyến khích solver dịch chuyển
việc sạc sang sáng sớm/tối. `start_clock_hour` liên kết giờ mô phỏng với giờ
tường khi tra bảng.

### 6.5. Nhóm trọng số mục tiêu

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `w_time` | `1.0` | Trọng số thời gian (drive+wait+charge). |
| `w_electricity` | `0.3` | Trọng số tiền điện. |
| `w_degradation` | `0.2` | Trọng số chi phí suy giảm pin. |

Đây là các trọng số tạo ra F. Chúng phải không âm và có ít nhất một cái dương.
Tăng `w_electricity` sẽ khiến solver ưu tiên tránh giờ giá cao hơn.

### 6.6. Nhóm suy giảm pin (degradation)

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `deep_charge_delta_soc` | `0.6` | Nếu một phiên sạc tăng SoC ≥ 60% thì tính là **một sự cố sạc sâu**. |
| `deep_discharge_soc` | `0.15` | Ngưỡng SoC bị coi là **xả sâu** khi đi xuống dưới 15%. |
| `discharge_reset_soc` | `0.25` | Phải sạc lại lên ≥ 25% mới thoát trạng thái "đang xả sâu". |
| `deep_charge_cost` | `0.8` | Chi phí F cho **mỗi** sự cố sạc sâu. |
| `deep_discharge_cost` | `0.6` | Chi phí F cho **mỗi** sự cố xả sâu. |
| `reserve_soc` | `0.02` | Mức pin dự trữ tối thiểu bắt buộc (2%), không bao giờ được đi xuống dưới. |

Ràng buộc validate: `reserve_soc ≤ deep_discharge_soc < discharge_reset_soc ≤ 1`.
Cơ chế "low episode" đảm bảo mỗi lần tụt xuống dưới ngưỡng chỉ tính **một** sự
cố, không tính lặp lại.

### 6.7. Nhóm rời rạc hoá bài toán sạc DP

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `power_fractions` | `[0.5, 1.0]` | Các mức công suất đặt trước được DP thử (một nửa hoặc toàn bộ công suất trụ). Mỗi mức là một lựa chọn cho bài toán con. |
| `time_step_hours` | `1/12 = 0.0833h` | Lưới thời gian (5 phút). Đồng hồ được làm tròn lên bội số `time_step_hours` để đồ thị tìm kiếm hữu hạn. |
| `soc_step` | `0.1` | Bước SoC (10%) khi sinh các mức sạc mục tiêu. |
| `energy_quantum_kwh` | `0.01` | Bước lượng tử hoá năng lượng dùng làm khoá trạng thái DP — hai nhãn cùng mọi thứ trừ năng lượng trong cùng 0.01 kWh coi như một. Nhỏ hơn = chính xác hơn nhưng nhiều nhãn hơn. |
| `candidate_stations` | `3` | Mỗi chặng DP chỉ xét tối đa 3 trạm sạc **gần nhất trên đường** đi qua. Giảm mạnh kích thước không gian tìm kiếm. |
| `max_station_hops` | `2` | Tối đa **2 trạm sạc** được chèn giữa hai điểm bắt buộc. |
| `max_labels` | `12000` | Số nhãn A* tối đa mở rộng cho một lần giải XCT. Vượt → trả `search_limit`. |
| `dp_budget_seconds` | `0.8` | Ngân sách thời gian cho **mỗi** lần gọi DP sạc. |

`max_labels` và `dp_budget_seconds` là hai cơ chế "chặn trên" độc lập; cái nào
tới trước thì dừng. `search_limit` chỉ nghĩa là "chưa chứng minh được", nên tăng
hai giá trị này có thể cải thiện chất lượng nhưng làm chậm mọi thứ.

### 6.8. Nhóm ngân sách solver

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `solver_budget_seconds` | `30.0` | Tổng ngân sách thời gian của **một lần giải** (một epoch), tính từ lúc bắt đầu. GA dừng khi hết ngân sách dù chưa hết `generations`. Greedy dùng nó làm hạn để ngừng chèn thêm khách. |

Vì mô phỏng replan nhiều epoch, tổng thời gian một lần chạy xấp xỉ
`replans * solver_budget_seconds` (cộng thêm thời gian dựng solution).

### 6.9. Nhóm tham số di truyền (GA)

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `population` | `12` | Kích thước quần thể mỗi thế hệ. |
| `generations` | `25` | Số thế hệ tối đa (còn bị chặn bởi `solver_budget_seconds`). |
| `mutation_probability` | `0.3` | Xác suất 30% một cá thể con bị đột biến. |
| `elite_size` | `2` | Số cá thể tốt nhất giữ nguyên sang thế hệ sau (chế độ scalar). |
| `vns_iterations` | `10` | Số bước VNS thử mỗi thế hệ (chỉ `ga_vns`). |

Ràng buộc: `population ≥ 2` và `1 ≤ elite_size < population`.

### 6.10. Nhóm cờ điều khiển

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `pareto_selection` | `true` | `true` = chọn lọc NSGA-II (tối ưu đa mục tiêu: unassigned, time, electricity, degradation). `false` = chọn lọc scalar theo `rank`. |
| `use_station_genes` | `true` | `true` = bật gen trạm sạc (gợi ý trạm cho DP) và lân cận charge-adjust của VNS. `false` = tắt, GA-VNS chỉ còn 3 lân cận tuyến. |
| `replan_interval_hours` | `0.5` | Trong chế độ `dynamic`, solver tái tối ưu mỗi **30 phút** mô phỏng. Nhỏ hơn = phản ứng nhanh hơn nhưng nhiều lần giải hơn (chậm hơn). Ở chế độ `static` giá trị này bị bỏ qua (replan một lần cho cả horizon). |

---

## 7. Quy trình đầy đủ (ví dụ)

```bash
# 1. cài đặt
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. (tuỳ chọn) sinh lại dataset enhanced từ XML gốc
python3 -m evrp prepare --data data/montoya-et-al-2017 --out data/enhanced \
    --config configs/benchmark.json

# 3. kiểm tra nhanh một instance
python3 -m evrp run --data data/enhanced --instance tc0c10s2cf1 \
    --algorithm ga_vns --output results/run

# 4. benchmark bộ 26 instance, 2 seed
JOBS=12 SEEDS="42 43" bash benchmarks/run_subset_26.sh

# 5. vẽ biểu đồ
python3 benchmarks/visualization.py results/benchmark_subset26
```

Kết quả và biểu đồ nằm trong `results/benchmark_subset26/`.

---

## 8. Đọc thêm

- [`ENHANCE_DATASET.md`](ENHANCE_DATASET.md) — chi tiết từng cải tiến dữ liệu và
  định dạng JSON enhanced.
- [`benchmarks/README.md`](benchmarks/README.md) — hướng dẫn benchmark gọn hơn.
