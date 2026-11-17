/**
 * 三版前端的路徑對應（純函式，不依賴 React，方便用 node --test 測試）。
 *
 * - v1（舊版）維持原網址（/、/courses…）。
 * - v2 放在 /v2 底下，對應規則在 ../v2/paths.ts。
 * - v3 放在 /v3 底下：版面沿用 v2，外觀改用 v1 的風格。目前只有 V3_PAGES 列出的頁面，其他頁面連回舊版。
 */
import { hasV2Page, isV2Path, normalizePath, toLegacyPath as stripV2, toV2Path } from '../v2/paths.ts';

export const V3_BASE = '/v3';

/**
 * v3 已經有的頁面（以舊版路徑表示）。
 * 刻意不直接引用 V2_PAGES：v2 之後補做的頁面，v3 要另外跟進後才加進來。
 */
export const V3_PAGES = ['/', '/assessment', '/curriculum', '/courses', '/course-search'] as const;

export type SiteVersion = 'v1' | 'v2' | 'v3';

/** react-router 比對路由不分大小寫，這裡也一樣（例如 `/V3/courses`）。 */
export function isV3Path(pathname: string): boolean {
  const lower = normalizePath(pathname).toLowerCase();
  return lower === V3_BASE || lower.startsWith(`${V3_BASE}/`);
}

/** 目前網址屬於哪一版。 */
export function versionOf(pathname: string): SiteVersion {
  if (isV3Path(pathname)) return 'v3';
  return isV2Path(pathname) ? 'v2' : 'v1';
}

/** 任一版的路徑 → 舊版路徑（去掉 /v2 或 /v3 前綴，之後的部分原樣保留，只整理斜線）。 */
export function toV1Path(pathname: string): string {
  const path = normalizePath(pathname);
  if (isV3Path(path)) {
    const rest = path.slice(V3_BASE.length);
    return rest === '' ? '/' : rest;
  }
  return stripV2(path);
}

/** 舊版路徑在 v3 有對應頁面時，回傳該頁的標準寫法（小寫）；沒有則回傳 null。 */
function matchV3Page(legacyPathname: string): string | null {
  const lower = normalizePath(legacyPathname).toLowerCase();
  return (V3_PAGES as readonly string[]).includes(lower) ? lower : null;
}

/** 舊版路徑在 v3 有沒有對應頁面。 */
export function hasV3Page(legacyPathname: string): boolean {
  return matchV3Page(legacyPathname) !== null;
}

/** 任一版的路徑 → v3 的同一頁；v3 沒有這一頁時回到 v3 首頁。 */
export function toV3Path(pathname: string): string {
  const page = matchV3Page(toV1Path(pathname));
  if (!page) return V3_BASE;
  return page === '/' ? V3_BASE : `${V3_BASE}${page}`;
}

/**
 * v3 頁面內的站內連結：v3 有的頁面連到 /v3 底下，其餘連回舊版。
 * 例如 v3Link('/courses') → '/v3/courses'；v3Link('/projects') → '/projects'。
 */
export function v3Link(legacyPathname: string): string {
  return hasV3Page(legacyPathname) ? toV3Path(legacyPathname) : legacyPathname;
}

/**
 * 切換到另一版、停在同一頁的網址（保留查詢字串）。
 * 目標版本沒有這一頁時：v1 一定有；v2、v3 回到該版首頁，查詢字串屬於原本那一頁，不帶過去。
 */
export function switchVersionHref(pathname: string, search: string, target: SiteVersion): string {
  const legacy = toV1Path(pathname);
  if (target === 'v1') return `${legacy}${search}`;
  const hasPage = target === 'v2' ? hasV2Page(legacy) : hasV3Page(legacy);
  const path = target === 'v2' ? toV2Path(legacy) : toV3Path(legacy);
  return hasPage ? `${path}${search}` : path;
}
