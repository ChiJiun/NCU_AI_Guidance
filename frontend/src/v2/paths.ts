/**
 * 新舊版路徑對應（純函式，不依賴 React，方便用 node --test 測試）。
 *
 * - 舊版維持原網址（/、/courses…），新版放在 /v2 底下（/v2、/v2/courses…）。
 * - 新版目前只有 V2_PAGES 列出的頁面；其他頁面在新版裡直接連回舊版。
 */

export const V2_BASE = '/v2';

/** 新版已經有的頁面（以舊版路徑表示）。 */
export const V2_PAGES = ['/', '/assessment', '/curriculum', '/courses', '/course-search'] as const;

const trimTrailingSlash = (pathname: string) =>
  pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;

export function isV2Path(pathname: string): boolean {
  return pathname === V2_BASE || pathname.startsWith(`${V2_BASE}/`);
}

/** 舊版路徑在新版有沒有對應頁面。 */
export function hasV2Page(legacyPathname: string): boolean {
  return (V2_PAGES as readonly string[]).includes(trimTrailingSlash(legacyPathname));
}

/** 舊版路徑 → 新版路徑；新版沒有這一頁時回到新版首頁。 */
export function toV2Path(pathname: string): string {
  const path = trimTrailingSlash(pathname);
  if (isV2Path(path)) return path;
  if (!hasV2Page(path)) return V2_BASE;
  return path === '/' ? V2_BASE : `${V2_BASE}${path}`;
}

/** 新版路徑 → 舊版路徑。 */
export function toLegacyPath(pathname: string): string {
  const path = trimTrailingSlash(pathname);
  if (!isV2Path(path)) return path;
  const rest = path.slice(V2_BASE.length);
  return rest === '' ? '/' : rest;
}

/**
 * 新版頁面內的站內連結：新版有的頁面連到 /v2 底下，其餘連回舊版。
 * 例如 v2Link('/courses') → '/v2/courses'；v2Link('/projects') → '/projects'。
 */
export function v2Link(legacyPathname: string): string {
  return hasV2Page(legacyPathname) ? toV2Path(legacyPathname) : legacyPathname;
}
