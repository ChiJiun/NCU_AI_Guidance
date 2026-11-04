import { HiAcademicCap, HiArrowRight, HiDocumentText } from 'react-icons/hi';
import { ASSISTANT_DESCRIPTIONS, ASSISTANT_LABELS, DEMO_CASES } from '../demo/cases';
import type { DemoAssistant } from '../demo/types';

const ICONS: Record<DemoAssistant, typeof HiAcademicCap> = {
  course: HiAcademicCap,
  research: HiDocumentText,
};

/** 展示模式首頁：取代登入 CTA，直接提供兩個助理的示範案例入口。 */
export default function DemoEntrySection({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <section className="px-6 py-4 md:px-10">
      <div className="mx-auto max-w-5xl overflow-hidden rounded-2xl bg-primary-900 px-8 py-7 text-white">
        <p className="text-base font-bold">AI 助理示範案例</p>
        <p className="mt-1 text-sm leading-6 text-primary-200">
          比賽展示版不提供即時提問。以下案例皆預先對真實系統提問並經人工檢查，完整呈現資料來源、分析過程與結論。
        </p>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {(Object.keys(ASSISTANT_LABELS) as DemoAssistant[]).map((key) => {
            const Icon = ICONS[key];
            const count = DEMO_CASES.filter((c) => c.assistant === key).length;
            return (
              <button
                key={key}
                type="button"
                onClick={() => onNavigate(`/demo?assistant=${key}`)}
                className="flex items-start gap-3 rounded-xl bg-white/10 p-4 text-left transition hover:bg-white/15"
              >
                <Icon className="mt-0.5 h-6 w-6 shrink-0 text-primary-200" />
                <span className="min-w-0">
                  <span className="flex items-center gap-2 text-sm font-semibold">
                    {ASSISTANT_LABELS[key]}
                    <span className="rounded-full bg-white/15 px-2 py-0.5 text-xs font-normal">{count} 個案例</span>
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-primary-200">{ASSISTANT_DESCRIPTIONS[key]}</span>
                </span>
                <HiArrowRight className="ml-auto mt-1 h-4 w-4 shrink-0 text-primary-200" />
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
