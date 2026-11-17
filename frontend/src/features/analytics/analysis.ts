/**
 * 個人分析（學習傾向）的計算邏輯：學院 → 學術領域、領域分佈、使用比例與探索型態判斷。
 * 純函式，不依賴 React，方便用 node --test 測試；內容逐字搬自舊版 AnalyticsPage，新舊版共用。
 */
import type { AnalyticsData, AnalyticsDistItem, PdfAnalyticsData } from '../../api/services';

// ── 學院 → 學術領域對照 ─────────────────────────────────────────
export const COLLEGE_TO_DOMAIN: Record<string, string> = {
  '理學院':                   '理工',
  '工學院':                   '理工',
  '地球科學學院':             '地科',
  '永續與綠能科技研究學院':   '理工',
  '資訊電機學院':             '資訊',
  '生醫理工學院':             '生醫',
  '文學院':                   '人文',
  '客家學院':                 '人文',
  '管理學院':                 '商管',
  '中心、處室':               '通識',
};
export const DOMAIN_ORDER = ['理工', '資訊', '地科', '生醫', '人文', '商管'];
export const DOMAIN_COLORS: Record<string, string> = {
  理工: '#6366f1', 資訊: '#0ea5e9', 地科: '#a16207',
  生醫: '#10b981', 人文: '#f59e0b', 商管: '#ef4444',
};

export interface DomainAxis {
  label: string;
  /** 相對最大領域的比例（0–100），雷達圖用 */
  value: number;
  /** 佔六個領域合計的百分比（小數一位） */
  pct: number;
}

/** 單一系統（課程助理或研究計畫）的學院分佈 → 六個學術領域 */
export function collegeDomainAxes(collegeDistribution: AnalyticsDistItem[] | undefined): DomainAxis[] {
  if (!collegeDistribution?.length) return [];
  const totals: Record<string, number> = {};
  for (const item of collegeDistribution) {
    const d = COLLEGE_TO_DOMAIN[item.name] ?? '其他';
    totals[d] = (totals[d] ?? 0) + item.count;
  }
  const nonGeTotal = DOMAIN_ORDER.reduce((s, d) => s + (totals[d] ?? 0), 0) || 1;
  const maxVal = Math.max(...DOMAIN_ORDER.map(d => totals[d] ?? 0)) || 1;
  return DOMAIN_ORDER.map(d => {
    const raw = totals[d] ?? 0;
    const pct = Math.round((raw / nonGeTotal) * 1000) / 10;
    const rel = Math.round((raw / maxVal) * 100);
    return { label: d, value: rel, pct };
  });
}

/** 兩個系統的使用量：課程助理提問輪數、研究計畫提問數與各自比例 */
export function interactionShare(courseData: AnalyticsData | null, projectData: PdfAnalyticsData | null) {
  const courseInteractions = courseData?.overview.total_turns ?? 0;
  const researchInteractions = projectData?.overview.total_questions ?? 0;
  const totalInteractions = courseInteractions + researchInteractions;
  const coursePct = totalInteractions > 0 ? Math.round((courseInteractions / totalInteractions) * 100) : 0;
  const researchPct = 100 - coursePct;
  return { courseInteractions, researchInteractions, totalInteractions, coursePct, researchPct };
}

export type RadarMode = 'weighted' | 'equal';

/** 綜合兩個系統的學術領域分佈；weighted 依互動量加權，equal 兩邊各 50% */
export function combinedDomainAxes(
  courseData: AnalyticsData | null,
  projectData: PdfAnalyticsData | null,
  radarMode: RadarMode,
  courseInteractions: number,
  totalInteractions: number,
): DomainAxis[] {
  const courseCols = courseData?.college_distribution ?? [];
  const projCols = projectData?.college_distribution ?? [];
  if (!courseCols.length && !projCols.length) return [];

  const courseTotal = courseCols.reduce((s, i) => s + i.count, 0) || 1;
  const projTotal = projCols.reduce((s, i) => s + i.count, 0) || 1;

  const courseW = radarMode === 'weighted'
    ? (totalInteractions > 0 ? courseInteractions / totalInteractions : 0.5)
    : 0.5;
  const projW = 1 - courseW;

  const blended: Record<string, number> = {};
  for (const item of courseCols) {
    const d = COLLEGE_TO_DOMAIN[item.name];
    if (!d) continue;
    blended[d] = (blended[d] ?? 0) + (item.count / courseTotal) * courseW;
  }
  for (const item of projCols) {
    const d = COLLEGE_TO_DOMAIN[item.name];
    if (!d) continue;
    blended[d] = (blended[d] ?? 0) + (item.count / projTotal) * projW;
  }

  const total = DOMAIN_ORDER.reduce((s, d) => s + (blended[d] ?? 0), 0) || 1;
  const maxVal = Math.max(...DOMAIN_ORDER.map(d => blended[d] ?? 0)) || 1;
  return DOMAIN_ORDER.map(d => ({
    label: d,
    value: Math.round((blended[d] ?? 0) / maxVal * 100),
    pct: Math.round((blended[d] ?? 0) / total * 1000) / 10,
  }));
}

/** 課程助理與研究計畫合計探索過的學院數 */
export function uniqueCollegeCount(courseData: AnalyticsData | null, projectData: PdfAnalyticsData | null): number {
  return new Set([
    ...(courseData?.college_distribution.map(i => i.name) ?? []),
    ...(projectData?.college_distribution.map(i => i.name) ?? []),
  ]).size;
}

// ── 課程助理的探索型態 ───────────────────────────────────────────
export type CourseTypeId = 'planning' | 'cross' | 'deep' | 'wide' | 'balanced';

export const COURSE_TYPE_TEXT: Record<CourseTypeId, { label: string; desc: string }> = {
  planning: { label: '規劃導向型', desc: '你常查詢學程規定與畢業門檻，展現清晰的修課規劃意識。' },
  cross:    { label: '跨域探索型', desc: '你的興趣橫跨三個以上學術領域，善於尋找跨領域的知識連結。' },
  deep:     { label: '專注深挖型', desc: '你深度探索特定領域的課程，方向清晰、目標明確。' },
  wide:     { label: '廣泛探索型', desc: '你對多元課程保持開放，探索範圍廣泛，善於發掘新可能。' },
  balanced: { label: '均衡探索型', desc: '你的探索模式均衡，兼顧深度與廣度，靈活應對各類需求。' },
};

/** 佔比 ≥ 15% 的領域數（課程助理的「跨域廣度」） */
export function activeDomainCount(domainAxes: { label: string; value: number }[]): number {
  return domainAxes.filter(a => ((a as { pct?: number }).pct ?? a.value) >= 15).length;
}

export function diagnoseCourseType(
  data: AnalyticsData,
  domainAxes: { label: string; value: number }[],
): CourseTypeId {
  if (data.overview.total_turns < 3) return 'balanced';

  const topDeptPct = data.dept_distribution[0]?.pct ?? 0;
  const deptCount  = data.dept_distribution.length;
  const planningTools = ['get_graduation_requirements', 'get_graduation_rules',
    'get_program_info', 'get_program_courses', 'get_requirements_notes'];
  const totalToolCalls = data.tool_usage.reduce((s, t) => s + t.count, 0) || 1;
  const planningCount  = data.tool_usage
    .filter(t => planningTools.includes(t.tool))
    .reduce((s, t) => s + t.count, 0);
  const planningRatio  = planningCount / totalToolCalls;
  const domainsActive  = activeDomainCount(domainAxes);

  if (planningRatio >= 0.25)              return 'planning';
  if (domainsActive >= 3)                 return 'cross';
  if (topDeptPct > 55 && deptCount <= 4)  return 'deep';
  if (deptCount >= 6 && topDeptPct < 30)  return 'wide';
  return 'balanced';
}

// ── 綜合（課程＋研究）探索型態 ───────────────────────────────────
export type CombinedTypeId = 'researcher' | 'planner' | 'course_explorer' | 'integrator' | 'explorer' | 'balanced';

export const COMBINED_TYPE_LABELS: Record<CombinedTypeId, string> = {
  researcher: '學術研究導向',
  planner: '課程規劃導向',
  course_explorer: '課程探索導向',
  integrator: '跨域整合型',
  explorer: '廣泛探索型',
  balanced: '均衡發展型',
};

export function diagnoseCombinedType(
  courseData: AnalyticsData | null,
  projectData: PdfAnalyticsData | null,
  coursePct: number,
  combinedAxes: { label: string; pct: number }[],
): { id: CombinedTypeId; desc: string } {
  const researchPct = 100 - coursePct;
  const avgDepth = projectData?.overview.avg_depth ?? 0;
  const uniqueColleges = uniqueCollegeCount(courseData, projectData);
  const domainsActive = combinedAxes.filter(a => a.pct >= 12).length;
  const planningTools = ['get_graduation_requirements','get_graduation_rules','get_program_info','get_program_courses','get_requirements_notes'];
  const totalToolCalls = courseData?.tool_usage.reduce((s, t) => s + t.count, 0) || 1;
  const planningCount  = (courseData?.tool_usage ?? [])
    .filter(t => planningTools.includes(t.tool))
    .reduce((s, t) => s + t.count, 0);
  const hasPlanningFocus = planningCount / totalToolCalls >= 0.25;

  if (researchPct > 60 && avgDepth >= 2) {
    return {
      id: 'researcher',
      desc: `你投入大量時間深入研讀研究計畫（佔 ${researchPct}% 互動量），平均每次對話提問 ${avgDepth} 輪，對學術研究有高度興趣。`,
    };
  }
  if (coursePct > 60 && hasPlanningFocus) {
    return {
      id: 'planner',
      desc: `你主要透過課程助理（佔 ${coursePct}%）規劃修課路徑，常查詢學分規定與畢業門檻，目標導向清晰。`,
    };
  }
  if (coursePct > 60) {
    return {
      id: 'course_explorer',
      desc: `你的互動以課程助理為主（佔 ${coursePct}%），廣泛探索各系所開設課程，對學習內容充滿好奇心。`,
    };
  }
  if (domainsActive >= 3 && uniqueColleges >= 3) {
    return {
      id: 'integrator',
      desc: `你在課程與研究兩個面向都跨越了 ${uniqueColleges} 個學院、${domainsActive} 個主要領域，具備強烈的跨域整合意識。`,
    };
  }
  if ((courseData?.dept_distribution.length ?? 0) + (projectData?.dept_distribution.length ?? 0) >= 8) {
    return {
      id: 'explorer',
      desc: `你在課程與研究兩個系統都保持廣泛探索，涉足的系所數量豐富，善於發掘不同領域的可能性。`,
    };
  }
  return {
    id: 'balanced',
    desc: `你在課程助理（${coursePct}%）與研究計畫（${researchPct}%）之間保持均衡，兼顧課程規劃與學術探索兩個面向。`,
  };
}

/** 使用偏好的一句話說明 */
export function usagePreferenceText(coursePct: number, researchPct: number): string {
  return coursePct > 70
    ? '你主要使用課程助理探索修課資訊，對課程規劃有清晰的需求。'
    : researchPct > 70
    ? '你大量使用研究計畫功能，對學術研究有高度的探索興趣。'
    : coursePct >= researchPct
    ? `你對兩個功能都有使用，課程助理（${coursePct}%）略多於研究計畫（${researchPct}%）。`
    : `你對兩個功能都有使用，研究計畫（${researchPct}%）略多於課程助理（${coursePct}%）。`;
}

export function formatRelativeTime(iso: string, now: number = Date.now()): string {
  const diff = now - new Date(iso).getTime();
  const days = Math.floor(diff / 86_400_000);
  if (days === 0) return '今天';
  if (days === 1) return '昨天';
  if (days < 30) return `${days} 天前`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} 個月前`;
  return `${Math.floor(months / 12)} 年前`;
}
