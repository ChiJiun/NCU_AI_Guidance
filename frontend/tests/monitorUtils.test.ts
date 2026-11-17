// 日期工具以本地時間建立日期再轉成 UTC 字串，固定時區才能得到穩定的結果
process.env.TZ = 'UTC';

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  agentLabel,
  combineActivity,
  combinedDailyCost,
  courseRowCost,
  fmt,
  fmtUptime,
  monthToRange,
  ms,
  pdfRowCost,
  resolveFetchOpts,
  weekToRange,
} from '../src/features/monitor/monitorUtils.ts';

test('週與月轉成起訖日期（UTC）', () => {
  assert.deepEqual(weekToRange('2026-W47'), { start: '2026-11-16', end: '2026-11-22' });
  assert.deepEqual(weekToRange('2026-W01'), { start: '2025-12-29', end: '2026-01-04' });
  assert.deepEqual(monthToRange('2026-11'), { start: '2026-11-01', end: '2026-11-30' });
  assert.deepEqual(monthToRange('2024-02'), { start: '2024-02-01', end: '2024-02-29' });
});

test('時間範圍 → 查詢參數；欄位空白時退回近 7 天', () => {
  const base = { mode: 'preset' as const, preset: '30d' as const, dayVal: '2026-11-17', weekVal: '2026-W47', monthVal: '2026-11' };
  assert.deepEqual(resolveFetchOpts(base), { preset: '30d' });
  assert.deepEqual(resolveFetchOpts({ ...base, mode: 'day' }), { start: '2026-11-17', end: '2026-11-17' });
  assert.deepEqual(resolveFetchOpts({ ...base, mode: 'week' }), { start: '2026-11-16', end: '2026-11-22' });
  assert.deepEqual(resolveFetchOpts({ ...base, mode: 'month' }), { start: '2026-11-01', end: '2026-11-30' });
  assert.deepEqual(resolveFetchOpts({ ...base, mode: 'day', dayVal: '' }), { preset: '7d' });
});

test('數字格式', () => {
  assert.equal(fmt(999), '999');
  assert.equal(fmt(1500), '1.5K');
  assert.equal(fmt(2_500_000), '2.5M');
  assert.equal(ms(850), '850ms');
  assert.equal(ms(1500), '1.5s');
  assert.equal(ms(90_000), '1.5m');
  assert.equal(fmtUptime(45), '45s');
  assert.equal(fmtUptime(125), '2m 5s');
  assert.equal(fmtUptime(3_725), '1h 2m');
  assert.equal(agentLabel('retrieval'), '文件搜尋');
  assert.equal(agentLabel('other'), 'other');
});

test('費用估算：課程推薦與大專生計畫（Agent 扣掉 Router）', () => {
  assert.equal(courseRowCost({ input: 1_000_000, output: 1_000_000, turns: 1, sessions: 1 }), 5.25);
  // Agent input 0、output 1M → $10；Router input 1M → $0.15
  const pdf = { input: 1_000_000, output: 1_000_000, router_input: 1_000_000, router_output: 0, turns: 1, sessions: 1 };
  assert.equal(pdfRowCost(pdf), 10.15);
});

test('每日費用對齊日期，缺的那天補 0', () => {
  const result = combinedDailyCost(
    [{ date: '2026-11-02', input: 1_000_000, output: 0, turns: 1, sessions: 1 }],
    [{ date: '2026-11-01', input: 0, output: 1_000_000, router_input: 0, router_output: 0, turns: 1, sessions: 1 }],
  );
  assert.deepEqual(result.dates, ['2026-11-01', '2026-11-02']);
  assert.deepEqual(result.courseCosts, [0, 0.75]);
  assert.deepEqual(result.pdfCosts, [10, 0]);
});

test('兩個功能的每日活動相加並依日期排序', () => {
  const merged = combineActivity(
    [{ date: '2026-11-02', sessions: 1, turns: 3 }, { date: '2026-11-01', sessions: 2, turns: 4 }],
    [{ date: '2026-11-02', sessions: 1, turns: 1 }, { date: '2026-11-03', sessions: 1, turns: 2 }],
  );
  assert.deepEqual(merged, [
    { date: '2026-11-01', sessions: 2, turns: 4 },
    { date: '2026-11-02', sessions: 2, turns: 4 },
    { date: '2026-11-03', sessions: 1, turns: 2 },
  ]);
});
