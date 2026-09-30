'use client';

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { InstanceInfo, RunResult, SearchTrace } from '@/lib/types';
import { clockLabel, fmt, METHOD_COLOR, METHOD_LABEL, VEHICLE_COLORS } from '@/lib/format';
import { activeEvent, batteryAt, interpolateCurve } from '@/lib/simulation';

export function BatteryPanel({ instance, run, time, selectedVehicle, onSelectVehicle }: {
  instance: InstanceInfo; run: RunResult; time: number; selectedVehicle: string | null; onSelectVehicle: (id: string) => void;
}) {
  const vehicleIds = Object.keys(run.routes).filter(id => run.routes[id][0]?.start <= time);
  return <div className="panel fleet-panel">
    <div className="panel-heading"><div><span className="eyebrow">FLEET STATUS</span><h3>Đội xe tại {clockLabel(time)}</h3></div><span className="subtle">{vehicleIds.length} xe đã xuất phát</span></div>
    {vehicleIds.length ? <div className="vehicle-list">{vehicleIds.map(id => {
      const route = run.routes[id];
      const battery = batteryAt(route, time, instance);
      const active = activeEvent(route, time);
      const pct = Math.max(0, Math.min(100, battery / instance.battery_wh * 100));
      const label = active?.kind === 'charge' ? 'Đang sạc' : active?.kind === 'visit' ? 'Đang giao' : active?.kind === 'station' ? 'Tới trạm' : active?.kind === 'depot' ? 'Về kho' : 'Đang chờ / xong';
      return <button key={id} className={`vehicle-row ${selectedVehicle === id ? 'selected' : ''}`} onClick={() => onSelectVehicle(id)}>
        <div className="vehicle-row-top"><span><i className="vehicle-swatch" style={{ background: VEHICLE_COLORS[Number(id) % VEHICLE_COLORS.length] }} />Xe {Number(id) + 1}</span><b>{fmt(pct, 0)}%</b></div>
        <div className="battery-track"><div style={{ width: `${pct}%`, background: pct < 20 ? '#f07082' : VEHICLE_COLORS[Number(id) % VEHICLE_COLORS.length] }} /></div>
        <small>{label}{active ? ` · điểm ${active.node}` : ''}</small>
      </button>;
    })}</div> : <p className="empty-note">Xe sẽ xuất hiện sau khi bắt đầu mô phỏng.</p>}
  </div>;
}

export function ChargingPanel({ instance, run, time, selectedVehicle }: {
  instance: InstanceInfo; run: RunResult; time: number; selectedVehicle: string | null;
}) {
  const allCharges = Object.entries(run.routes).flatMap(([id, events]) => events.filter(e => e.kind === 'charge').map(e => ({ id, event: e })));
  const selected = allCharges.filter(x => x.id === selectedVehicle && x.event.start <= time).at(-1)
    || allCharges.filter(x => x.event.start <= time).at(-1);
  const station = selected && instance.nodes.find(n => n.id === selected.event.node);
  const curve = instance.curves[station?.station_type || Object.keys(instance.curves)[0]] || [];
  const curvePoints = Array.from({ length: 41 }, (_, i) => {
    const energy = instance.battery_wh * i / 40;
    return { energy: energy / 1000, minutes: interpolateCurve(curve, energy) * 60 };
  });
  const before = selected ? selected.event.battery_after - selected.event.charge_wh : 0;
  const after = selected ? selected.event.battery_after : instance.battery_wh;
  return <div className="panel charge-panel">
    <div className="panel-heading"><div><span className="eyebrow">CHARGING INTELLIGENCE</span><h3>Sạc phi tuyến & giá điện</h3></div><span className="pill mint">Dữ liệu đường cong gốc</span></div>
    <p className="panel-description">Đường cong cho biết thời gian tích lũy để đạt từng mức pin. Dốc hơn ở mức pin cao nghĩa là sạc chậm hơn.</p>
    <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={curvePoints} margin={{ top: 10, right: 12, left: -15, bottom: 2 }}>
      <CartesianGrid stroke="#2a3849" strokeDasharray="3 4" /><XAxis dataKey="energy" type="number" domain={[0, instance.battery_wh / 1000]} tick={{ fill: '#8ea0b3', fontSize: 11 }} tickFormatter={x => `${x} kWh`} />
      <YAxis dataKey="minutes" tick={{ fill: '#8ea0b3', fontSize: 11 }} tickFormatter={x => `${x}′`} />
      <Tooltip contentStyle={{ background: '#1b2a3b', border: '1px solid #3b5067', borderRadius: 10, color: '#f3f6fa' }} formatter={(value) => [`${fmt(Number(value))} phút`, 'Thời gian tích lũy']} labelFormatter={x => `${fmt(Number(x))} kWh`} />
      <Line type="linear" dataKey="minutes" stroke="#6bdcc0" strokeWidth={3} dot={false} isAnimationActive={false} />
    </LineChart></ResponsiveContainer></div>
    <div className="tariff-title"><span>Giá điện mô phỏng theo giờ</span><span className="subtle">đơn vị tương đối / kWh</span></div>
    <div className="tariff-track"><div className="low" style={{ width: '20%' }}>0–2h · 1</div><div className="peak" style={{ width: '30%' }}>2–5h · 3</div><div className="mid" style={{ width: '50%' }}>5–10h · 1,5</div></div>
    {selected ? <div className="charge-insight"><span className="charge-icon">ϟ</span><div><strong>Xe {Number(selected.id) + 1} sạc tại trạm {selected.event.node}</strong><small>{clockLabel(selected.event.start)}–{clockLabel(selected.event.end)} · {fmt(before / 1000)} → {fmt(after / 1000)} kWh</small></div><b>{fmt(selected.event.cost)} đv</b></div>
      : <p className="empty-note">Chưa đến lần sạc nào; đồ thị vẫn thể hiện đường cong trạm sạc của benchmark.</p>}
  </div>;
}

export function SearchPanel({ trace }: { trace?: SearchTrace }) {
  const points = trace?.generations || [];
  const examples = trace?.examples || {};
  const chromosome = (ids?: number[]) => ids ? ids.slice(0, 13).join(' → ') + (ids.length > 13 ? ' …' : '') : '—';
  return <div className="search-grid">
    <div className="panel search-chart">
      <div className="panel-heading"><div><span className="eyebrow">OPTIMIZATION TRACE</span><h3>Điểm tốt nhất qua thế hệ</h3></div><span className="pill blue">Điểm thấp hơn tốt hơn</span></div>
      {points.length ? <div className="chart-wrap tall"><ResponsiveContainer width="100%" height="100%"><LineChart data={points} margin={{ top: 10, right: 12, left: -15, bottom: 5 }}>
        <CartesianGrid stroke="#2a3849" strokeDasharray="3 4" /><XAxis dataKey="generation" tick={{ fill: '#8ea0b3', fontSize: 11 }} /><YAxis domain={['dataMin', 'dataMax']} tick={{ fill: '#8ea0b3', fontSize: 11 }} />
        <Tooltip contentStyle={{ background: '#1b2a3b', border: '1px solid #3b5067', borderRadius: 10, color: '#f3f6fa' }} formatter={v => [fmt(Number(v), 4), 'Điểm tốt nhất']} labelFormatter={v => `Thế hệ ${v}`} />
        <Line type="stepAfter" dataKey="best_score" stroke="#faad5c" strokeWidth={3} dot={false} isAnimationActive={false} />
      </LineChart></ResponsiveContainer></div> : <p className="empty-note">Chạy GA hoặc GA+VNS để xem tiến trình tối ưu ở lần lập tuyến đang chọn.</p>}
      <p className="panel-description">Điểm được chuẩn hóa theo nghiệm tham lam của cùng lần lập tuyến. Đồ thị này chỉ diễn tả quá trình tìm kiếm, không phải ba mục tiêu độc lập.</p>
    </div>
    <div className="panel steps-panel">
      <div className="panel-heading"><div><span className="eyebrow">CHROMOSOME WALKTHROUGH</span><h3>Từ thứ tự khách đến tuyến xe</h3></div></div>
      <div className="algorithm-steps">
        <div><span className="step-index">01</span><div><strong>Hoán vị ban đầu</strong><p>Mỗi số là một khách cần giao. Bộ giải mã đi theo thứ tự này và chia thành các tuyến khả thi.</p><code>{chromosome(trace?.baseline)}</code></div></div>
        <div><span className="step-index">02</span><div><strong>Lai ghép OX</strong><p>Hai thứ tự cha mẹ tạo một thứ tự con, vẫn có đúng một lần cho mỗi khách.</p><code>{chromosome(examples.crossover?.child)}</code></div></div>
        <div><span className="step-index">03</span><div><strong>Đột biến</strong><p>Chuyển vị trí, đổi chỗ hoặc đảo một đoạn của thứ tự.</p><code>{chromosome(examples.mutation?.after)}</code></div></div>
        <div><span className="step-index">04</span><div><strong>VNS</strong><p>Thử các lân cận relocate, swap và reverse; giữ phương án có điểm thấp hơn.</p><code>{chromosome(examples.vns?.candidate)}</code></div></div>
      </div>
    </div>
  </div>;
}

export function ComparisonChart({ rows }: { rows: { method: keyof typeof METHOD_LABEL; hours: number; cost: number; wear: number }[] }) {
  const metrics = [
    { key: 'hours' as const, name: 'Giờ vận hành', unit: 'giờ' },
    { key: 'cost' as const, name: 'Chi phí điện', unit: 'đv' },
    { key: 'wear' as const, name: 'Chỉ số hao mòn', unit: 'kWh' },
  ];
  return <div className="metric-grid">{metrics.map(metric => {
    const max = Math.max(1, ...rows.map(r => r[metric.key]));
    return <div className="panel metric-panel" key={metric.key}><span className="eyebrow">{metric.name}</span>
      <div className="metric-bars">{rows.map(row => <div className="metric-bar-row" key={row.method}>
        <span>{METHOD_LABEL[row.method]}</span><div><i style={{ width: `${row[metric.key] / max * 100}%`, background: METHOD_COLOR[row.method] }} /></div><b>{fmt(row[metric.key])} <small>{metric.unit}</small></b>
      </div>)}</div>
    </div>;
  })}</div>;
}
