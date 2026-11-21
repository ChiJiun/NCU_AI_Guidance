import { useEffect, useState } from 'react';
import { HiArrowRight, HiChartPie, HiChatAlt2, HiDocumentText, HiSparkles } from 'react-icons/hi';
import { CategoryChip } from './DemoUI';
import { demoAPI, type CourseDemoCase, type ResearchDemoCase } from './demoCases';

/** 首頁的示範對話入口：展示版下訪客不用登入就能直接點進每一組示範。 */
export default function DemoShowcase({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [course, setCourse] = useState<CourseDemoCase[]>([]);
  const [research, setResearch] = useState<ResearchDemoCase[]>([]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([demoAPI.courseCases(), demoAPI.researchCases()]).then(([c, r]) => {
      if (cancelled) return;
      setCourse(c);
      setResearch(r);
    });
    return () => { cancelled = true; };
  }, []);

  const groups = [
    {
      key: 'course',
      title: 'AI 課程助理',
      desc: '用自然語言找課、比較先修要求、跨學院整合同一主題。',
      icon: HiChatAlt2,
      path: '/course-search',
      cases: course.map((c) => ({ id: c.id, title: c.title, category: c.category, question: c.turns[0]?.user ?? '' })),
    },
    {
      key: 'research',
      title: '研究計畫助理',
      desc: '針對單篇研究計畫 PDF 提問，回答附上來源頁碼。',
      icon: HiDocumentText,
      path: '/projects',
      cases: research.map((c) => ({ id: c.id, title: c.title, category: c.category, question: c.turns[0]?.user ?? '' })),
    },
  ];

  return (
    <section className="px-6 py-10 md:px-10">
      <div className="mx-auto max-w-5xl">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.25em] text-amber-600">
          <HiSparkles className="h-4 w-4" />
          示範對話
        </div>
        <h2 className="mt-2 text-2xl font-black text-slate-900">看看 AI 助理實際怎麼回答</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          展示版不開放即時提問。以下對話由系統實際執行後錄製，經人工檢查，涵蓋一般、複雜、資料不足與安全限制等情境；
          點進去可以看到推薦的課程、工具呼叫過程與引用來源。
        </p>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {groups.map((g) => (
            <div key={g.key} className="flex min-w-0 flex-col rounded-2xl bg-white/85 p-5 shadow-soft ring-1 ring-slate-200/80">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary-700">
                  <g.icon className="h-5 w-5" />
                </div>
                <div>
                  <p className="font-bold text-slate-900">{g.title}</p>
                  <p className="text-xs text-slate-500">{g.cases.length > 0 ? `${g.cases.length} 組示範` : '示範準備中'}</p>
                </div>
              </div>
              <p className="mt-3 text-sm text-slate-600">{g.desc}</p>
              <div className="mt-4 flex-1 space-y-2">
                {g.cases.slice(0, 4).map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => onNavigate(`${g.path}?demo=${encodeURIComponent(c.id)}`)}
                    className="flex w-full items-center gap-2 rounded-xl border border-slate-100 bg-white px-3 py-2 text-left text-sm text-slate-700 transition hover:border-primary-200 hover:bg-primary-50"
                  >
                    <CategoryChip category={c.category} />
                    <span className="min-w-0 flex-1 truncate">{c.question || c.title}</span>
                    <HiArrowRight className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => onNavigate(g.path)}
                className="mt-4 inline-flex items-center gap-1.5 self-start text-sm font-semibold text-primary-700 hover:text-primary-900"
              >
                看全部示範
                <HiArrowRight className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        <button
          type="button"
          onClick={() => onNavigate('/profile')}
          className="mt-4 flex w-full items-center gap-3 rounded-2xl bg-white/85 p-4 text-left shadow-soft ring-1 ring-slate-200/80 transition hover:ring-primary-200"
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-600">
            <HiChartPie className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-bold text-slate-900">示範學生的個人分析</p>
            <p className="text-xs text-slate-500">把上面的示範對話當成同一位學生的紀錄，看系統會整理出什麼學習傾向。</p>
          </div>
          <HiArrowRight className="h-4 w-4 shrink-0 text-slate-400" />
        </button>
      </div>
    </section>
  );
}
