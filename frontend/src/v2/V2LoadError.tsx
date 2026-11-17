import { toLegacyPath } from './paths';

/**
 * 新版 chunk 載入失敗時的畫面。這個元件打包在主 bundle 裡（新版的樣式還沒載入），
 * 所以只用舊版也有的 Tailwind class 與 inline style。
 */
export default function V2LoadError() {
  const { pathname, search, hash } = window.location;
  const legacyHref = `${toLegacyPath(pathname)}${search}${hash}`;

  return (
    <div
      role="alert"
      className="flex min-h-screen flex-col items-center justify-center gap-6 px-6 text-center"
      style={{ background: '#f5f2ea', color: '#15202b' }}
    >
      <p className="text-xl font-bold">新版載入失敗</p>
      <div className="flex flex-wrap justify-center gap-3">
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="min-h-11 rounded-lg px-5 text-sm font-semibold text-white"
          style={{ background: '#15202b' }}
        >
          重新載入
        </button>
        {/* 用整頁跳轉：拿到最新的 index.html，避免舊版的 chunk 也已經過期 */}
        <a href={legacyHref} className="flex min-h-11 items-center rounded-lg border px-5 text-sm font-semibold" style={{ borderColor: '#cfc8b8' }}>
          回舊版
        </a>
      </div>
    </div>
  );
}
