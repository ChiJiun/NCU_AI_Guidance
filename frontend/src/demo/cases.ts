import type { DemoAssistant, DemoCase, DemoCategory } from './types';

/**
 * build 時把 src/demo/cases/*.json 全部打包進來（瀏覽案例頁不需要後端，也不會呼叫模型）。
 * 這些檔案由 scripts/demo/record_demo_cases.py 對真實後端錄製，人工檢查後才標記為 approved。
 */
const modules = import.meta.glob<DemoCase>('./cases/*.json', { eager: true, import: 'default' });

const ALL_CASES: DemoCase[] = Object.values(modules).sort((a, b) => a.id.localeCompare(b.id));

/**
 * 是否顯示尚未人工檢查的案例：只有開發伺服器（npm run dev）會顯示，並加註「待人工檢查」；
 * 正式 build（npm run build）只列出 approved 的案例，避免未檢查的 AI 回答出現在公開頁面。
 * 注意：這是顯示層的過濾，未檢查的 JSON 仍會被打包進 bundle；有問題的錄製結果不要提交進 repo。
 */
export const SHOW_UNREVIEWED = import.meta.env.DEV;

export const DEMO_CASES: DemoCase[] = SHOW_UNREVIEWED
  ? ALL_CASES
  : ALL_CASES.filter((c) => c.review?.status === 'approved');

export function getDemoCase(id: string | undefined): DemoCase | undefined {
  return DEMO_CASES.find((c) => c.id === id);
}

export const ASSISTANT_LABELS: Record<DemoAssistant, string> = {
  course: '課程助理',
  research: '研究助理',
};

export const ASSISTANT_DESCRIPTIONS: Record<DemoAssistant, string> = {
  course: '整合課程、系所、學程與修業規定資料，回答選課與選系問題。',
  research: '閱讀大專生研究計畫 PDF，用白話解釋研究內容並附上引用來源。',
};

export const CATEGORY_LABELS: Record<DemoCategory, string> = {
  general: '一般情境',
  insufficient_data: '資料不足',
  comparison: '跨系比較',
  anomaly: '錯誤前提',
  safety: '安全與隱私',
  complex: '複雜推論',
};

export const CATEGORY_STYLES: Record<DemoCategory, string> = {
  general: 'bg-sky-50 text-sky-700 ring-sky-200',
  insufficient_data: 'bg-amber-50 text-amber-700 ring-amber-200',
  comparison: 'bg-violet-50 text-violet-700 ring-violet-200',
  anomaly: 'bg-orange-50 text-orange-700 ring-orange-200',
  safety: 'bg-rose-50 text-rose-700 ring-rose-200',
  complex: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
};
