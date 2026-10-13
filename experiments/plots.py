"""Plot experiment CSV outputs with matplotlib (no pandas dependency)."""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from evrp.algorithms.ranking import dominates


def _read(path: str | Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def plot_complexity(csv_path: str | Path, out_png: str | Path) -> Path:
    rows = _read(csv_path)
    by_alg: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    work: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        n = int(row["customers"])
        by_alg[row["algorithm"]][n].append(float(row["runtime_seconds"]))
        work[row["algorithm"]][n].append(float(row["dp_calls"]))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for algorithm, series in sorted(by_alg.items()):
        sizes = sorted(series)
        axes[0].plot(sizes, [statistics.mean(series[s]) for s in sizes], marker="o", label=algorithm)
        axes[1].plot(sizes, [statistics.mean(work[algorithm][s]) for s in sizes],
                     marker="s", label=algorithm)
    axes[0].set(xlabel="customers n", ylabel="runtime (s)", title="Runtime scaling")
    axes[1].set(xlabel="customers n", ylabel="charging-DP calls", title="DP work scaling")
    for axis in axes:
        axis.grid(True, alpha=0.3)
        axis.legend()
    fig.tight_layout()
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def plot_comparison(csv_path: str | Path, out_png: str | Path) -> Path:
    rows = _read(csv_path)
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if str(row.get("complete", "")).lower() in ("true", "1"):
            grouped[(row["instance"], row["algorithm"])].append(float(row["F"]))
    instances = sorted({key[0] for key in grouped})
    algorithms = sorted({key[1] for key in grouped})
    width = 0.8 / max(1, len(algorithms))
    fig, axis = plt.subplots(figsize=(max(7, 1.6 * len(instances)), 4.4))
    for index, algorithm in enumerate(algorithms):
        xs = []
        ys = []
        for position, instance in enumerate(instances):
            values = grouped.get((instance, algorithm))
            if values:
                xs.append(position + index * width)
                ys.append(statistics.mean(values))
        axis.bar(xs, ys, width=width, label=algorithm)
    axis.set_xticks([p + 0.4 - width / 2 for p in range(len(instances))])
    axis.set_xticklabels(instances, rotation=20, ha="right")
    axis.set(ylabel="mean F (complete runs)", title="Objective comparison")
    axis.grid(True, axis="y", alpha=0.3)
    axis.legend()
    fig.tight_layout()
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def plot_approximation(csv_path: str | Path, out_png: str | Path,
                       alpha: float = 2.0) -> Path:
    rows = _read(csv_path)
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get("ratio", "")
        if value not in ("", None):
            grouped[row["algorithm"]].append(float(value))
    algorithms = sorted(grouped)
    means = [statistics.mean(grouped[a]) for a in algorithms]
    maxima = [max(grouped[a]) for a in algorithms]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].bar(range(len(algorithms)), means, yerr=[[m - min(grouped[a]) for a, m in zip(algorithms, means)],
                                                    [max(grouped[a]) - m for a, m in zip(algorithms, means)]],
                capsize=4)
    axes[0].axhline(alpha, color="tab:red", linestyle="--", label=f"proven $\\alpha$={alpha:g}")
    axes[0].set_xticks(range(len(algorithms)))
    axes[0].set_xticklabels(algorithms)
    axes[0].set(ylabel="F / OPT", title="Approximation ratio (mean, range)")
    axes[0].legend()
    for algorithm in algorithms:
        sizes = sorted({int(r["customers"]) for r in rows if r["algorithm"] == algorithm
                        and r.get("ratio") not in ("", None)})
        series = []
        for size in sizes:
            values = [float(r["ratio"]) for r in rows
                      if r["algorithm"] == algorithm and int(r["customers"]) == size
                      and r.get("ratio") not in ("", None)]
            series.append(statistics.mean(values))
        axes[1].plot(sizes, series, marker="o", label=algorithm)
    axes[1].axhline(alpha, color="tab:red", linestyle="--")
    axes[1].set(xlabel="customers n", ylabel="F / OPT", title="Ratio vs instance size")
    for axis in axes:
        axis.grid(True, alpha=0.3)
    axes[1].legend()
    fig.tight_layout()
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def plot_pareto(csv_path: str | Path, out_png: str | Path) -> Path:
    """Pareto front (Time, electricity, degradation) as 3 pairwise projections."""
    rows = _read(csv_path)
    points: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for row in rows:
        try:
            point = (float(row["time"]), float(row["electricity"]), float(row["degradation"]))
        except (KeyError, TypeError, ValueError):
            continue
        points[row["algorithm"]].append(point)
    fronts: dict[str, list[tuple[float, float, float]]] = {}
    for algorithm, values in points.items():
        unique = sorted(set(values))
        fronts[algorithm] = [
            p for i, p in enumerate(unique)
            if not any(dominates(q, p) for j, q in enumerate(unique) if j != i)
        ]
    panels = [(0, 1, "T (h)", "electricity cost"),
              (0, 2, "T (h)", "battery degradation"),
              (1, 2, "electricity cost", "battery degradation")]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    for axis, (i, j, xlabel, ylabel) in zip(axes, panels):
        for algorithm in sorted(fronts):
            if not fronts[algorithm]:
                continue
            axis.scatter([p[i] for p in fronts[algorithm]], [p[j] for p in fronts[algorithm]],
                         s=32, label=algorithm)
        axis.set(xlabel=xlabel, ylabel=ylabel)
        axis.grid(True, alpha=0.3)
    axes[0].legend()
    fig.suptitle("Pareto front: trade-off time - electricity - battery life")
    fig.tight_layout()
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plot experiment results")
    parser.add_argument("--complexity", default="results/complexity/complexity.csv")
    parser.add_argument("--comparison", default="results/comparison/comparison_rows.csv")
    parser.add_argument("--approximation", default="results/approximation/approximation.csv")
    parser.add_argument("--pareto", default="results/comparison/pareto.csv")
    parser.add_argument("--output", default="results/report")
    args = parser.parse_args(argv)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if Path(args.complexity).is_file():
        print(plot_complexity(args.complexity, out / "complexity.png"))
    if Path(args.comparison).is_file():
        print(plot_comparison(args.comparison, out / "comparison.png"))
    if Path(args.approximation).is_file():
        print(plot_approximation(args.approximation, out / "approximation.png"))
    if Path(args.pareto).is_file():
        print(plot_pareto(args.pareto, out / "pareto.png"))


if __name__ == "__main__":
    main()