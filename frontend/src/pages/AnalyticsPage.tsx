import { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import 'echarts-wordcloud';
import { Link } from 'react-router-dom';
import {
  HiAcademicCap,
  HiChat,
  HiBookOpen,
  HiOfficeBuilding,
  HiChevronRight,
  HiClipboardList,
  HiGlobeAlt,
  HiZoomIn,
  HiMap,
  HiAdjustments,
  HiDocumentText,
  HiLightningBolt,
  HiSearchCircle,
  HiClock,
} from 'react-icons/hi';
import { useAuth } from '../auth/AuthContext';
import {
  type AnalyticsData,
  type AnalyticsGeneralEdu,
  type PdfAnalyticsData,
} from '../api/services';
import {
  COMBINED_TYPE_LABELS,
  COURSE_TYPE_TEXT,
  DOMAIN_COLORS,
  activeDomainCount,
  collegeDomainAxes,
  combinedDomainAxes,
  diagnoseCombinedType as diagnoseCombinedTypeId,
  diagnoseCourseType,
  formatRelativeTime,
  uniqueCollegeCount,
  usagePreferenceText,
} from '../features/analytics/analysis';
import { useAnalytics, type TabId } from '../features/analytics/useAnalytics';

// ── 探索型態診斷 ─────────────────────────────────────────────────
const EXPLORE_TYPES = [
  {
    id: 'planning',
    ...COURSE_TYPE_TEXT.planning,
    Icon: HiClipboardList,
    iconColor: 'text-amber-600',
    iconBg: 'bg-amber-100',
    color: 'from-amber-50 to-orange-50 border-amber-200',
    badge: 'bg-amber-100 text-amber-700',
  },
  {
    id: 'cross',
    ...COURSE_TYPE_TEXT.cross,
    Icon: HiGlobeAlt,
    iconColor: 'text-violet-600',
    iconBg: 'bg-violet-100',
    color: 'from-violet-50 to-purple-50 border-violet-200',
    badge: 'bg-violet-100 text-violet-700',
  },
  {
    id: 'deep',
    ...COURSE_TYPE_TEXT.deep,
    Icon: HiZoomIn,
    iconColor: 'text-blue-600',
    iconBg: 'bg-blue-100',
    color: 'from-blue-50 to-indigo-50 border-blue-200',
    badge: 'bg-blue-100 text-blue-700',
  },
  {
    id: 'wide',
    ...COURSE_TYPE_TEXT.wide,
    Icon: HiMap,
    iconColor: 'text-emerald-600',
    iconBg: 'bg-emerald-100',
    color: 'from-emerald-50 to-teal-50 border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700',
  },
  {
    id: 'balanced',
    ...COURSE_TYPE_TEXT.balanced,
    Icon: HiAdjustments,
    iconColor: 'text-slate-600',
    iconBg: 'bg-slate-100',
    color: 'from-slate-50 to-gray-50 border-slate-200',
    badge: 'bg-slate-100 text-slate-600',
  },
];

// ── 研究計畫探索型態 ────────────────────────────────────────────
const PDF_EXPLORE_TYPES = [
  {
    id: 'deep',
    label: '深度鑽研型',
    Icon: HiZoomIn,
    iconColor: 'text-blue-600',
    iconBg: 'bg-blue-100',
    color: 'from-blue-50 to-indigo-50 border-blue-200',
    badge: 'bg-blue-100 text-blue-700',
  },
  {
    id: 'cross',
    label: '跨域探索型',
    Icon: HiGlobeAlt,
    iconColor: 'text-violet-600',
    iconBg: 'bg-violet-100',
    color: 'from-violet-50 to-purple-50 border-violet-200',
    badge: 'bg-violet-100 text-violet-700',
  },
  {
    id: 'wide',
    label: '廣泛涉獵型',
    Icon: HiMap,
    iconColor: 'text-emerald-600',
    iconBg: 'bg-emerald-100',
    color: 'from-emerald-50 to-teal-50 border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700',
  },
  {
    id: 'focused',
    label: '專注研究型',
    Icon: HiSearchCircle,
    iconColor: 'text-amber-600',
    iconBg: 'bg-amber-100',
    color: 'from-amber-50 to-orange-50 border-amber-200',
    badge: 'bg-amber-100 text-amber-700',
  },
  {
    id: 'balanced',
    label: '均衡探索型',
    Icon: HiAdjustments,
    iconColor: 'text-slate-600',
    iconBg: 'bg-slate-100',
    color: 'from-slate-50 to-gray-50 border-slate-200',
    badge: 'bg-slate-100 text-slate-600',
  },
] as const;

const PDF_TYPE_MAP: Record<string, typeof PDF_EXPLORE_TYPES[number]> = {
  '深度鑽研型': PDF_EXPLORE_TYPES[0],
  '跨域探索型': PDF_EXPLORE_TYPES[1],
  '廣泛涉獵型': PDF_EXPLORE_TYPES[2],
  '專注研究型': PDF_EXPLORE_TYPES[3],
  '均衡探索型': PDF_EXPLORE_TYPES[4],
};

// ── 綜合探索型態 ─────────────────────────────────────────────────
const COMBINED_EXPLORE_TYPES = [
  {
    id: 'researcher',
    label: COMBINED_TYPE_LABELS.researcher,
    Icon: HiDocumentText,
    iconColor: 'text-emerald-600',
    iconBg: 'bg-emerald-100',
    color: 'from-emerald-50 to-teal-50 border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700',
  },
  {
    id: 'planner',
    label: COMBINED_TYPE_LABELS.planner,
    Icon: HiClipboardList,
    iconColor: 'text-amber-600',
    iconBg: 'bg-amber-100',
    color: 'from-amber-50 to-orange-50 border-amber-200',
    badge: 'bg-amber-100 text-amber-700',
  },
  {
    id: 'course_explorer',
    label: COMBINED_TYPE_LABELS.course_explorer,
    Icon: HiAcademicCap,
    iconColor: 'text-blue-600',
    iconBg: 'bg-blue-100',
    color: 'from-blue-50 to-sky-50 border-blue-200',
    badge: 'bg-blue-100 text-blue-700',
  },
  {
    id: 'integrator',
    label: COMBINED_TYPE_LABELS.integrator,
    Icon: HiGlobeAlt,
    iconColor: 'text-violet-600',
    iconBg: 'bg-violet-100',
    color: 'from-violet-50 to-purple-50 border-violet-200',
    badge: 'bg-violet-100 text-violet-700',
  },
  {
    id: 'explorer',
    label: COMBINED_TYPE_LABELS.explorer,
    Icon: HiMap,
    iconColor: 'text-indigo-600',
    iconBg: 'bg-indigo-100',
    color: 'from-indigo-50 to-blue-50 border-indigo-200',
    badge: 'bg-indigo-100 text-indigo-700',
  },
  {
    id: 'balanced',
    label: COMBINED_TYPE_LABELS.balanced,
    Icon: HiAdjustments,
    iconColor: 'text-slate-600',
    iconBg: 'bg-slate-100',
    color: 'from-slate-50 to-gray-50 border-slate-200',
    badge: 'bg-slate-100 text-slate-600',
  },
] as const;

function diagnoseCombinedType(
  courseData: AnalyticsData | null,
  projectData: PdfAnalyticsData | null,
  coursePct: number,
  combinedAxes: { label: string; pct: number }[],
): { style: typeof COMBINED_EXPLORE_TYPES[number]; desc: string } {
  const { id, desc } = diagnoseCombinedTypeId(courseData, projectData, coursePct, combinedAxes);
  return { style: COMBINED_EXPLORE_TYPES.find(t => t.id === id)!, desc };
}

function diagnoseType(
  data: AnalyticsData,
  domainAxes: { label: string; value: number }[],
): typeof EXPLORE_TYPES[0] {
  const id = diagnoseCourseType(data, domainAxes);
  return EXPLORE_TYPES.find(t => t.id === id)!;
}

// ── 雷達圖 (SVG) ────────────────────────────────────────────────
function RadarChart({ axes }: { axes: { label: string; value: number; pct?: number }[] }) {
  const SIZE = 200;
  const cx = SIZE / 2;
  const cy = SIZE / 2;
  const R = SIZE * 0.33;
  const LABEL_R = R + 26;
  const n = axes.length;

  const angle = (i: number) => (i * 2 * Math.PI) / n - Math.PI / 2;
  const pt = (i: number, frac: number) => ({
    x: cx + R * frac * Math.cos(angle(i)),
    y: cy + R * frac * Math.sin(angle(i)),
  });
  const polyStr = (fn: (i: number) => number) =>
    axes.map((_, i) => { const p = pt(i, fn(i)); return `${p.x},${p.y}`; }).join(' ');

  const labelPts = axes.map((_, i) => ({
    x: cx + LABEL_R * Math.cos(angle(i)),
    y: cy + LABEL_R * Math.sin(angle(i)),
  }));
  const pad = 22;
  const minX = Math.min(...labelPts.map(p => p.x)) - pad;
  const minY = Math.min(...labelPts.map(p => p.y)) - pad;
  const maxX = Math.max(...labelPts.map(p => p.x)) + pad;
  const maxY = Math.max(...labelPts.map(p => p.y)) + pad;

  return (
    <svg viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`} className="w-full max-w-[240px]">
      {[0.25, 0.5, 0.75, 1.0].map((lv, gi) => (
        <polygon key={gi} points={polyStr(() => lv)}
          fill="none" stroke="#e2e8f0" strokeWidth={gi === 3 ? 1.5 : 0.8} />
      ))}
      {axes.map((_, i) => {
        const end = pt(i, 1);
        return <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke="#e2e8f0" strokeWidth="1" />;
      })}
      <polygon
        points={polyStr(i => Math.max(axes[i].value / 100, 0.04))}
        fill="rgba(99,102,241,0.15)" stroke="#6366f1" strokeWidth="2"
      />
      {axes.map((ax, i) => {
        const p = pt(i, Math.max(ax.value / 100, 0.04));
        const color = DOMAIN_COLORS[ax.label] ?? '#6366f1';
        return <circle key={i} cx={p.x} cy={p.y} r="4" fill={color} />;
      })}
      {axes.map((ax, i) => {
        const lx = cx + LABEL_R * Math.cos(angle(i));
        const ly = cy + LABEL_R * Math.sin(angle(i));
        const color = DOMAIN_COLORS[ax.label] ?? '#334155';
        return (
          <g key={i}>
            <text x={lx} y={ly - 5} textAnchor="middle" fontSize="11"
              fill={color} fontFamily="system-ui,sans-serif" fontWeight="700">
              {ax.label}
            </text>
            <text x={lx} y={ly + 9} textAnchor="middle" fontSize="9.5"
              fill={DOMAIN_COLORS[ax.label] ?? '#94a3b8'} fontFamily="system-ui,sans-serif" opacity="0.7">
              {ax.value}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

const DONUT_COLORS = [
  '#6366f1', '#8b5cf6', '#06b6d4', '#10b981',
  '#f59e0b', '#f97316', '#ec4899', '#14b8a6',
];

// ── 滾動數字 hook ────────────────────────────────────────────────
function useCountUp(target: number, duration = 900) {
  const [val, setVal] = useState(0);
  const raf = useRef<number>(0);
  useEffect(() => {
    cancelAnimationFrame(raf.current);
    if (target === 0) { setVal(0); return; }
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - (1 - t) ** 3; // ease-out cubic
      setVal(target * eased);
      if (t < 1) raf.current = requestAnimationFrame(step);
      else setVal(target);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration]);
  return val;
}

// ── 概覽卡片 ────────────────────────────────────────────────────
function StatCard({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: string | number; sub?: string;
}) {
  const isFloat = typeof value === 'number' && !Number.isInteger(value);
  const animated = useCountUp(typeof value === 'number' ? value : 0);
  const displayed = typeof value !== 'number'
    ? value
    : isFloat
      ? animated.toFixed(1)
      : Math.round(animated);
  return (
    <div className="card flex items-start gap-4 p-5">
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-700">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        <p className="mt-0.5 truncate text-2xl font-bold text-primary-900">{displayed}</p>
        {sub && <p className="mt-0.5 truncate text-xs text-slate-400">{sub}</p>}
      </div>
    </div>
  );
}

// ── 區塊標題 ────────────────────────────────────────────────────
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 flex items-center gap-2 text-sm font-bold tracking-wide text-primary-900 uppercase">
      <span className="inline-block h-1 w-4 rounded-full bg-accent-400" />
      {children}
    </h2>
  );
}

function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-slate-100 ${className ?? ''}`} />;
}

function NotLoggedIn() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-100">
        <HiAcademicCap className="h-8 w-8 text-slate-400" />
      </div>
      <h2 className="text-lg font-semibold text-slate-700">請先登入</h2>
      <p className="mt-1 text-sm text-slate-400">登入後即可查看你的課程探索分析</p>
      <Link to="/course-search" className="btn-primary mt-6 inline-flex items-center gap-1.5 text-sm">
        前往課程助理 <HiChevronRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-100">
        <HiBookOpen className="h-8 w-8 text-slate-300" />
      </div>
      <h2 className="text-lg font-semibold text-slate-600">還沒有使用記錄</h2>
      <p className="mt-1 text-sm text-slate-400">開始使用課程助理，分析結果將在這裡呈現</p>
      <Link to="/course-search" className="btn-primary mt-6 inline-flex items-center gap-1.5 text-sm">
        開始搜尋課程 <HiChevronRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

// ── Tab Bar ─────────────────────────────────────────────────────
const TAB_LABELS: { id: TabId; label: string }[] = [
  { id: 'all',     label: '全部' },
  { id: 'course',  label: '課程助理' },
  { id: 'project', label: '研究計畫' },
];

function TabSwitcher({ active, onChange }: { active: TabId; onChange: (t: TabId) => void }) {
  return (
    <div className="flex items-center gap-0.5 rounded-full bg-black/5 px-0.5 py-0.5">
      {TAB_LABELS.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          onClick={() => onChange(id)}
          className={[
            'rounded-full px-3 py-1 text-xs font-medium transition-all duration-150 focus:outline-none',
            active === id
              ? 'bg-white text-primary-900 shadow-soft'
              : 'text-slate-400 hover:text-slate-600',
          ].join(' ')}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ── 全部 Tab ─────────────────────────────────────────────────────
function AllTab({
  courseData,
  projectData,
  loading,
}: {
  courseData: AnalyticsData | null;
  projectData: PdfAnalyticsData | null;
  loading: boolean;
}) {
  const [radarMode, setRadarMode] = useState<'weighted' | 'equal'>('weighted');

  const courseInteractions = courseData?.overview.total_turns ?? 0;
  const researchInteractions = projectData?.overview.total_questions ?? 0;
  const totalInteractions = courseInteractions + researchInteractions;
  const coursePct = totalInteractions > 0 ? Math.round((courseInteractions / totalInteractions) * 100) : 0;
  const researchPct = 100 - coursePct;

  // 綜合雷達圖
  // 計算量很小（六個領域），直接算；包 useMemo 反而會讓 React Compiler 放棄最佳化這個元件
  const combinedAxes = combinedDomainAxes(courseData, projectData, radarMode, courseInteractions, totalInteractions);

  const combined = diagnoseCombinedType(courseData, projectData, coursePct, combinedAxes);

  if (loading) return <TabLoadingSkeleton />;
  if (!courseData && !projectData) {
    return <p className="py-10 text-center text-sm text-slate-400">切換到「課程助理」或「研究計畫」分頁以開始分析</p>;
  }

  return (
    <div className="space-y-6">
      {/* 概覽數字 */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard icon={<HiChat className="h-5 w-5" />}         label="課程對話"   value={courseData?.overview.total_sessions ?? '—'}           sub="課程助理歷史對話" />
        <StatCard icon={<HiDocumentText className="h-5 w-5" />} label="研究計畫對話" value={projectData?.overview.total_conversations ?? '—'}    sub="研究計畫歷史對話" />
        <StatCard icon={<HiBookOpen className="h-5 w-5" />}     label="課程提問"   value={courseData?.overview.total_turns ?? '—'}              sub="累計提問次數" />
        <StatCard icon={<HiLightningBolt className="h-5 w-5" />} label="探索論文"  value={projectData?.overview.total_documents_explored ?? '—'} sub="不重複論文篇數" />
      </div>

      {/* 綜合學術領域雷達（左） + 探索型態診斷（右） */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {combinedAxes.filter(a => a.value > 0).length >= 2 && (
          <div className="card p-6">
            <div className="mb-4 flex items-center justify-between">
              <SectionTitle>綜合學術領域分佈</SectionTitle>
              <div className="flex items-center gap-0.5 rounded-full bg-slate-100 p-0.5">
                {(['weighted', 'equal'] as const).map(mode => (
                  <button key={mode} type="button" onClick={() => setRadarMode(mode)}
                    className={['rounded-full px-2.5 py-1 text-[11px] font-medium transition-all duration-150',
                      radarMode === mode ? 'bg-white text-primary-800 shadow-soft' : 'text-slate-400 hover:text-slate-600',
                    ].join(' ')}>
                    {mode === 'weighted' ? '加權' : '等比'}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-col items-center gap-4">
              <RadarChart axes={combinedAxes} />
              <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
                {combinedAxes.map(ax => (
                  <span key={ax.label} className="flex items-center gap-1.5 text-xs text-slate-500">
                    <span className="h-2 w-2 rounded-full" style={{ background: DOMAIN_COLORS[ax.label] ?? '#94a3b8' }} />
                    {ax.label} <span className="font-medium text-slate-700">{ax.pct}%</span>
                  </span>
                ))}
              </div>
              <p className="text-center text-[11px] text-slate-400">
                {radarMode === 'weighted'
                  ? `依互動量加權：課程助理 ${coursePct}%、研究計畫 ${researchPct}%`
                  : '兩個系統各佔 50% 等比計算'}
              </p>
            </div>
          </div>
        )}

        {/* 綜合探索型態診斷 */}
        {totalInteractions > 0 && (
          <div className={`card overflow-hidden border bg-gradient-to-br p-6 ${combined.style.color}`}>
            <SectionTitle>探索型態診斷</SectionTitle>
            <div className="flex flex-col items-center gap-5 pt-2 text-center">
              <div className={`flex h-20 w-20 items-center justify-center rounded-2xl ${combined.style.iconBg}`}>
                <combined.style.Icon className={`h-10 w-10 ${combined.style.iconColor}`} />
              </div>
              <div>
                <span className={`rounded-full px-4 py-1 text-sm font-bold ${combined.style.badge}`}>
                  {combined.style.label}
                </span>
                <p className="mt-3 text-sm leading-relaxed text-slate-600">{combined.desc}</p>
              </div>
              <div className="w-full rounded-xl bg-white/60 px-4 py-3 text-left">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">關鍵數據</p>
                <div className="space-y-1.5 text-xs text-slate-600">
                  <div className="flex justify-between">
                    <span>課程助理提問</span>
                    <span className="font-medium">{courseInteractions.toLocaleString()} 次</span>
                  </div>
                  <div className="flex justify-between">
                    <span>研究計畫提問</span>
                    <span className="font-medium">{researchInteractions.toLocaleString()} 次</span>
                  </div>
                  <div className="flex justify-between">
                    <span>探索學院數（合計）</span>
                    <span className="font-medium">
                      {uniqueCollegeCount(courseData, projectData)} 個
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>研究計畫平均對話深度</span>
                    <span className="font-medium">{projectData?.overview.avg_depth ?? '—'} 輪／次</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 使用偏好（下方全寬） */}
      {totalInteractions > 0 && (
        <div className="card p-6">
          <SectionTitle>使用偏好分析</SectionTitle>
          <div className="space-y-4">
            <div className="flex h-2.5 overflow-hidden rounded-full bg-slate-100">
              <div className="bg-indigo-400 transition-all duration-500" style={{ width: `${coursePct}%` }} />
              <div className="bg-emerald-400 transition-all duration-500" style={{ width: `${researchPct}%` }} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-start gap-3">
                <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-indigo-400" />
                <div>
                  <p className="text-xs font-medium text-slate-500">課程助理</p>
                  <p className="text-2xl font-bold text-indigo-600">{coursePct}%</p>
                  <p className="text-[11px] text-slate-400">{courseInteractions.toLocaleString()} 次提問</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-400" />
                <div>
                  <p className="text-xs font-medium text-slate-500">研究計畫</p>
                  <p className="text-2xl font-bold text-emerald-600">{researchPct}%</p>
                  <p className="text-[11px] text-slate-400">{researchInteractions.toLocaleString()} 次提問</p>
                </div>
              </div>
            </div>
            <p className="rounded-xl bg-slate-50 px-4 py-2.5 text-sm text-slate-600">
              {usagePreferenceText(coursePct, researchPct)}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 課程助理 Tab ─────────────────────────────────────────────────
function CourseTab({
  data,
  loading,
  error,
}: {
  data: AnalyticsData | null;
  loading: boolean;
  error: string;
}) {
  const domainAxes = useMemo(() => collegeDomainAxes(data?.college_distribution), [data]);

  const exploreType = useMemo(
    () => (data ? diagnoseType(data, domainAxes) : null),
    [data, domainAxes],
  );

  const hasData = data && data.overview.total_turns > 0;

  if (loading) return <TabLoadingSkeleton />;
  if (error) return <TabError msg={error} />;
  if (!hasData) return <EmptyState />;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard icon={<HiChat className="h-5 w-5" />} label="對話次數"
          value={data.overview.total_sessions} sub="歷史對話總數" />
        <StatCard icon={<HiBookOpen className="h-5 w-5" />} label="提問輪次"
          value={data.overview.total_turns} sub="累計提問次數" />
        <StatCard icon={<HiAcademicCap className="h-5 w-5" />} label="探索課程"
          value={data.overview.total_courses_explored} sub="不重複課程數" />
        <StatCard icon={<HiOfficeBuilding className="h-5 w-5" />} label="最常探索學院"
          value={data.overview.fav_college || '—'} sub="依出現頻率統計" />
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="card p-6">
          <SectionTitle>學術探索領域分佈</SectionTitle>
          {domainAxes.filter(a => a.value > 0).length < 2 ? (
            <p className="text-sm text-slate-400">需要更多對話資料</p>
          ) : (
            <div className="flex flex-col items-center gap-4">
              <RadarChart axes={domainAxes} />
              <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
                {domainAxes.map(ax => (
                  <span key={ax.label} className="flex items-center gap-1.5 text-xs text-slate-500">
                    <span className="h-2 w-2 rounded-full" style={{ background: DOMAIN_COLORS[ax.label] ?? '#94a3b8' }} />
                    {ax.label} <span className="font-medium text-slate-700">{ax.pct}%</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {exploreType && (
          <div className={`card overflow-hidden border bg-gradient-to-br p-6 ${exploreType.color}`}>
            <SectionTitle>探索型態診斷</SectionTitle>
            <div className="flex flex-col items-center gap-5 pt-2 text-center">
              <div className={`flex h-20 w-20 items-center justify-center rounded-2xl ${exploreType.iconBg}`}>
                <exploreType.Icon className={`h-10 w-10 ${exploreType.iconColor}`} />
              </div>
              <div>
                <span className={`rounded-full px-4 py-1 text-sm font-bold ${exploreType.badge}`}>
                  {exploreType.label}
                </span>
                <p className="mt-3 text-sm leading-relaxed text-slate-600">{exploreType.desc}</p>
              </div>
              <div className="w-full rounded-xl bg-white/60 px-4 py-3 text-left">
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">關鍵數據</p>
                <div className="space-y-1 text-xs text-slate-600">
                  <div className="flex justify-between">
                    <span>探索系所數</span>
                    <span className="font-medium">{data.dept_distribution.length} 個</span>
                  </div>
                  <div className="flex justify-between">
                    <span>最集中系所</span>
                    <span className="font-medium">{data.dept_distribution[0]?.pct.toFixed(1) ?? 0}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span>跨域廣度</span>
                    <span className="font-medium">{activeDomainCount(domainAxes)} 個主要領域</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {data.top_domain_tags.length > 0 && (
          <EChartsWordCloud tags={data.top_domain_tags} title="課程探索領域" />
        )}
        {data.top_course_domains.length > 0 && (
          <EChartsWordCloud
            tags={data.top_course_domains.map(d => ({ tag: d.domain, count: d.count }))}
            title="課程領域分佈"
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {data.dept_distribution.length > 0 && (
          <EChartsPie items={data.dept_distribution} title="探索系所分佈" />
        )}
        <GeneralEduRings ge={data.general_edu} />
      </div>
    </div>
  );
}

// ── 研究計畫 Tab ─────────────────────────────────────────────────
function ProjectTab({
  data,
  loading,
  error,
}: {
  data: PdfAnalyticsData | null;
  loading: boolean;
  error: string;
}) {
  const [showAllDocs, setShowAllDocs] = useState(false);

  const domainAxes = useMemo(() => collegeDomainAxes(data?.college_distribution), [data]);

  const pdfExploreStyle = data?.exploration_type.type
    ? (PDF_TYPE_MAP[data.exploration_type.type] ?? PDF_EXPLORE_TYPES[4])
    : null;

  const hasData = data && data.overview.total_conversations > 0;

  if (loading) return <TabLoadingSkeleton />;
  if (error) return <TabError msg={error} />;
  if (!hasData) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-100">
          <HiDocumentText className="h-8 w-8 text-slate-300" />
        </div>
        <h2 className="text-lg font-semibold text-slate-600">還沒有研究計畫探索記錄</h2>
        <p className="mt-1 text-sm text-slate-400">前往研究計畫頁面，與論文對話後分析將在這裡呈現</p>
        <Link to="/projects" className="btn-primary mt-6 inline-flex items-center gap-1.5 text-sm">
          前往研究計畫 <HiChevronRight className="h-4 w-4" />
        </Link>
      </div>
    );
  }

  const visibleDocs = showAllDocs ? data.document_list : data.document_list.slice(0, 4);

  return (
    <div className="space-y-6">
      {/* 概覽卡片 */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard icon={<HiChat className="h-5 w-5" />} label="對話次數"
          value={data.overview.total_conversations} sub="歷史對話總數" />
        <StatCard icon={<HiBookOpen className="h-5 w-5" />} label="提問次數"
          value={data.overview.total_questions} sub="累計提問次數" />
        <StatCard icon={<HiDocumentText className="h-5 w-5" />} label="探索論文"
          value={data.overview.total_documents_explored} sub="不重複論文篇數" />
        <StatCard icon={<HiOfficeBuilding className="h-5 w-5" />} label="最常探索學院"
          value={data.college_distribution[0]?.name || '—'} sub="依對話次數統計" />
      </div>

      {/* 學術領域雷達 + 探索型態診斷 */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="card p-6">
          <SectionTitle>研究領域探索分佈</SectionTitle>
          {domainAxes.filter(a => a.value > 0).length < 2 ? (
            <p className="text-sm text-slate-400">需要更多對話資料</p>
          ) : (
            <div className="flex flex-col items-center gap-4">
              <RadarChart axes={domainAxes} />
              <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
                {domainAxes.map(ax => (
                  <span key={ax.label} className="flex items-center gap-1.5 text-xs text-slate-500">
                    <span className="h-2 w-2 rounded-full" style={{ background: DOMAIN_COLORS[ax.label] ?? '#94a3b8' }} />
                    {ax.label} <span className="font-medium text-slate-700">{ax.pct}%</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {pdfExploreStyle && (
          <div className={`card overflow-hidden border bg-gradient-to-br p-6 ${pdfExploreStyle.color}`}>
            <SectionTitle>探索型態診斷</SectionTitle>
            <div className="flex flex-col items-center gap-5 pt-2 text-center">
              <div className={`flex h-20 w-20 items-center justify-center rounded-2xl ${pdfExploreStyle.iconBg}`}>
                <pdfExploreStyle.Icon className={`h-10 w-10 ${pdfExploreStyle.iconColor}`} />
              </div>
              <div>
                <span className={`rounded-full px-4 py-1 text-sm font-bold ${pdfExploreStyle.badge}`}>
                  {data.exploration_type.type}
                </span>
                <p className="mt-3 text-sm leading-relaxed text-slate-600">{data.exploration_type.desc}</p>
              </div>
              <div className="w-full rounded-xl bg-white/60 px-4 py-3 text-left">
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">關鍵數據</p>
                <div className="space-y-1 text-xs text-slate-600">
                  <div className="flex justify-between">
                    <span>探索論文篇數</span>
                    <span className="font-medium">{data.overview.total_documents_explored} 篇</span>
                  </div>
                  <div className="flex justify-between">
                    <span>平均對話深度</span>
                    <span className="font-medium">{data.overview.avg_depth} 輪／次</span>
                  </div>
                  <div className="flex justify-between">
                    <span>涉及系所數</span>
                    <span className="font-medium">{data.dept_distribution.length} 個</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 系所分佈 + 對話深度長條圖 */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {data.dept_distribution.length > 0 && (
          <EChartsPie items={data.dept_distribution} title="探索系所分佈" />
        )}
        <EChartsBar items={data.depth_distribution} title="對話深度分佈" />
      </div>

      {/* 論文探索列表 */}
      {data.document_list.length > 0 && (
        <div className="card p-6">
          <SectionTitle>探索的研究計畫</SectionTitle>
          <div className="space-y-3">
            {visibleDocs.map(doc => (
              <div key={doc.document_id}
                className="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-100">
                  <HiDocumentText className="h-5 w-5 text-primary-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800" title={doc.title}>
                    {doc.title || doc.department + ' 研究計畫'}
                  </p>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                    {doc.department && (
                      <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-slate-200 text-slate-500">
                        {doc.department}
                      </span>
                    )}
                    {doc.year && <span>{doc.year} 年度</span>}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm font-bold text-primary-700">{doc.conversation_count} 次對話</p>
                  {doc.last_viewed_at && (
                    <p className="text-[11px] text-slate-400">
                      {formatRelativeTime(doc.last_viewed_at)}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
          {data.document_list.length > 4 && (
            <button type="button" onClick={() => setShowAllDocs(v => !v)}
              className="mt-3 w-full rounded-xl border border-slate-200 py-2 text-xs font-medium text-slate-500 hover:bg-slate-50 transition">
              {showAllDocs ? '收起' : `查看全部 ${data.document_list.length} 篇`}
            </button>
          )}
        </div>
      )}

      {/* 最近提問 */}
      {data.recent_questions.length > 0 && (
        <div className="card p-6">
          <SectionTitle>最近提問記錄</SectionTitle>
          <div className="space-y-2">
            {data.recent_questions.map((q, i) => (
              <div key={i} className="flex items-start gap-3 rounded-xl border border-slate-100 px-4 py-3">
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-100">
                  <HiClock className="h-3.5 w-3.5 text-accent-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 text-sm text-slate-700">{q.question || '（無內容）'}</p>
                  {q.document_title && (
                    <p className="mt-0.5 truncate text-xs text-slate-400">{q.document_title}</p>
                  )}
                </div>
                {q.created_at && (
                  <span className="shrink-0 text-[11px] text-slate-400">{formatRelativeTime(q.created_at)}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TabLoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}
      </div>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Skeleton className="h-80" /><Skeleton className="h-80" />
        <Skeleton className="h-64" /><Skeleton className="h-64" />
      </div>
    </div>
  );
}

function TabError({ msg }: { msg: string }) {
  return (
    <div className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">{msg}</div>
  );
}

// ── 主頁面 ──────────────────────────────────────────────────────
export default function AnalyticsPage() {
  const { user, loading: authLoading } = useAuth();
  const {
    activeTab, setActiveTab,
    courseData, courseLoading, courseError,
    projectData, projectLoading, projectError,
  } = useAnalytics();

  if (authLoading) {
    return (
      <div className="page-container py-12">
        <Skeleton className="mb-8 h-16 w-64" />
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <Skeleton className="h-72" /><Skeleton className="h-72" />
        </div>
      </div>
    );
  }

  if (!user) return <div className="page-container py-12 page-animate"><NotLoggedIn /></div>;

  return (
    <div className="page-container py-10 page-animate">
      {/* 頁首 */}
      <div className="mb-8 flex items-start justify-between">
        <div className="flex items-center gap-4">
          {user.picture ? (
            <img src={user.picture} alt=""
              className="h-14 w-14 rounded-full object-cover ring-4 ring-primary-100" />
          ) : (
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-100 text-xl font-bold text-primary-700">
              {user.name?.[0] ?? '?'}
            </div>
          )}
          <div>
            <h1 className="text-xl font-bold text-primary-900">{user.name}</h1>
            <p className="text-sm text-slate-500">{user.email}</p>
            <p className="mt-0.5 text-xs text-slate-400">學習傾向分析</p>
          </div>
        </div>
        <TabSwitcher active={activeTab} onChange={setActiveTab} />
      </div>

      {activeTab === 'all' && (
        <AllTab courseData={courseData} projectData={projectData} loading={courseLoading || projectLoading} />
      )}
      {activeTab === 'course' && (
        <CourseTab data={courseData} loading={courseLoading} error={courseError} />
      )}
      {activeTab === 'project' && (
        <ProjectTab data={projectData} loading={projectLoading} error={projectError} />
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// ECharts 圖表元件
// ══════════════════════════════════════════════════════════════════

// ── ECharts WordCloud：domain_tags ────────────────────────────────
function EChartsWordCloud({ tags, title = '課程探索領域' }: { tags: { tag: string; count: number }[]; title?: string }) {
  const option = {
    series: [{
      type: 'wordCloud',
      shape: 'circle',
      left: 'center', top: 'center',
      width: '95%', height: '95%',
      sizeRange: [13, 52],
      rotationRange: [0, 0],       // 全部水平，中文更易讀
      gridSize: 10,
      drawOutOfBound: false,
      textStyle: {
        fontFamily: 'system-ui, sans-serif',
        fontWeight: 'bold',
        color() {
          const palette = [
            '#6366f1','#8b5cf6','#0ea5e9','#10b981',
            '#f59e0b','#ec4899','#14b8a6','#f97316',
          ];
          return palette[Math.floor(Math.random() * palette.length)];
        },
      },
      emphasis: { focus: 'self', textStyle: { shadowBlur: 10, shadowColor: '#333' } },
      data: tags.map(t => ({ name: t.tag, value: t.count })),
    }],
  };
  return (
    <div className="card flex flex-col p-6">
      <SectionTitle>{title}</SectionTitle>
      <p className="mb-3 text-xs text-slate-400">字體大小反映探索頻率</p>
      <ReactECharts option={option} style={{ flex: 1, minHeight: 200 }} />
    </div>
  );
}

// ── ECharts Pie：學院分佈 ─────────────────────────────────────────
function EChartsPie({
  items,
  title = '探索分佈',
}: {
  items: { name: string; count: number; pct: number }[];
  title?: string;
}) {
  // 系所名稱比學院長，legend 欄位要更寬
  const nmWidth = items.some(i => i.name.length > 6) ? 136 : 108;
  const option = {
    tooltip: { trigger: 'item', formatter: '{b}：{d}%', confine: true },
    legend: {
      orient: 'vertical',
      right: 0,
      top: 'middle',
      itemWidth: 8,
      itemHeight: 8,
      formatter: (name: string) => {
        const it = items.find(i => i.name === name);
        return `{nm|${name}}{pt|${it?.pct ?? 0}%}`;
      },
      textStyle: {
        rich: {
          nm: { width: nmWidth, align: 'left',  fontSize: 11, color: '#475569' },
          pt: { width: 36,      align: 'right', fontSize: 11, color: '#94a3b8' },
        },
      },
    },
    series: [{
      type: 'pie',
      radius: ['40%', '66%'],
      center: ['30%', '50%'],
      label: { show: false },
      labelLine: { show: false },
      emphasis: {
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.15)' },
      },
      data: items.map((it, i) => ({
        name: it.name,
        value: it.count,
        itemStyle: { color: DONUT_COLORS[i % DONUT_COLORS.length] },
      })),
    }],
  };
  return (
    <div className="card flex flex-col p-6">
      <SectionTitle>{title}</SectionTitle>
      <ReactECharts option={option} style={{ flex: 1, minHeight: 200 }} />
    </div>
  );
}

// ── ECharts Bar：對話深度分佈 ──────────────────────────────────
function EChartsBar({
  items,
  title = '分佈',
}: {
  items: { range: string; count: number }[];
  title?: string;
}) {
  const option = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true },
    grid: { left: 16, right: 16, top: 16, bottom: 16, containLabel: true },
    xAxis: {
      type: 'category',
      data: items.map(i => i.range),
      axisLabel: { fontSize: 11, color: '#64748b' },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { fontSize: 11, color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
    },
    series: [{
      type: 'bar',
      data: items.map((it, i) => ({
        value: it.count,
        itemStyle: { color: DONUT_COLORS[i % DONUT_COLORS.length], borderRadius: [6, 6, 0, 0] },
      })),
      barMaxWidth: 60,
    }],
  };
  return (
    <div className="card flex flex-col p-6">
      <SectionTitle>{title}</SectionTitle>
      <ReactECharts option={option} style={{ flex: 1, minHeight: 200 }} />
    </div>
  );
}

const DOMAIN_TREEMAP_COLORS = [
  '#6366f1','#8b5cf6','#0ea5e9','#10b981',
  '#f59e0b','#ec4899','#f97316','#14b8a6',
  '#64748b','#a855f7','#06b6d4','#84cc16',
];

// ── 通識與一般選修：圓形進度環 + 分類標籤 ──────────────────────
const GE_CAT_COLORS: Record<string, string> = {
  通識: '#8b5cf6', 外語: '#0ea5e9', 體育: '#10b981', 服務學習: '#f59e0b',
};

function GeneralEduRings({ ge }: { ge: AnalyticsGeneralEdu }) {
  const top = ge.top_topic_tags.slice(0, 6);
  const maxCount = top[0]?.count ?? 1;
  const C = 2 * Math.PI * 28;

  const hasData = top.length > 0 || ge.categories.length > 0;
  if (!hasData) return null;

  return (
    <div className="card p-6">
      <SectionTitle>通識與一般選修</SectionTitle>

      {/* 分類計數標籤 */}
      {ge.categories.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {ge.categories.map(cat => {
            const color = GE_CAT_COLORS[cat.name] ?? '#94a3b8';
            return (
              <span key={cat.name}
                className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
                style={{ background: color + '18', color }}>
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
                {cat.name}
                <span className="font-semibold ml-0.5">{cat.count} 門</span>
              </span>
            );
          })}
        </div>
      )}

      {/* 通識 topic_tags 圓形環 */}
      {top.length > 0 ? (
        <div className="grid grid-cols-3 gap-3">
          {top.map((t, i) => {
            const pct = t.count / maxCount;
            const color = DOMAIN_TREEMAP_COLORS[i % DOMAIN_TREEMAP_COLORS.length];
            const dash = pct * C;
            const gap  = C - dash;
            return (
              <div key={t.tag} className="flex flex-col items-center gap-1.5">
                <div className="relative h-[68px] w-[68px]">
                  <svg viewBox="0 0 64 64" className="h-full w-full -rotate-90">
                    <circle cx="32" cy="32" r="28" fill="none" stroke="#f1f5f9" strokeWidth="7" />
                    <circle cx="32" cy="32" r="28" fill="none"
                      stroke={color} strokeWidth="7" strokeLinecap="round"
                      strokeDasharray={`${dash} ${gap}`} />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center text-[11px] font-bold"
                    style={{ color }}>
                    {Math.round(pct * 100)}%
                  </div>
                </div>
                <span className="max-w-[72px] text-center text-[10px] leading-tight text-slate-600">
                  {t.tag}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-slate-400">尚無通識課程探索記錄</p>
      )}
    </div>
  );
}
