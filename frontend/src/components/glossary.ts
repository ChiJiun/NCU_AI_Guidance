// 名詞白話詞庫的比對：在回答文字裡找出詞庫中的術語，換成 <dfn> 標記，由 GlossaryTerm 顯示提示框。
// 純函式、不依賴 React，方便單獨測試（frontend/tests/glossary.test.ts）。

export interface GlossaryHit {
  surface: string;
  gloss:   string;
}

export interface GlossaryMatcher {
  pattern: RegExp | null;
  glosses: Record<string, string>;
}

// 這些片段裡的字不標：程式碼、課名標籤與課名按鈕、Markdown 連結、網址、HTML 標籤。
// 串流中尚未閉合的 ``` 也一併保護到結尾，避免半截程式碼被標。
const PROTECTED = new RegExp(
  [
    '```[\\s\\S]*?```',
    '```[\\s\\S]*$',
    '`[^`\\n]*`',
    '<course>[\\s\\S]*?</course>',
    '<mark\\b[^>]*>[\\s\\S]*?</mark>',
    '!?\\[[^\\]]*\\]\\([^)]*\\)',
    'https?://\\S+',
    '<[^>]+>',
  ].join('|'),
  'g',
);

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function createMatcher(glosses: Record<string, string>): GlossaryMatcher {
  const surfaces = Object.keys(glosses).sort((a, b) => b.length - a.length);   // 長詞優先，避免「音韻」吃掉「音韻學」
  if (surfaces.length === 0) return { pattern: null, glosses };
  const parts = surfaces.map((s) => {
    const body = escapeRegExp(s);
    // 英文縮寫（SVM、GRU）不可出現在較長的英數字串中間
    return /^[\x20-\x7e]+$/.test(s) ? `(?<![A-Za-z0-9])${body}(?![A-Za-z0-9])` : body;
  });
  return { pattern: new RegExp(parts.join('|'), 'g'), glosses };
}

/**
 * 把回答中的術語換成 `<dfn data-gi="N">寫法</dfn>`。每個詞（含別名）只標第一次出現的位置。
 * 回傳新文字與命中清單，data-gi 即清單的索引。
 */
export function injectGlossary(text: string, matcher: GlossaryMatcher): { text: string; hits: GlossaryHit[] } {
  const hits: GlossaryHit[] = [];
  if (!matcher.pattern || !text) return { text, hits };
  const seen = new Set<string>();
  const pattern = matcher.pattern;

  const annotate = (chunk: string): string =>
    chunk.replace(pattern, (surface) => {
      const gloss = matcher.glosses[surface];
      if (!gloss || seen.has(gloss)) return surface;
      seen.add(gloss);   // 以說明為鍵：同一個詞的不同寫法只標一次
      hits.push({ surface, gloss });
      return `<dfn data-gi="${hits.length - 1}">${surface}</dfn>`;
    });

  let out = '';
  let last = 0;
  for (const m of text.matchAll(PROTECTED)) {
    const start = m.index ?? 0;
    out += annotate(text.slice(last, start)) + m[0];
    last = start + m[0].length;
  }
  out += annotate(text.slice(last));
  return { text: out, hits };
}
