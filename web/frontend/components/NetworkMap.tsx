'use client';

import type { InstanceInfo, RunResult } from '@/lib/types';
import { VEHICLE_COLORS } from '@/lib/format';
import { clamp, latestSnapshot, servedAt, vehiclePosition } from '@/lib/simulation';

interface Props {
  instance: InstanceInfo;
  run?: RunResult;
  time: number;
  selectedVehicle: string | null;
  onSelectVehicle: (id: string) => void;
  proofTour?: number[];
  proofEdges?: number[][];
  showVehicles?: boolean;
}

export default function NetworkMap({ instance, run, time, selectedVehicle, onSelectVehicle, proofTour, proofEdges, showVehicles = true }: Props) {
  const W = 900, H = 550, margin = 56;
  const xs = instance.nodes.map(n => n.x), ys = instance.nodes.map(n => n.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(1, maxX - minX), spanY = Math.max(1, maxY - minY);
  const scale = Math.min((W - 2 * margin) / spanX, (H - 2 * margin) / spanY);
  const tx = (x: number) => W / 2 + (x - (minX + maxX) / 2) * scale;
  const ty = (y: number) => H / 2 - (y - (minY + maxY) / 2) * scale;
  const nodeMap = new Map(instance.nodes.map(n => [n.id, n]));
  const served = servedAt(run, time);
  const snapshot = latestSnapshot(run, time);
  const routes = run?.routes || {};
  const path = (points: { x: number; y: number }[]) => points.map((p, i) => `${i ? 'L' : 'M'} ${tx(p.x)} ${ty(p.y)}`).join(' ');

  return <div className="map-shell">
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Bản đồ tuyến xe và vị trí khách hàng" className="network-map">
      <defs>
        <pattern id="grid" width="38" height="38" patternUnits="userSpaceOnUse"><path d="M 38 0 L 0 0 0 38" fill="none" stroke="#283442" strokeWidth="1" /></pattern>
        <radialGradient id="mapGlow"><stop stopColor="#32405a" stopOpacity=".5" /><stop offset="1" stopColor="#121c2a" stopOpacity="0" /></radialGradient>
        <filter id="markerGlow"><feGaussianBlur stdDeviation="7" /></filter>
      </defs>
      <rect width={W} height={H} fill="#121c2a" />
      <rect width={W} height={H} fill="url(#grid)" opacity=".8" />
      <ellipse cx="360" cy="265" rx="480" ry="340" fill="url(#mapGlow)" />
      {proofEdges?.map(([a, b], i) => {
        const from = nodeMap.get(a), to = nodeMap.get(b);
        return from && to ? <line key={`mst-${i}`} x1={tx(from.x)} y1={ty(from.y)} x2={tx(to.x)} y2={ty(to.y)} stroke="#6bdcc0" strokeWidth="8" opacity=".22" /> : null;
      })}
      {proofTour && <path d={path(proofTour.map(id => nodeMap.get(id)!).filter(Boolean))} stroke="#faad5c" strokeWidth="3" fill="none" opacity=".8" />}
      {run && showVehicles && Object.entries(routes).map(([id, events]) => {
        const color = VEHICLE_COLORS[Number(id) % VEHICLE_COLORS.length];
        const points = [nodeMap.get(0)!];
        let previous = nodeMap.get(0)!;
        for (const e of events) {
          if (e.start > time) break;
          const target = nodeMap.get(e.node)!;
          if (e.end <= time) points.push(target);
          else {
            const arrival = e.kind === 'visit' ? e.end - target.service_time : e.end;
            const fraction = e.kind === 'charge' ? 1 : clamp((time - e.start) / Math.max(arrival - e.start, 0.000001));
            points.push({ ...target, x: previous.x + (target.x - previous.x) * fraction, y: previous.y + (target.y - previous.y) * fraction });
            break;
          }
          previous = target;
        }
        return <path key={`actual-${id}`} d={path(points)} fill="none" stroke={color} strokeWidth={selectedVehicle === id ? 4 : 2.8} opacity={selectedVehicle && selectedVehicle !== id ? .38 : .9} strokeLinejoin="round" />;
      })}
      {snapshot && Object.entries(snapshot.vehicles).map(([id, vehicle]) => {
        const color = VEHICLE_COLORS[Number(id) % VEHICLE_COLORS.length];
        let previous = nodeMap.get(vehicle.origin_node) || nodeMap.get(0)!;
        const segments = vehicle.planned.map(e => {
          const target = nodeMap.get(e.node)!;
          const segment = e.end > time && e.kind !== 'charge' && e.kind !== 'dispatch'
            ? <line key={`${e.start}-${e.node}`} x1={tx(previous.x)} y1={ty(previous.y)} x2={tx(target.x)} y2={ty(target.y)}
                stroke={color} strokeWidth={selectedVehicle === id ? 3 : 2} strokeDasharray="7 7" opacity={selectedVehicle && selectedVehicle !== id ? .2 : .5} />
            : null;
          previous = target;
          return segment;
        });
        return <g key={`planned-${id}`}>{segments}</g>;
      })}
      {instance.nodes.map(node => {
        if (node.kind === 1 && run && Number(run.releases[String(node.id)]) > time) return null;
        const isServed = served.has(node.id);
        return <g key={node.id} transform={`translate(${tx(node.x)} ${ty(node.y)})`}>
          {node.kind === 0 ? <><circle r="17" fill="#f6ae5d" opacity=".2" /><rect x="-9" y="-9" width="18" height="18" rx="3" fill="#f8b566" stroke="#fff0d8" strokeWidth="1.5" /></>
            : node.kind === 2 ? <><circle r="13" fill="#59d5ba" opacity=".16" /><rect x="-7" y="-7" width="14" height="14" rx="3" fill="#5adbbd" /><text textAnchor="middle" dominantBaseline="central" fontSize="10" fontWeight="bold" fill="#122a2b">ϟ</text></>
              : <><circle r={isServed ? 5 : 7} fill={isServed ? '#5b7180' : '#eaeefa'} stroke={isServed ? '#7295a0' : '#5474a1'} strokeWidth="2" />{instance.customers.length <= 20 && <text y="-12" textAnchor="middle" fontSize="11" fill={isServed ? '#859ba9' : '#d8e6f7'}>{node.id}</text>}</>}
          <title>{node.kind === 0 ? 'Kho' : node.kind === 2 ? `Trạm sạc ${node.id}` : `Khách ${node.id}${isServed ? ' · đã giao' : ''}`}</title>
        </g>;
      })}
      {run && Object.entries(routes).map(([id, events]) => {
        const position = vehiclePosition(events, time, instance);
        if (!position) return null;
        const color = VEHICLE_COLORS[Number(id) % VEHICLE_COLORS.length];
        return <g key={`vehicle-${id}`} className="vehicle-marker" onClick={() => onSelectVehicle(id)} style={{ cursor: 'pointer' }}>
          <circle cx={tx(position.x)} cy={ty(position.y)} r="17" fill={color} opacity=".27" filter="url(#markerGlow)" />
          <circle cx={tx(position.x)} cy={ty(position.y)} r={selectedVehicle === id ? 12 : 10} fill={color} stroke="#101925" strokeWidth="3" />
          <text x={tx(position.x)} y={ty(position.y) + 4} textAnchor="middle" fontSize="11" fontWeight="bold" fill="#101925">{Number(id) + 1}</text>
          <title>Xe {Number(id) + 1}</title>
        </g>;
      })}
    </svg>
    <div className="map-legend"><span><i className="legend-square" /> Kho</span><span><i className="legend-station" /> Trạm sạc</span><span><i className="legend-dot" /> Khách</span><span><i className="legend-line" /> Đã đi</span><span><i className="legend-dash" /> Dự kiến</span></div>
  </div>;
}
