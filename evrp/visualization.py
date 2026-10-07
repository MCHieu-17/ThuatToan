"""Plotly figures built from executed actions, not fabricated animation paths."""
from __future__ import annotations

import plotly.graph_objects as go
from plotly.colors import qualitative

from evrp.config import Config
from evrp.domain import Instance
from evrp.simulation.engine import RunResult


COLORS = qualitative.Safe
LABELS = {"baseline": "Greedy + DP", "ga_vns": "GA + VNS + DP"}


def energy_at(action, at: float) -> float:
    if action.kind == "charge":
        energy = action.energy_before
        for start, end, power in action.power_segments:
            energy += max(0.0, min(at, end) - start) * power
        return min(energy, action.energy_after)
    if action.end <= action.start:
        return action.energy_after
    fraction = max(0.0, min(1.0, (at - action.start) / (action.end - action.start)))
    return action.energy_before + fraction * (action.energy_after - action.energy_before)


def vehicle_snapshot(instance: Instance, result: RunResult, vehicle: int, at: float) -> dict:
    node, energy, status, destination = instance.depot, instance.capacity_kwh, "Tại depot", instance.depot
    x, y = instance.nodes[node].x, instance.nodes[node].y
    for action in sorted((a for a in result.actions if a.vehicle == vehicle), key=lambda a: (a.start, a.end)):
        if action.start > at + 1e-9:
            break
        if action.end <= at + 1e-9:
            node, energy = action.destination, action.energy_after
            x, y = instance.nodes[node].x, instance.nodes[node].y
            continue
        energy = energy_at(action, at)
        destination = action.destination
        status = {"drive": "Đang di chuyển", "charge": "Đang sạc", "wait": "Đang chờ",
                  "service": "Đang giao hàng"}[action.kind]
        if action.kind == "drive":
            a, b = instance.nodes[action.origin], instance.nodes[action.destination]
            fraction = (at - action.start) / (action.end - action.start)
            x, y = a.x + fraction * (b.x - a.x), a.y + fraction * (b.y - a.y)
        break
    return {"Xe": vehicle + 1, "Trạng thái": status, "SoC (%)": round(energy / instance.capacity_kwh * 100, 1),
            "Điểm tiếp theo": destination, "x": x, "y": y}


def route_figure(instance: Instance, result: RunResult, at: float) -> go.Figure:
    fig = go.Figure()
    served = {a.destination for a in result.actions if a.kind == "service" and a.end <= at + 1e-9}
    styles = [
        ("Depot", [instance.depot], "diamond", "#153145", 17),
        ("Trạm sạc", instance.stations, "square", "#059669", 13),
        ("Đã giao", sorted(served), "circle", "#64748b", 9),
        ("Đơn đã xuất hiện", [n for n in instance.customers if n not in served and result.releases[n] <= at],
         "circle", "#f59e0b", 11),
    ]
    # Unknown customer locations are hidden during replay, matching online revelation.
    for label, ids, symbol, color, size in styles:
        if ids:
            fig.add_trace(go.Scatter(x=[instance.nodes[n].x for n in ids],
                                    y=[instance.nodes[n].y for n in ids], mode="markers+text",
                                    text=[str(n) for n in ids], textposition="top center", name=label,
                                    marker={"symbol": symbol, "color": color, "size": size}))
    for v in range(result.config["vehicles"]):
        color = COLORS[v % len(COLORS)]
        xs, ys = [], []
        for a in result.actions:
            if a.vehicle != v or a.kind != "drive" or a.start > at:
                continue
            origin, dest = instance.nodes[a.origin], instance.nodes[a.destination]
            fraction = min(1.0, (at - a.start) / max(a.end - a.start, 1e-12))
            xs.extend([origin.x, origin.x + fraction * (dest.x - origin.x), None])
            ys.extend([origin.y, origin.y + fraction * (dest.y - origin.y), None])
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line={"color": color, "width": 2},
                                name=f"Lộ trình xe {v + 1}", showlegend=False))
        snapshot = vehicle_snapshot(instance, result, v, at)
        fig.add_trace(go.Scatter(x=[snapshot["x"]], y=[snapshot["y"]], mode="markers", name=f"Xe {v + 1}",
                                marker={"size": 16, "color": color, "symbol": "triangle-up"},
                                hovertemplate=f"Xe {v + 1}<br>SoC: {snapshot['SoC (%)']}%<extra></extra>"))
    fig.update_layout(height=450, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis_title="X (km)", yaxis_title="Y (km)", legend={"orientation": "h"},
                      template="plotly_white")
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def soc_figure(instance: Instance, result: RunResult) -> go.Figure:
    fig = go.Figure()
    for v in range(result.config["vehicles"]):
        xs, ys = [0.0], [100.0]
        for a in sorted((a for a in result.actions if a.vehicle == v), key=lambda a: (a.start, a.end)):
            xs.append(a.start)
            ys.append(a.energy_before / instance.capacity_kwh * 100)
            if a.kind == "charge":
                for _, end, _ in a.power_segments:
                    xs.append(end)
                    ys.append(energy_at(a, end) / instance.capacity_kwh * 100)
            else:
                xs.append(a.end)
                ys.append(a.energy_after / instance.capacity_kwh * 100)
        fig.add_trace(go.Scatter(x=xs, y=ys, name=f"Xe {v + 1}", mode="lines",
                                line={"color": COLORS[v % len(COLORS)]}))
    fig.add_hline(y=result.config["deep_discharge_soc"] * 100, line_dash="dash", line_color="#ef4444",
                  annotation_text="Ngưỡng xả cạn")
    fig.update_layout(height=340, xaxis_title="Thời gian mô phỏng (giờ)", yaxis_title="SoC (%)",
                      yaxis_range=[0, 102], template="plotly_white", margin={"t": 25, "b": 20})
    return fig


def power_figure(instance: Instance, result: RunResult, station: int) -> go.Figure:
    config = Config(**result.config)
    actions = [a for a in result.actions if a.kind == "charge" and a.origin == station]
    boundaries = sorted({0.0, instance.horizon_hours} | {t for a in actions for s in a.power_segments for t in s[:2]})
    xs, actual, reserved = [], [], []
    for left, right in zip(boundaries, boundaries[1:]):
        middle = (left + right) / 2
        real = sum(p for a in actions for start, end, p in a.power_segments if start <= middle < end)
        allocation = sum(a.allocated_kw for a in actions if a.start <= middle < a.end)
        xs.extend([left, right])
        actual.extend([real, real])
        reserved.extend([allocation, allocation])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=actual, mode="lines", name="Công suất thực", fill="tozeroy"))
    fig.add_trace(go.Scatter(x=xs, y=reserved, mode="lines", name="Công suất đặt chỗ", line_dash="dash"))
    fig.add_hline(y=config.station(station)["power_kw"], line_color="#ef4444", annotation_text="Giới hạn trạm")
    fig.update_layout(height=320, xaxis_title="Thời gian mô phỏng (giờ)", yaxis_title="kW",
                      template="plotly_white", margin={"t": 25, "b": 20})
    return fig


def timeline_figure(result: RunResult) -> go.Figure:
    fig = go.Figure()
    names = {"drive": "Di chuyển", "wait": "Chờ", "charge": "Sạc", "service": "Giao hàng"}
    colors = {"drive": "#2563eb", "wait": "#f59e0b", "charge": "#10b981", "service": "#8b5cf6"}
    for kind, label in names.items():
        actions = [a for a in result.actions if a.kind == kind]
        fig.add_trace(go.Bar(x=[a.end - a.start for a in actions], base=[a.start for a in actions],
                             y=[f"Xe {a.vehicle + 1}" for a in actions], orientation="h",
                             name=label, marker_color=colors[kind],
                             customdata=[a.destination for a in actions],
                             hovertemplate="Điểm %{customdata}<br>Thời lượng %{x:.3f} giờ<extra></extra>"))
    fig.update_layout(barmode="overlay", height=300, xaxis_title="Thời gian mô phỏng (giờ)",
                      template="plotly_white", margin={"t": 20, "b": 20})
    return fig


def objective_figure(results: list[RunResult]) -> go.Figure:
    fig = go.Figure()
    for field, weight, label in [("T_total", "w_time", "w₁ × thời gian"),
                                 ("C_electricity", "w_electricity", "w₂ × tiền điện"),
                                 ("D_battery_degradation", "w_degradation", "w₃ × hao pin")]:
        fig.add_trace(go.Bar(x=[LABELS[r.algorithm] for r in results],
                             y=[r.metrics[field] * r.config[weight] for r in results], name=label))
    fig.update_layout(barmode="stack", height=350, yaxis_title="Đóng góp vào F",
                      template="plotly_white", margin={"t": 20, "b": 20})
    return fig
