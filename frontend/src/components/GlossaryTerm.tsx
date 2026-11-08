import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

interface GlossaryTermProps {
  term:     string;
  gloss:    string;
  children: ReactNode;
}

const POPOVER_WIDTH = 256;
const EDGE_GAP      = 8;

interface Position { left: number; top: number }

/**
 * 回答中的術語：虛線底線，電腦上滑過去、手機上點一下會出現白話說明。
 * 提示框用 portal 貼在畫面最上層，不會被表格或捲動區切掉，並限制在螢幕範圍內。
 */
export default function GlossaryTerm({ term, gloss, children }: GlossaryTermProps) {
  const id = useId();
  const buttonRef  = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [open, setOpen]     = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pos, setPos]       = useState<Position | null>(null);

  const close = useCallback(() => { setOpen(false); setPinned(false); }, []);

  const place = useCallback(() => {
    const btn = buttonRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const width  = Math.min(POPOVER_WIDTH, window.innerWidth - EDGE_GAP * 2);
    const height = popoverRef.current?.offsetHeight ?? 0;
    const left = Math.min(Math.max(r.left + r.width / 2 - width / 2, EDGE_GAP), window.innerWidth - width - EDGE_GAP);
    const below = r.bottom + 6;
    const top = below + height > window.innerHeight - EDGE_GAP && r.top - 6 - height > EDGE_GAP
      ? r.top - 6 - height
      : below;
    setPos({ left, top });
  }, []);

  useLayoutEffect(() => {
    if (open) place();
    else setPos(null);
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!buttonRef.current?.contains(target) && !popoverRef.current?.contains(target)) close();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    window.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('keydown', onKey);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', close, true);   // 捲動時收起，避免提示框和文字錯位
    return () => {
      window.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', close, true);
    };
  }, [open, close, place]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => { if (open && pinned) close(); else { setOpen(true); setPinned(true); } }}
        onPointerEnter={(e) => { if (e.pointerType === 'mouse') setOpen(true); }}
        onPointerLeave={(e) => { if (e.pointerType === 'mouse' && !pinned) setOpen(false); }}
        onFocus={() => setOpen(true)}
        onBlur={() => { if (!pinned) setOpen(false); }}
        className="m-0 inline cursor-help appearance-none border-0 bg-transparent p-0 text-left font-[inherit] text-inherit underline decoration-primary-400 decoration-dotted decoration-2 underline-offset-[3px] hover:bg-primary-50 focus-visible:rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-400"
      >
        {children}
      </button>
      {open && createPortal(
        <div
          id={id}
          ref={popoverRef}
          role="tooltip"
          style={{
            position: 'fixed',
            left: pos?.left ?? -9999,
            top: pos?.top ?? -9999,
            width: Math.min(POPOVER_WIDTH, window.innerWidth - EDGE_GAP * 2),
          }}
          className="pointer-events-none z-[1000] rounded-lg bg-white px-3 py-2 text-xs leading-relaxed text-gray-700 shadow-lg ring-1 ring-black/10"
        >
          <div className="font-semibold text-gray-900">{term}</div>
          <div className="mt-0.5">{gloss}</div>
          <div className="mt-1 text-[10px] text-gray-400">AI 整理的白話說明，僅供參考</div>
        </div>,
        document.body,
      )}
    </>
  );
}
