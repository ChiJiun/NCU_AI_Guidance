import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatDate, sourceLabel, stepLabel, toDebugTrace } from '../src/features/demo/caseDetail.ts';
import { countByAssistant, filterDemoCases, isAssistant, isCategory, presentCategories, withFilter } from '../src/features/demo/gallery.ts';
import type { DemoCase, DemoCategory } from '../src/demo/types.ts';

const LABELS: Record<DemoCategory, string> = {
  general: '一般情境',
  insufficient_data: '資料不足',
  comparison: '跨系比較',
  anomaly: '錯誤前提',
  safety: '安全與隱私',
  complex: '複雜推論',
};

const demo = (id: string, assistant: DemoCase['assistant'], category: DemoCategory) => ({ id, assistant, category }) as DemoCase;

const cases = [demo('a', 'course', 'general'), demo('b', 'research', 'safety'), demo('c', 'course', 'safety')];

test('網址參數驗證', () => {
  assert.equal(isAssistant('course'), true);
  assert.equal(isAssistant('x'), false);
  assert.equal(isAssistant(null), false);
  assert.equal(isCategory('safety', LABELS), true);
  assert.equal(isCategory('nope', LABELS), false);
  assert.equal(isCategory(null, LABELS), false);
});

test('計數、出現過的分類與篩選', () => {
  assert.deepEqual(countByAssistant(cases), { course: 2, research: 1 });
  assert.deepEqual(presentCategories(cases, LABELS), ['general', 'safety']);
  assert.deepEqual(filterDemoCases(cases, 'course', null).map((c) => c.id), ['a', 'c']);
  assert.deepEqual(filterDemoCases(cases, null, 'safety').map((c) => c.id), ['b', 'c']);
  assert.deepEqual(filterDemoCases(cases, 'course', 'safety').map((c) => c.id), ['c']);
});

test('設定或清除篩選時保留其他參數，也不改動原本的參數物件', () => {
  const params = new URLSearchParams('assistant=course&x=1');
  assert.equal(withFilter(params, 'category', 'safety').toString(), 'assistant=course&x=1&category=safety');
  assert.equal(withFilter(params, 'assistant', null).toString(), 'x=1');
  assert.equal(params.toString(), 'assistant=course&x=1');
});

test('內頁：日期、來源與分析步驟', () => {
  assert.equal(formatDate(null), '—');
  assert.equal(formatDate('not-a-date'), 'not-a-date');
  assert.equal(sourceLabel('p.3'), 'p.3');
  assert.equal(sourceLabel({ title: '計畫書', page: 4 }), '計畫書（第 4 頁）');
  assert.equal(sourceLabel({ name: 'x', metadata: { page: 2 } }), 'x（第 2 頁）');
  assert.equal(sourceLabel({ foo: 1 }), '{"foo":1}');
  assert.equal(stepLabel({ kind: 'tool', tool: 'search_courses', status: 'done', count: 5 }), '搜尋課程（找到 5 筆）');
  assert.equal(stepLabel({ kind: 'tool', tool: 'unknown_tool', status: 'done' }), 'unknown_tool');
  assert.equal(stepLabel({ kind: 'verify', status: 'done', pool_size: 8, selected: ['a', 'b'] }), '驗證推薦課程：從 8 門候選中保留 2 門');
});

test('內頁：沒有工具呼叫也沒有驗證時不顯示除錯面板', () => {
  assert.equal(toDebugTrace({ user: 'q', assistant: 'a' }), null);
  const trace = toDebugTrace({ user: 'q', assistant: 'a', steps: [{ kind: 'verify', status: 'done', pool_size: 3, selected: ['x'] }] });
  assert.deepEqual(trace, { toolCalls: [], verify: { poolSize: 3, selected: ['x'], filteredOut: [], method: undefined } });
});
