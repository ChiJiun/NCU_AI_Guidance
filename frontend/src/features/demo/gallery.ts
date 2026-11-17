/**
 * 示範案例列表的篩選邏輯（純函式，不依賴 React 與 import.meta，方便用 node --test 測試）。
 * 內容逐字搬自舊版 DemoGalleryPage，新舊版共用。
 */
import type { DemoAssistant, DemoCase, DemoCategory } from '../../demo/types';

export function isAssistant(v: string | null): v is DemoAssistant {
  return v === 'course' || v === 'research';
}

export function isCategory(v: string | null, labels: Record<DemoCategory, string>): v is DemoCategory {
  return v !== null && v in labels;
}

/** 各助理的案例數 */
export function countByAssistant(cases: DemoCase[]): Record<DemoAssistant, number> {
  const c: Record<DemoAssistant, number> = { course: 0, research: 0 };
  for (const d of cases) c[d.assistant] += 1;
  return c;
}

/** 至少有一個案例的情境分類（依 labels 的順序） */
export function presentCategories(cases: DemoCase[], labels: Record<DemoCategory, string>): DemoCategory[] {
  return (Object.keys(labels) as DemoCategory[]).filter((k) => cases.some((c) => c.category === k));
}

export function filterDemoCases(
  cases: DemoCase[],
  assistant: DemoAssistant | null,
  category: DemoCategory | null,
): DemoCase[] {
  return cases.filter(
    (c) => (!assistant || c.assistant === assistant) && (!category || c.category === category),
  );
}

/** 設定或清除一個篩選條件，其他網址參數保留 */
export function withFilter(params: URLSearchParams, key: 'assistant' | 'category', value: string | null): URLSearchParams {
  const next = new URLSearchParams(params);
  if (value) next.set(key, value);
  else next.delete(key);
  return next;
}
