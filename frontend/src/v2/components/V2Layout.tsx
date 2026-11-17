import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { HiLogout, HiMenu, HiX } from 'react-icons/hi';
import logo from '../../assets/NCULogo.png';
import { useAuth } from '../../auth/AuthContext';
import { isDeveloper } from '../../auth/developerUtils';
import { GoogleMark } from '../../components/GoogleLoginButton';
import { toLegacyPath, v2Link } from '../paths';

/** 新版已有的頁面 */
const PRIMARY_LINKS = [
  { to: '/assessment', label: '興趣量表' },
  { to: '/curriculum', label: '系所修課' },
  { to: '/courses', label: '課程' },
  { to: '/course-search', label: '課程助理' },
];

/** 參考資料類的頁面（導覽列上和工具類分開一組） */
const REFERENCE_LINKS = [
  { to: '/projects', label: '研究計畫' },
  { to: '/resources', label: '資源' },
];

/** 工具型頁面：佔滿視窗高度，內容區自己捲動 */
const APP_PAGES = ['/courses', '/course-search', '/curriculum', '/projects'];

/** Esc 或點到外面時關閉 */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
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

function Account() {
  const { user, loading, loginWithGoogle, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [loginFailed, setLoginFailed] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));

  if (loading) return <span className="v2-skeleton block h-9 w-9 !rounded-full" aria-hidden="true" />;

  if (!user) {
    const handleLogin = async () => {
      setLoginFailed(false);
      try {
        await loginWithGoogle();
      } catch {
        setLoginFailed(true);
      }
    };
    return (
      <div className="relative">
        <button type="button" onClick={handleLogin} className="v2-btn v2-btn--ghost v2-btn--sm">
          <GoogleMark />
          登入
        </button>
        {loginFailed && (
          <p role="alert" className="absolute right-0 top-full mt-1 whitespace-nowrap text-xs" style={{ color: 'var(--v2-danger)' }}>
            登入失敗，請再試一次
          </p>
        )}
      </div>
    );
  }

  const initial = user.name?.[0]?.toUpperCase() ?? 'U';
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`帳號選單：${user.name}`}
        className="flex h-11 w-11 items-center justify-center rounded-full"
      >
        {user.picture ? (
          <img src={user.picture} alt="" className="h-9 w-9 rounded-full object-cover" referrerPolicy="no-referrer" />
        ) : (
          <span className="flex h-9 w-9 items-center justify-center rounded-full text-sm font-bold text-white" style={{ background: 'var(--v2-ink)' }}>
            {initial}
          </span>
        )}
      </button>
      {open && (
        <div role="menu" className="v2-panel absolute right-0 top-full z-50 mt-2 w-60 overflow-hidden shadow-lg">
          <div className="px-4 py-3">
            <p className="truncate text-sm font-semibold">{user.name}</p>
            <p className="v2-faint truncate text-xs">{user.email}</p>
          </div>
          <hr className="v2-rule" />
          <Link role="menuitem" to={v2Link('/profile')} className="v2-row !border-b-0 text-sm" onClick={() => setOpen(false)}>
            個人分析
          </Link>
          {isDeveloper(user.email) && (
            <Link role="menuitem" to={v2Link('/monitor')} className="v2-row !border-b-0 text-sm" onClick={() => setOpen(false)}>
              系統監控
            </Link>
          )}
          <hr className="v2-rule" />
          <button
            type="button"
            role="menuitem"
            className="v2-row !border-b-0 text-sm"
            onClick={() => {
              setOpen(false);
              void logout();
            }}
          >
            <HiLogout className="h-4 w-4" aria-hidden="true" />
            登出
          </button>
        </div>
      )}
    </div>
  );
}

export default function V2Layout() {
  const { pathname, search } = useLocation();
  // 記下「在哪一頁打開選單」：換頁後自然關閉，不需要在 effect 裡同步狀態
  const [menuOpenAt, setMenuOpenAt] = useState<string | null>(null);
  const menuOpen = menuOpenAt === pathname;
  const menuRef = useDismiss(menuOpen, () => setMenuOpenAt(null));
  const legacyPath = toLegacyPath(pathname);
  const isApp = APP_PAGES.includes(legacyPath);
  const legacyHref = `${legacyPath}${search}`;

  return (
    <div className={`v2 ${isApp ? 'v2--app' : ''}`}>
      <a href="#v2-main" className="v2-skip">
        跳到主要內容
      </a>

      <header className="v2-nav" ref={menuRef}>
        <div className="mx-auto flex h-full w-full max-w-screen-2xl items-center gap-2 px-4 md:px-6">
          <Link to={v2Link('/')} className="mr-2 flex min-h-11 items-center gap-2.5" aria-label="中大科系探索 首頁">
            <img src={logo} alt="" className="h-8 w-8 object-contain" />
            <span className="v2-serif text-base">中大科系探索</span>
          </Link>

          <nav aria-label="主要導覽" className="hidden items-center lg:flex">
            {PRIMARY_LINKS.map((item) => (
              <NavLink key={item.to} to={v2Link(item.to)} className="v2-navlink">
                {item.label}
              </NavLink>
            ))}
            <span className="mx-2 h-4 w-px" style={{ background: 'var(--v2-line-2)' }} aria-hidden="true" />
            {REFERENCE_LINKS.map((item) => (
              <NavLink key={item.to} to={v2Link(item.to)} className="v2-navlink">
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1">
            <Link to={legacyHref} className="v2-navlink" title="切換到舊版介面">
              舊版
            </Link>
            <Account />
            <button
              type="button"
              className="v2-iconbtn lg:!hidden"
              aria-label={menuOpen ? '關閉選單' : '開啟選單'}
              aria-expanded={menuOpen}
              aria-controls="v2-mobile-menu"
              onClick={() => setMenuOpenAt(menuOpen ? null : pathname)}
            >
              {menuOpen ? <HiX className="h-6 w-6" aria-hidden="true" /> : <HiMenu className="h-6 w-6" aria-hidden="true" />}
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav
            id="v2-mobile-menu"
            aria-label="主要導覽"
            className="absolute inset-x-0 top-full border-b shadow-lg lg:hidden"
            style={{ background: 'var(--v2-paper)', borderColor: 'var(--v2-line)' }}
          >
            {PRIMARY_LINKS.map((item) => (
              <NavLink key={item.to} to={v2Link(item.to)} className="v2-row v2-serif !min-h-14 !px-5 text-lg">
                {item.label}
              </NavLink>
            ))}
            {REFERENCE_LINKS.map((item) => (
              <NavLink key={item.to} to={v2Link(item.to)} className="v2-row v2-muted !min-h-12 !px-5">
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      {/* tabIndex=-1：skip link 跳過來時焦點真的會移到主要內容 */}
      <main id="v2-main" tabIndex={-1} className={`outline-none ${isApp ? 'min-h-0 flex-1' : ''}`}>
        <Outlet />
      </main>
    </div>
  );
}
