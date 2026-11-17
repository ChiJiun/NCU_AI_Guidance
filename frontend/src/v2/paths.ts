/**
 * 新舊版路徑對應（純函式，不依賴 React，方便用 node --test 測試）。
 *
 * - 舊版維持原網址（/、/courses…），新版放在 /v2 底下（/v2、/v2/courses…）。
 * - 新版目前只有 V2_PAGES 列出的頁面；其他頁面在新版裡直接連回舊版。
 */

export const V2_BASE = '/v2';

/** 新版已經有的頁面（以舊版路徑表示）。 */
export const V2_PAGES = ['/', '/assessment', '/curriculum', '/courses', '/course-search'] as const;

/**
 * 合併連續斜線並去掉結尾斜線。
 * react-router 會把 `//courses` 當成外部網址而丟錯，所以 `/v2//courses` 這類網址要先整理。
 */
export function normalizePath(pathname: string): string {
  const collapsed = pathname.replace(/\/{2,}/g, '/') || '/';
  return collapsed.length > 1 && collapsed.endsWith('/') ? collapsed.slice(0, -1) : collapsed;
}

/** react-router 比對路由不分大小寫，這裡也一樣（例如 `/V2/courses`）。 */
export function isV2Path(pathname: string): boolean {
  const lower = normalizePath(pathname).toLowerCase();
  return lower === V2_BASE || lower.startsWith(`${V2_BASE}/`);
}

/** 舊版路徑在新版有對應頁面時，回傳該頁的標準寫法（小寫）；沒有則回傳 null。 */
function matchV2Page(legacyPathname: string): string | null {
  const lower = normalizePath(legacyPathname).toLowerCase();
  return (V2_PAGES as readonly string[]).includes(lower) ? lower : null;
}

/** 舊版路徑在新版有沒有對應頁面。 */
export function hasV2Page(legacyPathname: string): boolean {
  return matchV2Page(legacyPathname) !== null;
}

/** 舊版路徑 → 新版路徑；新版沒有這一頁時回到新版首頁。 */
export function toV2Path(pathname: string): string {
  if (isV2Path(pathname)) {
    // 已經是新版路徑：只把前綴改成標準寫法（/V2//courses → /v2/courses）
    const rest = toLegacyPath(pathname);
    return rest === '/' ? V2_BASE : `${V2_BASE}${rest}`;
  }
  const page = matchV2Page(pathname);
  if (!page) return V2_BASE;
  return page === '/' ? V2_BASE : `${V2_BASE}${page}`;
}

/** 新版路徑 → 舊版路徑（`/v2` 之後的部分原樣保留，只整理斜線）。 */
export function toLegacyPath(pathname: string): string {
  const path = normalizePath(pathname);
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
