# EVRP thời gian thực — Montoya 2017

Dự án Python so sánh **Greedy + DP** với **GA + VNS + DP** cho điều độ xe giao hàng
điện có đơn hàng xuất hiện trong ngày, sạc phi tuyến, giới hạn công suất trạm và
giá điện TOU. Giao diện Streamlit phát lại nhật ký thực hiện của các xe.

Hàm mục tiêu giữ nguyên yêu cầu, **không chuẩn hóa tự động**:

$$\min F=w_1T_{total}+w_2C_{electricity}+w_3D_{battery\_degradation}.$$

## 1. Chạy dự án

Yêu cầu **Python 3.10+**. Chạy các lệnh từ thư mục chứa `app.py` và `pyproject.toml`.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Mở địa chỉ mà Streamlit in ra, mặc định `http://localhost:8501`.
Không cần API key, cơ sở dữ liệu hay dịch vụ bản đồ.

**Đặt các XML của bạn vào `data/montoya-et-al-2017/`.** Bộ đọc tìm cả thư mục con;
không yêu cầu đổi tên file hoặc chuyển chúng sang CSV. Archive mã nguồn không
đóng gói lại dataset Montoya. Nếu chưa có dataset, chọn demo trong giao diện.

```bash
# Xem các instances và kiểm tra định dạng XML
python -m evrp list

# Chạy hai phương pháp trên cùng instance và cùng luồng sự kiện
python -m evrp run --instance tc0c10s2cf1 --algorithm both --config configs/default.json --seed 42 --output results/my_run

# Chạy nhanh bằng dữ liệu giả lập có sẵn; đây KHÔNG phải Montoya
python -m evrp run --demo --config configs/demo.json --output results/demo

# Benchmark nhiều lần
python -m evrp benchmark --instances tc0c10s2cf1 tc2c10s2ct0 --config configs/benchmark_quick.json --seeds 42 43 --output results/benchmark

# Hoặc lấy 3 instances đầu tiên có không quá 20 khách hàng
python -m evrp benchmark --max-customers 20 --limit 3 --seeds 42 43 44

# Dataset ở vị trí khác
python -m evrp run --data /path/to/montoya-et-al-2017 --instance tc0c10s2cf1
```

`--instance` nhận tên instance hoặc đường dẫn XML. Khi dùng nhiều file cùng tên
trong các thư mục con, cung cấp đường dẫn cụ thể để tránh chọn nhầm.
Lõi thuật toán và CLI chỉ sử dụng thư viện chuẩn; các dependency trong
`requirements.txt` phục vụ giao diện và biểu đồ.

## 2. Cấu trúc thư mục

| Đường dẫn | Trách nhiệm |
|---|---|
| `app.py` | Giao diện Streamlit, cấu hình, phát lại, xuất kết quả |
| `evrp/domain.py` | Node, Instance, VehicleState, Action, RoutePlan, Solution |
| `evrp/config.py` | Cấu hình và kiểm tra dữ liệu nhập |
| `evrp/scenario.py` | Sinh thời điểm xuất hiện đơn hàng bằng seed |
| `evrp/io/montoya.py` | Đọc XML Montoya, hỗ trợ namespace và đổi đơn vị |
| `evrp/io/results.py` | Xuất JSON, CSV so sánh và thống kê |
| `evrp/charging/model.py` | Sạc phi tuyến, đếm sự kiện hao pin |
| `evrp/charging/tariff.py` | Tích phân chi phí điện qua các khung TOU |
| `evrp/charging/calendar.py` | Lịch đặt chỗ, số cổng và tổng công suất |
| `evrp/algorithms/charging_dp.py` | DP cho chiến lược sạc với thứ tự khách hàng cố định |
| `evrp/algorithms/evaluator.py` | Bộ đánh giá đội xe chung, lập lịch theo ưu tiên ID xe |
| `evrp/algorithms/greedy.py` | Baseline chèn đơn tham lam |
| `evrp/algorithms/ga_vns.py` | GA, lai ghép OX, đột biến, VNS |
| `evrp/simulation/engine.py` | Mô phỏng online, cam kết hành động đang thực hiện |
| `evrp/validation.py` | Kiểm tra độc lập nhật ký thực hiện |
| `evrp/visualization.py` | Lộ trình, SoC, công suất và timeline bằng Plotly |
| `configs/` | Các kịch bản JSON tái lập được |
| `tests/` | Kiểm thử dữ liệu, sạc, TOU, thuật toán, mô phỏng, giao diện |
| `docs/` | Kết quả benchmark mẫu và ghi chú thí nghiệm |
| `data/demo.xml` | Fixture giả lập có 6 khách hàng, 2 trạm |
| `data/montoya-et-al-2017/` | Dataset XML bạn cung cấp |
| `results/` | Đầu ra các lượt chạy |

## 3. Dataset và giả định bổ sung

Montoya 2017 có sạc **phi tuyến**, biểu diễn bằng các đoạn tuyến tính của hàm
năng lượng tích lũy theo thời gian. Bộ gốc không có đơn hàng động, TOU, giới hạn
công suất tổng trạm hoặc mô hình chi phí hao pin được dùng trong dự án này.

Reader đọc các trường:

- `node type="0/1/2"`: depot / khách hàng / trạm sạc; `cx`, `cy`: tọa độ.
- `requests/request`: khách hàng và `service_time`.
- `vehicle_profile`: depot, `speed_factor`, `max_travel_time`.
- `custom`: `battery_capacity`, `consumption_rate`, `charging_functions`.
- `node/custom/cs_type`: loại đường cong của trạm.

**Đơn vị Montoya gốc:** Wh, Wh/km, giờ và km/h. Reader đổi năng lượng sang kWh,
không đoán đơn vị từ độ lớn con số. Với XML đã chuyển sang kWh, chọn
`--energy-unit kWh` hoặc đổi tùy chọn trong giao diện. Bộ gốc có pin 16 kWh,
tốc độ 40 km/h và mức tiêu thụ 0.125 kWh/km; reader đọc từ XML, không hardcode.

Tọa độ sử dụng để tính khoảng cách Euclidean và vẽ mặt phẳng km, không phải
kinh độ/vĩ độ. Một loại xe đồng nhất, một depot; mỗi xe có thể thực hiện nhiều
chuyến trong ngày. Pin ban đầu đầy. Không thêm tải trọng, giao thông, nhiệt độ,
phụ tải HVAC hoặc cửa sổ giao hàng ngoài thời hạn hoạt động chung của XML.

Các tham số đội xe, trạm, giá điện, hao pin và thời điểm phát sinh đơn là
**giả lập**, được lưu trong cấu hình. Giá điện và hao pin dùng cùng một đơn vị
tiền giả lập, không đại diện biểu giá điện Việt Nam hay giá thay pin thực tế.
Hiệu suất sạc được giả định bằng 1; không có sạc tại depot và không có V2G.

`dynamic_fraction` chọn tỷ lệ khách hàng có release > 0. Các release được sinh
đều trong `(0, release_until_fraction × horizon]` với seed. Có thể không phục vụ
hết đơn nếu release quá muộn, số xe ít hoặc các giới hạn tìm kiếm quá chặt.
Generator không bảo đảm mọi kịch bản khả thi: nhật ký luôn giữ danh sách đơn
chưa phục vụ, không xóa đơn hoặc nới thời hạn để tạo kết quả tốt.

## 4. Mô hình toán học

### 4.1. Tập, tham số và biến

| Ký hiệu | Ý nghĩa |
|---|---|
| $I,S,V$, $0$ | Khách hàng, trạm, xe, depot |
| $H$ | Thời hạn hoạt động, lấy từ `max_travel_time` |
| $r_i,g_i$ | Thời điểm đơn i xuất hiện và thời gian phục vụ |
| $d_{ij},t_{ij},e_{ij}$ | Khoảng cách, thời gian, năng lượng di chuyển |
| $Q,q_v(t)$ | Dung lượng pin và năng lượng pin hiện tại |
| $m_s,G_s,P_s^{port}$ | Số cổng, công suất tổng, công suất mỗi cổng |
| $\pi(t)$ | Giá điện theo giờ trong ngày, lặp lại mỗi 24 giờ |
| $x_{vij}$ | Xe v sử dụng chặng i → j; các lần ghé được phân biệt trong nhật ký |
| $b_{vk},a_{vk}$ | Bắt đầu và kết thúc hành động k của xe v |
| $q^-_{vk},q^+_{vk}$ | Năng lượng trước/sau hành động |
| $u_{vk},p_{vk}(t)$ | Công suất được đặt chỗ và công suất thực tế khi sạc |

$$d_{ij}=\sqrt{(x_i-x_j)^2+(y_i-y_j)^2},\quad
t_{ij}=d_{ij}/speed,\quad e_{ij}=consumption\times d_{ij}.$$

Trong code, `routes` biểu diễn thứ tự khách hàng; `Action` biểu diễn các chặng,
phiên sạc, chờ và phục vụ với mốc giờ và năng lượng cụ thể.

### 4.2. Thành phần thời gian

$$T_{total}=\sum_{v\in V}(T_v^{drive}+T_v^{wait}+T_v^{charge}).$$

Chờ gồm xếp hàng trạm, chờ TOU, chờ đơn đã biết khi cần và thời gian căn lưới
DP. **Thời gian phục vụ không cộng vào F** theo định nghĩa của đề bài, nhưng
vẫn làm tiến đồng hồ xe và phải nằm trong H. Xe đỗ tại depot khi không có công
việc được xem là ngoài ca, không cộng thời gian đỗ này vào chờ vận hành.

`makespan_hours` được báo cáo riêng, không thay thế `T_total`.

### 4.3. Sạc phi tuyến và TOU

Với breakpoint $(q_l,\tau_l)$ của đường cong sạc trạm:

$$P_l^{battery}=\frac{q_{l+1}-q_l}{\tau_{l+1}-\tau_l},\qquad
p(t)=\min(P_l^{battery},u),\qquad
\Delta t_l=\frac{\Delta q_l}{p(t)}.$$

Một hành động sạc có thể đi qua nhiều đoạn SoC. Công suất thực giảm khi vào
đoạn taper của đường cong gốc; không dùng công thức sạc tuyến tính toàn miền.

$$C_{electricity}=\sum_{v,s}\int_{v\text{ sạc tại }s}\pi(t)p_{v,s}(t)\,dt.$$

Code tích phân riêng tại các điểm đổi công suất và khung TOU. Đơn vị:
`kW × giờ × tiền/kWh`. Khung TOU là giờ đồng hồ, còn nhật ký dùng thời gian
trôi qua từ đầu mô phỏng; `start_clock_hour` nối hai cách biểu diễn.

### 4.4. Chi phí hao pin

$$D_{battery\_degradation}=c_{ch}N_{deep\_charge}+c_{dis}N_{deep\_discharge}.$$

Quy tắc xấp xỉ được công bố rõ:

$$deep\_charge_k=\mathbf{1}\left[(q^+_k-q^-_k)/Q\ge\theta_{ch}\right].$$

Mặc định $\theta_{ch}=0.60$: một phiên nạp ít nhất 60% dung lượng được tính
một lần sạc sâu. **Sạc sâu không phải sạc nhanh.** Một lần dừng ở trạm chỉ có
một phiên sạc; không chia phiên đang thực hiện khi tái tối ưu để né chi phí.

Xả cạn là một lần SoC đi từ trên/ngang $\theta_{low}$ xuống dưới ngưỡng đó.
Trong cùng một đợt SoC thấp, các chặng tiếp theo không bị đếm lại. Chỉ kích
hoạt lại bộ đếm sau khi sạc lên ít nhất $\theta_{reset}>\theta_{low}$.
Mặc định các ngưỡng là 15% và 25%; SoC dự trữ tối thiểu là 2%.

Đây là mô hình chi phí theo sự kiện phục vụ bài tập, không phải mô hình điện
hóa dự báo SOH. Không tính hao pin của các hành động chưa thực hiện.

### 4.5. Ràng buộc

1. Mỗi khách hàng được phục vụ một lần trong lời giải hoàn chỉnh; thời điểm
   bắt đầu phục vụ $b_i\ge r_i$.
2. Các hành động một xe liên tục về vị trí, năng lượng và không chồng thời
   gian; xe xuất phát/kết thúc tại depot, kết thúc không muộn hơn H.
3. Di chuyển cập nhật $q^+=q^--e_{ij}$; chờ/phục vụ giữ nguyên năng lượng.
4. $Q\times reserve\_soc\le q_v(t)\le Q$; sạc chỉ ở trạm.
5. Mỗi phiên sạc giữ một cổng suốt khoảng nửa mở $[b,a)$; không ngắt phiên.
6. Giới hạn số cổng và công suất:

$$\sum_v\mathbf{1}[v\text{ đang sạc tại }s,t]\le m_s,$$
$$0<u_{vk}\le P_s^{port},\qquad
\sum_{k:\,s(k)=s,\,b_k\le t<a_k}u_{vk}\le G_s.$$

Trong triển khai, một phiên **đặt chỗ công suất cố định u**, còn công suất
thực tế p(t) có thể giảm theo taper. Vì $p(t)\le u$, giới hạn công suất thực
được bảo đảm. Phần công suất đặt chỗ nhưng chưa dùng không được tự động phân
phối lại. Đây là chính sách bảo thủ, chưa phải tối ưu chia sẻ công suất liên
tục toàn đội xe.

7. Tái tối ưu giữ nguyên các hành động đã hoàn thành và hành động đã bắt đầu,
   cùng lịch đặt chỗ sạc tương ứng; chỉ thay đổi phần chưa cam kết.

## 5. Baseline: Greedy + DP

### 5.1. Greedy khởi tạo và chèn đơn

Sắp xếp các đơn chưa được phân công theo release, khoảng cách đến depot và ID.
Với từng đơn, thử các vị trí chèn trong các tuyến xe. Mỗi phương án được giải
sạc và kiểm tra lịch trạm; chọn phương án khả thi có mức tăng F nhỏ nhất.
Không chấp nhận việc làm mất các đơn đã được phân công để chèn đơn mới.

```text
solution ← đánh giá các tuyến hiện tại bằng FleetEvaluator
for customer in các đơn chưa phân công:
    candidates ← chèn customer tại từng vị trí của từng xe
    với mỗi candidate: giải sạc DP + đặt chỗ trạm
    giữ các candidate phục vụ customer và giữ toàn bộ đơn đã phân công
    nếu có candidate hợp lệ: chọn candidate có F nhỏ nhất
return solution cùng danh sách đơn chưa phân công
```

### 5.2. DP cho thứ tự khách hàng cố định

"Fixed route" trong dự án nghĩa là **thứ tự khách hàng đã cố định**. Vẫn được
chèn các trạm giữa khách hàng để quyết định sạc ở đâu và bao nhiêu.

Trạng thái nhãn:

$$z=(k,n,h,q,\ell,B,c).$$

- k: khách hàng tiếp theo trong chuỗi cố định; n: node hiện tại.
- h: chỉ số bước thời gian; q: năng lượng thực còn lại, không làm tròn xuống.
- $\ell$: đang ở trong đợt SoC thấp hay không.
- B: các trạm đã ghé trong khoảng giữa hai khách hàng.
- c: đã sạc tại lần dừng hiện tại hay chưa.

Hành động: đi tới khách hàng tiếp theo/depot; ghé trạm; chờ một bước tại trạm;
sạc tới một SoC mục tiêu bằng một mức công suất đặt chỗ.

Mức đích sạc gồm lưới `soc_step × Q`, toàn bộ breakpoint và Q. Mức u lấy từ
`power_fractions × min(charger_kw, station_power_kw)`. Thời gian di chuyển,
phục vụ và sạc là giá trị vật lý; sau mỗi chuyển trạng thái, thời gian được
căn lên lưới bằng một hành động chờ có ghi nhận trong mục tiêu.

$$g(z')=\min\{g(z')\,,\;g(z)+w_1\Delta T+w_2\Delta C+w_3\Delta D\}.$$

Code dùng label-setting DP và hàng đợi A* với cận dưới khả chấp về di chuyển,
năng lượng cần sạc, công suất nhanh nhất và giá thấp nhất. Nhãn đích đầu tiên
tối ưu **trong đồ thị rời rạc đã quy định**, với lịch trạm bên ngoài cố định.

Giới hạn mặc định:

- Bước thời gian 5 phút; bước SoC mục tiêu 10%.
- Xét tối đa 3 trạm có độ vòng đường nhỏ nhất tại mỗi trạng thái.
- Tối đa 2 trạm giữa hai khách hàng; không lặp trạm trong cùng khoảng.
- Không ghé trạm thuần túy để đi xuyên qua mà không sạc; mạng Euclidean cho
  phép đi trực tiếp.
- `max_labels=12000`, `dp_budget_seconds=0.8`.

Các trạng thái kết thúc: `optimal_discrete`, `search_limit`,
`no_path_in_discrete_graph`. **`search_limit` không chứng minh vô nghiệm.**
`no_path_in_discrete_graph` chỉ kết luận trong đồ thị đã giới hạn, không phải
toàn bài toán liên tục. Để mở rộng tìm kiếm, tăng thời gian, giảm bước lưới,
đặt `candidate_stations=0` và `max_labels=0`, tăng `max_station_hops`.

### 5.3. Ghép lịch sạc nhiều xe

Giải các xe tuần tự theo ID tăng dần. DP của xe sau đọc lịch đặt chỗ đã chốt
của xe trước và các phiên sạc đang thực hiện. Phương án thử dùng bản sao lịch,
không ghi đè lịch mô phỏng nếu bị loại. Cache chỉ giữ kết quả tìm kiếm hoàn
tất, không giữ timeout như một kết luận vô nghiệm.

**DP không tối ưu toàn bộ đội xe cùng lúc.** Chính sách ưu tiên xe, giới hạn
đồ thị và giới hạn thời gian áp dụng giống nhau cho hai phương pháp.

## 6. GA + VNS + DP

Chromosome có hai phần: hoán vị khách hàng và gene xe cho từng khách hàng.
Decode lấy các khách hàng thuộc một xe theo thứ tự trong hoán vị.

1. Khởi tạo bằng Greedy và các nghiệm biến đổi/ngẫu nhiên. Chi phí khởi tạo
   tính trong ngân sách của GA; không được cấp thêm ngân sách miễn phí.
2. Tournament chọn cha mẹ; order crossover OX giữ mỗi khách hàng đúng một lần.
   Gene xe được lấy từ cha hoặc mẹ theo từng khách hàng.
3. Đột biến hoán đổi thứ tự hoặc đổi xe được phân công.
4. Decode bằng cùng FleetEvaluator và charging DP của baseline.
5. VNS trên cá thể tốt: relocate, swap (cả trong/giữa tuyến), 2-opt trong tuyến.
   Cải thiện thì quay lại neighborhood đầu tiên, nếu không thì đổi neighborhood.
6. Giữ elite; dừng khi hết thế hệ hoặc ngân sách thời gian.

```text
incumbent ← Greedy trong một phần ngân sách
population ← chromosome Greedy và các biến thể
while còn thế hệ và thời gian:
    sắp xếp population theo tính khả dụng, số đơn chưa phân công, F
    cải thiện cá thể tốt bằng VNS
    giữ elite
    tournament → OX → mutation → DP decode
    cập nhật incumbent
return incumbent
```

Khi đang tìm nghiệm, nghiệm không thể đưa xe về depot bị xếp sau nghiệm khả
dụng; sau đó ưu tiên phục vụ nhiều đơn hơn, rồi tối thiểu F. Đây là quy tắc
khả thi để tìm lời giải, **không thêm một thành phần phạt vào hàm mục tiêu**.
F của một lượt chưa phục vụ hết đơn không được dùng như F hợp lệ của toàn đề.

GA + VNS chưa bảo đảm tìm nghiệm tối ưu hay luôn tốt hơn Greedy. Trong môi
trường động, một quyết định tốt cho các đơn đã biết có thể bất lợi khi đơn
mới xuất hiện; không dùng dữ liệu tương lai để né tình huống đó.

## 7. Mô phỏng online

Tại mỗi thời điểm release hoặc tick thử lại đơn tồn:

1. Cam kết các hành động đã thực hiện và hành động đang chạy đến hết.
2. Nếu đang đi đến khách hàng, cam kết luôn phần phục vụ ngay sau chặng đó.
3. Giữ nguyên phiên sạc đang chạy, cập nhật trạng thái SoC thấp/sạc tại chỗ.
4. Công bố các đơn có release không lớn hơn thời gian hiện tại.
5. Solver chỉ nhận các đơn đã công bố và chưa nằm trong phần cam kết.
6. Nếu có đơn mới hoặc tồn chưa phân công, tái tối ưu từ trạng thái neo của
   mỗi xe; các xe đang chạy có trạng thái neo ở cuối hành động đã cam kết.
7. Nếu phương án mới không tốt hơn/không khả dụng, giữ lịch cũ, đơn mới chờ
   và được thử lại ở tick kế tiếp. Cuối ngày báo đầy đủ đơn chưa phục vụ.

Đây là **mô phỏng ra quyết định online**, không phải kết nối GPS hoặc đơn hàng
thật. Đồng hồ mô phỏng không tiến theo thời gian CPU; thời gian tính toán
được ghi riêng tại mỗi lần tái tối ưu. Deadline dùng thời gian thực của máy;
kiểm tra theo vòng lặp, nên có thể vượt vài mili giây do thao tác đang chạy.
Kết quả có thể khác giữa máy khi deadline bị chạm, dù seed giống nhau.

## 8. Giao diện

- Chọn XML hoặc demo; chỉnh xe, đơn động, trạm, trọng số, ngưỡng hao pin và TOU.
- Chạy từng phương pháp hoặc chạy cả hai với cùng scenario.
- Hiển thị F, các thành phần thô, đóng góp có trọng số, số đơn đã phục vụ.
- Phát/tạm dừng, chọn thời điểm, đổi tốc độ phát; vị trí xe được nội suy từ
  nhật ký, SoC khi sạc được nội suy theo đúng các đoạn công suất.
- Ẩn khách hàng chưa xuất hiện trong khung phát lại; hiển thị tuyến đã đi.
- SoC, ngưỡng xả cạn, công suất thực và công suất đặt chỗ so với giới hạn trạm.
- Timeline di chuyển/chờ/sạc/phục vụ, lịch sử tìm kiếm theo từng epoch.
- Tải CSV và JSON. Các bảng/biểu đồ thống kê toàn lượt chạy là kết quả sau mô
  phỏng, không phải thông tin được solver biết trước.

## 9. Thí nghiệm và đọc kết quả

| Cấu hình | Đặc điểm |
|---|---|
| `static.json` | Không có đơn động, giá cố định, trạm ít gây nghẽn |
| `tou.json` | Tĩnh, có TOU, trạm ít gây nghẽn |
| `limited_power.json` | Tĩnh, TOU, công suất tổng trạm 30 kW |
| `default.json` | Động 50%, release trong 35% đầu ngày, TOU, công suất 40 kW |
| `benchmark_quick.json` | Động 50%, release trong 5% đầu ngày; 5 giây/lần tái tối ưu |
| `demo.json` | Fixture nhỏ, 3 xe, tổng công suất trạm 6 kW |

Số xe mặc định 5 là giả định thí nghiệm, không phải thông số đội xe của
Montoya. Với instances 20–80 khách hàng, cần cấu hình đội xe phù hợp. Không
so sánh F thấp do không phục vụ hết khách hàng với nghiệm hoàn chỉnh.

Đầu ra:

- `<instance>_<algorithm>_seed<seed>.json`: cấu hình, release, hành động, từng
  quyết định, thời gian tính toán, kiểm tra tính đúng và metric.
- `comparison.csv`: tất cả lượt chạy, kể cả chưa hoàn thành.
- `statistics.csv`: tỷ lệ hoàn thành, số đơn trung bình; trung bình/độ lệch
  chuẩn T/C/D/F **chỉ trên các lượt hoàn thành và đạt kiểm tra**.

`objective_valid=true` chỉ khi toàn bộ đơn được phục vụ và nhật ký hợp lệ.
`F` vẫn được ghi cho công việc thực hiện trong lượt chưa hoàn thành để kiểm
tra/debug; không dùng nó để kết luận thắng/thua. Khi tập lượt hoàn thành
khác nhau giữa hai thuật toán, cần so sánh bổ sung trên **các seed cùng hoàn
thành**; số liệu tổng hợp riêng mỗi thuật toán chưa phải kiểm định ghép cặp.

Để so sánh khoa học: dùng cùng XML, seed sự kiện, cấu hình, deadline, chính
sách lập lịch sạc, máy chạy và độ phân giải DP. Báo riêng tỷ lệ hoàn thành,
F, T/C/D, số sự kiện hao pin và độ trễ tái tối ưu. Kết quả mẫu trong
`docs/EXPERIMENTS.md` là kiểm tra chạy thực tế, không phải khẳng định thống kê.

## 10. Kiểm thử

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

Kiểm thử kiểm tra đơn vị/namespace XML, dữ liệu lỗi, taper và giới hạn công
suất, tích phân TOU qua nửa đêm, giới hạn cổng độc lập với kW, chờ giá rẻ,
sạc một phần, timeout DP, tính toàn vẹn chromosome, đếm hao pin, không lộ
release tương lai, giữ phiên sạc đang chạy, phát hiện nhật ký bị sửa và luồng
chạy/seek trên Streamlit. Nếu có dữ liệu Montoya trong thư mục mặc định, test
tích hợp đọc toàn bộ XML; khi chưa có dữ liệu này, test đó được skip.

## 11. Nguồn tham khảo

- Montoya, A., Guéret, C., Mendoza, J.E., Villegas, J.G. (2017).
  *The electric vehicle routing problem with nonlinear charging function*.
  Transportation Research Part B, 103, 87–110.
  https://doi.org/10.1016/j.trb.2017.02.004
- Dataset gốc: https://www.vrp-rep.org/datasets/item/2016-0020.html
- Định nghĩa benchmark E-VRP-NL và giới hạn cổng E-VRP-NL-C:
  https://dimacs.rutgers.edu/programs/implementation-challenges/vehicle-routing/implementation-challenge-vehicle-routing/electric-vehicle-routing-problem

Mã nguồn trong dự án này tự triển khai các bộ giải; không dùng lời giải tốt
nhất của Montoya làm kết quả cho bài toán mở rộng có TOU/động/hao pin.
