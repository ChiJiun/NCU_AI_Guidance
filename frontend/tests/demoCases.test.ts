// 執行：npm run test:unit（Node 內建測試，不需額外套件）
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { selectVisibleCases } from '../src/demo/demoCases.ts';

const cases = [
  { id: 'ok', reviewed: true, turns: [{}] },
  { id: 'draft', reviewed: false, turns: [{}] },
  { id: 'empty', reviewed: true, turns: [] },
];

test('正式版只放出人工檢查過的示範', () => {
  assert.deepEqual(selectVisibleCases(cases, false).map((c) => c.id), ['ok']);
});

test('開發時連未審核的也顯示，方便檢查', () => {
  assert.deepEqual(selectVisibleCases(cases, true).map((c) => c.id), ['ok', 'draft']);
});

test('沒有任何對話的案例一律不顯示', () => {
  assert.ok(!selectVisibleCases(cases, true).some((c) => c.id === 'empty'));
});
