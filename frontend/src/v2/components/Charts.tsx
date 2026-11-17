import type { ReactNode } from 'react';

/**
 * 新版的輕量圖表（純 HTML/CSS，不載入 ECharts）：個人分析與系統監控共用。
 * 只用墨色與灰階，朱紅保留給「你在這裡」。
 */

export interface StatItem {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}

/** 一排大數字：數字在上、名稱在下（dt/dd 語意，畫面上用 flex-col-reverse 反過來） */
export function StatRow({ items, className = '' }: { items: StatItem[]; className?: string }) {
  return (
    <dl className={`grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4 ${className}`}>
      {items.map((item) => (
        <div key={item.label} className="flex min-w-0 flex-col-reverse">
          <dt className="v2-muted text-sm">
            {item.label}
            {item.sub != null && item.sub !== '' && <span className="v2-faint block text-xs">{item.sub}</span>}
          </dt>
          <dd className="v2-num truncate text-3xl leading-tight">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export interface BarItem {
  label: string;
  value: number;
  /** 右側顯示的文字，預設是 value */
  display?: ReactNode;
}

/** 由大到小的橫條清單（呼叫端負責排序） */
export function BarList({ items, empty = '尚無資料' }: { items: BarItem[]; empty?: string }) {
  if (items.length === 0) return <p className="v2-faint text-sm">{empty}</p>;
  const max = Math.max(...items.map((item) => item.value), 0) || 1;
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.label}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 truncate">{item.label}</span>
            <span className="v2-num flex-none">{item.display ?? item.value.toLocaleString()}</span>
          </div>
          <div className="v2-bar mt-1" aria-hidden="true">
            <span style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export interface ColumnSeries {
  name: string;
  values: number[];
  /** 'ink' 深色、'soft' 淺色 */
  tone?: 'ink' | 'soft';
}

const TONE_COLOR = { ink: 'var(--v2-ink)', soft: 'var(--v2-line-2)' } as const;

/**
 * 直條圖（時間序列）。多個系列時預設堆疊；labels 太多時只標示一部分。
 * 每根柱子的 title 會列出各系列的數值，滑鼠停留可看。
 */
export function Columns({
  labels,
  series,
  format = (value: number) => value.toLocaleString(),
  height = 140,
  label,
  empty = '尚無資料',
}: {
  labels: string[];
  series: ColumnSeries[];
  format?: (value: number) => string;
  height?: number;
  /** 圖表的無障礙名稱 */
  label: string;
  empty?: string;
}) {
  const totals = labels.map((_, index) => series.reduce((sum, s) => sum + (s.values[index] ?? 0), 0));
  const max = Math.max(...totals, 0);
  if (labels.length === 0 || max <= 0) return <p className="v2-faint py-6 text-sm">{empty}</p>;

  const every = Math.max(1, Math.ceil(labels.length / 6));
  return (
    <figure aria-label={label} className="m-0">
      <div className="flex items-end gap-px border-b" style={{ height, borderColor: 'var(--v2-line-2)' }}>
        {labels.map((name, index) => {
          const title = [name, ...series.map((s) => `${s.name} ${format(s.values[index] ?? 0)}`)].join('\n');
          return (
            <div key={`${name}-${index}`} className="flex h-full min-w-0 flex-1 flex-col-reverse" title={title}>
              {series.map((s) => {
                const value = s.values[index] ?? 0;
                if (value <= 0) return null;
                return (
                  <span
                    key={s.name}
                    className="block w-full"
                    style={{ height: `${(value / max) * 100}%`, background: TONE_COLOR[s.tone ?? 'ink'] }}
                  />
                );
              })}
            </div>
          );
        })}
      </div>
      {/* overflow-hidden：最後一個標籤可能比柱子寬，不能把頁面撐出水平捲軸 */}
      <div className="v2-faint mt-1 flex gap-px overflow-hidden text-[0.6875rem] tabular-nums" aria-hidden="true">
        {labels.map((name, index) => (
          <span key={`${name}-${index}`} className="min-w-0 flex-1 overflow-visible whitespace-nowrap">
            {index % every === 0 ? name : ''}
          </span>
        ))}
      </div>
      {series.length > 1 && (
        <figcaption className="v2-muted mt-2 flex flex-wrap gap-x-4 text-xs">
          {series.map((s) => (
            <span key={s.name} className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-3" style={{ background: TONE_COLOR[s.tone ?? 'ink'] }} aria-hidden="true" />
              {s.name}
            </span>
          ))}
        </figcaption>
      )}
    </figure>
  );
}

/** 區塊標題（細線上方的小標），讓版面自己分組 */
export function Block({ title, aside, children, className = '' }: { title: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={className}>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t pt-3" style={{ borderColor: 'var(--v2-ink)' }}>
        <h2 className="font-semibold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
