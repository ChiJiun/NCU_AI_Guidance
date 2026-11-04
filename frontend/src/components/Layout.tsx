import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Navbar from './Navbar';
import DemoBanner from './DemoBanner';

interface LayoutProps {
  fullHeight?: boolean;
  noPad?: boolean;
}

const BACKGROUND_THEMES = [
  'bg-theme-1',
  'bg-theme-2',
  'bg-theme-3',
  'bg-theme-4',
  'bg-theme-5',
  'bg-theme-6',
  'bg-theme-7',
  'bg-theme-8',
  'bg-theme-9',
  'bg-theme-10',
];

export default function Layout({ fullHeight = false, noPad = false }: LayoutProps) {
  const location = useLocation();
  const [backgroundIndex, setBackgroundIndex] = useState(0);
  const backgroundClass = useMemo(() => BACKGROUND_THEMES[backgroundIndex % BACKGROUND_THEMES.length], [backgroundIndex]);
  const isHome = location.pathname === '/';

  const handleBackgroundClick = (event: React.MouseEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget) return;
    setBackgroundIndex((prev) => (prev + 1) % BACKGROUND_THEMES.length);
  };

  // 讓 HomePage footer 的換色按鈕可以觸發背景切換
  useEffect(() => {
    const handler = () => setBackgroundIndex((prev) => (prev + 1) % BACKGROUND_THEMES.length);
    document.addEventListener('cycle-background', handler);
    return () => document.removeEventListener('cycle-background', handler);
  }, []);

  return (
    <div
      className={`${noPad ? 'bg-slate-950' : backgroundClass} ${fullHeight ? 'flex h-screen flex-col overflow-hidden' : 'min-h-screen'} transition-colors duration-500`}
      onClick={noPad ? undefined : handleBackgroundClick}
    >
      <Navbar />
      <DemoBanner />
      <main
        className={fullHeight ? 'flex-1 overflow-hidden' : noPad ? '' : isHome ? '' : 'page-container py-8'}
        onClick={noPad ? undefined : handleBackgroundClick}
      >
        <div key={location.pathname} className={`page-animate ${fullHeight ? 'h-full' : ''}`}>
          <Outlet />
        </div>
      </main>
      {/* 首頁 footer 由 HomePage 自行管理；其他一般頁面顯示此 footer */}
      {!isHome && !noPad && !fullHeight ? (
        <footer className="mt-20 border-t border-white/70 bg-white/75 py-8 backdrop-blur">
          <div className="page-container text-center text-sm text-slate-600">
            <p>© 2026 國立中央大學科系探索平台</p>
          </div>
        </footer>
      ) : null}
    </div>
  );
}
