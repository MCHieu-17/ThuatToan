from __future__ import annotations

from evrp.algorithms.ranking import crowding_distance, dominates, fast_non_dominated_sort


def test_dominates_basic():
    assert dominates((0.0, 1.0), (1.0, 1.0))
    assert dominates((0.0, 0.0), (1.0, 1.0))
    assert not dominates((1.0, 1.0), (0.0, 0.0))
    assert not dominates((0.0, 1.0), (1.0, 0.0))
    assert not dominates((1.0, 1.0), (1.0, 1.0))


def test_non_dominated_sort_layers():
    objectives = [
        (0.0, 3.0),   # front 0
        (1.0, 2.0),   # front 0
        (2.0, 1.0),   # front 0
        (2.0, 2.0),   # dominated by (1,2) and (2,1)
        (5.0, 5.0),   # dominated by all
    ]
    fronts = fast_non_dominated_sort(objectives)
    assert sorted(fronts[0]) == [0, 1, 2]
    assert fronts[1] == [3]
    assert fronts[2] == [4]


def test_non_dominated_sort_handles_duplicates():
    objectives = [(1.0, 1.0), (1.0, 1.0)]
    fronts = fast_non_dominated_sort(objectives)
    assert sorted(fronts[0]) == [0, 1]
    assert len(fronts) == 1


def test_crowding_distance_boundaries_infinite():
    objectives = [(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)]
    front = [0, 1, 2]
    distance = crowding_distance(objectives, front)
    assert distance[0] == float("inf")
    assert distance[2] == float("inf")
    assert distance[1] > 0.0