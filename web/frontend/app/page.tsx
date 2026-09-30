'use client';

import { useCallback, useEffect, useState } from 'react';
import NetworkMap from '@/components/NetworkMap';
import { BatteryPanel, ChargingPanel, ComparisonChart, SearchPanel } from '@/components/Insights';
import type { ExperimentRow, InstanceInfo, Job, Method, Proof, RunResult, Tab } from '@/lib/types';
import { clockLabel, eventLabel, fmt, METHOD_COLOR, METHOD_LABEL, runEnd } from '@/lib/format';
import { latestSnapshot, servedAt } from '@/lib/simulation';

type InstanceListItem = { name: string; customers: number; stations: number };
type Ratio = 0 | 0.5 | 1;
type Budget = 0.1 | 0.5 | 2;
const methods: Method[] = ['greedy', 'ga', 'ga_vns'];

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: 'no-store', ...init });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Lỗi HTTP ${response.status}`);
  }
  return response.json();
}

export default function Home() {
  const [tab, setTab] = useState<Tab>('simulation');
  const [instances, setInstances] = useState<InstanceListItem[]>([]);
  const [instanceName, setInstanceName] = useState('tc0c10s2cf1');
  const [instance, setInstance] = useState<InstanceInfo | null>(null);
  const [proof, setProof] = useState<Proof | null>(null);
  const [rows, setRows] = useState<ExperimentRow[]>([]);
  const [ratio, setRatio] = useState<Ratio>(0.5);
  const [seed, setSeed] = useState(0);
  const [budget, setBudget] = useState<Budget>(0.1);
  const [method, setMethod] = useState<Method>('ga_vns');
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [selectedVehicle, setSelectedVehicle] = useState<string | null>(null);
  const resetPlayback = () => { setJob(null); setJobId(null); setPlaying(false); setTime(0); setSelectedVehicle(null); };

  useEffect(() => {
    Promise.all([api<InstanceListItem[]>('/api/instances'), api<ExperimentRow[]>('/api/experiments')])
      .then(([items, experimentRows]) => { setInstances(items); setRows(experimentRows); })
      .catch(err => setError(`Không kết nối được FastAPI: ${err.message}. Hãy chạy backend ở cổng 8000.`));
  }, []);

  useEffect(() => {
    setInstance(null); setProof(null); setJob(null); setJobId(null); setTime(0); setPlaying(false);
    Promise.all([api<InstanceInfo>(`/api/instances/${instanceName}`), api<Proof>(`/api/proof/${instanceName}`)])
      .then(([details, proofData]) => { setInstance(details); setProof(proofData); setError(null); })
      .catch(err => setError(err.message));
  }, [instanceName]);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    const poll = async () => {
      try {
        const next = await api<Job>(`/api/runs/${jobId}`);
        if (!active) return;
        setJob(next);
        if (next.status === 'failed') setError(next.error || 'Mô phỏng thất bại');
        if (next.status !== 'running') clearInterval(timer);
      } catch (err) {
        if (active) { setError((err as Error).message); clearInterval(timer); }
      }
    };
    const timer = setInterval(poll, 600);
    poll();
    return () => { active = false; clearInterval(timer); };
  }, [jobId]);

  const run = job?.results[method];
  const maxTime = runEnd(run);
  useEffect(() => {
    if (!playing || !run) return;
    const timer = setInterval(() => setTime(t => {
      const next = Math.min(maxTime, t + 0.08 * speed);
      if (next >= maxTime) setPlaying(false);
      return next;
    }), 80);
    return () => clearInterval(timer);
  }, [playing, run, maxTime, speed]);

  const startRun = useCallback(async (all: boolean) => {
    if (!instance) return;
    setError(null); setPlaying(false); setTime(0); setSelectedVehicle(null);
    try {
      const result = await api<{ id: string }>('/api/runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instance: instanceName, dynamic_ratio: ratio, seed, seconds: budget,
                               methods: all ? methods : [method] }),
      });
      setJob(null); setJobId(result.id);
    } catch (err) { setError((err as Error).message); }
  }, [instance, instanceName, ratio, seed, budget, method]);

  const selectPreset = (name: string, nextRatio: Ratio, nextSeed: number) => {
    setRatio(nextRatio); setSeed(nextSeed); setMethod('ga_vns'); setTab('simulation');
    if (instanceName === name) resetPlayback();
    else setInstanceName(name);
  };

  const snapshot = latestSnapshot(run, time);
  const served = servedAt(run, time).size;
  const revealed = run ? Object.values(run.releases).filter(t => t <= time + 1e-8).length : 0;
  const experimentSubset = rows.filter(r => r.instance === instanceName && r.dynamic_ratio === ratio);
  const hasLiveComparison = methods.every(m => !!job?.results[m]);
  const comparison = methods.map(m => {
    const result = hasLiveComparison ? job?.results[m] : undefined;
    const group = experimentSubset.filter(r => r.method === m);
    const average = (key: 'operating_hours' | 'electricity_cost' | 'wear_proxy_kwh') => group.reduce((sum, row) => sum + row[key], 0) / (group.length || 1);
    const latencies = result?.replans.map(r => r.solve_seconds).sort((a, b) => a - b);
    return { method: m, hours: result?.operating_hours ?? average('operating_hours'),
             cost: result?.electricity_cost ?? average('electricity_cost'),
             wear: result?.wear_proxy_kwh ?? average('wear_proxy_kwh'),
             vehicles: result?.vehicles ?? group.reduce((sum, row) => sum + row.vehicles, 0) / (group.length || 1),
             served: result?.served ?? group.reduce((sum, row) => sum + row.served, 0) / (group.length || 1),
             p95: latencies?.length ? latencies[Math.ceil(0.95 * latencies.length) - 1]
               : group.length ? group.reduce((sum, row) => sum + row.p95_replan_seconds, 0) / group.length : null,
    };
  });
  const hasComparison = hasLiveComparison || experimentSubset.length > 0;
  const recentEvents = run ? [
    ...run.snapshots.map(s => ({ time: s.time, label: `${s.new_orders.length} đơn mới xuất hiện`, detail: `Lập lại tuyến · ${s.outstanding.length} đơn đang chờ`, icon: '◆' })),
    ...Object.entries(run.routes).flatMap(([id, route]) => route.filter(e => e.kind === 'visit' || e.kind === 'charge').map(e => ({
      time: e.end, label: `${eventLabel[e.kind]} · xe ${Number(id) + 1}`, detail: e.kind === 'charge' ? `Trạm ${e.node} · ${fmt(e.charge_wh / 1000)} kWh` : `Khách ${e.node}`, icon: e.kind === 'charge' ? 'ϟ' : '✓',
    }))),
  ].filter(e => e.time <= time + 1e-8).sort((a, b) => b.time - a.time).slice(0, 6) : [];

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><span className="brand-mark">ϟ</span><div><strong>EVRP<span>VISUAL LAB</span></strong><small>TRỰC QUAN HÓA THUẬT TOÁN</small></div></div>
      <nav className="nav-tabs" aria-label="Điều hướng chính">
        <button className={tab === 'simulation' ? 'active' : ''} onClick={() => setTab('simulation')}>◉ <span>Mô phỏng</span></button>
        <button className={tab === 'comparison' ? 'active' : ''} onClick={() => setTab('comparison')}>▥ <span>So sánh</span></button>
        <button className={tab === 'explanation' ? 'active' : ''} onClick={() => setTab('explanation')}>◇ <span>Giải thích thuật toán</span></button>
      </nav><div className="topbar-right"><span className="status-dot" /> DEMO TRÊN MÁY CÁ NHÂN</div></header>

    <main className="content">
      <div className="page-intro"><div className="section-kicker"><span className="accent-line" /> EV ROUTING RESEARCH / INTERACTIVE DEMO</div>
        <h1>{tab === 'simulation' ? <>Khi đơn hàng xuất hiện, <em>tuyến xe thay đổi.</em></> : tab === 'comparison' ? <>Cùng một kịch bản, <em>ba cách điều độ.</em></> : <>Nhìn thấy thuật toán <em>ra quyết định.</em></>}</h1>
        <p>{tab === 'simulation' ? 'Theo dõi xe điện giao hàng theo thời gian mô phỏng: tuyến đường, mức pin, trạm sạc và thời điểm đơn mới làm kế hoạch thay đổi.' : tab === 'comparison' ? 'So sánh tham lam, GA và GA+VNS trên cùng bộ đơn, seed và ngân sách. Các mục tiêu được trình bày riêng để thấy đánh đổi.' : 'Đi từ một thứ tự khách hàng đến lịch xe khả thi, xem GA+VNS cải thiện nghiệm và kiểm tra giới hạn của chứng minh xấp xỉ.'}</p>
      </div>

      {error && <div className="error-banner" role="alert"><strong>Có lỗi:</strong> {error}<button onClick={() => setError(null)} aria-label="Đóng thông báo">×</button></div>}

      <section className="scenario-bar panel">
        <div className="scenario-title"><span className="eyebrow">THIẾT LẬP KỊCH BẢN</span><strong>Chọn dữ liệu & thuật toán</strong></div>
        <label>Benchmark<select disabled={job?.status === 'running'} value={instanceName} onChange={e => setInstanceName(e.target.value)}>{instances.length ? instances.map(item => <option key={item.name} value={item.name}>{item.name} · {item.customers} khách</option>) : <option value={instanceName}>{instanceName}</option>}</select></label>
        <label>Đơn phát sinh<select disabled={job?.status === 'running'} value={ratio} onChange={e => { resetPlayback(); setRatio(Number(e.target.value) as Ratio); }}><option value={0}>0% · Tĩnh</option><option value={0.5}>50% · Động</option><option value={1}>100% · Động</option></select></label>
        <label>Seed<input disabled={job?.status === 'running'} type="number" min="0" max="9999" value={seed} onChange={e => { resetPlayback(); setSeed(Math.max(0, Math.min(9999, Number(e.target.value) || 0))); }} /></label>
        <label>Ngân sách / lần<select disabled={job?.status === 'running'} value={budget} onChange={e => { resetPlayback(); setBudget(Number(e.target.value) as Budget); }}><option value={0.1}>0,1 giây</option><option value={0.5}>0,5 giây</option><option value={2}>2 giây</option></select></label>
        {tab !== 'comparison' && <label>Phương pháp<select disabled={job?.status === 'running'} value={method} onChange={e => setMethod(e.target.value as Method)}>{methods.map(m => <option key={m} value={m}>{METHOD_LABEL[m]}</option>)}</select></label>}
        <button className="primary-button" disabled={!instance || job?.status === 'running'} onClick={() => startRun(tab === 'comparison')}><span>▶</span> {job?.status === 'running' ? 'Đang tính...' : tab === 'comparison' ? 'Chạy cả 3' : 'Chạy mô phỏng'}</button>
      </section>

      {job?.status === 'running' && <div className="progress-banner"><span className="spinner" /> Đang tính {job.progress ? `${METHOD_LABEL[job.progress.method]} · lần ${job.progress.completed}/${job.progress.total} · phương pháp ${job.progress.method_index}/${job.progress.method_count}` : 'kịch bản...'} <small>Thời gian này là thời gian máy tính xử lý, khác đồng hồ mô phỏng bên dưới.</small></div>}

      {tab === 'simulation' && <>
        <div className="preset-row"><span>KỊCH BẢN GỢI Ý</span>
          <button disabled={job?.status === 'running'} onClick={() => selectPreset('tc0c10s2cf1', 0.5, 0)}>◆ Đơn hàng đến dần <b>10 khách</b></button>
          <button disabled={job?.status === 'running'} onClick={() => selectPreset('tc0c20s3cf2', 0.5, 0)}>ϟ Sạc trong giờ cao điểm <b>20 khách</b></button>
          <button disabled={job?.status === 'running'} onClick={() => selectPreset('tc0c10s2cf1', 0, 0)}>◎ Tất cả đơn biết trước <b>Tĩnh</b></button>
        </div>
        <div className="stat-strip">
          <div><span>KHÁCH ĐÃ XUẤT HIỆN</span><strong>{revealed}<small> / {instance?.customers.length || 0}</small></strong></div>
          <div><span>ĐÃ GIAO TẠI THỜI ĐIỂM NÀY</span><strong>{served}<small> / {instance?.customers.length || 0}</small></strong></div>
          <div><span>GIỜ VẬN HÀNH CẢ TUYẾN</span><strong>{run ? fmt(run.operating_hours) : '—'}<small> giờ</small></strong></div>
          <div><span>CHI PHÍ ĐIỆN CẢ TUYẾN</span><strong>{run ? fmt(run.electricity_cost) : '—'}<small> đv</small></strong></div>
        </div>
        <div className="simulation-grid">
          <div className="panel map-panel"><div className="panel-heading"><div><span className="eyebrow">LIVE ROUTE VIEW</span><h2>Mạng lưới giao hàng</h2></div><span className="pill"><i className="status-dot" /> GIỜ MÔ PHỎNG {clockLabel(time)}</span></div>
            {instance ? <NetworkMap instance={instance} run={run} time={time} selectedVehicle={selectedVehicle} onSelectVehicle={setSelectedVehicle} /> : <div className="map-loading">Đang tải dữ liệu benchmark...</div>}
            <div className="playback"><button className="play-button" disabled={!run} onClick={() => { if (time >= maxTime) setTime(0); setPlaying(!playing); }}>{playing ? 'Ⅱ' : '▶'}</button><span>{clockLabel(time)}</span>
              <div className="range-wrap"><input aria-label="Tua thời gian mô phỏng" type="range" min="0" max={Math.max(maxTime, 0.01)} step="0.01" value={Math.min(time, maxTime || 0)} disabled={!run} onChange={e => { setPlaying(false); setTime(Number(e.target.value)); }} />
                {run?.snapshots.map((s, i) => <button key={i} className="timeline-tick" style={{ left: `${s.time / Math.max(maxTime, 0.01) * 100}%` }} title={`${clockLabel(s.time)} · ${s.new_orders.length} đơn mới`} onClick={() => { setPlaying(false); setTime(s.time); }} />)}</div>
              <span>{clockLabel(maxTime)}</span><select aria-label="Tốc độ phát" value={speed} onChange={e => setSpeed(Number(e.target.value))}><option value={0.5}>0,5×</option><option value={1}>1×</option><option value={2}>2×</option></select></div>
          </div>
          <div className="side-stack">
            <div className="panel decision-panel"><span className="eyebrow">QUYẾT ĐỊNH HIỆN TẠI</span><h3>{snapshot ? `Lập lại tuyến lúc ${clockLabel(snapshot.time)}` : 'Chờ kịch bản bắt đầu'}</h3>
              <p>{snapshot ? `${snapshot.new_orders.length} đơn mới xuất hiện. Thuật toán sắp xếp ${snapshot.outstanding.length} khách đang chờ; xe đang chạy giữ nguyên chặng hiện tại.` : 'Bấm “Chạy mô phỏng”, sau đó phát hoặc tua đến dấu trên thanh thời gian để thấy từng lần đổi tuyến.'}</p>
              {snapshot && <div className="order-chips">{snapshot.new_orders.map(id => <span key={id}>Khách {id}</span>)}</div>}
              {snapshot && <button className="text-button" onClick={() => setTab('explanation')}>Xem GA + VNS hoạt động →</button>}
            </div>
            {instance && run ? <BatteryPanel instance={instance} run={run} time={time} selectedVehicle={selectedVehicle} onSelectVehicle={setSelectedVehicle} /> : <div className="panel fleet-panel"><span className="eyebrow">FLEET STATUS</span><h3>Đội xe</h3><p className="empty-note">Mức pin từng xe sẽ xuất hiện sau khi chạy mô phỏng.</p></div>}
          </div>
        </div>
        <div className="bottom-grid">{instance && run ? <ChargingPanel instance={instance} run={run} time={time} selectedVehicle={selectedVehicle} /> : <div className="panel charge-panel"><span className="eyebrow">CHARGING INTELLIGENCE</span><h3>Sạc phi tuyến & giá điện</h3><p className="empty-note">Chạy một kịch bản để xem đường cong sạc và chi phí của các lần sạc thực tế.</p></div>}
          <div className="panel activity-panel"><div className="panel-heading"><div><span className="eyebrow">EVENT STREAM</span><h3>Điều gì vừa xảy ra?</h3></div></div>
            {recentEvents.length ? <div className="activity-list">{recentEvents.map((e, i) => <div key={`${e.time}-${i}`}><span className="activity-icon">{e.icon}</span><div><strong>{e.label}</strong><small>{e.detail}</small></div><time>{clockLabel(e.time)}</time></div>)}</div> : <p className="empty-note">Sự kiện giao hàng, sạc và đơn mới sẽ hiện ở đây theo đồng hồ mô phỏng.</p>}
          </div></div>
      </>}

      {tab === 'comparison' && <>
        <div className="comparison-head"><div><span className="eyebrow">FAIR COMPARISON</span><h2>Ba phương pháp. Cùng điều kiện.</h2><p>{hasLiveComparison ? `Lượt chạy vừa tạo: seed ${seed}, tỷ lệ ${ratio * 100}%, ngân sách ${budget} giây mỗi lần.` : experimentSubset.length ? `Trung bình ${experimentSubset.length / 3} seed trong kết quả thí nghiệm có sẵn; ngân sách 0,1 giây mỗi lần.` : 'Chưa có thí nghiệm sẵn cho tỷ lệ này. Bấm “Chạy cả 3” để so sánh.'}</p></div><span className="pill blue">{hasLiveComparison ? 'LƯỢT CHẠY MỚI' : 'DỮ LIỆU THÍ NGHIỆM'}</span></div>
        {hasComparison ? <><ComparisonChart rows={comparison} />
          {hasLiveComparison && instance && <div className="route-comparison">{methods.map(m => {
            const comparedRun = job?.results[m];
            return comparedRun && <div className="panel route-card" key={m}><div className="panel-heading"><div><span className="eyebrow">TUYẾN ĐÃ THỰC HIỆN</span><h3><i className="method-dot" style={{ background: METHOD_COLOR[m] }} />{METHOD_LABEL[m]}</h3></div><span className="subtle">{comparedRun.vehicles} xe</span></div>
              <NetworkMap instance={instance} run={comparedRun} time={runEnd(comparedRun)} selectedVehicle={null} onSelectVehicle={() => {}} showVehicles={false} />
            </div>;
          })}</div>}
          <div className="panel comparison-table-wrap"><div className="panel-heading"><div><span className="eyebrow">FULL METRICS</span><h3>Chỉ số theo phương pháp</h3></div><span className="subtle">Giá điện: đơn vị tương đối · hao mòn: chỉ số đại diện</span></div>
          <div className="table-scroll"><table><thead><tr><th>Phương pháp</th><th>Khách phục vụ</th><th>Số xe</th><th>Giờ vận hành</th><th>Chi phí điện</th><th>Hao mòn (kWh)</th><th>P95 tính toán</th></tr></thead><tbody>{comparison.map(r => <tr key={r.method}><td><i className="method-dot" style={{ background: METHOD_COLOR[r.method] }} />{METHOD_LABEL[r.method]}</td><td>{fmt(r.served)}</td><td>{fmt(r.vehicles)}</td><td>{fmt(r.hours)}</td><td>{fmt(r.cost)}</td><td>{fmt(r.wear)}</td><td>{r.p95 == null ? '—' : `${fmt(r.p95, 3)} s`}</td></tr>)}</tbody></table></div>
          <p className="panel-description">Khi có lượt chạy mới, tất cả các cột lấy từ lượt đó; nếu chưa có, các cột là trung bình thí nghiệm có sẵn. Thời gian lập tuyến có thể vượt nhẹ ngân sách vì thế hệ GA đang xử lý sẽ hoàn thành.</p>
        </div></> : <div className="panel empty-state">Chưa có dữ liệu so sánh cho cấu hình này.</div>}
        <div className="callout"><span>◈</span><div><strong>Cách đọc kết quả</strong><p>Thời gian, tiền điện và chỉ số hao mòn được tối ưu cùng lúc bằng điểm có trọng số. Hãy xem từng cột; một phương pháp có thể tốt ở mục tiêu này nhưng kém ở mục tiêu khác. “Hao mòn” chưa phải tuổi thọ pin đo ngoài thực tế.</p></div></div>
      </>}

      {tab === 'explanation' && <>
        <div className="flow-strip"><div><span>01</span><strong>Đơn xuất hiện</strong><small>Biết khách nào cần giao</small></div><b>→</b><div><span>02</span><strong>Hoán vị khách</strong><small>GA tìm thứ tự ứng viên</small></div><b>→</b><div><span>03</span><strong>Giải mã tuyến</strong><small>Chèn trạm sạc, kiểm tra pin</small></div><b>→</b><div><span>04</span><strong>VNS cải thiện</strong><small>Đổi chỗ, chuyển, đảo đoạn</small></div><b>→</b><div><span>05</span><strong>Xe thực hiện</strong><small>Giữ chặng đang chạy</small></div></div>
        <SearchPanel trace={snapshot?.search} />
        <div className="proof-grid"><div className="panel proof-copy"><span className="eyebrow">APPROXIMATION PROOF</span><h2>Giới hạn xấp xỉ 2</h2><p>Chỉ xét trường hợp đặc biệt: một xe, mọi đơn biết trước, khoảng cách Euclid, pin đủ cho toàn tuyến và không cần sạc.</p>
          <div className="proof-formula">ALG ≤ 2 × MST ≤ 2 × OPT</div><p>Một hành trình tối ưu chứa cây khung nhỏ nhất, nên MST ≤ OPT. Nhân đôi các cạnh cây tạo hành trình dài 2×MST; đi tắt đỉnh lặp không làm tăng quãng đường.</p>
          {proof && <div className="proof-values"><div><span>MST</span><b>{fmt(proof.mst_km)} km</b></div><div><span>Hành trình thuật toán</span><b>{fmt(proof.tour_km)} km</b></div><div><span>{proof.optimal_km ? 'TSP tối ưu (Held–Karp)' : 'Cận trên 2×MST'}</span><b>{fmt(proof.optimal_km || proof.upper_bound_km)} km</b></div></div>}
          <small className="proof-note">Không áp dụng bảo đảm tỷ lệ 2 cho EVRP động, sạc pin hoặc GA+VNS.</small></div>
          <div className="panel proof-map"><div className="panel-heading"><div><span className="eyebrow">SPECIAL CASE TOUR</span><h3>Cây MST (xanh) và hành trình (cam)</h3></div></div>{instance && proof ? <NetworkMap instance={instance} time={0} selectedVehicle={null} onSelectVehicle={() => {}} proofTour={proof.tour} proofEdges={proof.mst_edges} /> : null}</div></div>
      </>}

      <footer className="footer"><span>EVRP VISUAL LAB · Montoya E-VRP-NL benchmark</span><span>Đơn phát sinh, giá TOU và hao mòn pin là phần mô phỏng có thể tái lập.</span></footer>
    </main>
  </div>;
}
