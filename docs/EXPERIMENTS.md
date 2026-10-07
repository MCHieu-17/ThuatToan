# Kết quả chạy kiểm tra

Các số dưới đây được tạo bằng lượt chạy thật trên XML Montoya tải từ VRP-REP. Đây là kiểm tra chức năng với 2 instances × 2 seed × 2 phương pháp, chưa phải nghiên cứu thống kê quy mô lớn.

## Cấu hình

- `configs/benchmark_quick.json`: 5 xe, 50% đơn động; đơn mới xuất hiện trong 5% đầu ngày (0.5 giờ trên instance có H=10 giờ).
- 2 cổng/trạm, tổng công suất 40 kW, mỗi cổng 44 kW; TOU và các hệ số hao pin trong JSON.
- 5 giây tối đa/lần tái tối ưu; DP 0.8 giây/lần, bước thời gian 5 phút, bước SoC 10%.
- Cùng luồng release và các tham số cho cả hai phương pháp. Giá trị F không chuẩn hóa.
- Môi trường kiểm tra: Python 3.12.14, Streamlit 1.65.0, Plotly 7.1.0, pandas 2.2.3, pytest 9.1.1.

## Số đo

| Instance | Seed | Phương pháp | Đã phục vụ | F | T (giờ) | Tiền điện | Hao pin | CPU mô phỏng (s) |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| tc0c10s2cf1 | 42 | Greedy + DP | 9/10 | Không hợp lệ¹ | 21.7818 | 13.4271 | 4.8000 | 2.30 |
| tc0c10s2cf1 | 42 | GA + VNS + DP | 10/10 | 38.8215 | 30.6649 | 21.7220 | 8.2000 | 9.87 |
| tc0c10s2cf1 | 43 | Greedy + DP | 10/10 | 33.7489 | 26.6561 | 19.1094 | 6.8000 | 1.37 |
| tc0c10s2cf1 | 43 | GA + VNS + DP | 10/10 | 39.8225 | 30.2472 | 25.9179 | 9.0000 | 9.86 |
| tc2c10s2ct0 | 42 | Greedy + DP | 10/10 | 17.1400 | 14.7269 | 7.2438 | 1.2000 | 1.73 |
| tc2c10s2ct0 | 42 | GA + VNS + DP | 10/10 | 15.1836 | 13.4769 | 4.8890 | 1.2000 | 10.99 |
| tc2c10s2ct0 | 43 | Greedy + DP | 10/10 | 17.8255 | 15.4170 | 7.2281 | 1.2000 | 1.97 |
| tc2c10s2ct0 | 43 | GA + VNS + DP | 10/10 | 15.3134 | 13.5837 | 4.9655 | 1.2000 | 10.94 |

¹ F thô vẫn được lưu trong CSV để debug, nhưng lượt chưa phục vụ đủ đơn không có F hợp lệ cho toàn bài toán. T/C/D của dòng này chỉ tính các hành động thực hiện.

Tất cả 8 nhật ký vượt qua bộ kiểm tra độc lập: năng lượng, thời gian, phi tuyến, TOU, cổng, công suất, sự kiện hao pin, phục vụ sau release và trở về depot.

## Diễn giải

- Trên `tc2c10s2ct0`, cả hai seed đều hoàn thành đủ đơn; GA + VNS giảm F trong các lượt này.
- Trên `tc0c10s2cf1`, seed 42 baseline chưa hoàn thành; không tính phần trăm cải thiện bằng F của lượt này.
- Seed 43 của instance đó: cả hai hoàn thành nhưng GA + VNS có F cao hơn. Tái tối ưu tốt trên các đơn đã biết chưa bảo đảm tổng chi phí cả ngày tốt hơn khi đơn mới xuất hiện.
- Không thay số đo để tạo kết luận GA luôn tốt hơn. Deadline có thể khiến số đo khác giữa các máy; chạy thêm seed và so sánh ghép cặp trước khi kết luận.

## Tái lập

```bash
python -m evrp benchmark --instances tc0c10s2cf1 tc2c10s2ct0 --config configs/benchmark_quick.json --seeds 42 43 --output results/benchmark
```

Xem `sample_results/comparison.csv`, `statistics.csv` và từng JSON để kiểm tra cấu hình, release và các quyết định. Dataset gốc không nằm trong archive mã nguồn; đặt XML vào đường dẫn mặc định trước khi tái lập.
