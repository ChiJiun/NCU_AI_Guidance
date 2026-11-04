import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation } from 'react-router-dom';
import { HiMenu, HiX, HiUser, HiChartBar, HiLogout } from 'react-icons/hi';
import logo from '../assets/NCULogo.png';
import GoogleLoginButton from './GoogleLoginButton';
import { useAuth, type AuthUser } from '../auth/AuthContext';
import { isDeveloper } from '../auth/developerUtils';
import { DEMO_MODE } from '../demo/config';

const navItems = [
  { path: '/', label: '首頁' },
  { path: '/assessment', label: '興趣量表' },
  { path: '/curriculum', label: '系所修課' },
  { path: '/courses', label: '課程資訊' },
  // 展示模式：課程助理不開放即時提問，改連到 AI 示範案例
  DEMO_MODE ? { path: '/demo', label: 'AI 示範' } : { path: '/course-search', label: '課程助理' },
  { path: '/projects', label: '研究計畫' },
  { path: '/resources', label: '資源連結' },
];

function Avatar({ picture, name }: { picture: string; name: string }) {
  if (picture) {
    return <img src={picture} alt={name} className="h-8 w-8 rounded-full object-cover" />;
  }
  return (
    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-600 text-sm font-bold text-white">
      {name?.[0]?.toUpperCase() ?? 'U'}
    </div>
  );
}

function MobileMenuOverlay({
  pathname,
  onClose,
  user,
  isDev,
  onLogout,
}: {
  pathname: string;
  onClose: () => void;
  user: AuthUser | null;
  isDev: boolean;
  onLogout: () => void;
}) {
  return createPortal(
    <div className="fixed inset-0 z-[9999] bg-transparent md:hidden">
      <div className="w-full overflow-hidden border-b border-slate-200 bg-white shadow-2xl">
        <div className="flex h-16 items-center justify-between px-4">
          <Link to="/" className="flex items-center space-x-3" onClick={onClose}>
            <img src={logo} alt="國立中央大學科系探索平台" className="h-10 w-10 object-contain" />
          </Link>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            aria-label="關閉導覽選單"
          >
            <HiX className="h-7 w-7" />
          </button>
        </div>

        <div className="w-full max-h-[calc(100vh-5rem)] overflow-y-auto border-t border-slate-200 bg-white px-4 py-4">
          <div className="flex w-full flex-col items-stretch gap-2">
            {/* 主要導覽 */}
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={onClose}
                className={`block w-full self-stretch px-4 py-4 text-base font-medium transition ${
                  pathname === item.path
                    ? 'bg-primary-900 text-white'
                    : 'bg-white text-slate-800 hover:bg-slate-50'
                }`}
              >
                {item.label}
              </Link>
            ))}

            {/* 使用者區塊（展示模式不提供登入） */}
            {DEMO_MODE ? null : user ? (
              <>
                <div className="mt-2 border-t border-slate-200 pt-4">
                  {/* 使用者資訊 */}
                  <div className="mb-2 flex items-center gap-3 rounded-xl bg-slate-50 px-4 py-3">
                    <Avatar picture={user.picture} name={user.name} />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-800">{user.name}</p>
                      <p className="truncate text-xs text-slate-400">{user.email}</p>
                    </div>
                  </div>

                  <Link
                    to="/profile"
                    onClick={onClose}
                    className={`flex items-center gap-3 w-full px-4 py-3 text-base font-medium transition ${
                      pathname === '/profile'
                        ? 'bg-primary-900 text-white'
                        : 'text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <HiUser className="h-5 w-5" />
                    個人分析
                  </Link>

                  {isDev && (
                    <Link
                      to="/monitor"
                      onClick={onClose}
                      className={`flex items-center gap-3 w-full px-4 py-3 text-base font-medium transition ${
                        pathname === '/monitor'
                          ? 'bg-primary-900 text-white'
                          : 'text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      <HiChartBar className="h-5 w-5" />
                      系統監控
                      <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
                        Dev
                      </span>
                    </Link>
                  )}

                  <button
                    type="button"
                    onClick={() => {
                      onLogout();
                      onClose();
                    }}
                    className="flex w-full items-center gap-3 px-4 py-3 text-base font-medium text-red-500 transition hover:bg-red-50"
                  >
                    <HiLogout className="h-5 w-5" />
                    登出
                  </button>
                </div>
              </>
            ) : (
              <div className="mt-2 border-t border-slate-200 pt-4">
                <GoogleLoginButton />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

export default function Navbar() {
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const { user, logout } = useAuth();
  const isDev = isDeveloper(user?.email);

  useEffect(() => {
    void (async () => { await Promise.resolve(); setIsMobileMenuOpen(false); })();
  }, [location.pathname]);

  useEffect(() => {
    if (!isMobileMenuOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isMobileMenuOpen]);

  return (
    <>
      <nav className="sticky top-0 z-50 border-b border-white/70 bg-white/80 backdrop-blur-xl">
        <div className="page-container-wide">
          <div className="flex h-16 items-center justify-between">
            <Link to="/" className="flex items-center space-x-3 transition duration-200 hover:-translate-y-0.5">
              <img src={logo} alt="國立中央大學科系探索平台" className="h-10 w-10 object-contain" />
              <div className="hidden sm:block">
                <div className="text-sm font-bold text-primary-900">國立中央大學</div>
                <div className="text-xs text-slate-500">科系探索平台</div>
              </div>
            </Link>

            {/* 桌面版導覽 */}
            <div className="hidden items-center space-x-1 md:flex">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`nav-chip ${location.pathname === item.path ? 'nav-chip-active' : ''}`}
                >
                  {item.label}
                </Link>
              ))}
              {!DEMO_MODE && <GoogleLoginButton />}
            </div>

            {/* 手機版漢堡按鈕 */}
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen((prev) => !prev)}
              className="rounded-xl p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 md:hidden"
              aria-label={isMobileMenuOpen ? '關閉導覽選單' : '開啟導覽選單'}
              aria-expanded={isMobileMenuOpen}
            >
              {isMobileMenuOpen ? <HiX className="h-6 w-6" /> : <HiMenu className="h-6 w-6" />}
            </button>
          </div>
        </div>
      </nav>

      {isMobileMenuOpen ? (
        <MobileMenuOverlay
          pathname={location.pathname}
          onClose={() => setIsMobileMenuOpen(false)}
          user={user}
          isDev={isDev}
          onLogout={logout}
        />
      ) : null}
    </>
  );
}
