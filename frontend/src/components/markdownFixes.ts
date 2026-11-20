// LLM 回答的 markdown 修正（課程助理用）。

// 程式碼區塊與行內程式碼不處理
const CODE = /(```[\s\S]*?```|`[^`\n]*`)/g;
const BOLD = /\*\*(?=\S)([^*\n]*?\S)\*\*/g;

/**
 * 把 `**粗體**` 先轉成 `<strong>`（需搭配 rehype-raw）。
 *
 * CommonMark 的強調規則對中文不友善：`**` 前後若是標點（「」、（）或我們插入的
 * `<mark>`／`<dfn>` 標籤）而另一側緊接中文字，就不算成對的強調符號，結果畫面上
 * 直接出現 `**`。例如 `修**<dfn>微積分</dfn>**的` 或 `**「程式設計」**是`。
 * 在插入課名／術語標記之前先轉成 HTML，就不受這條規則影響。
 */
export function normalizeBold(text: string): string {
  return text
    .split(CODE)
    .map((part, i) => (i % 2 === 1 ? part : part.replace(BOLD, '<strong>$1</strong>')))
    .join('');
}
