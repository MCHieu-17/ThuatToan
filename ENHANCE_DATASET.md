# Cải tiến bộ dữ liệu (Enhanced Dataset)

Tài liệu mô tả bộ dữ liệu gốc và các cải tiến được thêm vào cho bài toán EVRP
(giao hàng bằng xe điện). Pipeline tạo dữ liệu nằm ở `evrp/io/enhance.py`.

---

## 1. Dữ liệu gốc — Montoya et al. 2017

**Vị trí:** `data/montoya-et-al-2017/` (120 file XML, giữ nguyên không sửa).

**Nguồn:** https://www.vrp-rep.org/datasets/item/2016-0020.html

### Cấu trúc XML

```xml
<instance>
  <info>
    <dataset>Montoya et al. 2016</dataset>
    <name>tc0c10s2cf1</name>
  </info>
  <network>
    <nodes>
      <node id="0" type="0"> <cx>77.59</cx> <cy>78.35</cy> </node>          <!-- depot -->
      <node id="1" type="1"> <cx>12.44</cx> <cy>47.61</cy> </node>          <!-- customer -->
      <node id="11" type="2">                                               <!-- charging station -->
        <cx>93.39</cx> <cy>10.8</cy>
        <custom><cs_type>fast</cs_type></custom>
      </node>
    </nodes>
    <euclidean />
    <decimals>14</decimals>
  </network>
  <fleet>
    <vehicle_profile type="0">
      <departure_node>0</departure_node>
      <arrival_node>0</arrival_node>
      <max_travel_time>10</max_travel_time>   <!-- horizon, giờ -->
      <speed_factor>40</speed_factor>          <!-- km/h -->
      <custom>
        <consumption_rate>125</consumption_rate>   <!-- Wh/km -->
        <battery_capacity>16000</battery_capacity>  <!-- Wh -->
        <charging_functions>
          <function cs_type="fast">
            <breakpoint> <battery_level>0</battery_level>     <charging_time>0.0</charging_time> </breakpoint>
            <breakpoint> <battery_level>13600</battery_level> <charging_time>0.31</charging_time> </breakpoint>
            <breakpoint> <battery_level>15200</battery_level> <charging_time>0.39</charging_time> </breakpoint>
            <breakpoint> <battery_level>16000</battery_level> <charging_time>0.51</charging_time> </breakpoint>
          </function>
        </charging_functions>
      </custom>
    </vehicle_profile>
  </fleet>
  <requests>
    <request id="1" node="1"> <service_time>0.5</service_time> </request>
    ...
  </requests>
</instance>
```

### Đặc điểm dữ liệu gốc

| Thành phần | Ý nghĩa |
|---|---|
| `type=0` | Depot (nơi xuất phát & kết thúc) |
| `type=1` | Khách hàng (customer) |
| `type=2` | Trạm sạc (charging station), có `cs_type`: `slow` / `normal` / `fast` |
| `<cx>, <cy>` | Tọa độ Euclid tính bằng km |
| `<max_travel_time>` | Thời gian tối đa của lộ trình (giờ) |
| `<speed_factor>` | Tốc độ xe (km/h) |
| `<consumption_rate>` | Mức tiêu thụ năng lượng (Wh/km) |
| `<battery_capacity>` | Dung lượng pin (Wh) |
| `charging_functions` | Hàm sạc phi tuyến dạng piecewise-linear (3 điểm gãy) |
| `<service_time>` | Thời gian phục vụ mỗi khách (giờ) |

**Quy ước tên file:** `tcAcBsCcDE`
- `A`: cách đặt khách — `0`=ngẫu nhiên đều, `1`=cụm, `2`=hỗn hợp
- `B`: số khách
- `C`: số trạm sạc
- `D`: `t`=đặt trạm bằng p-median, `f`=đặt trạm ngẫu nhiên
- `E`: số thứ tự instance (0–4)

**Đơn vị gốc:** Wh, Wh/km, giờ, km/h. Trong code, năng lượng được quy đổi về kWh
một lần duy nhất ở `evrp/io/montoya.py` (chia 1000) để phần còn lại không phải
đoán đơn vị.

**Hạn chế của dữ liệu gốc đối với bài toán của đồ án:**
- Chưa có ràng buộc **công suất trạm sạc** (mỗi trạm chỉ là một điểm, không giới
  hạn số cổng hay tổng công suất).
- Chưa có **giá điện theo khung giờ** (TOU) và **chi phí suy giảm pin**.
- Chưa có **đơn hàng realtime** (mọi khách đều sẵn sàng từ đầu).
- Chưa chỉ rõ **số lượng xe** cho các bài toán nhiều xe.

---

## 2. Các cải tiến thêm vào

Chạy sinh dữ liệu:

```bash
python3 -m evrp prepare --data data/montoya-et-al-2017 --out data/enhanced --config configs/default.json
```

Kết quả: 120 file JSON tại `data/enhanced/`, mỗi file tương ứng một instance XML.
Sinh lại với cùng `seed` (mặc định 42) cho ra kết quả **giống hệt** (reproducible).

### 2.1. Đơn hàng realtime (release times) — *đang dùng*

Một phần khách hàng được gán **thời điểm xuất hiện** (`release_hours`) thay vì
sẵn sàng ngay từ đầu. Đây là phần "realtime" hiện tại của bộ dữ liệu: thông tin
được lưu **tĩnh** trong file JSON, mô tả *đơn nào đến lúc nào*.

Cơ chế sinh (`build_enhanced`):
- `dynamic_fraction` (mặc định `0.5`): tỉ lệ khách được coi là "động".
- `release_until_fraction` (mặc định `0.35`): các đơn động được rải đều trong
  khoảng `[1e-6, release_until_fraction * horizon]` giờ.
- Các khách còn lại có `release_hours = 0.0` (sẵn sàng từ đầu).
- Dùng `random.Random(seed)` nên tái lập được.

Ví dụ (`tc0c10s2cf1`, horizon = 10h → đơn động rải trong ~3.5h đầu):

```json
{ "id": 3, "kind": "customer", "release_hours": 0.0 },
{ "id": 1, "kind": "customer", "release_hours": 0.488384 },
{ "id": 5, "kind": "customer", "release_hours": 2.592337 }
```

> **Ghi chú quan trọng:** Bộ dữ liệu này chỉ *lưu thời điểm release*. Cách tầng
> mô phỏng (`evrp/simulation.py`) đọc và xử lý các release time này là một chuyện
> khác, không thuộc phạm vi cải tiến dữ liệu. Hiện tại tài liệu này chỉ mô tả
> phần dữ liệu realtime **đang được dùng**, không mô tả các thay đổi mô phỏng
> khác.

### 2.2. Trạm sạc giới hạn công suất

Mỗi trạm sạc được bổ sung tham số theo loại (`cs_type`), lấy từ
`config.stations_by_type`:

| Loại | ports (số cổng) | power_kw (tổng công suất trạm) | charger_kw (công suất tối đa mỗi trụ) |
|---|---|---|---|
| `fast` | 2 | 50.0 | 44.0 |
| `normal` | 2 | 22.0 | 22.0 |
| `slow` | 1 | 7.0 | 7.0 |

Trong JSON:

```json
"stations": {
  "11": { "ports": 2, "power_kw": 50.0, "charger_kw": 44.0 },
  "12": { "ports": 2, "power_kw": 50.0, "charger_kw": 44.0 }
}
```

Ràng buộc này được thực thi trong `evrp/charging/calendar.py`: một trạm không
nhận thêm phiên sạc nếu vượt số cổng (`ports`) hoặc vượt tổng công suất
(`power_kw`) tại cùng thời điểm.

### 2.3. Giá điện theo khung giờ (TOU)

Biểu giá TOU được thêm vào mỗi instance (mặc định trong `config.tou`):

```json
"tou": [
  { "start": 0.0,  "end": 9.0,  "price": 0.12 },
  { "start": 9.0,  "end": 12.0, "price": 0.25 },
  { "start": 12.0, "end": 17.0, "price": 0.45 },
  { "start": 17.0, "end": 24.0, "price": 0.18 }
]
```

- Các khung phủ liên tục `[0, 24]`, đơn vị giá là tiền/kWh.
- `start_clock_hour` (mặc định `8.0`) liên kết đồng hồ mô phỏng (giờ trôi từ đầu
  ngày) với giờ tường trong ngày.
- Việc tính chi phí theo từng đoạn thời gian được thực hiện trong
  `evrp/charging/tariff.py` (hỗ trợ cả trường hợp vắt qua nửa đêm).

### 2.4. Chi phí suy giảm pin (battery degradation)

Các tham số suy giảm pin được thêm vào mỗi instance:

```json
"degradation": {
  "deep_charge_delta_soc": 0.6,
  "deep_discharge_soc": 0.15,
  "discharge_reset_soc": 0.25,
  "deep_charge_cost": 0.8,
  "deep_discharge_cost": 0.6,
  "reserve_soc": 0.02
}
```

| Tham số | Ý nghĩa |
|---|---|
| `deep_charge_delta_soc` | Ngưỡng tăng SoC trong một phiên sạc bị coi là "sạc sâu" |
| `deep_discharge_soc` | Ngưỡng SoC bị coi là "xả sâu" khi đi xuống dưới mức này |
| `discharge_reset_soc` | Mức SoC cần đạt lại để thoát trạng thái xả sâu |
| `deep_charge_cost` | Chi phí một biến cố sạc sâu |
| `deep_discharge_cost` | Chi phí một biến cố xả sâu |
| `reserve_soc` | Mức SoC dự trữ tối thiểu bắt buộc |

### 2.5. Số lượng xe (fleet) theo hình học

Dữ liệu gốc không nêu số xe. Bộ enhanced sinh fleet dựa trên **khối lượng công
việc thời gian**, thay vì một tỉ lệ cứng khách/xe (vì khách Montoya rất xa nhau,
một chuyến đi-về có thể đã chiếm phần lớn pin và ngày làm việc):

- Mỗi khách: work = thời gian đi-về depot + thời gian phục vụ.
- Một xe không vượt `fleet_time_utilization * horizon` (mặc định `0.75`).
- `fleet_clustering_discount` (mặc định `1.0`) chiết khấu phần di chuyển khi
  khách gần nhau.
- Năng lượng **không** phải ràng buộc cứng vì xe có thể nạp lại tại trạm sạc.
- Khách có chuyến riêng vượt ngày được cấp xe riêng.

Trường `vehicles` trong JSON lưu kết quả. Ví dụ 10 khách → 4–7 xe, 320 khách →
122–169 tùy địa lý từng instance. Nếu `config.vehicles > 0` thì dùng giá trị chỉ
định thay vì ước lượng.

---

## 3. Định dạng file JSON enhanced

Format tag: `"format": "evrp-enhanced-1"`.

```json
{
  "format": "evrp-enhanced-1",
  "name": "tc0c10s2cf1",
  "source": "data/montoya-et-al-2017/tc0c10s2cf1.xml",
  "seed": 42,
  "energy_unit": "kWh",
  "depot": 0,
  "capacity_kwh": 16.0,
  "consumption_kwh_km": 0.125,
  "speed_kmh": 40.0,
  "horizon_hours": 10.0,
  "vehicles": 4,
  "start_clock_hour": 8.0,
  "dynamic_fraction": 0.5,
  "release_until_fraction": 0.35,
  "tou": [ ... ],
  "degradation": { ... },
  "curves": {
    "fast": [[0.0, 0.0], [13.6, 0.31], [15.2, 0.39], [16.0, 0.51]]
  },
  "nodes": [
    { "id": 0, "kind": "depot",    "x": 77.59, "y": 78.35, "service_hours": 0.0, "station_type": "", "release_hours": 0.0 },
    { "id": 1, "kind": "customer", "x": 12.44, "y": 47.61, "service_hours": 0.5, "station_type": "", "release_hours": 0.488384 },
    { "id": 11, "kind": "station", "x": 93.39, "y": 10.8, "service_hours": 0.0, "station_type": "fast", "release_hours": 0.0 }
  ],
  "stations": {
    "11": { "ports": 2, "power_kw": 50.0, "charger_kw": 44.0 }
  }
}
```

### Bảng tóm tắt các cải tiến

| # | Cải tiến | Trường dữ liệu | Trạng thái |
|---|---|---|---|
| 1 | Đơn hàng realtime | `release_hours`, `dynamic_fraction`, `release_until_fraction` | Đang dùng |
| 2 | Trạm sạc giới hạn công suất | `stations[].ports/power_kw/charger_kw` | Đang dùng |
| 3 | Giá điện TOU | `tou`, `start_clock_hour` | Đang dùng |
| 4 | Suy giảm pin | `degradation.*` | Đang dùng |
| 5 | Số xe theo hình học | `vehicles`, `fleet_*` | Đang dùng |
| — | Đơn vị quy đổi | `energy_unit: "kWh"` (từ Wh gốc) | Đang dùng |

---

## 4. Tái lập & kiểm chứng

- Dữ liệu gốc **không bị chỉnh sửa**; mọi cải tiến nằm ở file JSON mới.
- `build_enhanced` là hàm thuần (pure) theo `(instance, config, seed)`; sinh lại
  toàn bộ 120 file cho kết quả khớp 100%.
- Hàm `load_enhanced` đọc JSON trả về `(Instance, ScenarioMeta)`; `apply_meta`
  áp các tham số scenario (TOU, degradation, dynamic) trở lại `Config` khi chạy.
