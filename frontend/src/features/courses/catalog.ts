import type { Course } from '../../types';

// 課程資訊頁的常數、型別與純函式（新舊版頁面共用）

export const COLLEGE_ORDER = ['文學院', '理學院', '工學院', '管理學院', '資訊電機學院', '地球科學學院', '客家學院', '生醫理工學院', '永續與綠能科技研究學院', '中心、處室'] as const;
export const FALLBACK_COLLEGE = '中心、處室';
export const FALLBACK_DEPARTMENT = '未分類單位';
export const COMPARE_LIMIT = 3;

export type NavigationLevel = 'colleges' | 'departments' | 'courses';
export type ResultTab = 'course_name' | 'detail_info';
export type SearchMode = 'semantic' | 'keyword';
export type SemanticSearchMode = 'idle' | 'semantic' | 'fallback';
export type GroupedCourses = Record<string, Record<string, Course[]>>;

export const normalize = (value?: string | null) => (value ?? '').trim();
export const splitFields = (value?: string | null) => (value ?? '').split(/[、,;；／/]/).map((s) => s.trim()).filter(Boolean);
export const courseKey = (course: Course) => `${course.serial_no}-${course.course_id}`;
export const formatScore = (score?: number) => (typeof score === 'number' ? `${Math.round(score * 100)}%` : null);
export const sameStringArray = (left: string[], right: string[]) => {
  if (left.length !== right.length) return false;
  const rightSet = new Set(right);
  return left.every((value) => rightSet.has(value));
};
export const metadataPreview = (course: Course) =>
  Array.from(new Set([...(course.tools ?? []), ...(course.concepts ?? []), ...(course.topic_tags ?? [])].map((item) => item.trim()).filter(Boolean))).slice(0, 3);

export const getDetailPreview = (course: Course, keyword: string) => {
  const text = [
    course.semantic_summary,
    course.course_objective,
    course.course_content,
    course.course_field,
    course.textbooks,
    course.note,
    course.instructor,
    course.eligibility_summary,
    ...(course.tools ?? []),
    ...(course.concepts ?? []),
    ...(course.topic_tags ?? []),
    ...(course.domain_tags ?? []),
    ...(course.languages ?? []),
    ...(course.simplified_concepts ?? []),
    ...(course.core_questions ?? []),
  ].filter(Boolean).join(' ');
  if (!text) return '';
  const query = keyword.trim().toLowerCase();
  if (!query) return text.slice(0, 80);
  const hit = text.toLowerCase().indexOf(query);
  if (hit === -1) return text.slice(0, 80);
  const start = Math.max(0, hit - 18);
  const end = Math.min(text.length, hit + query.length + 36);
  return `${start > 0 ? '...' : ''}${text.slice(start, end)}${end < text.length ? '...' : ''}`;
};
