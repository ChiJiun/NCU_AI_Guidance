/**
 * 系統監控頁的純函式：日期區間、數字格式、費用估算與活動彙整。
 * 不依賴 React，方便用 node --test 測試；內容逐字搬自舊版 MonitorPage，新舊版共用。
 */
import type { MonitorStats, PdfStats } from '../../api/services';

// ── 日期工具 ─────────────────────────────────────────────────────
export function toISO(d: Date) { return d.toISOString().split('T')[0]; }
export function weekToRange(w: string) {
  const [yr, wn] = w.split('-W');
  const year = parseInt(yr), week = parseInt(wn);
  const jan4 = new Date(year, 0, 4);
  const mon = new Date(jan4);
  mon.setDate(jan4.getDate() - (jan4.getDay() || 7) + 1 + (week - 1) * 7);
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
  return { start: toISO(mon), end: toISO(sun) };
}
export function monthToRange(m: string) {
  const [yr, mo] = m.split('-').map(Number);
  return { start: toISO(new Date(yr, mo - 1, 1)), end: toISO(new Date(yr, mo, 0)) };
}
export function todayISO() { return toISO(new Date()); }
export function currentWeekISO() {
  const now = new Date();
  const d   = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yr  = d.getUTCFullYear();
  const wk  = Math.ceil((((d.getTime() - Date.UTC(yr, 0, 1)) / 86400000) + 1) / 7);
  return `${yr}-W${String(wk).padStart(2, '0')}`;
}
export function currentMonthISO() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

// ── 時間範圍 ─────────────────────────────────────────────────────
export type PickerMode = 'preset'|'day'|'week'|'month';

export interface TimeRangeState {
  mode: PickerMode;
  preset: '1d'|'7d'|'30d';
  dayVal: string;
  weekVal: string;
  monthVal: string;
}

export type MonitorFetchOpts =
  | { preset: '1d'|'7d'|'30d' }
  | { start: string; end: string };

/** 時間範圍選擇器的狀態 → /monitor/stats 的查詢參數；欄位空白時退回近 7 天 */
export function resolveFetchOpts(timeState: TimeRangeState): MonitorFetchOpts {
  const { mode, preset, dayVal, weekVal, monthVal } = timeState;
  if (mode==='preset') return { preset };
  if (mode==='day'   && dayVal)   return { start:dayVal,    end:dayVal };
  if (mode==='week'  && weekVal)  { const r=weekToRange(weekVal);  return { start:r.start,end:r.end }; }
  if (mode==='month' && monthVal) { const r=monthToRange(monthVal);return { start:r.start,end:r.end }; }
  return { preset:'7d' as const };
}

// ── 數字格式 ─────────────────────────────────────────────────────
export function fmt(n: number) {
  if (n >= 1_000_000) return `${(n/1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n/1_000).toFixed(1)}K`;
  return String(n);
}
export function ms(n: number) {
  if (n >= 60_000) return `${(n/60_000).toFixed(1)}m`;
  if (n >= 1_000)  return `${(n/1_000).toFixed(1)}s`;
  return `${n}ms`;
}
export function fmtUptime(sec: number): string {
  if (sec < 60)   return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec/60)}m ${sec%60}s`;
  const h = Math.floor(sec/3600), minu = Math.floor((sec%3600)/60);
  return `${h}h ${minu}m`;
}

export const AGENT_LABEL: Record<string, string> = {
  chat: '直接回答',
  retrieval: '文件搜尋',
  research: '深度研究',
};
export function agentLabel(name: string) { return AGENT_LABEL[name] ?? name; }

// ── 費用估算（每 token 的美元單價） ──────────────────────────────
export const COURSE_INPUT_PRICE       = 0.75  / 1_000_000;
export const COURSE_OUTPUT_PRICE      = 4.50  / 1_000_000;
export const PDF_AGENT_INPUT_PRICE    = 2.50  / 1_000_000;
export const PDF_AGENT_OUTPUT_PRICE   = 10.00 / 1_000_000;
export const PDF_ROUTER_INPUT_PRICE   = 0.15  / 1_000_000;
export const PDF_ROUTER_OUTPUT_PRICE  = 0.60  / 1_000_000;

type CourseTrendRow = MonitorStats['daily_trend'][number];
type PdfTrendRow = PdfStats['daily_trend'][number];

/** 課程推薦一個時段的估算費用（USD，四捨五入到小數 6 位） */
export function courseRowCost(r: CourseTrendRow): number {
  return +((r.input * COURSE_INPUT_PRICE + r.output * COURSE_OUTPUT_PRICE).toFixed(6));
}

/** 大專生計畫一個時段的估算費用：Agent（總量扣掉 Router）＋ Router 分開計價 */
export function pdfRowCost(r: PdfTrendRow): number {
  const ai = Math.max(0, (r.input || 0) - (r.router_input || 0));
  const ao = Math.max(0, (r.output || 0) - (r.router_output || 0));
  return +(
    ai * PDF_AGENT_INPUT_PRICE + ao * PDF_AGENT_OUTPUT_PRICE +
    (r.router_input || 0) * PDF_ROUTER_INPUT_PRICE + (r.router_output || 0) * PDF_ROUTER_OUTPUT_PRICE
  ).toFixed(6);
}

/** 兩個功能的每日費用，對齊到同一組日期（由舊到新） */
export function combinedDailyCost(courseTrend: CourseTrendRow[], pdfTrend: PdfTrendRow[]) {
  const dates = Array.from(new Set([
    ...courseTrend.map(r => r.date ?? ''),
    ...pdfTrend.map(r => r.date ?? ''),
  ])).filter(Boolean).sort();

  const cMap = new Map(courseTrend.map(r => [r.date ?? '', r]));
  const pMap = new Map(pdfTrend.map(r => [r.date ?? '', r]));

  const courseCosts = dates.map(d => {
    const r = cMap.get(d); if (!r) return 0;
    return courseRowCost(r);
  });
  const pdfCosts = dates.map(d => {
    const r = pMap.get(d); if (!r) return 0;
    return pdfRowCost(r);
  });
  return { dates, courseCosts, pdfCosts };
}

/** 課程推薦與大專生計畫的每日活動相加（依日期排序） */
export function combineActivity(
  courseActivity: { date: string; sessions: number; turns: number }[],
  pdfActivity: { date: string; sessions: number; turns: number }[],
): { date: string; sessions: number; turns: number }[] {
  const dateMap = new Map<string, { sessions: number; turns: number }>();
  for (const r of courseActivity) dateMap.set(r.date, { sessions: r.sessions, turns: r.turns });
  for (const r of pdfActivity) {
    const e = dateMap.get(r.date) ?? { sessions: 0, turns: 0 };
    dateMap.set(r.date, { sessions: e.sessions + r.sessions, turns: e.turns + r.turns });
  }
  return Array.from(dateMap.entries()).sort(([a],[b]) => a < b ? -1 : 1).map(([date, v]) => ({ date, ...v }));
}
