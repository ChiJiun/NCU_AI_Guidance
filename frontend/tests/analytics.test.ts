import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { AnalyticsData, PdfAnalyticsData } from '../src/api/services.ts';
import {
  activeDomainCount,
  collegeDomainAxes,
  combinedDomainAxes,
  diagnoseCombinedType,
  diagnoseCourseType,
  formatRelativeTime,
  interactionShare,
  uniqueCollegeCount,
  usagePreferenceText,
} from '../src/features/analytics/analysis.ts';

const dist = (items: [string, number][]) => items.map(([name, count]) => ({ name, count, pct: 0 }));

function course(overrides: Partial<AnalyticsData> = {}): AnalyticsData {
  return {
    overview: { total_sessions: 2, total_turns: 10, total_courses_explored: 5, fav_college: '資訊電機學院' },
    dept_distribution: [],
    college_distribution: [],
    tool_usage: [],
    top_courses: [],
    top_domain_tags: [],
    general_edu: { total: 0, categories: [], top_topic_tags: [] },
    top_course_domains: [],
    ...overrides,
  };
}

function project(overrides: Partial<PdfAnalyticsData> = {}): PdfAnalyticsData {
  return {
    overview: { total_conversations: 3, total_questions: 10, total_documents_explored: 2, avg_depth: 3 },
    dept_distribution: [],
    college_distribution: [],
    depth_distribution: [],
    exploration_type: { type: '', desc: '' },
    document_list: [],
    recent_questions: [],
    ...overrides,
  };
}

const turns = (n: number) => ({ total_sessions: 1, total_turns: n, total_courses_explored: 0, fav_college: '' });

test('學院分佈換算成六個學術領域（通識不算在分母）', () => {
  const axes = collegeDomainAxes(dist([['資訊電機學院', 6], ['理學院', 2], ['工學院', 2], ['中心、處室', 5]]));
  assert.deepEqual(axes.map((a) => a.label), ['理工', '資訊', '地科', '生醫', '人文', '商管']);
  const info = axes.find((a) => a.label === '資訊')!;
  const sci = axes.find((a) => a.label === '理工')!;
  assert.equal(info.pct, 60);
  assert.equal(info.value, 100);
  assert.equal(sci.pct, 40);
  assert.equal(sci.value, 67);
  assert.deepEqual(collegeDomainAxes([]), []);
  assert.deepEqual(collegeDomainAxes(undefined), []);
});

test('使用比例：沒有任何互動時課程佔 0%', () => {
  assert.deepEqual(interactionShare(null, null), {
    courseInteractions: 0, researchInteractions: 0, totalInteractions: 0, coursePct: 0, researchPct: 100,
  });
  const share = interactionShare(course({ overview: turns(30) }), project());
  assert.equal(share.coursePct, 75);
  assert.equal(share.researchPct, 25);
});

test('綜合領域：weighted 依互動量加權、equal 各半', () => {
  const c = course({ college_distribution: dist([['資訊電機學院', 1]]), overview: turns(30) });
  const pj = project({ college_distribution: dist([['文學院', 1]]) });
  const weighted = combinedDomainAxes(c, pj, 'weighted', 30, 40);
  assert.equal(weighted.find((a) => a.label === '資訊')!.pct, 75);
  assert.equal(weighted.find((a) => a.label === '人文')!.pct, 25);
  const equal = combinedDomainAxes(c, pj, 'equal', 30, 40);
  assert.equal(equal.find((a) => a.label === '資訊')!.pct, 50);
  assert.deepEqual(combinedDomainAxes(null, null, 'weighted', 0, 0), []);
});

test('課程探索型態', () => {
  assert.equal(diagnoseCourseType(course({ overview: turns(2) }), []), 'balanced');
  const planning = course({
    tool_usage: [{ tool: 'get_graduation_rules', label: '', count: 3 }, { tool: 'search_courses', label: '', count: 7 }],
  });
  assert.equal(diagnoseCourseType(planning, []), 'planning');
  const crossAxes = [{ label: 'a', value: 100, pct: 30 }, { label: 'b', value: 80, pct: 30 }, { label: 'c', value: 60, pct: 20 }];
  assert.equal(activeDomainCount(crossAxes), 3);
  assert.equal(diagnoseCourseType(course(), crossAxes), 'cross');
  const deep = course({ dept_distribution: [{ name: '資工', count: 9, pct: 70 }, { name: '電機', count: 3, pct: 30 }] });
  assert.equal(diagnoseCourseType(deep, []), 'deep');
  const wide = course({ dept_distribution: Array.from({ length: 6 }, (_, i) => ({ name: `系${i}`, count: 1, pct: 16 })) });
  assert.equal(diagnoseCourseType(wide, []), 'wide');
});

test('綜合探索型態', () => {
  const researcher = project({ overview: { total_conversations: 1, total_questions: 5, total_documents_explored: 1, avg_depth: 2 } });
  assert.equal(diagnoseCombinedType(null, researcher, 30, []).id, 'researcher');
  const planner = course({ tool_usage: [{ tool: 'get_program_info', label: '', count: 1 }] });
  assert.equal(diagnoseCombinedType(planner, null, 80, []).id, 'planner');
  assert.equal(diagnoseCombinedType(course(), null, 80, []).id, 'course_explorer');
  const c = course({ college_distribution: dist([['文學院', 1], ['理學院', 1], ['管理學院', 1]]) });
  const axes = [{ label: 'a', pct: 40 }, { label: 'b', pct: 30 }, { label: 'c', pct: 30 }];
  const integrator = diagnoseCombinedType(c, null, 50, axes);
  assert.equal(integrator.id, 'integrator');
  assert.match(integrator.desc, /3 個學院/);
  assert.equal(diagnoseCombinedType(null, null, 50, []).id, 'balanced');
});

test('合計學院數會去重', () => {
  const c = course({ college_distribution: dist([['文學院', 1], ['理學院', 1]]) });
  assert.equal(uniqueCollegeCount(c, project({ college_distribution: dist([['理學院', 2]]) })), 2);
});

test('使用偏好的說明', () => {
  assert.match(usagePreferenceText(80, 20), /主要使用課程助理/);
  assert.match(usagePreferenceText(20, 80), /大量使用研究計畫/);
  assert.match(usagePreferenceText(50, 50), /課程助理（50%）略多於/);
  assert.match(usagePreferenceText(40, 60), /研究計畫（60%）略多於/);
});

test('相對時間', () => {
  const now = Date.parse('2026-11-17T12:00:00Z');
  assert.equal(formatRelativeTime('2026-11-17T08:00:00Z', now), '今天');
  assert.equal(formatRelativeTime('2026-11-16T08:00:00Z', now), '昨天');
  assert.equal(formatRelativeTime('2026-11-07T12:00:00Z', now), '10 天前');
  assert.equal(formatRelativeTime('2026-08-17T12:00:00Z', now), '3 個月前');
  assert.equal(formatRelativeTime('2024-11-17T12:00:00Z', now), '2 年前');
});
