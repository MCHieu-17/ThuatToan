"""NSGA-II ranking helpers: Pareto dominance, non-dominated sorting, crowding.

Objective vectors are minimization vectors (see `Solution.objectives`). A vector
a dominates b when it is no worse on every objective and strictly better on at
least one. `fast_non_dominated_sort` groups indices into fronts; `crowding_distance`
measures diversity inside a front so the GA can break ties without collapsing the
population onto a single point.
"""
from __future__ import annotations


def dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """True if objective vector `a` Pareto-dominates `b` (both minimize)."""
    better = False
    for x, y in zip(a, b):
        if x > y:
            return False
        if x < y:
            better = True
    return better


def fast_non_dominated_sort(objectives: list[tuple[float, ...]]) -> list[list[int]]:
    """Pareto fronts of index lists; front 0 is the non-dominated front."""
    n = len(objectives)
    dominated: list[list[int]] = [[] for _ in range(n)]
    dominated_count = [0] * n
    fronts: list[list[int]] = [[]]
    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if dominates(objectives[p], objectives[q]):
                dominated[p].append(q)
            elif dominates(objectives[q], objectives[p]):
                dominated_count[p] += 1
        if dominated_count[p] == 0:
            fronts[0].append(p)
    i = 0
    while fronts[i]:
        nxt: list[int] = []
        for p in fronts[i]:
            for q in dominated[p]:
                dominated_count[q] -= 1
                if dominated_count[q] == 0:
                    nxt.append(q)
        fronts.append(nxt)
        i += 1
    fronts.pop()
    return fronts


def crowding_distance(objectives: list[tuple[float, ...]],
                      front: list[int]) -> dict[int, float]:
    """Crowding distance for each index in `front` (boundary points get inf)."""
    distance = {i: 0.0 for i in front}
    if len(front) <= 2:
        for i in front:
            distance[i] = float("inf")
        return distance
    dimensions = len(objectives[front[0]])
    for k in range(dimensions):
        ordered = sorted(front, key=lambda i: objectives[i][k])
        distance[ordered[0]] = float("inf")
        distance[ordered[-1]] = float("inf")
        span = objectives[ordered[-1]][k] - objectives[ordered[0]][k]
        if span <= 0:
            continue
        for idx in range(1, len(ordered) - 1):
            distance[ordered[idx]] += ((objectives[ordered[idx + 1]][k]
                                        - objectives[ordered[idx - 1]][k]) / span)
    return distance