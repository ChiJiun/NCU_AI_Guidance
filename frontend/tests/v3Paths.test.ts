import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  hasV3Page,
  isV3Path,
  switchVersionHref,
  toV1Path,
  toV3Path,
  v3Link,
  versionOf,
} from '../src/v3/paths.ts';

test('isV3Path 只認 /v3 與 /v3/ 開頭，不分大小寫', () => {
  assert.equal(isV3Path('/v3'), true);
  assert.equal(isV3Path('/v3/'), true);
  assert.equal(isV3Path('/v3/courses'), true);
  assert.equal(isV3Path('/V3/Courses'), true);
  assert.equal(isV3Path('/'), false);
  assert.equal(isV3Path('/v3x'), false);
  assert.equal(isV3Path('/v2/courses'), false);
  assert.equal(isV3Path('/courses/v3'), false);
});

test('versionOf 分辨三版', () => {
  assert.equal(versionOf('/'), 'v1');
  assert.equal(versionOf('/courses'), 'v1');
  assert.equal(versionOf('/v2'), 'v2');
  assert.equal(versionOf('/V2/courses'), 'v2');
  assert.equal(versionOf('/v3'), 'v3');
  assert.equal(versionOf('//v3//courses/'), 'v3');
  assert.equal(versionOf('/v3x'), 'v1');
});

test('toV1Path：去掉 /v2 或 /v3 前綴，其餘原樣保留', () => {
  assert.equal(toV1Path('/v3'), '/');
  assert.equal(toV1Path('/v3/'), '/');
  assert.equal(toV1Path('/v3/courses'), '/courses');
  assert.equal(toV1Path('/V3/projects'), '/projects');
  assert.equal(toV1Path('/v3//course-search/'), '/course-search');
  assert.equal(toV1Path('/v3/demo/CaseA'), '/demo/CaseA');
  assert.equal(toV1Path('/v2/courses'), '/courses');
  assert.equal(toV1Path('/courses'), '/courses');
  assert.equal(toV1Path('//'), '/');
});

test('toV3Path：v3 有的頁面對應到同一頁，不論從哪一版來', () => {
  assert.equal(toV3Path('/'), '/v3');
  assert.equal(toV3Path('/courses'), '/v3/courses');
  assert.equal(toV3Path('/course-search'), '/v3/course-search');
  assert.equal(toV3Path('/assessment'), '/v3/assessment');
  assert.equal(toV3Path('/curriculum'), '/v3/curriculum');
  assert.equal(toV3Path('/v2/courses'), '/v3/courses');
  assert.equal(toV3Path('/v2'), '/v3');
  assert.equal(toV3Path('/V3//Courses/'), '/v3/courses');
  assert.equal(toV3Path('/Courses'), '/v3/courses');
});

test('toV3Path：v3 沒有的頁面回到 v3 首頁', () => {
  assert.equal(toV3Path('/projects'), '/v3');
  assert.equal(toV3Path('/profile'), '/v3');
  assert.equal(toV3Path('/demo/some-case'), '/v3');
  assert.equal(toV3Path('/v3/projects'), '/v3');
});

test('v1 與 v3 互轉可以來回', () => {
  for (const path of ['/', '/assessment', '/curriculum', '/courses', '/course-search']) {
    assert.equal(toV1Path(toV3Path(path)), path);
  }
});

test('v3Link：v3 有的頁面連到 /v3，其餘連回舊版', () => {
  assert.equal(hasV3Page('/courses'), true);
  assert.equal(hasV3Page('/COURSES/'), true);
  assert.equal(hasV3Page('/projects'), false);
  assert.equal(v3Link('/'), '/v3');
  assert.equal(v3Link('/curriculum'), '/v3/curriculum');
  assert.equal(v3Link('/projects'), '/projects');
  assert.equal(v3Link('/resources'), '/resources');
  assert.equal(v3Link('/profile'), '/profile');
});

test('switchVersionHref：三版之間互切停在同一頁並保留查詢字串', () => {
  const search = '?search=%E5%BE%AE%E7%A9%8D%E5%88%86&level=bachelor';
  const pages: [string, string, string][] = [
    ['/', '/v2', '/v3'],
    ['/courses', '/v2/courses', '/v3/courses'],
    ['/course-search', '/v2/course-search', '/v3/course-search'],
    ['/assessment', '/v2/assessment', '/v3/assessment'],
    ['/curriculum', '/v2/curriculum', '/v3/curriculum'],
  ];
  for (const triple of pages) {
    for (const from of triple) {
      assert.equal(switchVersionHref(from, search, 'v1'), `${triple[0]}${search}`);
      assert.equal(switchVersionHref(from, search, 'v2'), `${triple[1]}${search}`);
      assert.equal(switchVersionHref(from, search, 'v3'), `${triple[2]}${search}`);
    }
  }
  assert.equal(switchVersionHref('/v3/courses', '', 'v1'), '/courses');
});

test('switchVersionHref：目標版沒有這一頁時回到該版首頁，不帶原頁的查詢字串', () => {
  assert.equal(switchVersionHref('/projects', '?id=3', 'v3'), '/v3');
  assert.equal(switchVersionHref('/projects', '?id=3', 'v2'), '/v2');
  assert.equal(switchVersionHref('/projects', '?id=3', 'v1'), '/projects?id=3');
  assert.equal(switchVersionHref('/demo/CaseA', '', 'v1'), '/demo/CaseA');
});
