"""Summarize the reproducible experiment CSV and plot empirical scaling."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(input_csv: Path, output_dir: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with input_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("Empty experiment CSV")
    groups = defaultdict(list)
    for row in rows:
        groups[(int(row["customers"]), float(row["dynamic_ratio"]), row["method"])].append(row)

    def mean(items, key):
        return statistics.mean(float(row[key]) for row in items)

    def mean_sd(items, key):
        values = [float(row[key]) for row in items]
        sd = statistics.stdev(values) if len(values) > 1 else 0.0
        return f"{statistics.mean(values):.2f} ± {sd:.2f}"

    output_dir.mkdir(parents=True, exist_ok=True)
    budgets = sorted({row.get("budget_seconds", "unknown") for row in rows})
    lines = ["# Kết quả EVRP", "", f"Nguồn: `{input_csv}`; số lần chạy: {len(rows)}; "
             f"ngân sách mỗi lần tái lập tuyến: {', '.join(budgets)} giây.", "",
             "| Khách | Đơn động | Phương pháp | Giao được | Giờ vận hành | Chi phí điện | Hao mòn đại diện (kWh) | Trung vị lập tuyến (s) | P95 (s) |",
             "|---:|---:|---|---:|---:|---:|---:|---:|---:|"]
    for (n, ratio, method), items in sorted(groups.items()):
        lines.append(f"| {n} | {ratio:.0%} | {method} | "
                     f"{mean(items, 'served'):.1f}/{n} | {mean_sd(items, 'operating_hours')} | "
                     f"{mean_sd(items, 'electricity_cost')} | "
                     f"{mean_sd(items, 'wear_proxy_kwh')} | "
                     f"{mean(items, 'median_replan_seconds'):.3f} | "
                     f"{mean(items, 'p95_replan_seconds'):.3f} |")
    lines += ["", "Ba mục tiêu được báo cáo dưới dạng trung bình ± độ lệch chuẩn mẫu "
              "theo các bài toán và seed trong cùng nhóm.",
              "Thời gian lập tuyến phụ thuộc máy tính và ngân sách thời gian đã chọn.",
              "Chỉ số hao mòn là đại diện, không phải tuổi thọ pin thực đo.", ""]
    report = output_dir / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for method in ("greedy", "ga", "ga_vns"):
        points = sorted((n, mean(items, "median_replan_seconds"))
                        for (n, ratio, name), items in groups.items()
                        if ratio == 0.5 and name == method)
        if points:
            ax.plot([p[0] for p in points], [p[1] for p in points], marker="o", label=method)
    ax.set(xlabel="Customers", ylabel="Mean median replanning time (s)",
           title="Empirical runtime, 50% dynamic orders")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "runtime.png", dpi=180)
    plt.close(fig)

    # The wall-clock budget flattens the GA curves, so also show cost per unique
    # decoded candidate. This reveals how candidate evaluation scales with n.
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for method in ("greedy", "ga", "ga_vns"):
        points = sorted((n, statistics.mean(
            float(row["total_solve_seconds"]) / max(1, int(row["evaluations"]))
            for row in items))
            for (n, ratio, name), items in groups.items()
            if ratio == 0.5 and name == method)
        if points:
            ax.plot([p[0] for p in points], [1000 * p[1] for p in points],
                    marker="o", label=method)
    ax.set(xlabel="Customers", ylabel="Mean time per evaluated solution (ms)",
           title="Empirical candidate evaluation cost, 50% dynamic orders")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "evaluation_cost.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    for ax, metric, title in zip(axes,
                                 ("operating_hours", "electricity_cost", "wear_proxy_kwh"),
                                 ("Operating hours", "Electricity cost", "Wear proxy (kWh)")):
        for method in ("greedy", "ga", "ga_vns"):
            points = sorted((n, mean(items, metric)) for (n, ratio, name), items in groups.items()
                            if ratio == 0.5 and name == method)
            if points:
                ax.plot([p[0] for p in points], [p[1] for p in points], marker="o", label=method)
        ax.set(xlabel="Customers", title=title)
        ax.grid(alpha=0.3)
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(output_dir / "objectives.png", dpi=180)
    plt.close(fig)
    return report
