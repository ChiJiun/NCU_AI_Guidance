import { useState, useEffect, useMemo, useContext, createContext } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { deptSortKey } from '../constants/colleges';
import CourseDetailModal from '../components/CourseDetailModal';
import type { CourseCard } from '../types';
import {
  CATEGORIES_ORDER, REQUIRED_COURSE_FIELDS,
  findCrossMatches, groupBySem, normalizeCourse,
} from '../features/curriculum/courseIndex';
import type {
  CourseEntry, CourseHit, CourseIndex, DeptDetail, DeptSummary,
  ElectiveGroup, GraduationRule, NotesEntry,
} from '../features/curriculum/types';
import { useCurriculumData } from '../features/curriculum/useCurriculumData';

// ── Context ──────────────────────────────────────────────────────────────

interface CurriculumContextValue {
  courseIndex: CourseIndex;
  indexReady: boolean;
  currentDeptId: string;
  comparePool: DeptSummary[];
  toggleCompare: (dept: DeptSummary) => void;
  navigateTo: (deptId: string) => void;
  openCrossSearch: (course: CourseEntry) => void;
}

const CurriculumCtx = createContext<CurriculumContextValue>({
  courseIndex: new Map(),
  indexReady: false,
  currentDeptId: '',
  comparePool: [],
  toggleCompare: () => {},
  navigateTo: () => {},
  openCrossSearch: () => {},
});

// ══════════════════════════════════════════════════════════════════════════
// 樹狀節點元件
// ══════════════════════════════════════════════════════════════════════════

const INDENT = 20; // px per level

function TreeNode({
  label,
  badge,
  badgeColor = 'bg-slate-100 text-slate-500',
  icon,
  depth = 0,
  defaultOpen = false,
  children,
  leaf = false,
  dimmed = false,
}: {
  label: React.ReactNode;
  badge?: string | number;
  badgeColor?: string;
  icon?: string;
  depth?: number;
  defaultOpen?: boolean;
  children?: React.ReactNode;
  leaf?: boolean;
  dimmed?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const hasChildren = !!children;

  return (
    <div className="mb-0.5">
      <div
        className={`flex items-center gap-2 py-1.5 pr-2 rounded-xl cursor-pointer select-none transition-all duration-200 ease-in-out border border-transparent
          ${hasChildren ? 'hover:bg-white hover:shadow-sm hover:border-slate-100' : 'hover:bg-slate-50'} ${dimmed ? 'opacity-50' : ''}`}
        style={{ paddingLeft: depth * INDENT + 8 }}
        onClick={() => hasChildren && setOpen((v) => !v)}
      >
        {/* expand icon */}
        <span className={`w-5 shrink-0 flex items-center justify-center text-[10px] text-slate-400 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}>
          {!leaf && hasChildren ? '▶' : ''}
        </span>
        {icon && <span className="text-base drop-shadow-sm">{icon}</span>}
        <span className={`flex-1 text-sm ${dimmed ? 'text-slate-400 font-normal' : 'text-slate-700 font-medium'}`}>{label}</span>
        {badge !== undefined && badge !== '' && (
          <span className={`shrink-0 rounded-lg px-3.5 py-[5.5px] text-[10px] font-bold leading-none tracking-wide shadow-sm border border-black/5 ${badgeColor}`}>
            {badge}
          </span>
        )}
      </div>
      {open && hasChildren && <div className="mt-0.5 relative">{children}</div>}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 學期分組工具
// ══════════════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════════════
// 課程節點
// ══════════════════════════════════════════════════════════════════════════

function CourseLeaf({ c, depth, hideIndent = false, accentHex = '#6366f1' }: { c: CourseEntry; depth: number; hideIndent?: boolean; accentHex?: string }) {
  const { openCrossSearch } = useContext(CurriculumCtx);

  const handleShowDetail = (e: React.MouseEvent) => {
    e.stopPropagation();
    window.dispatchEvent(
      new CustomEvent('SHOW_COURSE_DETAIL', {
        detail: {
          id: c.code || c.name,
          code: c.code || '',
          name: c.name,
          credits: c.credits || 0,
          type: c.mandatory ? '必修' : '選修',
          teacher: '',
        },
      })
    );
  };

  return (
    <div
      onClick={handleShowDetail}
      className="flex items-center gap-3 py-2.5 px-4 bg-white rounded-lg border border-slate-100 hover:border-slate-200 hover:bg-slate-50/60 transition-colors mb-2 cursor-pointer shadow-sm group"
      style={!hideIndent ? { marginLeft: depth * INDENT } : {}}
    >
      <div className="w-1 self-stretch rounded-full shrink-0" style={{ backgroundColor: accentHex }} />
      <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold text-slate-800 group-hover:text-slate-900 transition-colors">{c.name}</span>
        {c.mandatory && (
          <span className="px-1.5 py-[1px] rounded text-[9px] font-bold border" style={{ backgroundColor: accentHex + '18', borderColor: accentHex + '40', color: accentHex }}>必修</span>
        )}
        {c.when && <span className="text-[10px] text-slate-400 font-medium">{c.when}</span>}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="text-xs font-mono text-slate-400">{c.code}</span>
        <span className="text-xs font-bold px-2 py-[3px] rounded-md leading-none" style={{ backgroundColor: accentHex + '12', color: accentHex }}>{c.credits} 學分</span>
        <button
          onClick={e => { e.stopPropagation(); openCrossSearch(c); }}
          className="opacity-0 group-hover:opacity-100 transition-opacity h-6 w-6 flex items-center justify-center rounded-full text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"
          title="查看此課程在其他系所"
          aria-label="跨系查找"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </button>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 選修群樹
// ══════════════════════════════════════════════════════════════════════════

function ElectiveGroupTree({ g, depth, accentHex = '#6366f1' }: { g: ElectiveGroup; depth: number; accentHex?: string }) {
  const selectLabel = g.select
    ? `選 ${g.select} 門`
    : g.select_credits
      ? `選 ${g.select_credits} 學分`
      : '';

  const allCourses = g.courses ?? [];
  const hasOptions = !!(g.option_a || g.option_b || g.option_c);
  const hasSlots = !!(g.slots && g.slots.length > 0);
  const isEmpty = allCourses.length === 0 && !hasOptions && !hasSlots;

  return (
    <div className="mb-3 bg-white rounded-lg border border-slate-100 shadow-sm overflow-hidden" style={{ marginLeft: depth * INDENT }}>
      <div className="px-4 py-3 flex items-center gap-3 border-b border-slate-100/60">
        <div className="flex-1 flex items-center gap-2.5 flex-wrap">
          <span className="text-[15px] font-bold text-slate-800">{g.name || '選修群組'}</span>
          {selectLabel && (
            <span className="px-2 py-[3px] rounded-md text-[10px] font-bold leading-none border" style={{ backgroundColor: accentHex + '12', borderColor: accentHex + '35', color: accentHex }}>
              {selectLabel}
            </span>
          )}
          {isEmpty && <span className="text-[11px] text-slate-400 italic">（課程清單未收錄）</span>}
        </div>
        {allCourses.length > 0 && (
          <span className="text-[10px] font-bold text-slate-400 shrink-0">{allCourses.length} 門</span>
        )}
      </div>
      {allCourses.length > 0 && (
        <div className="p-3">
          <SemesterGroup courses={allCourses} depth={0} hideSemesters accentHex={accentHex} />
        </div>
      )}
      {/* slots */}
      {hasSlots && g.slots!.map((slot, i) => (
        <div key={i} className="border-t border-slate-100 p-3">
          <div className="text-[11px] font-bold mb-2" style={{ color: accentHex }}>{slot.slot_name || `Slot ${i + 1}`}</div>
          <SemesterGroup courses={slot.courses} depth={0} hideSemesters accentHex={accentHex} />
        </div>
      ))}
      {/* options (sub groups) */}
      {hasOptions && (
        <div className="border-t border-slate-100 p-3 space-y-4">
          {g.option_a && (
            <div>
              <div className="text-[11px] font-bold text-slate-500 mb-2">▪ 選項 A</div>
              <SemesterGroup courses={g.option_a} depth={0} hideSemesters accentHex={accentHex} />
            </div>
          )}
          {g.option_b && (
            <div>
              <div className="text-[11px] font-bold text-slate-500 mb-2">▪ 選項 B</div>
              <SemesterGroup courses={g.option_b} depth={0} hideSemesters accentHex={accentHex} />
            </div>
          )}
          {g.option_c && (
            <div>
              <div className="text-[11px] font-bold text-slate-500 mb-2">▪ 選項 C</div>
              <SemesterGroup courses={g.option_c} depth={0} hideSemesters accentHex={accentHex} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 畢業規定節點
// ══════════════════════════════════════════════════════════════════════════

const CATEGORY_COLOR: Record<string, string> = {
  '學分規定': 'bg-blue-50 text-blue-700',
  '指定選課': 'bg-purple-50 text-purple-700',
  '先修條件': 'bg-yellow-50 text-yellow-700',
  '外部認證': 'bg-green-50 text-green-700',
  '特殊規定': 'bg-orange-50 text-orange-700',
  '其他規定': 'bg-gray-50 text-gray-600',
};

const CATEGORY_HEX: Record<string, string> = {
  '學分規定': '#3b82f6',
  '指定選課': '#8b5cf6',
  '先修條件': '#f59e0b',
  '外部認證': '#22c55e',
  '特殊規定': '#f97316',
  '其他規定': '#94a3b8',
};

function RuleTree({ rule, depth, dotHex = '#94a3b8' }: { rule: GraduationRule; depth: number; dotHex?: string }) {
  const hasCourses =
    (rule.course_codes && rule.course_codes.length > 0) ||
    (rule.courses && rule.courses.length > 0);
  const hasOptions = !!(rule.options && rule.options.length > 0);
  const isLeaf = !hasCourses && !hasOptions;

  const isEnglishKey = /^[a-zA-Z_]+$/.test(rule.type);
  const label = (
    <span className="flex items-center gap-2">
      {!isEnglishKey && rule.type && (
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold shadow-sm border border-slate-100 ${CATEGORY_COLOR[rule.category] ?? 'bg-slate-50 text-slate-500'}`}>
          {rule.type}
        </span>
      )}
      <span className="text-slate-700 font-medium">
        {rule.description ?? (rule.cert ? `認證：${rule.cert}` : '')}
      </span>
    </span>
  );

  const creditBadge = rule.credits !== undefined
    ? `${rule.credits} 學分`
    : rule.select !== undefined
      ? `選${rule.select}門`
      : undefined;

  if (isLeaf) {
    return (
      <div className="flex items-start gap-2.5 py-1.5 pr-2 rounded-lg hover:bg-slate-50 transition-colors duration-150"
        style={{ paddingLeft: depth * INDENT + 8 }}>
        <div className="w-2 h-2 rounded-full shrink-0 mt-[7px]" style={{ backgroundColor: dotHex }} />
        <span className="flex-1 text-sm leading-relaxed">{label}</span>
        {creditBadge && (
          <span className="shrink-0 rounded-full px-2.5 py-[3px] text-xs font-semibold leading-none text-slate-600 bg-slate-100 border border-slate-200/60">
            {creditBadge}
          </span>
        )}
      </div>
    );
  }

  return (
    <TreeNode label={label} badge={creditBadge} depth={depth} defaultOpen={false} icon="•">
      {rule.course_codes?.map((code) => (
        <div key={code} style={{ paddingLeft: (depth + 1) * INDENT + 4 }}
          className="py-0.5 font-mono text-xs text-gray-500 hover:bg-gray-50 rounded">
          <span className="w-4 inline-block" /> {code}
        </div>
      ))}
      {rule.courses?.map((c) => (
        <CourseLeaf key={c.code} c={c} depth={depth + 1} />
      ))}
      {rule.options?.map((opt, i) => (
        <div key={i} style={{ paddingLeft: (depth + 1) * INDENT + 4 }}
          className="py-0.5 text-sm text-gray-600 hover:bg-gray-50 rounded">
          <span className="w-4 inline-block" /> {opt.name}
          {opt.credits && <span className="ml-1 text-xs text-gray-400">{opt.credits}cr</span>}
        </div>
      ))}
    </TreeNode>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 系所詳情樹（核心元件）
// ══════════════════════════════════════════════════════════════════════════


function SemesterGroup({
  courses,
  depth,
  hideSemesters = false,
  accentHex = '#6366f1',
}: {
  courses: CourseEntry[];
  depth: number;
  hideSemesters?: boolean;
  accentHex?: string;
}) {
  if (hideSemesters) {
    return (
      <div style={{ marginLeft: depth * INDENT }}>
        {courses.map((c) => <CourseLeaf key={c.code} c={c} depth={0} hideIndent accentHex={accentHex} />)}
      </div>
    );
  }

  const semMap = groupBySem(courses);
  return (
    <div className="space-y-5">
      {Array.from(semMap.entries()).map(([sem, cs]) => (
        <div key={sem} style={{ marginLeft: depth * INDENT }}>
          <div className="text-xs font-bold uppercase tracking-wider mb-2 flex items-center gap-2 leading-6 pb-1 border-b border-slate-100" style={{ color: accentHex + 'cc' }}>
            <span>{sem}</span>
          </div>
          <div>
            {cs.map((c) => <CourseLeaf key={c.code} c={c} depth={0} hideIndent accentHex={accentHex} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

function SectionCard({ children, hasProgress, current, max }: { children: React.ReactNode, hasProgress?: boolean, current?: number, max?: number }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-100 px-6 py-6 mb-5 transition-shadow duration-300 hover:shadow-md relative overflow-hidden group">
      {hasProgress && max && max > 0 && current !== undefined && (
        <div className="absolute top-0 left-0 w-full h-1 bg-slate-100">
          <div className="h-full bg-gradient-to-r from-indigo-500 to-blue-500 rounded-r-full transition-all duration-1000 ease-out" style={{ width: `${Math.min((current / max) * 100, 100)}%` }}></div>
        </div>
      )}
      {children}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 跨系查找浮層
// ══════════════════════════════════════════════════════════════════════════

function CrossDeptPopover({
  course,
  onClose,
}: {
  course: CourseEntry;
  onClose: () => void;
}) {
  const { courseIndex, indexReady, currentDeptId, navigateTo } = useContext(CurriculumCtx);
  const rtrNavigate = useNavigate();

  const { exact, similar } = useMemo(
    () => (indexReady ? findCrossMatches(course.name, currentDeptId, courseIndex) : { exact: [], similar: [] }),
    [course.name, currentDeptId, courseIndex, indexReady]
  );
  const isEmpty = exact.length === 0 && similar.length === 0;
  const [expandedSimilar, setExpandedSimilar] = useState<Set<string>>(new Set());
  const toggleSimilar = (key: string) => setExpandedSimilar(prev => {
    const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next;
  });

  // 將 similar 展平為「課名+課號+修別」各自一列
  const similarRows = useMemo(() => {
    const rows: Array<{ rowKey: string; courseName: string; code: string; category: 'required'|'elective'; hits: CourseHit[] }> = [];
    for (const { hits } of similar.slice(0, 5)) {
      const codeMap = new Map<string, CourseHit[]>();
      for (const hit of hits) {
        const k = hit.originalCode ? `${hit.originalCode}-${hit.category}` : `solo-${hit.deptId}`;
        if (!codeMap.has(k)) codeMap.set(k, []);
        codeMap.get(k)!.push(hit);
      }
      for (const [, codeHits] of codeMap) {
        const r = codeHits[0];
        rows.push({ rowKey: `${r.originalName}-${r.originalCode}-${r.category}`, courseName: r.originalName, code: r.originalCode, category: r.category, hits: codeHits });
      }
    }
    return rows;
  }, [similar]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-slate-100">
          <div className="min-w-0">
            <div className="font-bold text-slate-900 text-sm truncate">{course.name}</div>
            <div className="text-xs text-slate-400 mt-0.5">跨系出現狀況</div>
          </div>
          <button onClick={onClose} className="shrink-0 h-7 w-7 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 transition">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="overflow-y-auto max-h-[60vh]">
          {!indexReady ? (
            <div className="p-6 text-center text-sm text-slate-400 animate-pulse">課程索引建立中…</div>
          ) : isEmpty ? (
            <div className="p-6 text-center text-sm text-slate-400">在其他系所修課規定中未發現此課程</div>
          ) : (
            <>
              {exact.length > 0 && (() => {
                // 依課號+修別分組，無課號的各自一組
                const groups = exact.reduce<Map<string, CourseHit[]>>((acc, hit) => {
                  const key = hit.originalCode ? `${hit.originalCode}-${hit.category}` : `solo-${hit.deptId}`;
                  if (!acc.has(key)) acc.set(key, []);
                  acc.get(key)!.push(hit);
                  return acc;
                }, new Map());
                return (
                  <div>
                    <div className="px-4 pt-3 pb-1.5 flex items-center gap-2">
                      <span className="w-[3px] h-3.5 rounded-full bg-emerald-400 shrink-0" />
                      <span className="text-xs font-bold text-emerald-700">完全相同（{exact.length} 系）</span>
                    </div>
                    <div className="divide-y divide-slate-50">
                      {Array.from(groups.values()).map(hits => {
                        const rep = hits[0];
                        const byCollege = hits.reduce<Map<string, CourseHit[]>>((acc, hit) => {
                          if (!acc.has(hit.collegeName)) acc.set(hit.collegeName, []);
                          acc.get(hit.collegeName)!.push(hit);
                          return acc;
                        }, new Map());
                        return (
                          <div key={`${rep.originalCode}-${rep.category}-${rep.deptId}`} className="flex gap-3 px-4 py-2">
                            {/* 左側：課號 + 課名 + 修別 */}
                            <div className="w-24 shrink-0 pt-0.5 overflow-hidden">
                              {rep.originalCode && <div className="font-mono text-xs font-semibold text-slate-700">{rep.originalCode}</div>}
                              <div className="text-[10px] text-slate-500 mt-0.5 leading-snug line-clamp-2">{rep.originalName}</div>
                              <div className={`text-[10px] mt-0.5 ${rep.category === 'required' ? 'text-red-400' : 'text-green-500'}`}>
                                {rep.category === 'required' ? '必修' : '選修'}
                              </div>
                            </div>
                            {/* 右側：學院 + chips */}
                            <div className="flex-1 min-w-0 space-y-1.5">
                              {Array.from(byCollege.entries()).map(([college, collegeHits]) => (
                                <div key={college}>
                                  <div className="text-[9px] text-slate-400 mb-0.5">{college}</div>
                                  <div className="flex flex-wrap gap-1">
                                    {collegeHits.map(hit => (
                                      <button
                                        key={hit.deptId}
                                        onClick={() => { navigateTo(hit.deptId); onClose(); }}
                                        className="flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-100 transition"
                                      >
                                        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: hit.accentHex }} />
                                        {hit.deptName}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <div className="h-1" />
                  </div>
                );
              })()}
              {similarRows.length > 0 && (
                <div className={exact.length > 0 ? 'border-t border-slate-100' : ''}>
                  <div className="px-4 pt-3 pb-1.5 flex items-center gap-2">
                    <span className="w-[3px] h-3.5 rounded-full bg-amber-400 shrink-0" />
                    <span className="text-xs font-bold text-amber-700">名稱相似</span>
                  </div>
                  <div className="divide-y divide-slate-50">
                    {similarRows.map(({ rowKey, courseName, code, category, hits }) => {
                      const isOpen = expandedSimilar.has(rowKey);
                      const byCollege = hits.reduce<Map<string, CourseHit[]>>((acc, hit) => {
                        if (!acc.has(hit.collegeName)) acc.set(hit.collegeName, []);
                        acc.get(hit.collegeName)!.push(hit);
                        return acc;
                      }, new Map());
                      return (
                        <div key={rowKey}>
                          <button
                            onClick={() => toggleSimilar(rowKey)}
                            className="w-full text-left flex items-center gap-3 px-4 py-1.5 hover:bg-amber-50 transition"
                          >
                            <div className="flex-1 min-w-0 flex items-center gap-2">
                              <span className="text-sm font-medium text-slate-700">{courseName}</span>
                              <span className="font-mono text-[10px] text-slate-400">{code}</span>
                              <span className={`text-[10px] ${category === 'required' ? 'text-red-400' : 'text-green-500'}`}>
                                {category === 'required' ? '必修' : '選修'}
                              </span>
                              <span className="text-[10px] text-slate-300">{hits.length} 系</span>
                            </div>
                            <svg className={`w-3 h-3 text-slate-300 shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                            </svg>
                          </button>
                          {isOpen && (
                            <div className="px-4 pb-2 space-y-1.5">
                              {Array.from(byCollege.entries()).map(([college, collegeHits]) => (
                                <div key={college}>
                                  <div className="text-[9px] text-slate-400 mb-0.5">{college}</div>
                                  <div className="flex flex-wrap gap-1">
                                    {collegeHits.map(hit => (
                                      <button
                                        key={hit.deptId}
                                        onClick={() => { navigateTo(hit.deptId); onClose(); }}
                                        className="flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-100 transition"
                                      >
                                        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: hit.accentHex }} />
                                        {hit.deptName}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div className="px-4 py-2 text-[10px] text-slate-400 italic">名稱相似但可能為不同課程，請自行確認</div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="border-t border-slate-100 px-4 py-3">
          <button
            onClick={() => { rtrNavigate(`/courses?search=${encodeURIComponent(course.name)}`); onClose(); }}
            className="flex items-center gap-2 text-xs text-indigo-600 hover:text-indigo-800 font-semibold transition"
          >
            <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            前往課程資訊頁搜尋「{course.name}」
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 全局課程搜尋（側邊欄課程搜尋模式）
// ══════════════════════════════════════════════════════════════════════════

function GlobalCourseSearch({ onNavigate }: { onNavigate: (deptId: string) => void }) {
  const { courseIndex, indexReady } = useContext(CurriculumCtx);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const toggleExpand = (key: string) => setExpandedKeys(prev => {
    const next = new Set(prev);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  });

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 220);
    return () => clearTimeout(t);
  }, [query]);

  const results = useMemo(() => {
    if (!debouncedQuery.trim() || !courseIndex) return [];
    const norm = normalizeCourse(debouncedQuery);
    if (norm.length < 2) return [];
    const hits: Array<{ displayName: string; key: string; depts: CourseHit[] }> = [];
    const seen = new Set<string>();
    for (const [key, depts] of courseIndex) {
      if (!seen.has(key) && key.length >= 2 && (key.includes(norm) || norm.includes(key))) {
        hits.push({ displayName: depts[0]?.originalName ?? key, key, depts });
        seen.add(key);
      }
    }
    hits.sort((a, b) => {
      const ae = a.key === norm, be = b.key === norm;
      if (ae !== be) return ae ? -1 : 1;
      return b.depts.length - a.depts.length;
    });
    return hits.slice(0, 25);
  }, [debouncedQuery, courseIndex]);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="px-3 py-2">
        <div className="flex items-center gap-2 rounded-xl bg-slate-100 px-3 py-2">
          <svg className="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text" value={query} onChange={e => setQuery(e.target.value)}
            placeholder="搜尋課程名稱…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400 text-slate-900"
            autoFocus
          />
          {query && (
            <button onClick={() => setQuery('')} className="text-slate-400 hover:text-slate-600 transition">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-2">
        {!indexReady && (
          <div className="text-center py-10 text-xs text-slate-400 animate-pulse">正在建立課程索引…</div>
        )}
        {indexReady && !debouncedQuery.trim() && (
          <div className="text-center py-10 text-xs text-slate-400 leading-relaxed">
            輸入課程名稱<br />搜尋所有系所修課規定
          </div>
        )}
        {indexReady && debouncedQuery.trim() && results.length === 0 && (
          <div className="text-center py-10 text-xs text-slate-400">未找到「{debouncedQuery}」</div>
        )}
        {indexReady && results.length > 0 && (
          <>
            <div className="text-[10px] text-slate-400 font-medium">找到 {results.length} 筆</div>
            {results.map(({ displayName, key, depts }) => (
              <div key={key} className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-800 flex-1 min-w-0 truncate">{displayName}</span>
                  {depts[0]?.credits > 0 && <span className="shrink-0 text-[10px] font-bold text-slate-400">{depts[0].credits} 學分</span>}
                </div>
                <div className="divide-y divide-slate-50">
                  {(expandedKeys.has(key) ? depts : depts.slice(0, 6)).map(hit => (
                    <button key={`${hit.deptId}-${hit.category}`} onClick={() => onNavigate(hit.deptId)}
                      className="w-full text-left flex items-center gap-2 px-3 py-2 hover:bg-slate-50 transition">
                      <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: hit.accentHex }} />
                      <span className="flex-1 text-xs text-slate-700 truncate">{hit.deptName}</span>
                      <span className={`shrink-0 text-[10px] ${hit.category === 'required' ? 'text-red-400' : 'text-green-500'}`}>
                        {hit.category === 'required' ? '必修' : '選修'}
                      </span>
                    </button>
                  ))}
                  {depts.length > 6 && (
                    <button onClick={() => toggleExpand(key)}
                      className="w-full px-3 py-1.5 text-[10px] text-indigo-500 hover:text-indigo-700 hover:bg-indigo-50 transition text-left flex items-center gap-1">
                      {expandedKeys.has(key)
                        ? <><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 15l7-7 7 7" /></svg>收合</>
                        : <><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" /></svg>還有 {depts.length - 6} 個系所</>
                      }
                    </button>
                  )}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 科系比較 Bar + Modal
// ══════════════════════════════════════════════════════════════════════════

// ── 右下角浮動比較面板（CoursesPage 同款）
function DeptCompareBar({ pool, onRemove, onClear, onOpen }: {
  pool: DeptSummary[]; onRemove: (d: DeptSummary) => void; onClear: () => void; onOpen: () => void;
}) {
  if (pool.length === 0) return null;
  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 rounded-t-2xl border-t border-slate-200 bg-white px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-4 shadow-2xl md:bottom-4 md:left-auto md:right-4 md:w-80 md:rounded-2xl md:border md:pb-4 animate-in slide-in-from-bottom-2 duration-200">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-950">科系比較</div>
          <div className="mt-0.5 text-xs text-slate-500">已選 {pool.length} / 3 個系所</div>
        </div>
        <button type="button" onClick={onClear}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition hover:bg-red-50 hover:text-red-600"
          aria-label="清空比較">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
        </button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {pool.map(dept => (
          <button key={dept.id} type="button" onClick={() => onRemove(dept)}
            className="inline-flex max-w-full items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition hover:opacity-80"
            style={{ borderColor: dept.accentHex + '50', backgroundColor: dept.accentHex + '12', color: dept.accentHex }}>
            <span className="truncate max-w-[100px]">{dept.name}</span>
            <svg className="h-3 w-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <button type="button" onClick={onOpen} disabled={pool.length < 2}
          className="flex-1 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300">
          開始比較
        </button>
      </div>
      {pool.length < 2 && <div className="mt-2 text-xs text-slate-500">至少選 2 個系所才能開始比較。</div>}
    </div>
  );
}

// ── 科系比較 Modal（兩個 Tab）
function DeptCompareModal({ pool, allDetails, onClose, onRemove }: {
  pool: DeptSummary[]; allDetails: Map<string, DeptDetail>; onClose: () => void; onRemove: (d: DeptSummary) => void;
}) {
  const [extraDetails, setExtraDetails] = useState<Map<string, DeptDetail>>(new Map());
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'courses'>('overview');
  const poolKey = pool.map(d => d.id).join(',');

  useEffect(() => {
    const missing = pool.filter(d => !allDetails.has(d.id) && !extraDetails.has(d.id));
    if (missing.length === 0) return;
    setLoading(true);
    Promise.all(missing.map(d => apiClient.get(`/curriculum/dept/${d.id}`)))
      .then(results => {
        setExtraDetails(prev => {
          const next = new Map(prev);
          results.forEach((r, i) => next.set(missing[i].id, r.data));
          return next;
        });
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poolKey]);

  const getDetail = (id: string) => allDetails.get(id) ?? extraDetails.get(id) ?? null;
  const depts = pool.map(d => ({ summary: d, detail: getDetail(d.id) }));
  const allLoaded = !loading && depts.every(d => d.detail !== null);

  // 必修課程：共同 + 各系分列
  const { shared, perDept } = useMemo(() => {
    if (!allLoaded) return { shared: [] as string[], perDept: [] as { summary: DeptSummary; courses: string[] }[] };
    const REQUIRED_KEYS = [
      'required_courses', 'foundation_courses', 'college_required_courses', 'common_required_courses',
      'dept_required_courses', 'required_electives', 'cross_domain_required', 'earth_system_courses',
      'cross_group_required', 'application_courses', 'first_domain_electives',
    ] as const;
    const deptMaps = depts.map(({ detail }) => {
      const m = new Map<string, string>();
      for (const key of REQUIRED_KEYS) {
        for (const c of (detail![key] as CourseEntry[] | undefined) ?? []) {
          const k = normalizeCourse(c.name);
          if (k) m.set(k, c.name);
        }
      }
      return m;
    });
    // 找共同（normalize key 出現 2+ 系）
    const keyCount = new Map<string, number>();
    for (const m of deptMaps) for (const k of m.keys()) keyCount.set(k, (keyCount.get(k) ?? 0) + 1);
    const sharedKeys = new Set([...keyCount.entries()].filter(([, v]) => v >= 2).map(([k]) => k));
    const sharedNames = [...sharedKeys].map(k => deptMaps.find(m => m.has(k))!.get(k)!).sort((a, b) => a.localeCompare(b, 'zh-Hant'));
    // 各系全部課程（含共同）
    const perDeptList = depts.map(({ summary, detail }) => {
      const m = new Map<string, string>();
      for (const key of REQUIRED_KEYS) {
        for (const c of (detail![key] as CourseEntry[] | undefined) ?? []) {
          const k = normalizeCourse(c.name);
          if (k) m.set(k, c.name);
        }
      }
      return { summary, courses: [...m.values()].sort((a, b) => a.localeCompare(b, 'zh-Hant')) };
    });
    return { shared: sharedNames, perDept: perDeptList };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allLoaded, poolKey]);

  const tabs = [
    { id: 'overview' as const, label: '基本資訊與畢業規定' },
    { id: 'courses' as const, label: '必修課程' },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/50 flex items-end sm:items-center justify-center p-0 sm:p-4" onClick={onClose}>
      <div className="w-full sm:max-w-5xl max-h-[92vh] sm:max-h-[90vh] bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="shrink-0 flex items-center justify-between gap-4 px-5 py-4 border-b border-slate-200">
          <div>
            <h2 className="text-lg font-bold text-slate-900">科系比較</h2>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {pool.map(d => (
                <span key={d.id} className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-2 py-0.5"
                  style={{ backgroundColor: d.accentHex + '15', color: d.accentHex }}>
                  {d.name}
                </span>
              ))}
            </div>
          </div>
          <button onClick={onClose} className="h-9 w-9 flex items-center justify-center rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200 transition shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        {/* Tab bar */}
        <div className="shrink-0 flex items-center gap-1 px-5 border-b border-slate-100">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              className={`px-4 py-3 text-sm font-bold border-b-[2.5px] transition-colors duration-150 ${activeTab === t.id ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-slate-400 hover:text-slate-700'}`}>
              {t.label}
            </button>
          ))}
        </div>

        {!allLoaded ? (
          <div className="flex-1 flex items-center justify-center text-slate-400 text-sm animate-pulse">載入中…</div>
        ) : activeTab === 'overview' ? (
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-8">

            {/* 基本資訊 */}
            <section>
              <div className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">基本資訊</div>
              <div className="grid gap-3 sm:gap-4" style={{ gridTemplateColumns: `repeat(${pool.length}, minmax(0, 1fr))` }}>
                {depts.map(({ summary, detail }) => (
                  <div key={summary.id} className="relative rounded-xl border border-slate-200 p-4 overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-1 rounded-t-xl" style={{ backgroundColor: summary.accentHex }} />
                    <button onClick={() => onRemove(summary)} title="從比較移除"
                      className="absolute top-3 right-3 h-6 w-6 flex items-center justify-center rounded-full text-slate-300 hover:bg-slate-100 hover:text-slate-600 transition text-xs">×</button>
                    <div className="flex items-center gap-2 mb-3 mt-1">
                      <div className="w-1 h-4 rounded-full shrink-0" style={{ backgroundColor: summary.accentHex }} />
                      <div className="min-w-0 pr-5">
                        <div className="font-bold text-slate-900 text-sm truncate">{summary.name}</div>
                        <div className="text-[10px] text-slate-400">{summary.collegeName}</div>
                      </div>
                    </div>
                    <div className="space-y-2 text-xs">
                      {[
                        { label: '最低畢業學分', value: `${detail!.min_credits} 學分`, accent: true },
                        { label: '必修學分', value: detail!.required_credits !== undefined ? `${detail!.required_credits} 學分` : '—' },
                        { label: '畢業規定', value: `${detail!.graduation_rules?.length ?? 0} 項` },
                        { label: '分組', value: (detail!.groups?.length ?? 0) > 0 ? `${detail!.groups!.length} 組` : '無' },
                      ].map(({ label, value, accent }) => (
                        <div key={label} className="flex justify-between items-center gap-1">
                          <span className="text-slate-500">{label}</span>
                          <span className="font-bold" style={accent ? { color: summary.accentHex } : { color: '#374151' }}>{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* 畢業規定 */}
            <section>
              <div className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">畢業規定</div>
              <div className="grid gap-3 sm:gap-4" style={{ gridTemplateColumns: `repeat(${pool.length}, minmax(0, 1fr))` }}>
                {depts.map(({ summary, detail }) => (
                  <div key={summary.id} className="rounded-xl border border-slate-200 overflow-hidden">
                    <div className="px-3 py-2 bg-slate-50 border-b border-slate-100 flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: summary.accentHex }} />
                      <span className="text-xs font-bold text-slate-600 truncate flex-1">{summary.name}</span>
                      <span className="text-[10px] text-slate-400 shrink-0">{detail!.graduation_rules?.length ?? 0} 項</span>
                    </div>
                    <div className="overflow-y-auto max-h-64 p-3 space-y-1.5">
                      {(detail!.graduation_rules?.length ?? 0) === 0 ? (
                        <div className="text-xs text-slate-400 text-center py-4">無資料</div>
                      ) : detail!.graduation_rules!.map((rule, i) => (
                        <div key={i} className="flex items-start gap-2">
                          <div className="w-1.5 h-1.5 rounded-full shrink-0 mt-1.5" style={{ backgroundColor: CATEGORY_HEX[rule.category] ?? '#94a3b8' }} />
                          <span className="text-xs text-slate-700 leading-relaxed">{rule.description ?? rule.type ?? ''}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>

          </div>
        ) : (
          /* 必修課程 Tab */
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">

            {/* 共同必修 */}
            {shared.length > 0 && (
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                  <span className="text-xs font-bold text-emerald-700 uppercase tracking-widest">共同必修（{shared.length} 門）</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {shared.map(name => (
                    <span key={name} className="inline-flex items-center text-xs font-semibold rounded-full px-3 py-1 bg-emerald-50 text-emerald-800 border border-emerald-200">
                      {name}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {/* 各系必修條列 */}
            <section>
              <div className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">各系必修課程</div>
              <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${pool.length}, minmax(0, 1fr))` }}>
                {perDept.map(({ summary, courses }) => (
                  <div key={summary.id} className="rounded-xl border border-slate-200 overflow-hidden">
                    <div className="px-3 py-2 bg-slate-50 border-b border-slate-100 flex items-center gap-2 sticky top-0">
                      <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: summary.accentHex }} />
                      <span className="text-xs font-bold text-slate-700 truncate flex-1">{summary.name}</span>
                      <span className="text-[10px] text-slate-400 shrink-0">{courses.length} 門</span>
                    </div>
                    {courses.length === 0 ? (
                      <div className="p-4 text-center text-xs text-slate-400">無資料</div>
                    ) : (
                      <ul className="divide-y divide-slate-50 max-h-80 overflow-y-auto">
                        {courses.map(name => {
                          const isShared = shared.includes(name);
                          return (
                            <li key={name} className={`flex items-center gap-2 px-3 py-2 text-xs ${isShared ? 'bg-emerald-50/40' : ''}`}>
                              {isShared
                                ? <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-emerald-400" />
                                : <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-slate-200" />}
                              <span className={isShared ? 'text-emerald-800 font-semibold' : 'text-slate-700'}>{name}</span>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </section>

          </div>
        )}
      </div>
    </div>
  );
}


function DeptTree({
  detail,
  depth = 0,
  defaultTab,
  showNotes,
  setShowNotes,
  accentHex = '#6366f1',
}: {
  detail: DeptDetail;
  depth?: number;
  defaultTab?: 'required' | 'elective' | 'rules';
  showNotes?: boolean;
  setShowNotes?: React.Dispatch<React.SetStateAction<boolean>>;
  accentHex?: string;
}) {
  // ── 計算各 tab 是否有內容 ──
  const reqSections = REQUIRED_COURSE_FIELDS
    .map(({ key, label }) => ({
      label,
      courses: (detail[key] as CourseEntry[] | undefined) ?? [],
    }))
    .filter(({ courses }) => courses.length > 0);

  const rulesByCategory: Record<string, GraduationRule[]> = {};
  for (const cat of CATEGORIES_ORDER) rulesByCategory[cat] = [];
  for (const rule of detail.graduation_rules ?? []) {
    const cat = rule.category ?? '其他規定';
    if (!rulesByCategory[cat]) rulesByCategory[cat] = [];
    rulesByCategory[cat].push(rule);
  }
  const totalRules = (detail.graduation_rules ?? []).length;

  const hasRequired = reqSections.length > 0;
  const hasElective =
    (detail.elective_courses?.length ?? 0) > 0 ||
    (detail.elective_groups?.length ?? 0) > 0 ||
    (detail.core_elective_groups?.length ?? 0) > 0 ||
    (detail.college_required_elective_groups?.length ?? 0) > 0 ||
    (detail.science_ability_groups?.length ?? 0) > 0 ||
    (detail.other_elective_groups?.length ?? 0) > 0;
  const hasRules = totalRules > 0 || !!detail.graduation_notes;
  const hasGroups = (detail.groups?.length ?? 0) > 0;

  const availableTabs = (
    [hasRequired ? 'required' : null, hasElective ? 'elective' : null, hasRules ? 'rules' : null] as const
  ).filter((t): t is 'required' | 'elective' | 'rules' => t !== null);

  const [activeTab, setActiveTab] = useState<'required' | 'elective' | 'rules'>(
    defaultTab ?? availableTabs[0] ?? 'required'
  );
  const [selectedGroup, setSelectedGroup] = useState<DeptDetail | null>(null);

  const tabLabels = { required: '核心必修', elective: '選修課程', rules: '畢業規定' };

  return (
    <div className="font-sans pb-10 leading-relaxed">

      {/* ── 分組選擇器（有 groups 時顯示）── */}
      {hasGroups && (
        <div className="mb-6 p-4 bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">選擇分組</span>
            {selectedGroup && (
              <button
                onClick={() => setSelectedGroup(null)}
                className="text-xs text-slate-400 hover:text-slate-700 underline underline-offset-2 transition-colors"
              >
                ← 返回共同課程
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {detail.groups!.map((g) => {
              const isActive = selectedGroup?.id === g.id;
              return (
                <button
                  key={g.id}
                  onClick={() => setSelectedGroup(isActive ? null : g)}
                  className={`px-4 py-1.5 rounded-xl border text-sm font-semibold transition-all duration-200 ${
                    isActive
                      ? 'text-white border-transparent shadow-sm'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300 hover:shadow-sm'
                  }`}
                  style={isActive ? { backgroundColor: accentHex, borderColor: accentHex } : {}}
                >
                  {g.name}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── 選擇了分組：直接顯示該組的 DeptTree ── */}
      {selectedGroup ? (
        <div className="animate-in fade-in slide-in-from-bottom-1 duration-200">
          <DeptTree detail={selectedGroup} depth={0} accentHex={accentHex} />
        </div>
      ) : (
        <>
          {/* ── Tabs 標籤列（只顯示有內容的 tab）── */}
          {availableTabs.length > 0 && (
            <div className="flex items-center justify-between border-b border-slate-200/80 mt-2 px-1 mb-6">
              <div className="flex items-center gap-1">
                {availableTabs.map((tab) => {
                  const isActive = activeTab === tab;
                  return (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className="px-5 py-3 text-sm font-extrabold border-b-[3px] transition-colors duration-200 border-transparent text-slate-500 hover:text-slate-800"
                      style={isActive ? { borderBottomColor: accentHex, color: accentHex } : {}}
                    >
                      {tabLabels[tab]}
                    </button>
                  );
                })}
              </div>
              {depth === 0 && showNotes !== undefined && setShowNotes !== undefined && (
                <div className="pb-1.5">
                  <button
                    onClick={() => setShowNotes((v) => !v)}
                    className={`flex items-center gap-1.5 rounded-xl border px-4 py-2 text-xs font-bold transition-all duration-200 shadow-sm ${
                      showNotes
                        ? 'bg-amber-50/50 border-amber-200 text-amber-700 hover:bg-amber-100/70 shadow-amber-100/20'
                        : 'bg-transparent border-slate-200 text-slate-600 hover:bg-slate-50/80 hover:text-amber-600 hover:border-amber-200'
                    }`}
                  >
                    <span>{showNotes ? '▶' : '◀'}</span>
                    {showNotes ? '隱藏參考文字' : '顯示參考文字'}
                  </button>
                </div>
              )}
            </div>
          )}

      {activeTab === 'required' && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
          {/* ── 必修課程（所有欄位彙整）────────────── */}
          {reqSections.length > 0 ? (
            <SectionCard>
              <TreeNode
                label={<span className="text-sm font-bold text-slate-800">必修課程</span>}
                depth={depth}
                defaultOpen={true}
              >
                <div className="space-y-4 mt-2">
                  {reqSections.length === 1 ? (
                    <SemesterGroup courses={reqSections[0].courses} depth={depth + 1} accentHex={accentHex} />
                  ) : (
                    reqSections.map(({ label, courses }) => (
                      <div key={label} style={{ marginLeft: (depth + 1) * INDENT }}>
                        <div className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
                          <span className="w-1 h-4 rounded-full inline-block" style={{ backgroundColor: accentHex }} />
                          <span>{label}</span>
                        </div>
                        <SemesterGroup courses={courses} depth={depth + 2} accentHex={accentHex} />
                      </div>
                    ))
                  )}
                </div>
              </TreeNode>
            </SectionCard>
          ) : (
            <div className="text-center py-10 text-slate-400 text-sm font-medium">尚無必修課程資料</div>
          )}
        </div>
      )}

      {activeTab === 'elective' && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300 space-y-6">
          {/* ── 核心必選群 ───────────────────────────── */}
          {detail.core_elective_groups && detail.core_elective_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-sm font-bold text-slate-800">核心必選群</span>}
                badge={detail.core_elective_groups.length}
                badgeColor="bg-slate-100 text-slate-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  {detail.core_elective_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} accentHex={accentHex} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 院訂必選群 ───────────────────────────── */}
          {detail.college_required_elective_groups && detail.college_required_elective_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-sm font-bold text-slate-800">院訂必選群</span>}
                badge={detail.college_required_elective_groups.length}
                badgeColor="bg-slate-100 text-slate-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  {detail.college_required_elective_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} accentHex={accentHex} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 科學能力群 ───────────────────────────── */}
          {detail.science_ability_groups && detail.science_ability_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-sm font-bold text-slate-800">科學能力必選</span>}
                badge={detail.science_ability_groups.length}
                badgeColor="bg-slate-100 text-slate-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  {detail.science_ability_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} accentHex={accentHex} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 選修群 ───────────────────────────────── */}
          {detail.elective_groups && detail.elective_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-sm font-bold text-slate-800">選修群</span>}
                badge={detail.elective_groups.length}
                badgeColor="bg-slate-100 text-slate-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  {detail.elective_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} accentHex={accentHex} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 領域選修課程 ── */}
          {detail.elective_courses && detail.elective_courses.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-sm font-bold text-slate-800">領域選修課程</span>}
                badge={`${detail.elective_courses.length}門可選`}
                badgeColor="bg-slate-100 text-slate-600"
                depth={depth}
                defaultOpen={true}
              >
                <div className="mt-4 space-y-2">
                  <SemesterGroup courses={detail.elective_courses} depth={depth + 1} hideSemesters accentHex={accentHex} />
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {/* ── 其他選修群 ───────────────────────────── */}
          {detail.other_elective_groups && detail.other_elective_groups.length > 0 && (
            <SectionCard>
              <TreeNode
                label={<span className="text-sm font-bold text-slate-800">其他選修群</span>}
                badge={detail.other_elective_groups.length}
                badgeColor="bg-slate-50 text-slate-500"
                depth={depth}
                defaultOpen={false}
              >
                <div className="mt-4 space-y-2">
                  {detail.other_elective_groups.map((g, i) => (
                    <ElectiveGroupTree key={i} g={g} depth={depth + 1} accentHex={accentHex} />
                  ))}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {(!detail.core_elective_groups?.length && !detail.elective_groups?.length && !detail.elective_courses?.length && !detail.other_elective_groups?.length) && (
            <div className="text-center py-10 text-slate-400 text-sm font-medium">尚無選修分組資料</div>
          )}
        </div>
      )}

      {activeTab === 'rules' && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300 space-y-6">
          {/* ── 畢業規定 ─────────────────────────────── */}
          {totalRules > 0 && (
            <SectionCard>
              <div className="flex items-center gap-3 mb-6">
                <span className="text-sm font-bold text-slate-800">畢業規定</span>
                <span className="text-xs text-slate-400 font-medium">{totalRules} 項規定</span>
              </div>
              <div className="space-y-6">
                {CATEGORIES_ORDER.map((cat) => {
                  const rules = rulesByCategory[cat];
                  if (!rules || rules.length === 0) return null;
                  const hex = CATEGORY_HEX[cat] ?? '#94a3b8';
                  return (
                    <div key={cat}>
                      <div className="flex items-center gap-2.5 mb-2.5">
                        <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: hex }} />
                        <span className="text-sm font-bold text-slate-800">{cat}</span>
                        <div className="flex-1 h-px bg-slate-100" />
                        <span className="text-xs text-slate-400">{rules.length} 項</span>
                      </div>
                      <div className="pl-4 space-y-0.5" style={{ borderLeft: `2px solid ${hex}30` }}>
                        {rules.map((r, i) => (
                          <RuleTree key={`${r.type}-${i}`} rule={r} depth={0} dotHex={hex} />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          )}

          {/* ── 畢業備註 ────────────────────────────── */}
          {detail.graduation_notes && (
            <SectionCard>
              <TreeNode label={<span className="text-sm font-bold text-slate-800">畢業說明</span>} depth={depth} defaultOpen={false}>
                <div
                  className="mt-4 mx-2 rounded-xl bg-amber-50/50 border border-amber-100 p-5 text-sm leading-relaxed text-slate-700 shadow-sm"
                  style={{ marginLeft: (depth + 1) * INDENT }}
                >
                  {detail.graduation_notes}
                </div>
              </TreeNode>
            </SectionCard>
          )}

          {(!totalRules && !detail.graduation_notes) && (
            <div className="text-center py-10 text-slate-400 text-sm font-medium">尚無畢業規定資料</div>
          )}
        </div>
      )}
      </>
    )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 系所 Header
// ══════════════════════════════════════════════════════════════════════════

function DeptHeader({ detail, accentHex = '#6366f1', onBack }: { detail: DeptDetail; accentHex?: string; onBack?: () => void }) {
  return (
    <div className="sticky top-0 z-20 border-b border-slate-200/60 bg-white/90 backdrop-blur-xl px-4 md:px-8 py-3 shadow-sm">
      {/* 單排：← 標題區 (手機可點整列返回) | 學分標籤 | PDF */}
      <div className="flex items-center gap-2 min-w-0">
        {/* 手機：整個左區塊可點返回；桌面：純展示 */}
        {onBack ? (
          <button
            onClick={onBack}
            className="md:hidden flex items-center gap-2 flex-1 min-w-0 text-left"
            aria-label="返回系所列表"
          >
            <svg className="w-4 h-4 shrink-0 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
            </svg>
            <div className="w-1 h-5 rounded-full shrink-0" style={{ backgroundColor: accentHex }} />
            <span className="min-w-0 text-base font-extrabold tracking-tight text-slate-900 truncate">
              {detail.name}
            </span>
            {detail.min_credits > 0 && (
              <span className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold text-slate-700 border"
                style={{ backgroundColor: accentHex + '12', borderColor: accentHex + '35' }}>
                最低 {detail.min_credits} 學分
              </span>
            )}
            {detail.required_credits !== undefined && (
              <span className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold text-slate-700 border"
                style={{ backgroundColor: accentHex + '18', borderColor: accentHex + '40' }}>
                必修 {detail.required_credits} 學分
              </span>
            )}
          </button>
        ) : null}
        <div className={`${onBack ? 'hidden md:flex' : 'flex'} items-center gap-2 flex-1 min-w-0`}>
          <div className="w-1 h-5 rounded-full shrink-0" style={{ backgroundColor: accentHex }} />
          <h2 className="min-w-0 text-xl font-extrabold tracking-tight text-slate-900 truncate">
            {detail.name}
          </h2>
          {detail.min_credits > 0 && (
            <span className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold text-slate-700 border"
              style={{ backgroundColor: accentHex + '12', borderColor: accentHex + '35' }}>
              最低 {detail.min_credits} 學分
            </span>
          )}
          {detail.required_credits !== undefined && (
            <span className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold text-slate-700 border"
              style={{ backgroundColor: accentHex + '18', borderColor: accentHex + '40' }}>
              必修 {detail.required_credits} 學分
            </span>
          )}
        </div>
        <button
          onClick={() => {
            const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
            window.open(`${baseUrl}/curriculum/pdf/${detail.id}`, '_blank');
          }}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-white border border-slate-200 h-7 w-7 md:w-auto md:px-3 justify-center text-xs font-semibold text-slate-600 shadow-sm hover:bg-slate-50 transition-colors"
          title="下載原始應修科目表"
        >
          <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          <span className="hidden md:inline">下載原始應修科目表</span>
        </button>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 參考文字面板
// ══════════════════════════════════════════════════════════════════════════

function NotesPanel({ deptId, hideHeader = false }: { deptId: string; hideHeader?: boolean }) {
  const [entries, setEntries] = useState<NotesEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!deptId) return;
    void (async () => { await Promise.resolve(); setLoading(true); })();
    apiClient
      .get(`/curriculum/notes/by-id/${deptId}`)
      .then((res) => setEntries(res.data.entries ?? []))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [deptId]);

  if (loading) return <div className="p-5 text-xs text-slate-400">載入參考資料…</div>;
  if (entries.length === 0)
    return <div className="p-5 text-xs text-slate-400 font-medium">（無對應的原始規定文字）</div>;

  return (
    <div className="space-y-4 p-5">
      {!hideHeader && (
        <div className="flex items-center gap-2 mb-2">
          <div className="text-[12px] font-bold uppercase tracking-widest text-amber-800/70">
            原始規定參考文字
          </div>
        </div>
      )}
      {entries.map((e) => (
        <div key={e.key} className="rounded-xl bg-white/95 backdrop-blur-sm p-5 shadow-soft transition-all duration-300">
          {entries.length > 1 && (
            <div className="mb-2 text-[12px] font-bold text-amber-700 border-b border-amber-200/50 pb-1">{e.key}</div>
          )}
          <div className="text-[12px] leading-relaxed text-slate-700" style={{ whiteSpace: 'pre-wrap' }}>
            {e.raw_text}
          </div>
          {e.source && e.source !== 'pdfplumber_fixed' && (
            <div className="mt-3 text-[10px] font-medium text-amber-500/80 flex justify-end">來源：{e.source}</div>
          )}
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// 學院風格定義
// ══════════════════════════════════════════════════════════════════════════

type CollegeStyle = { iconBg: string; badge: string; hex: string; icon: React.ReactNode };
const COLLEGE_STYLES: Record<string, CollegeStyle> = {
  '文學院': {
    iconBg: 'bg-violet-500',
    badge: 'bg-violet-50 text-violet-600 border-violet-100/50',
    hex: '#8b5cf6',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
  },
  '理學院': {
    iconBg: 'bg-sky-500',
    badge: 'bg-sky-50 text-sky-600 border-sky-100/50',
    hex: '#0ea5e9',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M9.75 3h4.5m-4.5 0v3.75L4.5 16.5a2.25 2.25 0 002.25 2.25h10.5a2.25 2.25 0 002.25-2.25L14.25 6.75V3m-4.5 0h4.5" /></svg>
  },
  '工學院': {
    iconBg: 'bg-orange-500',
    badge: 'bg-orange-50 text-orange-600 border-orange-100/50',
    hex: '#f97316',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><circle cx="12" cy="12" r="3" strokeWidth={2.2} /></svg>
  },
  '管理學院': {
    iconBg: 'bg-emerald-500',
    badge: 'bg-emerald-50 text-emerald-600 border-emerald-100/50',
    hex: '#10b981',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
  },
  '資訊電機學院': {
    iconBg: 'bg-indigo-500',
    badge: 'bg-indigo-50 text-indigo-600 border-indigo-100/50',
    hex: '#6366f1',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 5h10a2 2 0 012 2v10a2 2 0 01-2 2H7a2 2 0 01-2-2V7a2 2 0 012-2zM9 9h6v6H9V9z" /></svg>
  },
  '地球科學學院': {
    iconBg: 'bg-teal-600',
    badge: 'bg-teal-50 text-teal-600 border-teal-100/50',
    hex: '#0d9488',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
  },
  '客家學院': {
    iconBg: 'bg-pink-500',
    badge: 'bg-pink-50 text-pink-600 border-pink-100/50',
    hex: '#ec4899',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
  },
  '生醫理工學院': {
    iconBg: 'bg-rose-500',
    badge: 'bg-rose-50 text-rose-600 border-rose-100/50',
    hex: '#f43f5e',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M6 2c0 6 12 14 12 20 M18 2c0 6-12 14-12 20 M7 3.5h10 M8 6h8 M9 8.5h6 M11 10.5h2 M11 13.5h2 M9 15.5h6 M8 18h8 M7 20.5h10" /></svg>
  },
  'default': {
    iconBg: 'bg-slate-500',
    badge: 'bg-slate-50 text-slate-600 border-slate-100/50',
    hex: '#64748b',
    icon: <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
  }
};

const collegeHexOf = (collegeName: string) => (COLLEGE_STYLES[collegeName] || COLLEGE_STYLES['default']).hex;

// ══════════════════════════════════════════════════════════════════════════
// 主頁面
// ══════════════════════════════════════════════════════════════════════════

export default function CurriculumPage() {
  const {
    tree, childDeptIds,
    expandedColleges, toggleCollege,
    selectedId, detail,
    loadingTree, loadingDetail,
    isMobileMenuOpen, setIsMobileMenuOpen,
    selectedCollegeHex,
    sidebarMode, setSidebarMode,
    allDeptDetails, courseIndex, indexReady,
    comparePool, setComparePool, toggleCompare,
    navigateTo, selectDept,
  } = useCurriculumData(collegeHexOf);
  const [showNotes, setShowNotes] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [selectedCourse, setSelectedCourse] = useState<CourseCard | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);
  const [crossSearchCourse, setCrossSearchCourse] = useState<CourseEntry | null>(null);

  useEffect(() => {
    const handleShowCourse = (e: Event) => {
      setSelectedCourse((e as CustomEvent<CourseCard>).detail);
    };
    window.addEventListener('SHOW_COURSE_DETAIL', handleShowCourse);
    return () => window.removeEventListener('SHOW_COURSE_DETAIL', handleShowCourse);
  }, []);


  function DeptCard({
    dept,
    collegeHex,
    collegeName,
  }: {
    dept: { id: string; name: string; program_type?: string; min_credits: number; groups: { id: string; name: string }[] };
    collegeHex: string;
    collegeName: string;
  }) {
    const hasGroups = dept.groups.length > 0;
    const isDeptSelected = selectedId === dept.id;
    const isChildSelected = hasGroups && dept.groups.some(g => g.id === selectedId);
    const isActive = isDeptSelected || isChildSelected;
    const isExpanded = isActive;
    const isCompared = comparePool.some(d => d.id === dept.id);
    const poolFull = comparePool.length >= 3 && !isCompared;
    const deptSummary: DeptSummary = { id: dept.id, name: dept.name, collegeName, accentHex: collegeHex, min_credits: dept.min_credits };

    return (
      <div
        className="w-full bg-white rounded-lg border text-left transition-all duration-200 overflow-hidden group/card"
        style={{
          borderColor: isActive ? collegeHex + '50' : '#e2e8f0',
          borderLeftWidth: '3px',
          borderLeftColor: isActive ? collegeHex : 'transparent',
          boxShadow: isActive ? `0 2px 8px ${collegeHex}15` : '0 1px 3px rgba(0,0,0,0.04)',
        }}
      >
        {/* 卡片主體 */}
        <div className="w-full flex items-center py-2 px-3 gap-1">
          <div
            onClick={() => selectDept(dept.id)}
            className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer select-none py-0.5"
          >
            <span
              className="text-sm leading-tight transition-colors truncate font-medium"
              style={isActive ? { color: collegeHex, fontWeight: 700 } : { color: '#475569' }}
            >
              {dept.name}
            </span>
            {hasGroups && !isActive && (
              <span className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold leading-none bg-slate-100 text-slate-500">
                {dept.groups.length} 組
              </span>
            )}
          </div>
          {/* 加入比較按鈕 */}
          <button
            onClick={e => { e.stopPropagation(); if (!poolFull) toggleCompare(deptSummary); }}
            disabled={poolFull}
            title={isCompared ? '從比較移除' : poolFull ? '最多比較 3 個系所' : '加入比較'}
            className={`shrink-0 h-6 w-6 flex items-center justify-center rounded-full border text-xs font-bold transition-all duration-200
              opacity-0 group-hover/card:opacity-100 focus:opacity-100
              ${isCompared ? 'bg-indigo-600 border-indigo-600 text-white' : poolFull ? 'border-slate-200 text-slate-300 cursor-not-allowed' : 'border-slate-200 text-slate-400 hover:border-indigo-400 hover:text-indigo-600 hover:bg-indigo-50'}`}
          >
            {isCompared ? '✓' : '+'}
          </button>
          <div onClick={() => selectDept(dept.id)} className="cursor-pointer select-none shrink-0">
            <svg
              className="w-3 h-3 text-slate-300 transition-all duration-200"
              style={isActive ? { color: collegeHex, opacity: 0.7 } : {}}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </div>

        {/* 展開的子分組區域 */}
        {hasGroups && isExpanded && (
          <div className="px-3 pb-3 pt-1 border-t animate-in fade-in slide-in-from-top-1 duration-200" style={{ borderTopColor: collegeHex + '20' }}>
            <div className="relative pl-4 mt-2 space-y-2.5">
              {/* 垂直樹狀引導線（學院顏色） */}
              <div className="absolute left-[3px] top-1 bottom-3 w-[1.5px] rounded-full" style={{ backgroundColor: collegeHex + '40' }} />

              {dept.groups.map((g) => {
                const isSelected = selectedId === g.id;
                return (
                  <div
                    key={g.id}
                    onClick={(e) => { e.stopPropagation(); selectDept(g.id); }}
                    className="relative flex items-center group/item cursor-pointer"
                  >
                    <div className="absolute left-[-10px] top-[50%] w-[8px] h-[1.5px]" style={{ backgroundColor: collegeHex + '40' }} />
                    <div
                      className="absolute left-[-4px] w-1.5 h-1.5 rounded-full transition-all duration-200"
                      style={isSelected
                        ? { backgroundColor: collegeHex, boxShadow: `0 0 5px ${collegeHex}80` }
                        : { backgroundColor: '#cbd5e1' }
                      }
                    />
                    <span
                      className="text-sm pl-1.5 transition-all duration-150"
                      style={isSelected
                        ? { color: collegeHex, fontWeight: 700 }
                        : { color: '#475569' }
                      }
                    >
                      {g.name}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  }

  const ctxValue: CurriculumContextValue = {
    courseIndex, indexReady, currentDeptId: detail?.id ?? '',
    comparePool, toggleCompare, navigateTo,
    openCrossSearch: setCrossSearchCourse,
  };

  return (
    <CurriculumCtx.Provider value={ctxValue}>
    <div className="flex h-full overflow-hidden bg-slate-50 font-sans leading-7 text-slate-900 relative">

      {/* 側邊欄縮放把手（桌面限定） */}
      <button
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className={`absolute z-30 top-24 transition-all duration-300 hidden md:flex items-center justify-center w-5 h-20 bg-slate-50/95 backdrop-blur-md border-y border-r border-slate-300 rounded-r-xl shadow-[4px_0_12px_-2px_rgba(0,0,0,0.1)] hover:bg-teal-50 hover:border-teal-400 hover:text-teal-600 text-slate-500 ${isSidebarOpen ? 'left-[340px]' : 'left-0'}`}
      >
        <svg className={`w-4 h-4 transition-transform duration-300 ${isSidebarOpen ? '' : 'rotate-180'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" /></svg>
      </button>

      {/* ── 左側 Sidebar ── */}
      <div className={`shrink-0 transition-all duration-300 bg-white relative z-20 ${isMobileMenuOpen ? 'flex w-full' : 'hidden'} md:flex ${isSidebarOpen ? 'md:w-[340px]' : 'md:w-0'}`}>
        <aside className={`w-full md:w-[340px] h-full flex flex-col border-r border-slate-200/60 overflow-hidden ${isSidebarOpen ? 'md:opacity-100' : 'md:opacity-0 md:pointer-events-none'} transition-opacity duration-300`}>
          <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-4 pt-3 pb-2 shadow-sm">
            <div className="flex items-center justify-between mb-2.5">
              <h2 className="text-sm font-bold tracking-wide text-slate-900">修課規定</h2>
              {selectedId && sidebarMode === 'dept' && (
                <button
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="md:hidden shrink-0 inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100 transition"
                  aria-label="回到課程內容"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              )}
            </div>
            {/* 模式切換 */}
            <div className="flex gap-1 p-1 bg-slate-100 rounded-xl">
              {(['dept', 'search'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setSidebarMode(mode)}
                  className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all duration-200 flex items-center justify-center gap-1.5 ${sidebarMode === mode ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}
                >
                  {mode === 'dept' ? '科系導覽' : (
                    <>
                      課程搜尋
                      {!indexReady && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shrink-0" />}
                    </>
                  )}
                </button>
              ))}
            </div>
          </div>

          {sidebarMode === 'search' ? (
            <GlobalCourseSearch onNavigate={navigateTo} />
          ) : (
          <div className="flex-1 bg-slate-50 p-3 overflow-y-auto min-h-0">
            {loadingTree && <div className="py-6 text-center text-xs text-slate-400">載入中…</div>}
            {tree.map((college) => {
              const isOpen = expandedColleges.has(college.id);
              const style = COLLEGE_STYLES[college.name] || COLLEGE_STYLES['default'];

              const depts = [
                ...college.departments.map(d => ({
                  id: d.id, name: d.name, program_type: d.program_type, min_credits: d.min_credits,
                  groups: (d.groups || []).map(g => ({ id: g.id, name: g.group_label || g.name }))
                })),
                ...college.college_bachelor_programs.map(c => ({
                  id: c.id, name: c.name, program_type: c.program_type || 'bachelor_program', min_credits: c.min_credits,
                  groups: (c.specialization_tracks || []).map(t => ({ id: t.id, name: t.name }))
                }))
              ].sort((a, b) => {
                const ka = deptSortKey(a.name), kb = deptSortKey(b.name);
                if (ka !== kb) return ka - kb;
                return a.name.localeCompare(b.name, 'zh-Hant');
              });

              const deptCount = depts.length;

              return (
                <div key={college.id} className="relative mb-2">
                  {/* 學院卡片 */}
                  <div
                    onClick={() => toggleCollege(college.id)}
                    className={`group flex w-full items-center gap-3 rounded-xl border bg-white px-3 py-3 text-left shadow-sm transition duration-200 cursor-pointer select-none hover:-translate-y-0.5 hover:shadow-md ${
                      isOpen ? 'border-slate-300 shadow-md' : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${style.iconBg} shadow-sm shadow-slate-200 transition duration-200 group-hover:scale-105 text-white [&>svg]:w-5 [&>svg]:h-5`}>
                      {style.icon}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-slate-950">{college.name}</div>
                      <div className="mt-0.5 flex items-center gap-2">
                        {deptCount > 0 && (
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style.badge}`}>
                            {deptCount} 系所
                          </span>
                        )}
                      </div>
                    </div>
                    <svg
                      className={`w-5 h-5 shrink-0 transition-all duration-300 ${isOpen ? 'rotate-90 text-slate-500' : 'text-slate-300 group-hover:translate-x-0.5 group-hover:text-slate-500'}`}
                      fill="none" stroke="currentColor" viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  {isOpen && depts.length > 0 && (
                    <div
                      className="relative mt-1 pl-3 space-y-1 animate-in fade-in slide-in-from-top-1 duration-150"
                      style={{ borderLeft: `2px solid ${style.hex}25`, marginLeft: '4px' }}
                    >
                      {depts.map((dept) => (
                        <DeptCard key={dept.id} dept={dept} collegeHex={style.hex} collegeName={college.name} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          )}
        </aside>
      </div>

      {/* ── 主內容 ── */}
      <div className={`${isMobileMenuOpen ? 'hidden md:flex' : 'flex'} flex-1 flex-col min-h-0 overflow-hidden`}>
        {!selectedId ? (
          <div className="flex flex-1 items-center justify-center text-slate-400">
            <div className="text-center animate-pulse">
              <p className="text-base font-semibold tracking-wide">請從左側選擇系所</p>
            </div>
          </div>
        ) : loadingDetail ? (
          <div className="flex flex-1 items-center justify-center text-slate-400 text-sm font-medium">載入中…</div>
        ) : detail ? (
          <div className="flex flex-1 flex-col overflow-hidden min-h-0 bg-slate-50">
            <DeptHeader detail={detail} accentHex={selectedCollegeHex} onBack={() => setIsMobileMenuOpen(true)} />
            {/* content 區加 relative 讓 notes overlay 從這裡往下覆蓋 */}
            <div className="relative flex-1 overflow-hidden">
              <div className="h-full overflow-y-auto px-4 md:px-8 pt-5 pb-12">
                <div className="max-w-4xl mx-auto">
                  <DeptTree
                    key={detail.id}
                    detail={detail}
                    depth={0}
                    defaultTab={childDeptIds.has(detail.id) ? 'elective' : undefined}
                    showNotes={showNotes}
                    setShowNotes={setShowNotes}
                    accentHex={selectedCollegeHex}
                  />
                </div>
              </div>
              {/* Notes overlay：absolute 在 DeptHeader 下方，不蓋住標題列 */}
              {showNotes && (
                <div className="absolute inset-0 z-30 flex flex-col animate-in fade-in duration-150">
                  <div className="absolute inset-0 bg-black/25 backdrop-blur-sm" onClick={() => setShowNotes(false)} />
                  <div className="relative z-10 flex flex-col h-full bg-gradient-to-br from-amber-50 to-orange-50/95 md:m-6 md:rounded-2xl overflow-hidden shadow-2xl">
                    <div className="flex items-center justify-between px-5 py-3 border-b border-amber-200/60 bg-amber-50/95 backdrop-blur shrink-0">
                      <span className="text-sm font-bold text-amber-900/80 tracking-wide">原始規定參考文字</span>
                      <button
                        onClick={() => setShowNotes(false)}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-full text-amber-700 hover:bg-amber-200/60 transition"
                        aria-label="關閉"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                    <div className="flex-1 overflow-y-auto">
                      <NotesPanel deptId={detail.id} hideHeader />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>

      {selectedCourse && (
        <CourseDetailModal
          course={selectedCourse}
          onClose={() => setSelectedCourse(null)}
        />
      )}

      {/* ── 跨系查找浮層 ── */}
      {crossSearchCourse && (
        <CrossDeptPopover
          course={crossSearchCourse}
          onClose={() => setCrossSearchCourse(null)}
        />
      )}

      {/* ── 比較 Bar ── */}
      <DeptCompareBar
        pool={comparePool}
        onRemove={d => setComparePool(prev => prev.filter(x => x.id !== d.id))}
        onClear={() => setComparePool([])}
        onOpen={() => setCompareOpen(true)}
      />

      {/* ── 比較 Modal ── */}
      {compareOpen && (
        <DeptCompareModal
          pool={comparePool}
          allDetails={allDeptDetails}
          onClose={() => setCompareOpen(false)}
          onRemove={d => setComparePool(prev => prev.filter(x => x.id !== d.id))}
        />
      )}
    </div>
    </CurriculumCtx.Provider>
  );
}
