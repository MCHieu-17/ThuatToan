"""Genetic algorithm engine. `use_vns` toggles the hybrid GA-VNS variant."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.algorithms.greedy import greedy_insert
from evrp.algorithms.ranking import crowding_distance, fast_non_dominated_sort
from evrp.domain import Solution


@dataclass(frozen=True)
class Chromosome:
    order: tuple[int, ...]
    vehicles: tuple[int, ...]
    stations: tuple[int, ...] = ()

    def decode(self, fleet: list[int]) -> dict[int, list[int]]:
        routes = {vehicle: [] for vehicle in fleet}
        for customer, vehicle in zip(self.order, self.vehicles):
            routes[vehicle].append(customer)
        return routes

    def decode_plan(self, fleet: list[int]) -> tuple[dict[int, list[int]], dict[int, int]]:
        """Decode to routes plus a per-customer preferred charging station.

        The station gene is a *hint* handed to the charging DP (`-1` = no
        preference); the DP still optimizes capacity, SoC target and power.
        """
        preferred = {}
        genes = station_genes(self)
        for customer, station in zip(self.order, genes):
            if station is not None and station >= 0:
                preferred[customer] = station
        return self.decode(fleet), preferred


def station_genes(chromosome: Chromosome) -> tuple[int, ...]:
    """Station genes aligned with `order` (padded with -1 when absent)."""
    if len(chromosome.stations) == len(chromosome.order):
        return chromosome.stations
    return tuple([-1] * len(chromosome.order))


def _preference(chromosome: Chromosome) -> dict[int, int]:
    preferred = {}
    for customer, station in zip(chromosome.order, station_genes(chromosome)):
        if station is not None and station >= 0:
            preferred[customer] = station
    return preferred


def encode(routes: dict[int, list[int]], customers: list[int], fleet: list[int],
           rng: random.Random, preferred: dict[int, int] | None = None) -> Chromosome:
    preferred = preferred or {}
    order: list[int] = []
    assignment: list[int] = []
    for vehicle in fleet:
        for customer in routes.get(vehicle, []):
            order.append(customer)
            assignment.append(vehicle)
    for customer in customers:
        if customer not in order:
            order.append(customer)
            assignment.append(rng.choice(fleet))
    stations = tuple(preferred.get(customer, -1) for customer in order)
    return Chromosome(tuple(order), tuple(assignment), stations)


def crossover(first: Chromosome, second: Chromosome, rng: random.Random) -> Chromosome:
    n = len(first.order)
    if n < 2:
        return first
    left, right = sorted(rng.sample(range(n + 1), 2))
    child: list[int | None] = [None] * n
    child[left:right] = first.order[left:right]
    remaining = [x for x in second.order[right:] + second.order[:right] if x not in child]
    positions = list(range(right, n)) + list(range(left))
    for position, customer in zip(positions, remaining):
        child[position] = customer
    first_map = dict(zip(first.order, first.vehicles))
    second_map = dict(zip(second.order, second.vehicles))
    genes = tuple(first_map[c] if rng.random() < 0.5 else second_map[c] for c in child)
    first_st = dict(zip(first.order, station_genes(first)))
    second_st = dict(zip(second.order, station_genes(second)))
    stations = tuple(first_st[c] if rng.random() < 0.5 else second_st[c] for c in child)
    return Chromosome(tuple(child), genes, stations)


def mutate(chromosome: Chromosome, fleet: list[int], rng: random.Random,
           station_pool: tuple[int, ...] = ()) -> Chromosome:
    pairs = list(zip(chromosome.order, chromosome.vehicles))
    if not pairs:
        return chromosome
    stations = list(station_genes(chromosome))
    if len(pairs) > 1 and rng.random() < 0.5:
        i, j = rng.sample(range(len(pairs)), 2)
        pairs[i], pairs[j] = pairs[j], pairs[i]
        stations[i], stations[j] = stations[j], stations[i]
    elif station_pool and rng.random() < 0.3:
        i = rng.randrange(len(pairs))
        stations[i] = rng.choice((*station_pool, -1))
    else:
        i = rng.randrange(len(pairs))
        pairs[i] = (pairs[i][0], rng.choice(fleet))
    return Chromosome(tuple(p[0] for p in pairs), tuple(p[1] for p in pairs), tuple(stations))


def neighbor(chromosome: Chromosome, fleet: list[int], neighborhood: int,
             rng: random.Random, station_pool: tuple[int, ...] = ()) -> Chromosome:
    if neighborhood == 3 and station_pool:
        return _adjust_station(chromosome, rng, station_pool)
    routes = chromosome.decode(fleet)
    nonempty = [v for v in fleet if routes[v]]
    if not nonempty:
        return chromosome
    if neighborhood == 0:
        source = rng.choice(nonempty)
        customer = routes[source].pop(rng.randrange(len(routes[source])))
        destination = rng.choice(fleet)
        routes[destination].insert(rng.randrange(len(routes[destination]) + 1), customer)
    elif neighborhood == 1:
        source, destination = rng.choice(nonempty), rng.choice(nonempty)
        i = rng.randrange(len(routes[source]))
        j = rng.randrange(len(routes[destination]))
        routes[source][i], routes[destination][j] = routes[destination][j], routes[source][i]
    else:
        candidates = [v for v in fleet if len(routes[v]) >= 2]
        if not candidates:
            return chromosome
        vehicle = rng.choice(candidates)
        i, j = sorted(rng.sample(range(len(routes[vehicle]) + 1), 2))
        routes[vehicle][i:j] = reversed(routes[vehicle][i:j])
    return encode(routes, list(chromosome.order), fleet, rng, _preference(chromosome))


def _adjust_station(chromosome: Chromosome, rng: random.Random,
                    station_pool: tuple[int, ...]) -> Chromosome:
    """Charge-adjust neighborhood: retarget the preferred station of one leg."""
    genes = list(station_genes(chromosome))
    if not genes or not station_pool:
        return chromosome
    index = rng.randrange(len(genes))
    choices = [value for value in (*station_pool, -1) if value != genes[index]]
    if not choices:
        return chromosome
    genes[index] = rng.choice(choices)
    return Chromosome(chromosome.order, chromosome.vehicles, tuple(genes))


def _evaluate(evaluator: FleetEvaluator, chromosome: Chromosome, fleet: list[int],
              deadline: float | None):
    routes, preferred = chromosome.decode_plan(fleet)
    return evaluator.evaluate(routes, deadline, preferred)


def _apply_vns(chromosome: Chromosome, solution: Solution, evaluator: FleetEvaluator,
               rng: random.Random, deadline: float | None):
    fleet = sorted(evaluator.states)
    station_pool = tuple(evaluator.instance.stations) if evaluator.config.use_station_genes else ()
    neighborhood = 0
    for _ in range(evaluator.config.vns_iterations):
        if deadline is not None and time.perf_counter() >= deadline:
            break
        candidate_chromosome = neighbor(chromosome, fleet, neighborhood, rng, station_pool)
        if candidate_chromosome == chromosome:
            neighborhood = (neighborhood + 1) % 4
            continue
        candidate = _evaluate(evaluator, candidate_chromosome, fleet, deadline)
        if candidate.rank < solution.rank:
            chromosome, solution, neighborhood = candidate_chromosome, candidate, 0
        else:
            neighborhood = (neighborhood + 1) % 4
    return chromosome, solution


def _rank(objectives: list[tuple[float, ...]]):
    """Return (front_rank, crowding) maps keyed by population index."""
    fronts = fast_non_dominated_sort(objectives)
    ranks: dict[int, int] = {}
    crowd: dict[int, float] = {}
    for rank, front in enumerate(fronts):
        for index in front:
            ranks[index] = rank
        crowd.update(crowding_distance(objectives, front))
    return fronts, ranks, crowd


def _select_survivors(population: list, size: int) -> list:
    """NSGA-II environmental selection: best fronts first, crowding for the cut."""
    objectives = [solution.objectives for _, solution in population]
    fronts = fast_non_dominated_sort(objectives)
    survivors: list[int] = []
    for front in fronts:
        if len(survivors) + len(front) <= size:
            survivors.extend(front)
            continue
        distance = crowding_distance(objectives, front)
        ordered = sorted(front, key=lambda i: distance[i], reverse=True)
        survivors.extend(ordered[: size - len(survivors)])
        break
    return [population[i] for i in survivors]


def _export_front(population: list) -> list[dict]:
    """Serialize the non-dominated front at the best achieved feasibility level.

    The raw front also contains degenerate solutions that serve nobody to win on
    time; we keep only the trade-off set with the fewest unassigned customers.
    """
    if not population:
        return []
    objectives = [solution.objectives for _, solution in population]
    front = fast_non_dominated_sort(objectives)[0]
    best_unassigned = min(len(population[i][1].unassigned) for i in front)
    exported = []
    for index in front:
        solution = population[index][1]
        if len(solution.unassigned) != best_unassigned:
            continue
        exported.append({
            "unassigned": len(solution.unassigned),
            "time": solution.time_cost,
            "electricity": solution.electricity_cost,
            "degradation": solution.degradation_cost,
            "score": solution.score,
            "complete": solution.complete,
        })
    return exported


def run_ga(evaluator: FleetEvaluator, seed: int = 42, use_vns: bool = False,
           seed_routes: dict[int, list[int]] | None = None,
           deadline: float | None = None) -> Solution:
    started = time.perf_counter()
    config = evaluator.config
    rng = random.Random(seed)
    fleet = sorted(evaluator.states)
    customers = sorted(evaluator.customers)
    station_pool = tuple(evaluator.instance.stations) if config.use_station_genes else ()
    budget = config.solver_budget_seconds if deadline is None else max(0.0, deadline - started)
    deadline = min(evaluator.deadline or (started + budget), started + budget)
    evaluator.deadline = deadline

    warm_deadline = started + budget * 0.6
    incumbent = greedy_insert(evaluator, seed_routes, warm_deadline)
    seed_chromosome = encode(incumbent.routes, customers, fleet, rng)
    evaluated_seed = _evaluate(evaluator, seed_chromosome, fleet, deadline)
    if evaluated_seed.rank < incumbent.rank:
        incumbent = evaluated_seed

    population = [(seed_chromosome, evaluated_seed)]
    while len(population) < config.population and time.perf_counter() < deadline:
        if len(population) % 2 == 0:
            order = list(customers)
            rng.shuffle(order)
            chromosome = Chromosome(tuple(order), tuple(rng.choice(fleet) for _ in order))
        else:
            chromosome = mutate(seed_chromosome, fleet, rng, station_pool)
        population.append((chromosome, _evaluate(evaluator, chromosome, fleet, deadline)))

    if config.pareto_selection:
        population, incumbent = _evolve_pareto(population, incumbent, evaluator, fleet,
                                               customers, rng, deadline, use_vns, station_pool)
    else:
        population, incumbent = _evolve_scalar(population, incumbent, evaluator, fleet,
                                               customers, rng, deadline, use_vns, station_pool)

    incumbent.pareto_front = _export_front(population)
    incumbent.runtime = time.perf_counter() - started
    incumbent.evaluations = evaluator.counters.evaluations
    return incumbent


def _evolve_scalar(population, incumbent, evaluator, fleet, customers, rng, deadline, use_vns,
                   station_pool=()):
    config = evaluator.config

    def tournament():
        return min(rng.sample(population, min(3, len(population))),
                   key=lambda item: item[1].rank)[0]

    for _ in range(config.generations):
        if time.perf_counter() >= deadline or not customers:
            break
        population.sort(key=lambda item: item[1].rank)
        if use_vns:
            chromosome, improved = _apply_vns(*population[0], evaluator, rng, deadline)
            population[0] = (chromosome, improved)
            if improved.rank < incumbent.rank:
                incumbent = improved
        following = population[:min(config.elite_size, len(population))]
        while len(following) < config.population and time.perf_counter() < deadline:
            child = crossover(tournament(), tournament(), rng)
            if rng.random() < config.mutation_probability:
                child = mutate(child, fleet, rng, station_pool)
            solution = _evaluate(evaluator, child, fleet, deadline)
            following.append((child, solution))
            if solution.rank < incumbent.rank:
                incumbent = solution
        population = following
    return population, incumbent


def _evolve_pareto(population, incumbent, evaluator, fleet, customers, rng, deadline, use_vns,
                   station_pool=()):
    config = evaluator.config

    def select():
        a, b = rng.sample(range(len(population)), 2)
        if ranks[a] != ranks[b]:
            return population[a if ranks[a] < ranks[b] else b][0]
        return population[a if crowd.get(a, 0.0) >= crowd.get(b, 0.0) else b][0]

    for _ in range(config.generations):
        if time.perf_counter() >= deadline or not customers:
            break
        _, ranks, crowd = _rank([solution.objectives for _, solution in population])
        if use_vns:
            elite_index = min(range(len(population)), key=lambda i: population[i][1].rank)
            chromosome, improved = _apply_vns(*population[elite_index], evaluator, rng, deadline)
            population[elite_index] = (chromosome, improved)
            if improved.rank < incumbent.rank:
                incumbent = improved
        offspring = []
        while len(offspring) < config.population and time.perf_counter() < deadline:
            child = crossover(select(), select(), rng)
            if rng.random() < config.mutation_probability:
                child = mutate(child, fleet, rng, station_pool)
            solution = _evaluate(evaluator, child, fleet, deadline)
            offspring.append((child, solution))
            if solution.rank < incumbent.rank:
                incumbent = solution
        population = _select_survivors(population + offspring, config.population)
    return population, incumbent