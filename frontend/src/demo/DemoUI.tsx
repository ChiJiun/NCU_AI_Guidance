import { HiChatAlt2, HiSparkles } from 'react-icons/hi';
import { CATEGORY_STYLES, formatRecordedAt, type DemoCategory } from './demoCases';

export interface DemoListItem {
  id: string;
  title: string;
  category: DemoCategory;
  summary: string;
  reviewed: boolean;
  meta?: string;
}

export function DemoBadge({ className = '' }: { className?: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ${className}`}
    >
      <HiSparkles className="h-3 w-3" />
      展示版
    </span>
  );
}

export function CategoryChip({ category }: { category: DemoCategory }) {
  return (
    <span className={`inline-flex shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${CATEGORY_STYLES[category]}`}>
      {category}
    </span>
  );
}

export function DemoCaseList({
  items,
  selectedId,
  onSelect,
}: {
  items: DemoListItem[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  if (items.length === 0) {
    return <p className="p-4 text-center text-xs text-slate-400">示範對話準備中</p>;
  }
  return (
    <div className="flex-1 space-y-2 overflow-y-auto p-3">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onSelect(item.id)}
          className={`w-full rounded-2xl border p-3 text-left transition ${
            selectedId === item.id
              ? 'border-primary-300 bg-primary-50'
              : 'border-transparent bg-white hover:border-slate-200 hover:bg-slate-50'
          }`}
        >
          <div className="flex items-center gap-1.5">
            <CategoryChip category={item.category} />
            {!item.reviewed && (
              <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">未審核</span>
            )}
          </div>
          <h3 className="mt-1.5 line-clamp-2 text-sm font-semibold text-slate-900">{item.title}</h3>
          <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{item.meta ?? item.summary}</p>
        </button>
      ))}
    </div>
  );
}

/** 放在示範對話最上方，清楚標示這不是即時生成的回答。 */
export function DemoResultBanner({
  recordedAt,
  summary,
  reviewed,
}: {
  recordedAt: string;
  summary: string;
  reviewed: boolean;
}) {
  const date = formatRecordedAt(recordedAt);
  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-900">
      <p className="font-semibold">預先產生的示範結果</p>
      <p className="mt-0.5 text-amber-800">
        {summary && <>{summary}。</>}
        以下內容由系統實際執行後錄製{date && `（${date}）`}{reviewed ? '並經人工檢查' : '，尚未人工檢查'}，展示期間不會即時呼叫 AI 模型。
      </p>
    </div>
  );
}

/** 取代輸入框：說明展示版不開放即時提問，並列出其他示範題目。 */
export function DemoComposerNotice({
  items,
  selectedId,
  onSelect,
}: {
  items: { id: string; question: string }[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const others = items.filter((i) => i.id !== selectedId).slice(0, 4);
  return (
    <div className="border-t border-gray-200 p-3">
      <div className="rounded-2xl bg-slate-50 px-4 py-3">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-600">
          <HiChatAlt2 className="h-4 w-4 text-slate-400" />
          展示版不開放即時提問，可以點選其他示範問題
        </p>
        {others.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {others.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelect(item.id)}
                className="max-w-full truncate rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-700 transition hover:border-primary-300 hover:bg-primary-50 hover:text-primary-800"
                title={item.question}
              >
                {item.question}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
