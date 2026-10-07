"""Permutation + customer-to-vehicle genes, order crossover and VNS."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.algorithms.greedy import greedy_insert
from evrp.domain import Solution


@dataclass(frozen=True)
class Chromosome:
    order: tuple[int, ...]
    vehicles: tuple[int, ...]  # vehicle gene aligned with each customer in order

    def decode(self, fleet: list[int]) -> dict[int, list[int]]:
        routes = {v: [] for v in fleet}
        for node, vehicle in zip(self.order, self.vehicles):
            routes[vehicle].append(node)
        return routes


def encode(routes: dict[int, list[int]], customers: list[int], fleet: list[int], rng) -> Chromosome:
    order, assignment = [], []
    for v in fleet:
        for n in routes.get(v, []):
            order.append(n)
            assignment.append(v)
    for n in customers:
        if n not in order:
            order.append(n)
            assignment.append(rng.choice(fleet))
    return Chromosome(tuple(order), tuple(assignment))


def crossover(a: Chromosome, b: Chromosome, rng) -> Chromosome:
    n = len(a.order)
    if n < 2:
        return a
    left, right = sorted(rng.sample(range(n + 1), 2))
    child = [None] * n
    child[left:right] = a.order[left:right]
    remaining = [x for x in b.order[right:] + b.order[:right] if x not in child]
    positions = list(range(right, n)) + list(range(left))
    for position, node in zip(positions, remaining):
        child[position] = node
    am, bm = dict(zip(a.order, a.vehicles)), dict(zip(b.order, b.vehicles))
    genes = tuple(am[node] if rng.random() < 0.5 else bm[node] for node in child)
    return Chromosome(tuple(child), genes)


def mutate(chromosome: Chromosome, fleet: list[int], rng) -> Chromosome:
    pairs = list(zip(chromosome.order, chromosome.vehicles))
    if not pairs:
        return chromosome
    if len(pairs) > 1 and rng.random() < 0.5:
        i, j = rng.sample(range(len(pairs)), 2)
        pairs[i], pairs[j] = pairs[j], pairs[i]
    else:
        i = rng.randrange(len(pairs))
        pairs[i] = (pairs[i][0], rng.choice(fleet))
    return Chromosome(tuple(p[0] for p in pairs), tuple(p[1] for p in pairs))


def neighbor(chromosome: Chromosome, fleet: list[int], neighborhood: int, rng) -> Chromosome:
    routes = chromosome.decode(fleet)
    nonempty = [v for v in fleet if routes[v]]
    if not nonempty:
        return chromosome
    if neighborhood == 0:  # relocate, including between vehicles
        source = rng.choice(nonempty)
        node = routes[source].pop(rng.randrange(len(routes[source])))
        destination = rng.choice(fleet)
        routes[destination].insert(rng.randrange(len(routes[destination]) + 1), node)
    elif neighborhood == 1:  # swap, including between vehicles
        source, destination = rng.choice(nonempty), rng.choice(nonempty)
        i, j = rng.randrange(len(routes[source])), rng.randrange(len(routes[destination]))
        routes[source][i], routes[destination][j] = routes[destination][j], routes[source][i]
    else:  # 2-opt within a route
        candidates = [v for v in fleet if len(routes[v]) >= 2]
        if not candidates:
            return chromosome
        v = rng.choice(candidates)
        i, j = sorted(rng.sample(range(len(routes[v]) + 1), 2))
        routes[v][i:j] = reversed(routes[v][i:j])
    return encode(routes, list(chromosome.order), fleet, rng)


def vns(chromosome: Chromosome, solution: Solution, evaluator: FleetEvaluator, rng):
    fleet = sorted(evaluator.states)
    neighborhood = 0
    for _ in range(evaluator.config.vns_iterations):
        if time.perf_counter() >= evaluator.deadline:
            break
        candidate_chromosome = neighbor(chromosome, fleet, neighborhood, rng)
        candidate = evaluator.evaluate(candidate_chromosome.decode(fleet))
        if candidate.rank < solution.rank:
            chromosome, solution, neighborhood = candidate_chromosome, candidate, 0
        else:
            neighborhood = (neighborhood + 1) % 3
    return chromosome, solution


def solve_ga_vns(evaluator: FleetEvaluator, seed_routes: dict[int, list[int]] | None = None,
                 seed: int = 42) -> Solution:
    started = time.perf_counter()
    config = evaluator.config
    rng = random.Random(seed)
    fleet, customers = sorted(evaluator.states), sorted(evaluator.customers)
    warm_deadline = started + max(0.0, evaluator.deadline - started) * 0.45
    incumbent = greedy_insert(evaluator, seed_routes, warm_deadline)
    seed_chromosome = encode(incumbent.routes, customers, fleet, rng)
    evaluated_seed = evaluator.evaluate(seed_chromosome.decode(fleet))
    if evaluated_seed.rank < incumbent.rank:
        incumbent = evaluated_seed
    population = [(seed_chromosome, evaluated_seed)]
    history = [{"step": 0, "phase": "initial", "F_remaining": incumbent.score,
                "unassigned": len(incumbent.unassigned)}]
    while len(population) < config.population and time.perf_counter() < evaluator.deadline:
        chromosome = mutate(seed_chromosome, fleet, rng)
        if len(population) % 2 == 0:
            order = list(customers)
            rng.shuffle(order)
            chromosome = Chromosome(tuple(order), tuple(rng.choice(fleet) for _ in order))
        solution = evaluator.evaluate(chromosome.decode(fleet))
        population.append((chromosome, solution))
        if solution.rank < incumbent.rank:
            incumbent = solution
    for generation in range(config.generations):
        if time.perf_counter() >= evaluator.deadline or not customers:
            break
        population.sort(key=lambda item: item[1].rank)
        chromosome, improved = vns(*population[0], evaluator, rng)
        population[0] = (chromosome, improved)
        if improved.rank < incumbent.rank:
            incumbent = improved
        following = population[:min(config.elite_size, len(population))]

        def tournament():
            return min(rng.sample(population, min(3, len(population))), key=lambda p: p[1].rank)[0]

        while len(following) < config.population and time.perf_counter() < evaluator.deadline:
            child = crossover(tournament(), tournament(), rng)
            if rng.random() < config.mutation_probability:
                child = mutate(child, fleet, rng)
            solution = evaluator.evaluate(child.decode(fleet))
            following.append((child, solution))
            if solution.rank < incumbent.rank:
                incumbent = solution
        population = following
        history.append({"step": generation + 1, "phase": "GA_VNS",
                        "F_remaining": incumbent.score, "unassigned": len(incumbent.unassigned)})
    incumbent.runtime = time.perf_counter() - started
    incumbent.evaluations = evaluator.evaluations
    incumbent.history = history
    incumbent.diagnostics = evaluator.diagnostics()
    return incumbent
