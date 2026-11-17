import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CATEGORY_LABELS, DEMO_CASES } from '../../demo/cases';
import { countByAssistant, filterDemoCases, isAssistant, isCategory, presentCategories, withFilter } from './gallery';

/**
 * 示範案例列表的篩選狀態（存在網址的 ?assistant=、?category=）。新舊版頁面共用這個 hook。
 */
export function useDemoGallery() {
  const [params, setParams] = useSearchParams();
  const assistantParam = params.get('assistant');
  const categoryParam = params.get('category');
  const assistant = isAssistant(assistantParam) ? assistantParam : null;
  const category = isCategory(categoryParam, CATEGORY_LABELS) ? categoryParam : null;

  const counts = useMemo(() => countByAssistant(DEMO_CASES), []);

  const categoriesPresent = useMemo(() => presentCategories(DEMO_CASES, CATEGORY_LABELS), []);

  const visible = filterDemoCases(DEMO_CASES, assistant, category);

  const setFilter = (key: 'assistant' | 'category', value: string | null) => {
    setParams(withFilter(params, key, value), { replace: true });
  };

  return { assistant, category, counts, categoriesPresent, visible, setFilter };
}
