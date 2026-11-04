import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  HiArrowLeft,
  HiBadgeCheck,
  HiChip,
  HiClipboardList,
  HiCollection,
  HiExclamation,
  HiLightBulb,
  HiSparkles,
  HiUser,
} from 'react-icons/hi';
import CourseDetailModal from '../components/CourseDetailModal';
import DebugTracePanel from '../components/DebugTracePanel';
import HighlightedAnswer from '../components/HighlightedAnswer';
import { TOOL_LABELS } from '../constants/toolLabels';
import { ASSISTANT_LABELS, CATEGORY_LABELS, CATEGORY_STYLES, getDemoCase } from '../demo/cases';
import type { DemoCase, DemoStep, DemoTurn } from '../demo/types';
import type { CourseCard, DebugTrace } from '../types';

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-TW', { dateStyle: 'medium', timeStyle: 'short' });
}

function sourceLabel(src: unknown): string {
  if (typeof src === 'string') return src;
  if (src && typeof src === 'object') {
    const o = src as Record<string, unknown>;
    const text = o.title ?? o.name ?? o.source ?? o.page_content;
    const page = o.page ?? (o.metadata as Record<string, unknown> | undefined)?.page;
    if (text) return page != null ? `${String(text)}（第 ${String(page)} 頁）` : String(text);
    return JSON.stringify(src);
  }
  return String(src);
}

function stepLabel(step: DemoStep): string {
  if (step.kind === 'verify') {
    const kept = step.selected?.length ?? 0;
    return `驗證推薦課程：從 ${step.pool_size ?? '?'} 門候選中保留 ${kept} 門`;
  }
  const name = TOOL_LABELS[step.tool] ?? step.tool;
  return step.count != null ? `${name}（找到 ${step.count} 筆）` : name;
}

function toDebugTrace(turn: DemoTurn): DebugTrace | null {
  const toolCalls = turn.debug_trace?.toolCalls ?? [];
  const verifyStep = turn.steps?.find((s): s is Extract<DemoStep, { kind: 'verify' }> => s.kind === 'verify');
  const verify = verifyStep
    ? {
        poolSize: verifyStep.pool_size ?? 0,
        selected: verifyStep.selected ?? [],
        filteredOut: verifyStep.filtered_out ?? [],
        method: verifyStep.method,
      }
    : null;
  if (toolCalls.length === 0 && !verify) return null;
  return { toolCalls, verify };
}

function SectionTitle({ icon: Icon, children }: { icon: typeof HiUser; children: React.ReactNode }) {
  return (
    <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-slate-500">
      <Icon className="h-4 w-4" />
      {children}
    </h2>
  );
}

function AnalysisSteps({ turn, assistant }: { turn: DemoTurn; assistant: DemoCase['assistant'] }) {
  const items =
    assistant === 'course'
      ? (turn.steps ?? []).map(stepLabel)
      : [
          ...(turn.agent ? [`路由判斷：交由「${turn.agent.label}」處理`] : []),
          ...(turn.stages ?? []),
        ];
  if (items.length === 0) {
    return <p className="text-sm text-slate-400">這一輪沒有呼叫額外工具，直接根據對話脈絡回答。</p>;
  }
  return (
    <ol className="space-y-1.5">
      {items.map((label, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
            {i + 1}
          </span>
          <span className="leading-6">{label}</span>
        </li>
      ))}
    </ol>
  );
}

function Citations({ turn, onCourseClick }: { turn: DemoTurn; onCourseClick: (c: CourseCard) => void }) {
  const cards = turn.course_cards ?? [];
  const sources = turn.sources ?? [];
  if (cards.length === 0 && sources.length === 0) {
    return <p className="text-sm text-slate-400">這一輪沒有引用特定課程或文件段落。</p>;
  }
  return (
    <div className="space-y-2">
      {cards.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {cards.map((c) => (
            <button
              key={`${c.code}-${c.name}`}
              type="button"
              onClick={() => onCourseClick(c)}
              className="rounded-lg border border-blue-100 bg-blue-50 px-2 py-1 text-left text-xs text-blue-800 transition hover:border-blue-300"
            >
              {c.name}
              <span className="ml-1 text-blue-500">{c.dept}{c.credits ? ` · ${c.credits} 學分` : ''}</span>
            </button>
          ))}
        </div>
      )}
      {sources.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
          {sources.map((s, i) => (
            <li key={i} className="break-words">{sourceLabel(s)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function DemoCasePage() {
  const { caseId } = useParams();
  const demo = getDemoCase(caseId);
  const [selectedCourse, setSelectedCourse] = useState<CourseCard | null>(null);

  if (!demo) {
    return (
      <div className="space-y-4 text-center">
        <p className="text-slate-600">找不到這個示範案例。</p>
        <Link to="/demo" className="btn-secondary inline-flex">回到示範案例</Link>
      </div>
    );
  }

  const project = demo.input.project;

  return (
    <div className="space-y-6">
      <Link to="/demo" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
        <HiArrowLeft className="h-4 w-4" />
        所有示範案例
      </Link>

      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
            <HiSparkles className="h-3.5 w-3.5" />
            預先產生的示範結果
          </span>
          <span className="text-xs font-semibold text-primary-700">{ASSISTANT_LABELS[demo.assistant]}</span>
          <span className={`rounded-full px-2 py-0.5 text-xs ring-1 ${CATEGORY_STYLES[demo.category]}`}>
            {CATEGORY_LABELS[demo.category]}
          </span>
        </div>
        <h1 className="text-2xl font-bold text-slate-900">{demo.title}</h1>
      </header>

      {demo.review.status !== 'approved' && (
        <div className="flex items-start gap-2 rounded-xl border border-slate-300 bg-slate-800 px-4 py-3 text-sm text-white">
          <HiExclamation className="mt-0.5 h-4 w-4 shrink-0" />
          這個案例尚未人工檢查，只在開發模式顯示，不會出現在比賽展示版。
        </div>
      )}

      {/* 使用情境 + 輸入資料 */}
      <section className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2 rounded-2xl bg-white/90 p-5 shadow-soft">
          <SectionTitle icon={HiLightBulb}>使用情境</SectionTitle>
          <p className="text-sm leading-7 text-slate-700">{demo.scenario}</p>
        </div>
        <div className="space-y-2 rounded-2xl bg-white/90 p-5 shadow-soft">
          <SectionTitle icon={HiClipboardList}>輸入資料</SectionTitle>
          {project ? (
            <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="text-slate-400">研究計畫</dt>
              <dd className="text-slate-700">{project.title}</dd>
              <dt className="text-slate-400">系所</dt>
              <dd className="text-slate-700">{project.department}</dd>
              <dt className="text-slate-400">學年度</dt>
              <dd className="text-slate-700">{project.year}</dd>
            </dl>
          ) : (
            <p className="text-sm leading-7 text-slate-700">
              校內公開資料：課程綱要、系所與學分學程、應修科目表與修業規定、課程知識圖譜。
            </p>
          )}
          <p className="text-xs text-slate-400">共 {demo.input.messages.length} 個提問</p>
        </div>
      </section>

      {/* 對話與過程 */}
      <section className="space-y-5">
        {demo.turns.map((turn, i) => (
          <article key={i} className="space-y-4 rounded-2xl bg-white/90 p-5 shadow-soft">
            {demo.turns.length > 1 && <p className="text-xs font-semibold text-slate-400">第 {i + 1} 輪</p>}
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-600">
                <HiUser className="h-4 w-4" />
              </div>
              <p className="rounded-2xl rounded-tl-sm bg-slate-100 px-4 py-2.5 text-sm leading-7 text-slate-800">{turn.user}</p>
            </div>

            <div className="space-y-2 rounded-xl border border-slate-100 bg-slate-50/70 p-4">
              <SectionTitle icon={HiChip}>分析過程</SectionTitle>
              <AnalysisSteps turn={turn} assistant={demo.assistant} />
              {demo.assistant === 'course' && (() => {
                const trace = toDebugTrace(turn);
                return trace ? <DebugTracePanel trace={trace} /> : null;
              })()}
            </div>

            <div className="space-y-2">
              <SectionTitle icon={HiSparkles}>AI 回答</SectionTitle>
              <div className="prose prose-sm max-w-none text-slate-800">
                {demo.assistant === 'course' ? (
                  <HighlightedAnswer
                    text={turn.assistant}
                    courseCards={turn.course_cards ?? []}
                    onCourseClick={setSelectedCourse}
                  />
                ) : (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.assistant}</ReactMarkdown>
                )}
              </div>
            </div>

            <div className="space-y-2 border-t border-slate-100 pt-3">
              <SectionTitle icon={HiCollection}>引用依據</SectionTitle>
              <Citations turn={turn} onCourseClick={setSelectedCourse} />
            </div>
          </article>
        ))}
      </section>

      {/* 結論與人工檢查 */}
      <section className="space-y-3 rounded-2xl bg-primary-900 p-5 text-white shadow-soft">
        <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-primary-200">
          <HiBadgeCheck className="h-4 w-4" />
          結論與人工檢查
        </h2>
        {demo.review.conclusion ? (
          <p className="text-sm leading-7">{demo.review.conclusion}</p>
        ) : (
          <p className="text-sm text-primary-200">（尚未填寫結論）</p>
        )}
        <dl className="grid gap-x-6 gap-y-1 text-xs text-primary-200 sm:grid-cols-2">
          <div>檢查狀態：{demo.review.status === 'approved' ? '已人工檢查' : '待人工檢查'}</div>
          <div>檢查時間：{formatDate(demo.review.reviewed_at)}</div>
          <div>產生時間：{formatDate(demo.meta.generated_at)}</div>
          <div>模型：{demo.meta.models.join('、') || '—'}</div>
          <div>系統版本：{demo.meta.git_commit}</div>
          <div>回應耗時：{(demo.meta.total_latency_ms / 1000).toFixed(1)} 秒</div>
        </dl>
      </section>

      <CourseDetailModal course={selectedCourse} onClose={() => setSelectedCourse(null)} />
    </div>
  );
}
