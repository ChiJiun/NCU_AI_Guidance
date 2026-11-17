import { useLayoutEffect, useRef, type KeyboardEvent, type ReactNode } from 'react';

const ITEM = '[role="radio"], [role="tab"]';

type RovingGroupProps = {
  role: 'radiogroup' | 'tablist';
  children: ReactNode;
  className?: string;
  'aria-label'?: string;
};

const isSelected = (el: HTMLElement) => el.getAttribute('aria-checked') === 'true' || el.getAttribute('aria-selected') === 'true';

/**
 * radiogroup／tablist 的鍵盤操作（WAI-ARIA 的 roving tabindex）：
 * - 整組只有一個 Tab 停留點（目前選取的那一項）
 * - 方向鍵、Home、End 移動並直接選取
 * 子項目照常用 button + role="radio"/"tab" + aria-checked/aria-selected 寫即可。
 */
export default function RovingGroup({ role, children, className, ...aria }: RovingGroupProps) {
  const ref = useRef<HTMLDivElement>(null);

  // 每次 render 後依選取狀態更新 tabIndex（React 沒有管這些按鈕的 tabIndex，所以不會互相覆蓋）
  useLayoutEffect(() => {
    const items = [...(ref.current?.querySelectorAll<HTMLElement>(ITEM) ?? [])];
    const current = items.find(isSelected) ?? items[0];
    items.forEach((el) => {
      el.tabIndex = el === current ? 0 : -1;
    });
  });

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = [...(ref.current?.querySelectorAll<HTMLElement>(ITEM) ?? [])].filter(
      (el) => !(el as HTMLButtonElement).disabled,
    );
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (index < 0 || items.length === 0) return;
    let next = -1;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % items.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + items.length) % items.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = items.length - 1;
    if (next < 0) return;
    event.preventDefault();
    items[next].focus();
    items[next].click();
  };

  return (
    <div ref={ref} role={role} className={className} onKeyDown={onKeyDown} {...aria}>
      {children}
    </div>
  );
}
