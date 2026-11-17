/**
 * 示範案例內頁的純函式（不依賴 React，方便用 node --test 測試）。
 * 內容逐字搬自舊版 DemoCasePage，新舊版共用。
 */
import { TOOL_LABELS } from '../../constants/toolLabels.ts';
import type { DemoStep, DemoTurn } from '../../demo/types';
import type { DebugTrace } from '../../types';

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-TW', { dateStyle: 'medium', timeStyle: 'short' });
}

export function sourceLabel(src: unknown): string {
  if (typeof src === 'string') return src;
  if (src && typeof src === 'object') {
    const o = src as Record<string, unknown>;
    const text = o.title ?? o.name ?? o.source ?? o.page_content;
    const page = o.page ?? (o.metadata as Record<string, unknown> | undefined)?.page;
    if (text) return page != null ? `${String(text)}（第 ${String(page)} 頁）` : String(text);
    return JSON.stringify(src);
  }
  return String(src);
}

export function stepLabel(step: DemoStep): string {
  if (step.kind === 'verify') {
    const kept = step.selected?.length ?? 0;
    return `驗證推薦課程：從 ${step.pool_size ?? '?'} 門候選中保留 ${kept} 門`;
  }
  const name = TOOL_LABELS[step.tool] ?? step.tool;
  return step.count != null ? `${name}（找到 ${step.count} 筆）` : name;
}

export function toDebugTrace(turn: DemoTurn): DebugTrace | null {
  const toolCalls = turn.debug_trace?.toolCalls ?? [];
  const verifyStep = turn.steps?.find((s): s is Extract<DemoStep, { kind: 'verify' }> => s.kind === 'verify');
  const verify = verifyStep
    ? {
        poolSize: verifyStep.pool_size ?? 0,
        selected: verifyStep.selected ?? [],
        filteredOut: verifyStep.filtered_out ?? [],
        method: verifyStep.method,
      }
    : null;
  if (toolCalls.length === 0 && !verify) return null;
  return { toolCalls, verify };
}
