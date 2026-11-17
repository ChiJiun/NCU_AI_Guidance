import { useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { HiArrowLeft } from 'react-icons/hi';
import CourseDetailModal from '../../components/CourseDetailModal';
import DebugTracePanel from '../../components/DebugTracePanel';
import HighlightedAnswer from '../../components/HighlightedAnswer';
import { ASSISTANT_LABELS, CATEGORY_LABELS, getDemoCase } from '../../demo/cases';
import type { DemoCase, DemoTurn } from '../../demo/types';
import { formatDate, sourceLabel, stepLabel, toDebugTrace } from '../../features/demo/caseDetail';
import type { CourseCard } from '../../types';
import Markdown from '../components/Markdown';
import { v2Link } from '../paths';

function BackLink() {
  return (
    <Link to={v2Link('/demo')} className="v2-navlink !px-0">
      <HiArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
      所有示範案例
    </Link>
  );
}

/** 分析過程：課程助理列出呼叫的工具，研究助理列出路由與各階段 */
function Steps({ turn, assistant }: { turn: DemoTurn; assistant: DemoCase['assistant'] }) {
  const items =
    assistant === 'course'
      ? (turn.steps ?? []).map(stepLabel)
      : [...(turn.agent ? [`路由判斷：交由「${turn.agent.label}」處理`] : []), ...(turn.stages ?? [])];
  if (items.length === 0) return <p className="v2-faint text-sm">沒有呼叫額外工具，直接依對話脈絡回答。</p>;
  return (
    <ol className="space-y-1.5 text-sm">
      {items.map((label, index) => (
        <li key={index} className="flex gap-3">
          <span className="v2-num v2-faint w-5 flex-none">{index + 1}</span>
          <span className="v2-muted min-w-0">{label}</span>
        </li>
      ))}
    </ol>
  );
}

function Citations({ turn, onCourseClick }: { turn: DemoTurn; onCourseClick: (course: CourseCard) => void }) {
  const cards = turn.course_cards ?? [];
  const sources = turn.sources ?? [];
  if (cards.length === 0 && sources.length === 0) return <p className="v2-faint text-sm">沒有引用特定課程或文件段落。</p>;
  return (
    <div className="space-y-3">
      {cards.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {cards.map((card) => (
            <li key={`${card.code}-${card.name}`}>
              <button type="button" className="v2-chip v2-chip--sm" onClick={() => onCourseClick(card)}>
                {card.name}
                <span className="v2-faint">{card.dept}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {sources.length > 0 && (
        <ul className="v2-muted list-disc space-y-1 pl-5 text-sm">
          {sources.map((source, index) => (
            <li key={index} className="break-words">
              {sourceLabel(source)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** 左欄小標、右欄內容（手機改成上下排） */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-2 md:grid-cols-[8rem_1fr] md:gap-8">
      <h3 className="v2-faint text-sm">{label}</h3>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export default function DemoCaseV2() {
  const { caseId } = useParams();
  const demo = getDemoCase(caseId);
  const [selectedCourse, setSelectedCourse] = useState<CourseCard | null>(null);

  if (!demo) {
    return (
      <div className="v2-container pb-20 pt-12">
        <BackLink />
        <p className="v2-serif mt-8 text-3xl">找不到這個示範案例</p>
      </div>
    );
  }

  const project = demo.input.project;

  return (
    <div className="v2-container v2-container--mid pb-20 pt-8 md:pt-10">
      <BackLink />

      <header className="mt-6">
        <p className="v2-faint flex flex-wrap gap-x-3 text-sm">
          <span>{ASSISTANT_LABELS[demo.assistant]}</span>
          <span>{CATEGORY_LABELS[demo.category]}</span>
          <span>預先錄製，不會即時呼叫模型</span>
        </p>
        <h1 className="v2-serif mt-2 text-3xl leading-tight md:text-4xl">{demo.title}</h1>
        {demo.review.status !== 'approved' && (
          <p className="v2-accent mt-3 text-sm font-semibold">尚未人工檢查，只在開發伺服器顯示</p>
        )}
      </header>

      <div className="mt-10 space-y-6 border-t pt-6" style={{ borderColor: 'var(--v2-ink)' }}>
        <Row label="情境">
          <p className="leading-relaxed">{demo.scenario}</p>
        </Row>
        <Row label="輸入資料">
          {project ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="v2-faint">研究計畫</dt>
              <dd>{project.title}</dd>
              <dt className="v2-faint">系所</dt>
              <dd>{project.department}</dd>
              <dt className="v2-faint">學年度</dt>
              <dd>{project.year}</dd>
            </dl>
          ) : (
            <p className="text-sm leading-relaxed">課程綱要、系所與學分學程、應修科目表與修業規定、課程知識圖譜。</p>
          )}
        </Row>
      </div>

      <ol className="mt-12 space-y-14">
        {demo.turns.map((turn, index) => {
          const trace = demo.assistant === 'course' ? toDebugTrace(turn) : null;
          return (
            <li key={index} className="space-y-6">
              {demo.turns.length > 1 && <p className="v2-num v2-accent text-sm !tracking-widest">{String(index + 1).padStart(2, '0')}</p>}
              <p
                className="ml-auto max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-sm px-4 py-2.5 text-white"
                style={{ background: 'var(--v2-ink)' }}
              >
                {turn.user}
              </p>

              <Row label="分析過程">
                <Steps turn={turn} assistant={demo.assistant} />
                {trace && <DebugTracePanel trace={trace} />}
              </Row>

              <Row label="回答">
                {demo.assistant === 'course' ? (
                  // HighlightedAnswer 自帶 markdown 樣式，不再套 .v2-prose
                  <HighlightedAnswer text={turn.assistant} courseCards={turn.course_cards ?? []} onCourseClick={setSelectedCourse} />
                ) : (
                  <Markdown text={turn.assistant} />
                )}
              </Row>

              <Row label="引用">
                <Citations turn={turn} onCourseClick={setSelectedCourse} />
              </Row>
            </li>
          );
        })}
      </ol>

      <section aria-labelledby="demo-conclusion" className="mt-14 border-t pt-6" style={{ borderColor: 'var(--v2-ink)' }}>
        <h2 id="demo-conclusion" className="v2-serif text-2xl">
          結論
        </h2>
        <p className="mt-3 leading-relaxed">{demo.review.conclusion || '（尚未填寫）'}</p>
        <dl className="v2-muted mt-6 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
          {[
            ['人工檢查', demo.review.status === 'approved' ? '已檢查' : '待檢查'],
            ['檢查時間', formatDate(demo.review.reviewed_at)],
            ['錄製時間', formatDate(demo.meta.generated_at)],
            ['模型', demo.meta.models.join('、') || '—'],
            ['系統版本', demo.meta.git_commit],
            ['回應耗時', `${(demo.meta.total_latency_ms / 1000).toFixed(1)} 秒`],
          ].map(([label, value]) => (
            <div key={label} className="flex gap-3">
              <dt className="v2-faint w-20 flex-none">{label}</dt>
              <dd className="min-w-0 break-words">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <CourseDetailModal course={selectedCourse} onClose={() => setSelectedCourse(null)} />
    </div>
  );
}
