import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  buildProjectPdfUrl,
  createWelcomeMessage,
  filterAndSortProjects,
  formatSourceLabels,
  groupDepartmentsByCollege,
  matchRecentChats,
  projectDepartments,
  projectYears,
} from '../src/features/projects/projectUtils.ts';
import { getDeptCollege } from '../src/constants/colleges.ts';
import type { Project } from '../src/types/index.ts';

const p = (id: string, year: string, department: string, title: string, extra: Partial<Project> = {}): Project => ({
  id, year, department, title, type: 'E', studentName: '學生', ...extra,
});

const projects = [
  p('1', '112', '資訊工程學系', '深度學習與影像辨識'),
  p('2', '113', '中國文學系', '古典詩詞的情感分析', { documentId: 22 }),
  p('3', '113', '資訊工程學系', '區塊鏈投票系統'),
  p('4', '111', '物理學系', '量子點的光學性質'),
];

test('年份由新到舊、系所依學院順序', () => {
  assert.deepEqual(projectYears(projects), ['113', '112', '111']);
  assert.deepEqual(projectDepartments(projects), ['中國文學系', '物理學系', '資訊工程學系']);
});

test('篩選：年份、系所與標題關鍵字（不分大小寫、去頭尾空白）', () => {
  assert.deepEqual(filterAndSortProjects(projects, '113', '', '').map((x) => x.id), ['2', '3']);
  assert.deepEqual(filterAndSortProjects(projects, '', '資訊工程學系', '').map((x) => x.id), ['3', '1']);
  assert.deepEqual(filterAndSortProjects(projects, '', '', '  量子 ').map((x) => x.id), ['4']);
  assert.equal(filterAndSortProjects(projects, '', '', '沒有這個').length, 0);
});

test('排序：學院順序 → 同系所新年度在前', () => {
  assert.deepEqual(filterAndSortProjects(projects, '', '', '').map((x) => x.id), ['2', '4', '3', '1']);
});

test('最近對話只留下找得到研究計畫的那幾筆', () => {
  const recent = [
    { document_id: 22, thread_id: 't1', title: '對話一', created_at: null },
    { document_id: 99, thread_id: 't2', title: '找不到', created_at: null },
  ];
  const matched = matchRecentChats(recent, projects);
  assert.equal(matched.length, 1);
  assert.equal(matched[0].project.id, '2');
  assert.equal(matched[0].thread_id, 't1');
});

test('系所分組：研究所排在學系後面，未分類單位放最後', () => {
  const groups = groupDepartmentsByCollege(['網路學習科技研究所', '資訊工程學系', '不存在的單位', '中國文學系'], getDeptCollege);
  assert.equal(groups.at(-1)?.[0], '未分類單位');
  const csie = groups.find(([, depts]) => depts.includes('資訊工程學系'));
  assert.deepEqual(csie?.[1], ['資訊工程學系', '網路學習科技研究所']);
});

test('PDF 網址：絕對網址照用、/ 開頭接後端、否則由 pdfPath 組出', () => {
  // 與舊版相同：以 replace('/api', '') 去掉第一個 /api（主機名稱以 api. 開頭時會切錯，屬舊版既有行為）
  const api = 'http://localhost:8000/api';
  assert.equal(buildProjectPdfUrl(p('a', '1', 'd', 't', { pdfUrl: 'https://cdn.example.com/a.pdf' }), api), 'https://cdn.example.com/a.pdf');
  assert.equal(buildProjectPdfUrl(p('a', '1', 'd', 't', { pdfUrl: '/files/a.pdf' }), api), 'http://localhost:8000/files/a.pdf');
  assert.equal(
    buildProjectPdfUrl(p('a', '1', 'd', 't', { pdfPath: '112\\資工 系\\a#1.pdf' }), api),
    'http://localhost:8000/pdfs/112/%E8%B3%87%E5%B7%A5%20%E7%B3%BB/a%231.pdf',
  );
  assert.equal(buildProjectPdfUrl(p('a', '1', 'd', 't'), api), '');
});

test('來源頁碼：純數字補上 p.、去重、去空白', () => {
  assert.deepEqual(formatSourceLabels(['3', 'p.3', ' 5 - 6 ', '3', '', '附錄']), ['p.3', 'p.5-6', '附錄']);
  assert.deepEqual(formatSourceLabels(undefined), []);
});

test('歡迎訊息帶出研究計畫標題', () => {
  const message = createWelcomeMessage(projects[0]);
  assert.equal(message.role, 'assistant');
  assert.match(message.content, /深度學習與影像辨識/);
});
