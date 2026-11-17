import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { HiChartBar, HiLogout, HiMenu, HiUser, HiX } from 'react-icons/hi';
import logo from '../../assets/NCULogo.png';
import { useAuth } from '../../auth/AuthContext';
import { isDeveloper } from '../../auth/developerUtils';
import GoogleLoginButton from '../../components/GoogleLoginButton';
import { switchVersionHref, toV1Path, v3Link, type SiteVersion } from '../paths';

/** v3 已有的頁面（資訊架構與 v2 相同） */
const PRIMARY_LINKS = [
  { to: '/assessment', label: '興趣量表' },
  { to: '/curriculum', label: '系所修課' },
  { to: '/courses', label: '課程' },
  { to: '/course-search', label: '課程助理' },
];

/** 尚未改版、連回舊版的頁面 */
const LEGACY_LINKS = [
  { to: '/projects', label: '研究計畫' },
  { to: '/resources', label: '資源' },
];

/** 工具型頁面：佔滿視窗高度，內容區自己捲動 */
const APP_PAGES = ['/courses', '/course-search', '/curriculum'];

const VERSIONS: { id: SiteVersion; title: string }[] = [
  { id: 'v1', title: '舊版介面' },
  { id: 'v2', title: '新版介面（v2）' },
  { id: 'v3', title: '目前的介面（v3）' },
];

/** Esc 或點到外面時關閉 */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [open, close]);
  return ref;
}

/** 三版切換：停在同一頁並保留查詢字串 */
function VersionSwitch({ pathname, search }: { pathname: string; search: string }) {
  return (
    <nav aria-label="切換介面版本" className="v3-versions">
      {VERSIONS.map((version) =>
        version.id === 'v3' ? (
          <span key={version.id} aria-current="page" title={version.title}>
            {version.id}
          </span>
        ) : (
          <Link key={version.id} to={switchVersionHref(pathname, search, version.id)} title={`切換到${version.title}`}>
            {version.id}
          </Link>
        ),
      )}
    </nav>
  );
}

/** 手機選單裡的帳號區塊（< 640px 導覽列放不下登入鈕，比照舊版放進選單） */
function MobileAccount() {
  const { user, logout } = useAuth();
  if (!user) {
    return (
      <div className="px-4 py-3">
        <GoogleLoginButton />
      </div>
    );
  }
  return (
    <>
      <div className="flex items-center gap-3 px-5 py-3">
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-slate-800">{user.name}</span>
          <span className="block truncate text-xs text-slate-500">{user.email}</span>
        </span>
      </div>
      <Link to="/profile" className="v3-menu-row">
        <HiUser className="h-5 w-5 text-slate-400" aria-hidden="true" />
        個人分析
      </Link>
      {isDeveloper(user.email) && (
        <Link to="/monitor" className="v3-menu-row">
          <HiChartBar className="h-5 w-5 text-slate-400" aria-hidden="true" />
          系統監控
        </Link>
      )}
      <button type="button" className="v3-menu-row !text-red-700" onClick={() => void logout()}>
        <HiLogout className="h-5 w-5" aria-hidden="true" />
        登出
      </button>
    </>
  );
}

export default function V3Layout() {
  const { pathname, search } = useLocation();
  // 記下「在哪一頁打開選單」：換頁後自然關閉，不需要在 effect 裡同步狀態
  const [menuOpenAt, setMenuOpenAt] = useState<string | null>(null);
  const menuOpen = menuOpenAt === pathname;
  const menuRef = useDismiss(menuOpen, () => setMenuOpenAt(null));
  const isApp = APP_PAGES.includes(toV1Path(pathname));

  return (
    <div className={`v2 v3 ${isApp ? 'v2--app' : ''}`}>
      <a href="#v3-main" className="v2-skip">
        跳到主要內容
      </a>

      <header className="v3-nav" ref={menuRef}>
        <div className="page-container-wide flex h-full items-center gap-2">
          <Link to={v3Link('/')} className="mr-2 flex min-h-11 flex-none items-center gap-3" aria-label="國立中央大學科系探索平台 首頁">
            <img src={logo} alt="" className="h-10 w-10 object-contain" />
            <span className="hidden leading-tight sm:block">
              <span className="block text-sm font-bold text-primary-900">國立中央大學</span>
              <span className="block text-xs text-slate-500">科系探索平台</span>
            </span>
          </Link>

          <nav aria-label="主要導覽" className="hidden items-center gap-1 lg:flex">
            {PRIMARY_LINKS.map((item) => (
              <NavLink
                key={item.to}
                to={v3Link(item.to)}
                className={({ isActive }) => `nav-chip whitespace-nowrap !px-3.5 ${isActive ? 'nav-chip-active' : ''}`}
              >
                {item.label}
              </NavLink>
            ))}
            <span className="mx-1.5 h-4 w-px bg-slate-300" aria-hidden="true" />
            {LEGACY_LINKS.map((item) => (
              <Link key={item.to} to={item.to} className="nav-chip whitespace-nowrap !px-3.5">
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <VersionSwitch pathname={pathname} search={search} />
            <div className="hidden sm:block">
              <GoogleLoginButton />
            </div>
            <button
              type="button"
              className="v3-menubtn lg:!hidden"
              aria-label={menuOpen ? '關閉選單' : '開啟選單'}
              aria-expanded={menuOpen}
              aria-controls="v3-mobile-menu"
              onClick={() => setMenuOpenAt(menuOpen ? null : pathname)}
            >
              {menuOpen ? <HiX className="h-6 w-6" aria-hidden="true" /> : <HiMenu className="h-6 w-6" aria-hidden="true" />}
            </button>
          </div>
        </div>

        {menuOpen && (
          <div id="v3-mobile-menu" className="v3-mobile-menu lg:hidden">
            <nav aria-label="主要導覽" className="flex flex-col gap-1 p-3">
              {PRIMARY_LINKS.map((item) => (
                <NavLink key={item.to} to={v3Link(item.to)} className="v3-menu-row">
                  {item.label}
                </NavLink>
              ))}
              {LEGACY_LINKS.map((item) => (
                <Link key={item.to} to={item.to} className="v3-menu-row !font-normal !text-slate-500">
                  {item.label}
                </Link>
              ))}
            </nav>
            <div className="border-t border-slate-200 py-2 sm:hidden">
              <MobileAccount />
            </div>
          </div>
        )}
      </header>

      {/* tabIndex=-1：skip link 跳過來時焦點真的會移到主要內容 */}
      <main id="v3-main" tabIndex={-1} className={`outline-none ${isApp ? 'min-h-0 flex-1' : ''}`}>
        <Outlet />
      </main>
    </div>
  );
}
