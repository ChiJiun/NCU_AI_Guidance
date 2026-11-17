/**
 * 研究計畫頁的純函式（不依賴 React 與 import.meta.env，方便用 node --test 測試）。
 * 內容逐字搬自舊版 ProjectsPage，新舊版共用。
 */
import { COLLEGE_ORDER, deptSortKey, getDeptCollege, sortDeptsByCollegeOrder } from '../../constants/colleges.ts';
import type { Project } from '../../types';

export type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
};

export interface RecentChat {
  document_id: number;
  thread_id: string;
  title: string;
  created_at: string | null;
}

/** 年份選單：由新到舊 */
export function projectYears(projects: Project[]): string[] {
  return [...new Set(projects.map((project) => project.year))].sort((a, b) => b.localeCompare(a));
}

/** 系所選單：依學院順序 */
export function projectDepartments(projects: Project[]): string[] {
  return sortDeptsByCollegeOrder([...new Set(projects.map((p) => p.department))]);
}

/** 依年份、系所、標題關鍵字篩選，再依學院 → 系所 → 年份（新到舊）排序 */
export function filterAndSortProjects(
  projects: Project[],
  filterYear: string,
  filterDept: string,
  filterTitle: string,
): Project[] {
  const q = filterTitle.trim().toLowerCase();
  const filtered = projects.filter(
    (p) =>
      (!filterYear || p.year === filterYear) &&
      (!filterDept || p.department === filterDept) &&
      (!q || p.title.toLowerCase().includes(q))
  );
  return filtered.sort((a, b) => {
    const ca = getDeptCollege(a.department), cb = getDeptCollege(b.department);
    const ia = COLLEGE_ORDER.indexOf(ca as (typeof COLLEGE_ORDER)[number]);
    const ib = COLLEGE_ORDER.indexOf(cb as (typeof COLLEGE_ORDER)[number]);
    const ra = ia === -1 ? COLLEGE_ORDER.length : ia;
    const rb = ib === -1 ? COLLEGE_ORDER.length : ib;
    if (ra !== rb) return ra - rb;
    const ka = deptSortKey(a.department), kb = deptSortKey(b.department);
    if (ka !== kb) return ka - kb;
    const dc = a.department.localeCompare(b.department, 'zh-Hant');
    if (dc !== 0) return dc;
    return b.year.localeCompare(a.year);
  });
}

/** 最近對話：只留下還找得到研究計畫的那幾筆 */
export function matchRecentChats(recentChats: RecentChat[], projects: Project[]): (RecentChat & { project: Project })[] {
  return recentChats.flatMap(rc => {
    const proj = projects.find(p => p.documentId === rc.document_id);
    return proj ? [{ ...rc, project: proj }] : [];
  });
}

/**
 * 系所選單的分組：依學院分組（保留 departments 原本的順序），
 * 每個學院內學系／學士班在前、研究所／研究中心在後，「未分類單位」放最後。
 */
export function groupDepartmentsByCollege(
  departments: string[],
  getCollegeLabel: (dept: string) => string,
): [string, string[]][] {
  const isGrad = (d: string) =>
    d.includes('研究所') || (d.includes('研究中心') && !d.includes('學系'));
  const map = new Map<string, string[]>();
  // 依照 departments 原始順序插入，保留與專題列表相同的排序
  for (const dept of departments) {
    const college = getCollegeLabel(dept);
    if (!map.has(college)) map.set(college, []);
    map.get(college)!.push(dept);
  }
  // 每個學院內：學系/學士班在前，研究所/研究中心在後
  const sorted = Array.from(map.entries()).map(([college, depts]) => [
    college,
    [
      ...depts.filter((d) => !isGrad(d)),
      ...depts.filter((d) =>  isGrad(d)),
    ],
  ] as [string, string[]]);
  // 未分類放最後；其餘保留 departments 插入順序（已由 sortDeptsByCollegeOrder 保證）
  const normal = sorted.filter(([c]) => c !== '未分類單位');
  const uncat  = sorted.filter(([c]) => c === '未分類單位');
  return [...normal, ...uncat];
}

/** PDF 網址：pdfUrl 優先（絕對網址照用、/ 開頭接上後端網址），否則由 pdfPath 組出 /pdfs/… */
export function buildProjectPdfUrl(project: Project, apiUrl: string): string {
  const baseUrl = apiUrl.replace('/api', '');

  if (project.pdfUrl) {
    if (project.pdfUrl.startsWith('http://') || project.pdfUrl.startsWith('https://')) {
      return project.pdfUrl;
    }
    if (project.pdfUrl.startsWith('/')) {
      return `${baseUrl}${project.pdfUrl}`;
    }
    return project.pdfUrl;
  }

  if (!project.pdfPath) return '';
  const encodedPath = project.pdfPath.split('\\').map(encodeURIComponent).join('/');
  return `${baseUrl}/pdfs/${encodedPath}`;
}

export function createWelcomeMessage(project: Project): ChatMessage {
  return {
    role: 'assistant',
    content: `你現在正在查看「${project.title}」這份研究計畫。如果你想了解研究方向、內容重點或延伸問題，可以直接在這裡提問。`,
  };
}

/** 把後端回傳的來源字串（"p.3"、"p.5-6"、"3"…）整理成去重後的頁碼標籤 */
export function formatSourceLabels(sources?: string[]): string[] {
  if (!sources?.length) return [];
  const labels = sources
    .map((s) => (typeof s === 'string' ? s.trim() : ''))
    .filter(Boolean)
    .map((s) => (/^\d+(\s*[-–]\s*\d+)?$/.test(s) ? `p.${s.replace(/\s+/g, '')}` : s));
  return Array.from(new Set(labels));
}
