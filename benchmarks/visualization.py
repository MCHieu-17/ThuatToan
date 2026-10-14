#!/usr/bin/env python3
"""Ve bieu do tu ket qua benchmark CSV (comparison.csv / statistics.csv).

Vi du:
    python3 benchmarks/visualization.py results/benchmark_subset26
    python3 benchmarks/visualization.py results/benchmark_by_size --metric F
    python3 benchmarks/visualization.py results/benchmark_all120 --metric runtime_seconds

Tao ra trong thu muc ket qua:
    bars_F.png            - bieu do cot F trung binh theo kich thuoc + thuat toan
    bars_served.png       - bieu do cot ty le khach phuc vu
    bars_runtime.png      - bieu do cot thoi gian chay
    line_F.png            - linechart F theo kich thuoc (theo thuat toan)
    line_scaling.png      - linechart thoi gian chay / so label theo kich thuoc
    summary_by_size.csv   - bang tong hop theo (size, algorithm)

Cach doc kich thuoc instance: tcAcBsCcDE -> B la so khach.
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ALGORITHMS = ("greedy", "ga", "ga_vns")
COLORS = {"greedy": "#4C72B0", "ga": "#DD8452", "ga_vns": "#55A868"}
SIZE_RE = re.compile(r"tc\d+c(\d+)s\d+c[ft]\d+")


def instance_size(name: str) -> int | None:
    match = SIZE_RE.search(name)
    return int(match.group(1)) if match else None


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"khong tim thay {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_rows(directory: Path) -> list[dict]:
    """Doc comparison.csv neu co, nguoc lai gom tu statistics.csv."""
    comparison = directory / "comparison.csv"
    if comparison.is_file():
        rows = read_csv(comparison)
        for row in rows:
            row["_size"] = instance_size(row["instance"])
        return rows
    stats = directory / "statistics.csv"
    rows = read_csv(stats)
    for row in rows:
        row["_size"] = instance_size(row["instance"])
        row["F"] = row.get("F_mean", "")
        row["served"] = row.get("served_mean", "")
        row["total"] = ""
        row["runtime_seconds"] = row.get("runtime_mean", "")
        row["labels_expanded"] = row.get("labels_mean", "")
    return rows


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aggregate(rows: list[dict]) -> dict[tuple[int, str], dict]:
    """Gom theo (size, algorithm): trung binh cac chi so."""
    buckets: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in rows:
        size = row.get("_size")
        if size is None:
            continue
        buckets[(size, row["algorithm"])].append(row)

    out: dict[tuple[int, str], dict] = {}
    for key, group in buckets.items():
        def mean(field: str) -> float | None:
            vals = [v for v in (_to_float(r.get(field)) for r in group) if v is not None]
            return statistics.mean(vals) if vals else None

        served = [v for v in (_to_float(r.get("served")) for r in group) if v is not None]
        totals = [v for v in (_to_float(r.get("total")) for r in group) if v and v > 0]
        ratio = None
        if served and totals:
            ratio = statistics.mean(served) / statistics.mean(totals)

        out[key] = {
            "size": key[0],
            "algorithm": key[1],
            "runs": len(group),
            "F": mean("F"),
            "served_ratio": ratio,
            "served": statistics.mean(served) if served else None,
            "runtime": mean("runtime_seconds"),
            "labels": mean("labels_expanded"),
            "dp_calls": mean("dp_calls"),
            "evaluations": mean("evaluations"),
        }
    return out


def _sizes(agg: dict, algorithms=ALGORITHMS) -> list[int]:
    return sorted({size for (size, _) in agg})


def bar_by_size(agg, field, ylabel, title, path: Path):
    sizes = _sizes(agg)
    if not sizes:
        return
    width = 0.8 / len(ALGORITHMS)
    fig, ax = plt.subplots(figsize=(max(7, len(sizes) * 1.6), 5))
    for index, algorithm in enumerate(ALGORITHMS):
        values, positions = [], []
        for size in sizes:
            data = agg.get((size, algorithm))
            value = data.get(field) if data else None
            values.append(value if value is not None else 0.0)
            positions.append(index - 0 and index)
        offsets = [i + (index - (len(ALGORITHMS) - 1) / 2) * width for i in range(len(sizes))]
        bars = ax.bar(offsets, values, width, label=algorithm, color=COLORS[algorithm])
        ax.bar_label(bars, fmt="%.3g", fontsize=7, padding=1)
    ax.set_xticks(range(len(sizes)))
    ax.set_xticklabels([str(s) for s in sizes])
    ax.set_xlabel("So khach hang")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"wrote {path}")


def line_by_size(agg, field, ylabel, title, path: Path, logy: bool = False):
    sizes = _sizes(agg)
    if not sizes:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    for algorithm in ALGORITHMS:
        xs, ys = [], []
        for size in sizes:
            data = agg.get((size, algorithm))
            value = data.get(field) if data else None
            if value is not None:
                xs.append(size)
                ys.append(value)
        if xs:
            ax.plot(xs, ys, marker="o", label=algorithm, color=COLORS[algorithm], linewidth=2)
    ax.set_xscale("log", base=2)
    if logy:
        ax.set_yscale("log")
    ax.set_xticks(sizes)
    ax.set_xticklabels([str(s) for s in sizes])
    ax.set_xlabel("So khach hang")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"wrote {path}")


def write_summary(agg, path: Path):
    fields = ["size", "algorithm", "runs", "F", "served_ratio", "served",
              "runtime", "labels", "dp_calls", "evaluations"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for key in sorted(agg, key=lambda k: (k[0], k[1])):
            row = dict(agg[key])
            for field in fields:
                if isinstance(row.get(field), float):
                    row[field] = round(row[field], 4)
            writer.writerow({field: row.get(field, "") for field in fields})
    print(f"wrote {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Visualize benchmark CSV results")
    parser.add_argument("directory", help="thu muc chua comparison.csv/statistics.csv")
    parser.add_argument("--output", default=None, help="thu muc xuat anh (mac dinh = directory)")
    args = parser.parse_args(argv)

    directory = Path(args.directory)
    out = Path(args.output) if args.output else directory
    out.mkdir(parents=True, exist_ok=True)

    rows = load_rows(directory)
    agg = aggregate(rows)
    if not agg:
        raise SystemExit(f"khong co du lieu hop le trong {directory}")

    bar_by_size(agg, "F", "F (diem muc tieu, cang thap cang tot)",
                "F trung binh theo kich thuoc", out / "bars_F.png")
    bar_by_size(agg, "served_ratio", "Ty le khach duoc phuc vu",
                "Ty le phuc vu theo kich thuoc", out / "bars_served.png")
    bar_by_size(agg, "runtime", "Thoi gian chay (giay)",
                "Thoi gian chay theo kich thuoc", out / "bars_runtime.png")

    line_by_size(agg, "F", "F (cang thap cang tot)",
                 "Linechart F theo kich thuoc", out / "line_F.png")
    line_by_size(agg, "runtime", "Thoi gian chay (giay)",
                 "Scaling thoi gian chay theo kich thuoc", out / "line_scaling.png", logy=True)
    line_by_size(agg, "labels", "So label DP da mo rong",
                 "Scaling so label DP theo kich thuoc", out / "line_labels.png", logy=True)

    write_summary(agg, out / "summary_by_size.csv")


if __name__ == "__main__":
    main()
