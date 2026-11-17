import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

type V2DialogProps = {
  onClose: () => void;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  'aria-label'?: string;
  'aria-labelledby'?: string;
};

/**
 * 新版的 modal 對話框本體（外層的定位與背景遮罩由呼叫端決定）：
 * - 打開時焦點移進對話框（裡面已有 autoFocus 或其他元件搶先 focus 時不動它）
 * - Tab／Shift+Tab 只在對話框內循環
 * - Esc 關閉
 * - 關閉後焦點回到打開它的按鈕
 */
export default function V2Dialog({ onClose, children, className, style, ...aria }: V2DialogProps) {
  const ref = useRef<HTMLDivElement>(null);
  // 第一次 render 時（commit 之前）記下打開它的元素；autoFocus 會在 commit 時就把焦點移走
  const [opener] = useState(() => (typeof document === 'undefined' ? null : (document.activeElement as HTMLElement | null)));
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (!dialog.contains(document.activeElement)) {
      (dialog.querySelector<HTMLElement>(FOCUSABLE) ?? dialog).focus();
    }

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null);
      if (items.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!dialog.contains(active)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && (active === first || active === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (opener && opener.isConnected) opener.focus();
    };
  }, [opener]);

  return (
    <div ref={ref} role="dialog" aria-modal="true" tabIndex={-1} className={className} style={{ outline: 'none', ...style }} {...aria}>
      {children}
    </div>
  );
}
