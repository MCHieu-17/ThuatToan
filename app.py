"""Run from the project root: python -m streamlit run app.py"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from evrp.config import load_config
from evrp.io.montoya import discover_instances, load_instance
from evrp.io.results import summary_row
from evrp.scenario import generate_scenario
from evrp.simulation.engine import simulate
from evrp.visualization import (LABELS, objective_figure, power_figure, route_figure,
                                soc_figure, timeline_figure, vehicle_snapshot)


st.set_page_config(page_title="EVRP · Điều độ xe điện", page_icon="⚡", layout="wide")
st.markdown("""<style>
.stApp {background: #f8fafc;}
[data-testid="stMetric"] {background:white; padding:14px 18px; border-radius:12px; border:1px solid #e2e8f0;}
.block-container {padding-top:2rem;}
</style>""", unsafe_allow_html=True)
st.title("⚡ Điều độ xe giao hàng điện")
st.caption("Montoya 2017 · Sạc phi tuyến · Công suất trạm · TOU · Đơn hàng động")

with st.sidebar:
    st.subheader("Cấu hình thí nghiệm")
    directory = st.text_input("Thư mục XML", "data/montoya-et-al-2017")
    try:
        files = discover_instances(directory)
    except FileNotFoundError:
        files = []
    demo = st.checkbox("Dùng dữ liệu demo giả lập", value=not bool(files))
    if demo:
        selected = Path("data/demo.xml")
        st.info("Demo có 6 khách hàng; đây không phải dataset Montoya.")
    elif files:
        selected = st.selectbox("Instance", files, format_func=lambda p: p.stem)
    else:
        st.error("Chưa tìm thấy XML. Đặt dataset vào thư mục trên hoặc bật demo.")
        st.stop()
    unit = st.selectbox("Đơn vị năng lượng XML", ["Wh", "kWh"], disabled=demo,
                        help="Montoya gốc sử dụng Wh. Chỉ chọn kWh nếu bạn đã chuyển đổi XML.")
    try:
        instance = load_instance(selected, "Wh" if demo else unit)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        st.stop()
    preset = st.selectbox("Kịch bản", ["demo" if demo else "default", "static", "tou", "limited_power"])
    config = copy.deepcopy(load_config(f"configs/{preset}.json"))
    config.seed = int(st.number_input("Seed", value=config.seed, step=1))
    config.vehicles = st.number_input("Số xe", min_value=1, max_value=50, value=config.vehicles, step=1)
    config.dynamic_fraction = st.slider("Tỷ lệ đơn xuất hiện trong ngày", 0.0, 1.0, config.dynamic_fraction, 0.05)
    config.release_until_fraction = st.slider("Đơn mới xuất hiện đến phần nào của ngày", 0.0, 0.9,
                                             config.release_until_fraction, 0.05)
    config.station_ports = st.number_input("Số cổng mỗi trạm", min_value=1, value=config.station_ports, step=1)
    config.station_power_kw = st.number_input("Công suất tổng trạm (kW)", min_value=0.1,
                                             value=config.station_power_kw, step=1.0)
    config.charger_power_kw = st.number_input("Công suất mỗi cổng (kW)", min_value=0.1,
                                             value=config.charger_power_kw, step=1.0)
    with st.expander("Hàm mục tiêu và pin"):
        config.w_time = st.number_input("w₁ · thời gian", min_value=0.0, value=config.w_time, step=0.1)
        config.w_electricity = st.number_input("w₂ · tiền điện", min_value=0.0, value=config.w_electricity, step=0.1)
        config.w_degradation = st.number_input("w₃ · hao pin", min_value=0.0, value=config.w_degradation, step=0.1)
        config.deep_charge_delta_soc = st.slider("Ngưỡng ΔSoC sạc sâu", 0.05, 1.0,
                                                 config.deep_charge_delta_soc, 0.05)
        config.deep_charge_cost = st.number_input("Chi phí mỗi lần sạc sâu", min_value=0.0, value=config.deep_charge_cost)
        config.deep_discharge_cost = st.number_input("Chi phí mỗi lần xả cạn", min_value=0.0, value=config.deep_discharge_cost)
        config.deep_discharge_soc = st.slider("Ngưỡng SoC xả cạn", 0.02, 0.2,
                                              config.deep_discharge_soc, 0.01)
    with st.expander("Giá điện TOU"):
        edited_tou = st.data_editor(pd.DataFrame(config.tou), hide_index=True, num_rows="fixed",
                                   column_config={"start": "Từ giờ", "end": "Đến giờ", "price": "Giá / kWh"})
        config.tou = edited_tou.to_dict("records")
        config.start_clock_hour = st.number_input("Giờ bắt đầu ngày mô phỏng", 0.0, 23.0, config.start_clock_hour)
        st.caption("Giá và chi phí hao pin dùng cùng một đơn vị tiền giả lập.")
    with st.expander("DP và GA + VNS"):
        config.solver_budget_seconds = st.number_input("Ngân sách mỗi lần tái tối ưu (giây)", 0.2, 60.0,
                                                        config.solver_budget_seconds, 0.5)
        config.dp_budget_seconds = st.number_input("Giới hạn mỗi lần DP (giây)", 0.05, 10.0,
                                                    config.dp_budget_seconds, 0.05)
        minutes = st.selectbox("Bước thời gian DP (phút)", [2, 5, 10], index=1)
        config.time_step_hours = minutes / 60
        config.soc_step = st.selectbox("Bước SoC mục tiêu", [0.05, 0.1, 0.2], index=1)
        config.population = st.number_input("Kích thước quần thể", 3, 100, config.population)
        config.generations = st.number_input("Số thế hệ tối đa", 1, 200, config.generations)
    choice = st.radio("Phương pháp", ["So sánh cả hai", "Greedy + DP", "GA + VNS + DP"])
    run = st.button("Chạy mô phỏng", type="primary", width="stretch")

st.latex(r"\min F = w_1 T_{total} + w_2 C_{electricity} + w_3 D_{battery\_degradation}")
st.caption(f"{instance.name} · {len(instance.customers)} khách hàng · {len(instance.stations)} trạm · "
           f"Pin {instance.capacity_kwh:g} kWh · Ngày hoạt động {instance.horizon_hours:g} giờ")

if run:
    try:
        config.validate()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    algorithms = ["baseline", "ga_vns"] if choice == "So sánh cả hai" else [
        "baseline" if choice == "Greedy + DP" else "ga_vns"]
    scenario = generate_scenario(instance, config)
    results = []
    progress = st.progress(0, text="Đang mô phỏng…")
    for i, algorithm in enumerate(algorithms):
        with st.spinner(f"Đang chạy {LABELS[algorithm]}…"):
            results.append(simulate(instance, config, scenario, algorithm))
        progress.progress((i + 1) / len(algorithms), text=f"Hoàn tất {LABELS[algorithm]}")
    progress.empty()
    st.session_state["results"] = results
    st.session_state["result_instance"] = instance
    st.session_state["playing"] = False
    st.session_state["replay_clock"] = 0.0
    st.session_state["replay_slider"] = 0.0

if "results" not in st.session_state:
    st.info("Chọn dữ liệu và nhấn Chạy mô phỏng. Hai phương pháp dùng cùng luồng đơn hàng và cấu hình.")
    st.stop()

results = st.session_state["results"]
result_instance = st.session_state["result_instance"]
st.caption(f"Kết quả đang hiển thị: {result_instance.name}, seed {results[0].seed}. "
           "Thay đổi cấu hình chỉ có hiệu lực sau khi chạy lại.")
tabs = st.tabs(["Tổng quan", "Phát lại lộ trình", "Pin và trạm sạc", "Nhật ký và xuất dữ liệu"])
with tabs[0]:
    for column, result in zip(st.columns(len(results)), results):
        with column:
            st.subheader(LABELS[result.algorithm])
            m = result.metrics
            a, b = st.columns(2)
            a.metric("Đã phục vụ", f"{m['served']} / {m['total_customers']}")
            b.metric("F thực hiện", f"{m['F']:.3f}")
            a.metric("Di chuyển + chờ + sạc", f"{m['T_total']:.3f} h")
            b.metric("Chi phí điện", f"{m['C_electricity']:.3f}")
            a.metric("Chi phí hao pin", f"{m['D_battery_degradation']:.3f}")
            b.metric("Thời gian tính toán", f"{m['solver_seconds']:.2f} s")
            st.caption(f"Sạc sâu: {m['N_deep_charge']} · Xả cạn: {m['N_deep_discharge']} · "
                       f"Tái tối ưu: {m['replans']}")
            if not result.validation["valid"]:
                st.error("Nhật ký không đạt kiểm tra: " + "; ".join(result.validation["errors"]))
            elif not m["objective_valid"]:
                st.warning(f"Chưa phục vụ các đơn {m['unserved']}. F trên chỉ tính công việc đã thực hiện.")
            else:
                st.success("Hoàn thành tất cả đơn; nhật ký đạt kiểm tra.")
    st.plotly_chart(objective_figure(results), width="stretch", key="objective_comparison")
    if all(r.metrics["objective_valid"] for r in results) and len(results) == 2:
        baseline, hybrid = results
        denominator = baseline.metrics["F"]
        improvement = 100 * (denominator - hybrid.metrics["F"]) / denominator if denominator else 0.0
        st.write(f"Mức giảm F của GA + VNS so với baseline trong lần chạy này: **{improvement:.2f}%**.")

with tabs[1]:
    st.caption("Hiển thị vị trí từ nhật ký thực hiện; khách hàng chưa xuất hiện được ẩn.")
    left, middle, right = st.columns([1, 1, 4])
    if left.button("▶ Phát" if not st.session_state.get("playing") else "⏸ Tạm dừng"):
        st.session_state["playing"] = not st.session_state.get("playing", False)
        if not st.session_state["playing"]:
            st.session_state["sync_slider"] = True
        st.rerun()
    if middle.button("↺ Về đầu"):
        st.session_state["playing"] = False
        st.session_state["replay_clock"] = 0.0
        st.session_state["replay_slider"] = 0.0
        st.rerun()
    speed = right.select_slider("Bước phát (giờ mô phỏng / lần cập nhật)", [0.05, 0.1, 0.25, 0.5], value=0.1)
    def seek():
        st.session_state["replay_clock"] = st.session_state["replay_slider"]
    if st.session_state.pop("sync_slider", False):
        st.session_state["replay_slider"] = float(st.session_state["replay_clock"])
    st.slider("Thời gian mô phỏng (giờ)", 0.0, float(result_instance.horizon_hours),
              step=0.05, key="replay_slider", on_change=seek, disabled=st.session_state.get("playing", False))

    @st.fragment(run_every=0.8 if st.session_state.get("playing") else None)
    def replay():
        if st.session_state.get("playing"):
            st.session_state["replay_clock"] = min(result_instance.horizon_hours,
                                                    st.session_state["replay_clock"] + speed)
            if st.session_state["replay_clock"] >= result_instance.horizon_hours:
                st.session_state["playing"] = False
                st.session_state["sync_slider"] = True
                st.rerun()
        at = st.session_state.get("replay_clock", 0.0)
        clock = (results[0].config["start_clock_hour"] + at) % 24
        st.write(f"**t = {at:.2f} h · Đồng hồ {int(clock):02d}:{int(clock % 1 * 60):02d}**")
        for column, result in zip(st.columns(len(results)), results):
            with column:
                st.write(f"**{LABELS[result.algorithm]}**")
                st.plotly_chart(route_figure(result_instance, result, at), width="stretch",
                                key=f"replay_{result.algorithm}")
                snapshots = [vehicle_snapshot(result_instance, result, v, at)
                             for v in range(result.config["vehicles"])]
                st.dataframe(pd.DataFrame(snapshots).drop(columns=["x", "y"]), hide_index=True,
                             width="stretch")
    replay()

with tabs[2]:
    station = st.selectbox("Trạm sạc", result_instance.stations) if result_instance.stations else None
    for column, result in zip(st.columns(len(results)), results):
        with column:
            st.write(f"**{LABELS[result.algorithm]}**")
            st.plotly_chart(soc_figure(result_instance, result), width="stretch",
                            key=f"soc_{result.algorithm}")
            if station is not None:
                st.plotly_chart(power_figure(result_instance, result, station), width="stretch",
                                key=f"power_{result.algorithm}")
            st.plotly_chart(timeline_figure(result), width="stretch",
                            key=f"timeline_{result.algorithm}")

with tabs[3]:
    comparison = pd.DataFrame([summary_row(r) for r in results])
    st.dataframe(comparison, hide_index=True, width="stretch")
    st.download_button("Tải bảng so sánh CSV", comparison.to_csv(index=False).encode("utf-8-sig"),
                       "comparison.csv", "text/csv")
    for result in results:
        with st.expander(LABELS[result.algorithm]):
            decisions = [{k: v for k, v in d.items() if k != "history"} for d in result.decisions]
            st.dataframe(pd.DataFrame(decisions), hide_index=True, width="stretch")
            if result.decisions:
                epoch = st.selectbox("Lần tái tối ưu", list(range(len(result.decisions))),
                                    key=f"epoch_{result.algorithm}")
                st.caption("F còn lại giữa các lần tái tối ưu không so sánh trực tiếp với nhau.")
                history = result.decisions[epoch]["history"]
                if history:
                    st.dataframe(pd.DataFrame(history), hide_index=True)
            st.download_button("Tải toàn bộ nhật ký JSON",
                               json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                               f"{result.instance}_{result.algorithm}_seed{result.seed}.json",
                               "application/json", key=f"download_{result.algorithm}")
