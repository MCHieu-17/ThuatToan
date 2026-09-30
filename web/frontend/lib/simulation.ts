import type { EventInfo, InstanceInfo, RunResult } from './types';

export const clamp = (value: number, low = 0, high = 1) => Math.max(low, Math.min(high, value));

export function interpolateCurve(points: { energy_wh: number; hours: number }[], x: number, inverse = false): number {
  if (!points.length) return 0;
  const pairs = points.map(p => inverse ? [p.hours, p.energy_wh] : [p.energy_wh, p.hours]);
  const value = clamp(x, pairs[0][0], pairs[pairs.length - 1][0]);
  for (let i = 1; i < pairs.length; i++) {
    if (value <= pairs[i][0]) {
      const [a, b] = pairs[i - 1];
      const [c, d] = pairs[i];
      return b + (value - a) * (d - b) / (c - a);
    }
  }
  return pairs[pairs.length - 1][1];
}

export function activeEvent(route: EventInfo[], time: number): EventInfo | null {
  return route.find(e => e.start <= time && e.end > time) || null;
}

export function batteryAt(route: EventInfo[], time: number, instance: InstanceInfo): number {
  let before = instance.battery_wh;
  for (const e of route) {
    if (time < e.start) return before;
    if (time >= e.end || e.end === e.start) {
      before = e.battery_after;
      continue;
    }
    if (e.kind === 'charge') {
      const station = instance.nodes.find(n => n.id === e.node);
      const curve = instance.curves[station?.station_type || ''];
      if (curve) return interpolateCurve(curve, interpolateCurve(curve, before) + time - e.start, true);
    }
    const arrival = e.kind === 'visit' ? e.end - (instance.nodes.find(n => n.id === e.node)?.service_time || 0) : e.end;
    return before + (e.battery_after - before) * clamp((time - e.start) / Math.max(arrival - e.start, 0.000001));
  }
  return before;
}

export function vehiclePosition(route: EventInfo[], time: number, instance: InstanceInfo): { x: number; y: number; node: number } | null {
  const nodes = new Map(instance.nodes.map(n => [n.id, n]));
  let from = nodes.get(0);
  if (!from || !route.length || time < route[0].start) return null;
  for (const e of route) {
    const target = nodes.get(e.node);
    if (!target) continue;
    if (time < e.start) return { x: from.x, y: from.y, node: from.id };
    if (time < e.end) {
      const arrival = e.kind === 'visit' ? e.end - target.service_time : e.end;
      const fraction = e.kind === 'charge' ? 1 : clamp((time - e.start) / Math.max(arrival - e.start, 0.000001));
      return { x: from.x + (target.x - from.x) * fraction,
               y: from.y + (target.y - from.y) * fraction, node: fraction === 1 ? target.id : from.id };
    }
    from = target;
  }
  return { x: from.x, y: from.y, node: from.id };
}

export function latestSnapshot(run: RunResult | undefined, time: number) {
  return run?.snapshots.filter(s => s.time <= time + 1e-8).at(-1) || null;
}

export function servedAt(run: RunResult | undefined, time: number): Set<number> {
  if (!run) return new Set();
  return new Set(Object.values(run.routes).flat().filter(e => e.kind === 'visit' && e.end <= time).map(e => e.node));
}
