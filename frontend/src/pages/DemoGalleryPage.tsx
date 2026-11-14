import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { HiAcademicCap, HiArrowRight, HiDocumentText, HiSparkles } from 'react-icons/hi';
import {
  ASSISTANT_DESCRIPTIONS,
  ASSISTANT_LABELS,
  CATEGORY_LABELS,
  CATEGORY_STYLES,
  DEMO_CASES,
  SHOW_UNREVIEWED,
} from '../demo/cases';
import type { DemoAssistant, DemoCategory } from '../demo/types';

const ASSISTANT_ICONS: Record<DemoAssistant, typeof HiAcademicCap> = {
  course: HiAcademicCap,
  research: HiDocumentText,
};

function isAssistant(v: string | null): v is DemoAssistant {
  return v === 'course' || v === 'research';
}

function isCategory(v: string | null): v is DemoCategory {
  return v !== null && v in CATEGORY_LABELS;
}

export default function DemoGalleryPage() {
  const [params, setParams] = useSearchParams();
  const assistantParam = params.get('assistant');
  const categoryParam = params.get('category');
  const assistant = isAssistant(assistantParam) ? assistantParam : null;
  const category = isCategory(categoryParam) ? categoryParam : null;

  const counts = useMemo(() => {
    const c: Record<DemoAssistant, number> = { course: 0, research: 0 };
    for (const d of DEMO_CASES) c[d.assistant] += 1;
    return c;
  }, []);

  const categoriesPresent = useMemo(
    () => (Object.keys(CATEGORY_LABELS) as DemoCategory[]).filter((k) => DEMO_CASES.some((c) => c.category === k)),
    [],
  );

  const visible = DEMO_CASES.filter(
    (c) => (!assistant || c.assistant === assistant) && (!category || c.category === category),
  );

  const setFilter = (key: 'assistant' | 'category', value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
          <HiSparkles className="h-3.5 w-3.5" />
          預先產生的示範結果
        </div>
        <h1 className="text-2xl font-bold text-slate-900 md:text-3xl">AI 助理示範案例</h1>
        <p className="max-w-3xl text-sm leading-7 text-slate-600 md:text-base">
          以下每個案例都是事先對真實系統提問、完整記錄後再經人工檢查的結果，頁面瀏覽時不會即時呼叫模型。
          每個案例都附上使用情境、輸入資料、分析過程、引用依據與結論，方便檢視系統如何從資料推論出答案。
        </p>
      </header>

      {/* 兩個助理入口 */}
      <div className="grid gap-4 md:grid-cols-2">
        {(Object.keys(ASSISTANT_LABELS) as DemoAssistant[]).map((key) => {
          const Icon = ASSISTANT_ICONS[key];
          const active = assistant === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setFilter('assistant', active ? null : key)}
              className={`flex items-start gap-4 rounded-2xl border bg-white/90 p-5 text-left shadow-soft transition hover:-translate-y-0.5 hover:shadow-medium ${
                active ? 'border-primary-500 ring-2 ring-primary-200' : 'border-white/70'
              }`}
              aria-pressed={active}
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-900 text-white">
                <Icon className="h-6 w-6" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-base font-bold text-slate-900">{ASSISTANT_LABELS[key]}</span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{counts[key]} 個案例</span>
                </div>
                <p className="mt-1 text-sm leading-6 text-slate-600">{ASSISTANT_DESCRIPTIONS[key]}</p>
              </div>
            </button>
          );
        })}
      </div>

      {/* 情境分類 */}
      {categoriesPresent.length > 0 && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="情境分類">
          <button
            type="button"
            onClick={() => setFilter('category', null)}
            className={`nav-chip ${!category ? 'nav-chip-active' : ''}`}
          >
            全部情境
          </button>
          {categoriesPresent.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setFilter('category', category === k ? null : k)}
              className={`nav-chip ${category === k ? 'nav-chip-active' : ''}`}
            >
              {CATEGORY_LABELS[k]}
            </button>
          ))}
        </div>
      )}

      {/* 案例清單 */}
      {DEMO_CASES.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white/80 p-8 text-center text-sm leading-7 text-slate-500">
          <p className="font-medium text-slate-600">目前還沒有示範案例</p>
          <p className="mt-1">
            {SHOW_UNREVIEWED
              ? '尚未錄製任何示範案例。請執行 scripts/demo/record_demo_cases.py 錄製，並人工檢查後標記為 approved（詳見 docs/demo-cases-and-evaluation.md）。'
              : '示範案例準備中，請稍後再回來看看。'}
          </p>
        </div>
      ) : visible.length === 0 ? (
        <div className="rounded-2xl bg-white/80 p-8 text-center text-sm text-slate-500">沒有符合篩選條件的案例。</div>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {visible.map((c) => (
            <li key={c.id}>
              <Link
                to={`/demo/${c.id}`}
                className="group flex h-full flex-col rounded-2xl border border-white/70 bg-white/90 p-5 shadow-soft transition hover:-translate-y-0.5 hover:shadow-medium"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-primary-700">{ASSISTANT_LABELS[c.assistant]}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs ring-1 ${CATEGORY_STYLES[c.category]}`}>
                    {CATEGORY_LABELS[c.category]}
                  </span>
                  {c.review.status !== 'approved' && (
                    <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-white">待人工檢查</span>
                  )}
                </div>
                <h2 className="mt-3 text-base font-bold text-slate-900">{c.title}</h2>
                <p className="mt-1.5 line-clamp-3 flex-1 text-sm leading-6 text-slate-600">{c.scenario}</p>
                <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary-700 group-hover:text-primary-900">
                  查看完整過程
                  <HiArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
