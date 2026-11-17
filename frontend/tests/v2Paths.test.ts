import assert from 'node:assert/strict';
import { test } from 'node:test';
import { hasV2Page, isV2Path, toLegacyPath, toV2Path, v2Link } from '../src/v2/paths.ts';

test('isV2Path 只認 /v2 與 /v2/ 開頭', () => {
  assert.equal(isV2Path('/v2'), true);
  assert.equal(isV2Path('/v2/courses'), true);
  assert.equal(isV2Path('/'), false);
  assert.equal(isV2Path('/v2x'), false);
  assert.equal(isV2Path('/courses/v2'), false);
});

test('toV2Path：新版有的頁面對應到同一頁', () => {
  assert.equal(toV2Path('/'), '/v2');
  assert.equal(toV2Path('/courses'), '/v2/courses');
  assert.equal(toV2Path('/course-search'), '/v2/course-search');
  assert.equal(toV2Path('/assessment'), '/v2/assessment');
  assert.equal(toV2Path('/curriculum'), '/v2/curriculum');
  assert.equal(toV2Path('/courses/'), '/v2/courses');
});

test('toV2Path：研究計畫、資源、個人分析、示範案例、系統監控也有新版', () => {
  assert.equal(toV2Path('/projects'), '/v2/projects');
  assert.equal(toV2Path('/resources'), '/v2/resources');
  assert.equal(toV2Path('/profile'), '/v2/profile');
  assert.equal(toV2Path('/demo'), '/v2/demo');
  assert.equal(toV2Path('/monitor'), '/v2/monitor');
});

test('toV2Path：示範案例內頁保留 id 的大小寫', () => {
  assert.equal(toV2Path('/demo/some-case'), '/v2/demo/some-case');
  assert.equal(toV2Path('/Demo/CaseA'), '/v2/demo/CaseA');
  assert.equal(toV2Path('/demo/CaseA/'), '/v2/demo/CaseA');
  // V2App 用這個組合把網址導到標準寫法
  assert.equal(toV2Path(toLegacyPath('/V2/DEMO/CaseA')), '/v2/demo/CaseA');
  assert.equal(hasV2Page('/demo/CaseA'), true);
});

test('toV2Path：新版沒有的頁面回到新版首頁', () => {
  assert.equal(toV2Path('/unknown'), '/v2');
  assert.equal(toV2Path('/demo/a/b'), '/v2');
  assert.equal(toV2Path('/projects/123'), '/v2');
  assert.equal(hasV2Page('/demo/a/b'), false);
});

test('toV2Path：已經是新版路徑就不變', () => {
  assert.equal(toV2Path('/v2'), '/v2');
  assert.equal(toV2Path('/v2/courses'), '/v2/courses');
});

test('toLegacyPath：去掉 /v2 前綴', () => {
  assert.equal(toLegacyPath('/v2'), '/');
  assert.equal(toLegacyPath('/v2/'), '/');
  assert.equal(toLegacyPath('/v2/courses'), '/courses');
  assert.equal(toLegacyPath('/v2/projects'), '/projects');
  assert.equal(toLegacyPath('/courses'), '/courses');
});

test('新舊版互轉可以來回', () => {
  for (const path of [
    '/', '/assessment', '/curriculum', '/courses', '/course-search',
    '/projects', '/resources', '/profile', '/demo', '/demo/CaseA', '/monitor',
  ]) {
    assert.equal(toLegacyPath(toV2Path(path)), path);
  }
});

test('v2Link：新版有的頁面連到 /v2，其餘連回舊版', () => {
  assert.equal(hasV2Page('/courses'), true);
  assert.equal(hasV2Page('/projects'), true);
  assert.equal(hasV2Page('/unknown'), false);
  assert.equal(v2Link('/'), '/v2');
  assert.equal(v2Link('/courses'), '/v2/courses');
  assert.equal(v2Link('/projects'), '/v2/projects');
  assert.equal(v2Link('/resources'), '/v2/resources');
  assert.equal(v2Link('/profile'), '/v2/profile');
  assert.equal(v2Link('/monitor'), '/v2/monitor');
  assert.equal(v2Link('/demo'), '/v2/demo');
  assert.equal(v2Link('/demo/case-1'), '/v2/demo/case-1');
  assert.equal(v2Link('/unknown'), '/unknown');
});

test('連續斜線會先合併，避免 react-router 把 //courses 當成外部網址', () => {
  assert.equal(toLegacyPath('/v2//courses'), '/courses');
  assert.equal(toLegacyPath('//v2///projects//'), '/projects');
  assert.equal(toV2Path('//courses'), '/v2/courses');
  assert.equal(toV2Path('/v2//courses'), '/v2/courses');
});

test('/v2 前綴與新版頁面比對不分大小寫（和 react-router 一致）', () => {
  assert.equal(isV2Path('/V2/projects'), true);
  assert.equal(toLegacyPath('/V2/projects'), '/projects');
  assert.equal(toLegacyPath('/V2'), '/');
  assert.equal(toV2Path('/Courses'), '/v2/courses');
  assert.equal(hasV2Page('/COURSES'), true);
  // /v2 之後的部分原樣保留（例如 demo id 可能有大小寫）
  assert.equal(toLegacyPath('/v2/demo/CaseA'), '/demo/CaseA');
});
