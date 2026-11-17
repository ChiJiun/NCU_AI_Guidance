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

test('toV2Path：新版沒有的頁面回到新版首頁', () => {
  assert.equal(toV2Path('/projects'), '/v2');
  assert.equal(toV2Path('/profile'), '/v2');
  assert.equal(toV2Path('/demo/some-case'), '/v2');
  assert.equal(toV2Path('/monitor'), '/v2');
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
  for (const path of ['/', '/assessment', '/curriculum', '/courses', '/course-search']) {
    assert.equal(toLegacyPath(toV2Path(path)), path);
  }
});

test('v2Link：新版有的頁面連到 /v2，其餘連回舊版', () => {
  assert.equal(hasV2Page('/courses'), true);
  assert.equal(hasV2Page('/projects'), false);
  assert.equal(v2Link('/'), '/v2');
  assert.equal(v2Link('/courses'), '/v2/courses');
  assert.equal(v2Link('/projects'), '/projects');
  assert.equal(v2Link('/resources'), '/resources');
  assert.equal(v2Link('/profile'), '/profile');
});
