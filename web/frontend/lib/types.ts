export type Method = 'greedy' | 'ga' | 'ga_vns';
export type Tab = 'simulation' | 'comparison' | 'explanation';

export interface NodeInfo {
  id: number;
  kind: number;
  x: number;
  y: number;
  station_type: string;
  service_time: number;
}

export interface InstanceInfo {
  name: string;
  nodes: NodeInfo[];
  customers: number[];
  stations: number[];
  speed_kmh: number;
  consumption_wh_km: number;
  battery_wh: number;
  max_route_hours: number;
  curves: Record<string, { energy_wh: number; hours: number }[]>;
  tariff: { start: number; end: number; price: number }[];
}

export interface EventInfo {
  kind: 'dispatch' | 'visit' | 'station' | 'charge' | 'depot';
  node: number;
  start: number;
  end: number;
  battery_after: number;
  distance_km: number;
  charge_wh: number;
  cost: number;
  wear_wh: number;
}

export interface SearchTrace {
  baseline: number[];
  final_order: number[];
  generations: { generation: number; best_score: number; evaluations: number }[];
  examples: {
    crossover?: { parent_a: number[]; parent_b: number[]; child: number[] };
    mutation?: { before: number[]; after: number[] };
    vns?: { before: number[]; candidate: number[]; neighborhood: string };
  };
}

export interface Snapshot {
  time: number;
  new_orders: number[];
  outstanding: number[];
  order: number[];
  failed: number[];
  vehicles: Record<string, {
    origin_node: number;
    start_state: { node: number; time: number; battery: number; departure: number } | null;
    committed: EventInfo[];
    planned: EventInfo[];
  }>;
  search: SearchTrace;
}

export interface RunResult {
  instance: string;
  method: Method;
  seed: number;
  customers: number;
  served: number;
  unserved: number[];
  vehicles: number;
  operating_hours: number;
  electricity_cost: number;
  wear_proxy_kwh: number;
  replans: { time: number; revealed: number; outstanding: number; failed: number[]; evaluations: number; solve_seconds: number; score: number }[];
  routes: Record<string, EventInfo[]>;
  releases: Record<string, number>;
  dynamic_ratio: number;
  snapshots: Snapshot[];
}

export interface Job {
  id: string;
  status: 'running' | 'complete' | 'failed';
  progress: { method: Method; completed: number; total: number; method_index: number; method_count: number } | null;
  results: Partial<Record<Method, RunResult>>;
  error: string | null;
}

export interface ExperimentRow {
  instance: string;
  method: Method;
  seed: number;
  customers: number;
  served: number;
  vehicles: number;
  operating_hours: number;
  electricity_cost: number;
  wear_proxy_kwh: number;
  dynamic_ratio: number;
  unserved: number;
  replan_count: number;
  median_replan_seconds: number;
  p95_replan_seconds: number;
  total_solve_seconds: number;
  evaluations: number;
  budget_seconds: number;
}

export interface Proof {
  instance: string;
  tour: number[];
  mst_edges: number[][];
  tour_km: number;
  mst_km: number;
  upper_bound_km: number;
  optimal_km: number | null;
  ratio_to_optimal: number | null;
  scope: string;
}
