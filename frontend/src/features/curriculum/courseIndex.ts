import type { CourseEntry, CourseHit, CourseIndex, DeptDetail } from './types';

// 系所修課的純函式：課名正規化、跨系課程索引、學期分組、欄位定義（新舊版頁面共用）

export const normalizeCourse = (name: string): string =>
  name
    .replace(/[（）()【】「」『』、。，,\s]/g, '')
    .replace(/[一二三四五六七八九十百千]+$/g, '')
    .replace(/[上下甲乙丙丁]+$/g, '')
    .replace(/[IVXivx]+$/g, '')
    .replace(/\d+$/g, '')
    .toLowerCase();

// 第二層 normalize：剝前綴修飾詞 + 尾部單字母，供 similar 比對用
export const normalizeCourseDeep = (n1: string): string =>
  n1
    .replace(/^(高等|基礎|初等|進階|普通|概論|應用|入門|導論|近代|現代|理論|工程)/, '')
    .replace(/[a-z]$/, '');

export function collectAllCoursesFromDetail(detail: DeptDetail): { course: CourseEntry; category: CourseHit['category']; groupName?: string }[] {
  const out: { course: CourseEntry; category: CourseHit['category']; groupName?: string }[] = [];
  const REQUIRED_KEYS = [
    'required_courses', 'foundation_courses', 'college_required_courses', 'common_required_courses',
    'dept_required_courses', 'required_electives', 'cross_domain_required', 'earth_system_courses',
    'cross_group_required', 'application_courses', 'first_domain_electives',
  ] as const;
  for (const key of REQUIRED_KEYS) {
    for (const c of (detail[key] as CourseEntry[] | undefined) ?? []) out.push({ course: c, category: 'required' });
  }
  for (const c of detail.elective_courses ?? []) out.push({ course: c, category: 'elective' });
  const allGroups = [
    ...(detail.elective_groups ?? []), ...(detail.core_elective_groups ?? []),
    ...(detail.college_required_elective_groups ?? []), ...(detail.science_ability_groups ?? []),
    ...(detail.other_elective_groups ?? []),
  ];
  for (const g of allGroups) {
    const gc = [...(g.courses ?? []), ...(g.option_a ?? []), ...(g.option_b ?? []), ...(g.option_c ?? []),
      ...(g.slots ?? []).flatMap(s => s.courses)];
    for (const c of gc) out.push({ course: c, category: 'elective', groupName: g.name });
  }
  return out;
}

export function buildCourseIndex(
  allDetails: Map<string, DeptDetail>,
  metaMap: Map<string, { collegeName: string; accentHex: string }>
): CourseIndex {
  const index = new Map<string, CourseHit[]>();
  for (const [deptId, detail] of allDetails) {
    const meta = metaMap.get(deptId);
    if (!meta) continue;
    for (const { course, category, groupName } of collectAllCoursesFromDetail(detail)) {
      const key = normalizeCourse(course.name);
      if (!key || key.length < 2) continue;
      if (!index.has(key)) index.set(key, []);
      const hits = index.get(key)!;
      if (!hits.some(h => h.deptId === deptId && h.category === category)) {
        hits.push({ deptId, deptName: detail.name, collegeName: meta.collegeName, accentHex: meta.accentHex, category, groupName, credits: course.credits, originalName: course.name, originalCode: course.code ?? '' });
      }
    }
  }
  return index;
}

export function findCrossMatches(courseName: string, currentDeptId: string, index: CourseIndex) {
  const norm = normalizeCourse(courseName);
  const normDeep = normalizeCourseDeep(norm);
  const exact = (index.get(norm) ?? []).filter(h => h.deptId !== currentDeptId);
  const similar: Array<{ hits: CourseHit[] }> = [];
  const seen = new Set([norm]);
  for (const [key, hits] of index) {
    if (seen.has(key) || norm.length < 3 || key.length < 3) continue;
    const keyDeep = normalizeCourseDeep(key);
    // 包含關係（原有邏輯）
    const isContainment = norm.includes(key) || key.includes(norm);
    // 深層相同 stem（前綴/字母尾碼剝除後相同），避免 A/B 變體互相找不到
    const isDeepMatch = normDeep.length >= 3 && keyDeep.length >= 3 && normDeep === keyDeep;
    if (isContainment || isDeepMatch) {
      const other = hits.filter(h => h.deptId !== currentDeptId);
      if (other.length > 0) { similar.push({ hits: other }); seen.add(key); }
    }
  }
  return { exact, similar };
}

export const SEM_ORDER = ['大一上', '大一下', '大二上', '大二下', '大三上', '大三下', '大四上', '大四下'];

export function semKey(when: string): string {
  // 範圍取起始，例如 "大一上~大二下" → "大一上"
  return (when || '').split('~')[0].trim();
}

export function groupBySem(courses: CourseEntry[]): Map<string, CourseEntry[]> {
  const map = new Map<string, CourseEntry[]>();
  for (const c of courses) {
    const k = c.when ? semKey(c.when) : '未分配';
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(c);
  }
  // 排序：依 SEM_ORDER 順序
  const sorted = new Map<string, CourseEntry[]>();
  for (const sem of SEM_ORDER) {
    if (map.has(sem)) sorted.set(sem, map.get(sem)!);
  }
  if (map.has('未分配')) sorted.set('未分配', map.get('未分配')!);
  return sorted;
}

export const CATEGORIES_ORDER = ['學分規定', '指定選課', '外部認證', '先修條件', '特殊規定', '其他規定'];

// 所有可能的「必修課程」欄位，順序即顯示順序（elective_courses 獨立處理）
export const REQUIRED_COURSE_FIELDS: Array<{ key: keyof DeptDetail; label: string }> = [
  { key: 'required_courses', label: '必修課程' },
  { key: 'foundation_courses', label: '基礎必修' },
  { key: 'college_required_courses', label: '院訂必修' },
  { key: 'common_required_courses', label: '共同必修' },
  { key: 'dept_required_courses', label: '系訂必修' },
  { key: 'required_electives', label: '必選修' },
  { key: 'cross_domain_required', label: '跨域必修' },
  { key: 'earth_system_courses', label: '地球系統科學' },
  { key: 'cross_group_required', label: '跨組必修' },
  { key: 'application_courses', label: '應用課程' },
  { key: 'first_domain_electives', label: '第一領域選修' },
];
