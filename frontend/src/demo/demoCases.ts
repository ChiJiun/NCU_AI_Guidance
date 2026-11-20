// 比賽展示版的示範對話：由 scripts/demo/record_demos.py 實際跑真實 agent 後存成
// public/demo/*.json，前端只讀取靜態檔，不會觸發任何模型呼叫。
import type { AnalyticsData, PdfAnalyticsData } from '../api/services';
import type { CourseCard, DebugTrace } from '../types';

export type DemoCategory = '一般' | '複雜' | '資料不足' | '安全限制';

interface DemoCaseBase {
  id: string;
  title: string;
  category: DemoCategory;
  summary: string;
  /** 領域／學院，例如「地球科學學院」 */
  field?: string;
  /** 對應評測集 eval-set-v1 的題號 */
  origin?: string;
  reviewed: boolean;
  recorded_at: string;
  commit: string;
  model: string;
}

export interface CourseDemoTurn {
  user: string;
  assistant: string;
  course_cards: CourseCard[];
  tools_used: string[];
  debug_trace?: DebugTrace;
}

export interface CourseDemoCase extends DemoCaseBase {
  turns: CourseDemoTurn[];
}

export interface ResearchDemoTurn {
  user: string;
  assistant: string;
  sources: string[];
  agents: string[];
  stages: string[];
}

export interface ResearchDemoCase extends DemoCaseBase {
  project_id: string;
  project_title: string;
  project_department: string;
  project_year: string;
  turns: ResearchDemoTurn[];
}

interface DemoFile<T> {
  version: number;
  cases: T[];
}

export const CATEGORY_STYLES: Record<DemoCategory, string> = {
  '一般':     'bg-sky-50 text-sky-700 ring-sky-200',
  '複雜':     'bg-violet-50 text-violet-700 ring-violet-200',
  '資料不足': 'bg-amber-50 text-amber-700 ring-amber-200',
  '安全限制': 'bg-rose-50 text-rose-700 ring-rose-200',
};

/** 正式版只放出人工檢查過（reviewed）的案例；開發時全部顯示，方便檢查。 */
export function selectVisibleCases<T extends { reviewed: boolean; turns: unknown[] }>(
  cases: T[],
  includeUnreviewed: boolean,
): T[] {
  return cases.filter((c) => c.turns.length > 0 && (includeUnreviewed || c.reviewed));
}

export function formatRecordedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('zh-TW', { year: 'numeric', month: 'long', day: 'numeric' });
}

async function loadDemoFile<T extends DemoCaseBase & { turns: unknown[] }>(name: string): Promise<T[]> {
  const res = await fetch(`${import.meta.env.BASE_URL}demo/${name}`, { cache: 'no-cache' });
  if (!res.ok) return [];
  const data = (await res.json()) as DemoFile<T>;
  return selectVisibleCases(data.cases ?? [], import.meta.env.DEV);
}

export interface DemoAnalytics {
  generated_at: string;
  source: { course_cases: number; research_cases: number };
  course: AnalyticsData;
  project: PdfAnalyticsData;
}

/** 由已審核的示範對話算出的「示範學生」個人分析（scripts/demo/build_demo_analytics.py 產生）。 */
async function loadDemoAnalytics(): Promise<DemoAnalytics | null> {
  const res = await fetch(`${import.meta.env.BASE_URL}demo/analytics.json`, { cache: 'no-cache' });
  if (!res.ok) return null;
  return (await res.json()) as DemoAnalytics;
}

export const demoAPI = {
  courseCases: () => loadDemoFile<CourseDemoCase>('course-assistant.json').catch(() => []),
  researchCases: () => loadDemoFile<ResearchDemoCase>('research-assistant.json').catch(() => []),
  analytics: () => loadDemoAnalytics().catch(() => null),
};
