import { useState } from 'react';
import { HiChevronDown, HiChevronUp, HiBeaker, HiCheckCircle, HiXCircle } from 'react-icons/hi';
import type { DebugTrace } from '../types';
import { TOOL_LABELS } from '../constants/toolLabels';

interface DebugTracePanelProps {
  trace: DebugTrace;
}

function ArgBadge({ k, v }: { k: string; v: unknown }) {
  if (v === '' || v === null || v === undefined || v === false) return null;
  const display = typeof v === 'object' ? JSON.stringify(v) : String(v);
  return (
    <span className="inline-flex items-center gap-0.5 rounded-md bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
      <span className="text-slate-400">{k}=</span>
      <span className="font-mono">{display.length > 30 ? display.slice(0, 30) + '…' : display}</span>
    </span>
  );
}

export default function DebugTracePanel({ trace }: DebugTracePanelProps) {
  const [open, setOpen] = useState(false);
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set());

  const toggleTool = (i: number) =>
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(i)) { next.delete(i); } else { next.add(i); }
      return next;
    });

  const totalSelected = trace.verify?.selected.length ?? 0;
  const totalFiltered = trace.verify?.filteredOut.length ?? 0;

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1 text-xs text-gray-500 transition hover:border-primary-200 hover:bg-primary-50 hover:text-primary-700"
      >
        <HiBeaker className="h-3.5 w-3.5" />
        <span>推薦過程</span>
        <span className="ml-0.5 rounded-full bg-gray-100 px-1.5 py-0.5 text-xs text-gray-400">
          {trace.toolCalls.length} 個工具
          {trace.verify && ` · ${totalSelected} 門保留 / ${totalFiltered} 門過濾`}
        </span>
        {open ? <HiChevronUp className="h-3 w-3" /> : <HiChevronDown className="h-3 w-3" />}
      </button>

      {open && (
        <div className="mt-1.5 rounded-xl border border-gray-200 bg-white shadow-sm">
          {/* Tool Calls */}
          {trace.toolCalls.length > 0 && (
            <div className="border-b border-gray-100 p-3">
              <p className="mb-2 text-xs font-semibold text-gray-500">工具呼叫紀錄</p>
              <div className="space-y-1.5">
                {trace.toolCalls.map((t, i) => (
                  <div key={i} className="rounded-lg border border-gray-100 bg-gray-50">
                    <button
                      type="button"
                      onClick={() => toggleTool(i)}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left"
                    >
                      <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700">
                        {i + 1}
                      </span>
                      <span className="flex-1 text-xs font-medium text-gray-700">
                        {TOOL_LABELS[t.tool] ?? t.tool}
                        <span className="ml-1 font-mono text-gray-400">({t.tool})</span>
                      </span>
                      {t.count != null && (
                        <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">
                          {t.count} 筆
                        </span>
                      )}
                      {expandedTools.has(i) ? (
                        <HiChevronUp className="h-3.5 w-3.5 text-gray-400" />
                      ) : (
                        <HiChevronDown className="h-3.5 w-3.5 text-gray-400" />
                      )}
                    </button>

                    {expandedTools.has(i) && (
                      <div className="border-t border-gray-100 px-3 pb-2.5 pt-2">
                        {/* 參數 */}
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(t.args).map(([k, v]) => (
                            <ArgBadge key={k} k={k} v={v} />
                          ))}
                          {Object.keys(t.args).length === 0 && (
                            <span className="text-xs text-gray-400">（無參數）</span>
                          )}
                        </div>

                        {/* 找到的課程／學程 */}
                        {t.coursesFound.length > 0 && (
                          <div className="mt-2">
                            <p className="mb-1 text-xs text-gray-400">
                              {t.tool === 'search_programs' ? '找到的學程' : '找到的課程'}（共 {t.coursesFound.length} {t.tool === 'search_programs' ? '個' : '門'}）
                              {t.scoreType === 'distance' && <span className="ml-1 text-gray-400">· dist 越小越相似</span>}
                              {t.scoreType === 'shared_concepts' && <span className="ml-1 text-gray-400">· c= 共享概念數</span>}
                              {t.scoreType === 'ppr' && <span className="ml-1 text-gray-400">· ppr= PPR×1000</span>}
                            </p>
                            <div className="flex flex-wrap gap-1">
                              {t.coursesFound.map((name, j) => {
                                const sc = t.scores?.[j];
                                const label =
                                  t.scoreType === 'distance'        ? `d=${sc?.toFixed(2)}`
                                  : t.scoreType === 'shared_concepts' ? `c=${sc}`
                                  : t.scoreType === 'ppr'            ? `ppr=${sc}`
                                  : null;
                                return (
                                  <span key={j} className="inline-flex items-center gap-0.5 rounded-md bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700">
                                    {name}
                                    {label != null && sc != null && (
                                      <span className="ml-0.5 text-blue-400">{label}</span>
                                    )}
                                  </span>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Verify Section */}
          {trace.verify && (
            <div className="p-3">
              <p className="mb-2 text-xs font-semibold text-gray-500">
                課程提取
                <span className="ml-1 rounded bg-gray-100 px-1 py-0.5 text-xs font-mono text-gray-400">
                  {trace.verify.method === 'tag' ? '<course> 標籤' : 'LLM 篩選'}
                </span>
                <span className="ml-1 font-normal text-gray-400">（從 {trace.verify.poolSize} 門課中選出）</span>
              </p>

              {/* 保留的課程 */}
              {trace.verify.selected.length > 0 && (
                <div className="mb-2">
                  <div className="mb-1 flex items-center gap-1 text-xs text-green-600">
                    <HiCheckCircle className="h-3.5 w-3.5" />
                    保留 {trace.verify.selected.length} 門
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {trace.verify.selected.map((name, i) => (
                      <span key={i} className="rounded-md bg-green-50 px-1.5 py-0.5 text-xs text-green-700">
                        {name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 過濾掉的課程 */}
              {trace.verify.filteredOut.length > 0 && (
                <div>
                  <div className="mb-1 flex items-center gap-1 text-xs text-gray-400">
                    <HiXCircle className="h-3.5 w-3.5" />
                    過濾 {trace.verify.filteredOut.length} 門（與問題不相關）
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {trace.verify.filteredOut.slice(0, 12).map((name, i) => (
                      <span key={i} className="rounded-md bg-gray-100 px-1.5 py-0.5 text-xs text-gray-400 line-through">
                        {name}
                      </span>
                    ))}
                    {trace.verify.filteredOut.length > 12 && (
                      <span className="text-xs text-gray-400">…還有 {trace.verify.filteredOut.length - 12} 門</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
