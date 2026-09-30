import type { EventInfo, Method, RunResult } from './types';

export const METHOD_LABEL: Record<Method, string> = {
  greedy: 'Tham lam', ga: 'Genetic Algorithm', ga_vns: 'GA + VNS',
};
export const METHOD_COLOR: Record<Method, string> = {
  greedy: '#9da8ba', ga: '#5d8cf6', ga_vns: '#faad5c',
};
export const VEHICLE_COLORS = ['#fdac61', '#6d93fa', '#54d9bf', '#c898f7', '#f27090', '#dbd966', '#59beec', '#f5a4cb'];
export const fmt = (value: number, digits = 1) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: digits }).format(value);
export const clockLabel = (hour: number) => `${String(Math.floor(hour)).padStart(2, '0')}:${String(Math.floor((hour % 1) * 60)).padStart(2, '0')}`;
export const eventLabel: Record<EventInfo['kind'], string> = {
  dispatch: 'Xuất phát', visit: 'Giao hàng', station: 'Đến trạm', charge: 'Sạc pin', depot: 'Về kho',
};
export const runEnd = (run?: RunResult) => run ? Math.max(0, ...Object.values(run.routes).flat().map(e => e.end), ...run.replans.map(r => r.time)) : 0;
