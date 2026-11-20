import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation } from 'react-router-dom';
import { HiMenu, HiX, HiUser, HiChartBar, HiLogout, HiLogin } from 'react-icons/hi';
import logo from '../assets/NCULogo.png';
import GoogleLoginButton from './GoogleLoginButton';
import { useAuth, type AuthUser } from '../auth/AuthContext';
import { isDeveloper } from '../auth/developerUtils';
import { switchVersionHref } from '../v3/paths';
import { useDemoView } from '../hooks/useDemoView';

const navItems = [
  { path: '/', label: '首頁' },
  { path: '/assessment', label: '興趣量表' },
  { path: '/curriculum', label: '系所修課' },
  { path: '/courses', label: '課程資訊' },
  { path: '/course-search', label: '課程助理' },
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
  v2Href,
  v3Href,
  onClose,
  user,
  isDev,
  onLogout,
  onLogin,
  showVersionSwitch,
  showDemoProfile,
}: {
  pathname: string;
  /** v2（/v2）的對應頁面 */
  v2Href: string;
  /** v3（/v3）的對應頁面 */
  v3Href: string;
  onClose: () => void;
  user: AuthUser | null;
  isDev: boolean;
  onLogout: () => void;
  onLogin: () => Promise<void>;
  /** 展示版對外時不顯示新版／v3 切換 */
  showVersionSwitch: boolean;
  /** 展示版的訪客：顯示示範學生入口與團隊登入 */
  showDemoProfile: boolean;
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
            {showVersionSwitch && (
              <>
                <Link
                  to={v2Href}
                  onClick={onClose}
                  className="block w-full self-stretch px-4 py-4 text-base font-medium text-slate-500 transition hover:bg-slate-50"
                >
                  切換到新版 v2
                </Link>
                <Link
                  to={v3Href}
                  onClick={onClose}
                  className="block w-full self-stretch px-4 py-4 text-base font-medium text-slate-500 transition hover:bg-slate-50"
                >
                  切換到 v3
                </Link>
              </>
            )}

            {/* 使用者區塊 */}
            {user ? (
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
            ) : showDemoProfile ? (
              <div className="mt-2 border-t border-slate-200 pt-4">
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
                  示範學生的個人分析
                  <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
                    示範
                  </span>
                </Link>
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    void onLogin().catch(() => {});
                  }}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left text-base font-medium text-slate-500 transition hover:bg-slate-50"
                >
                  <HiLogin className="h-5 w-5" />
                  團隊成員登入（Google）
                </button>
              </div>
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
  const { user, logout, loginWithGoogle } = useAuth();
  const isDev = isDeveloper(user?.email);
  const demoView = useDemoView();
  // 展示版對外時隱藏新版／v3 切換（開發團隊登入後照常顯示）；確認中先不顯示，避免出現後又消失
  const showVersionSwitch = !demoView.loading && (!demoView.demoSite || isDev);
  const showDemoProfile = demoView.demoSite && !user;

  // 依賴視窗高度的舊版版面會扣掉細橫條高度（index.css 的 --legacy-nav-strip），隱藏時要一併歸零
  useEffect(() => {
    const root = document.documentElement;
    if (showVersionSwitch) delete root.dataset.hideVersionSwitch;
    else root.dataset.hideVersionSwitch = 'true';
  }, [showVersionSwitch]);
  const v2Href = switchVersionHref(location.pathname, location.search, 'v2');
  const v3Href = switchVersionHref(location.pathname, location.search, 'v3');

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
        {/*
          768–1279px 的新版入口：導覽列這個寬度沒有多餘空間，改放在導覽列頂端的細橫條。
          它是 sticky 導覽列的一部分，不會疊在頁面內容上；舊版彈窗（後出現的 z-50）也會把它一起蓋住。
        */}
        {/* 高度（含下框線）由 index.css 的 --legacy-nav-strip 決定，依賴視窗高度的舊版版面會扣掉同一個值 */}
        <div className={`box-border hidden h-[var(--legacy-nav-strip)] border-b border-white/70 xl:hidden ${showVersionSwitch ? 'md:block' : ''}`}>
          <div className="page-container-wide flex h-full items-center justify-end">
            <Link to={v2Href} className="flex h-full items-center px-2 text-xs font-medium text-slate-500 transition hover:text-slate-900">
              切換到新版 →
            </Link>
            <Link to={v3Href} className="flex h-full items-center px-2 text-xs font-medium text-slate-500 transition hover:text-slate-900" title="切換到 v3 介面">
              v3 →
            </Link>
          </div>
        </div>
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
              {/* 1280px 以下導覽列沒有多餘寬度（已登入時更窄），放進來會讓其他項目換行，改用上面的細橫條 */}
              {showVersionSwitch && (
                <>
                  <Link to={v2Href} className="nav-chip hidden whitespace-nowrap px-2.5 xl:block" title="切換到新版介面">
                    新版
                  </Link>
                  <Link to={v3Href} className="nav-chip hidden whitespace-nowrap px-2.5 xl:block" title="切換到 v3 介面">
                    v3
                  </Link>
                </>
              )}
              <GoogleLoginButton />
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
          v2Href={v2Href}
          v3Href={v3Href}
          onClose={() => setIsMobileMenuOpen(false)}
          user={user}
          isDev={isDev}
          onLogout={logout}
          onLogin={loginWithGoogle}
          showVersionSwitch={showVersionSwitch}
          showDemoProfile={showDemoProfile}
        />
      ) : null}
    </>
  );
}
