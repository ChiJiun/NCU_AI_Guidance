import { toV1Path } from './paths';

/**
 * v3 chunk 載入失敗時的畫面。這個元件打包在主 bundle 裡（v3 的樣式還沒載入），
 * 所以只用舊版也有的 Tailwind class（樣式本來就是舊版風格）。
 */
export default function V3LoadError() {
  const { pathname, search, hash } = window.location;
  const legacyHref = `${toV1Path(pathname)}${search}${hash}`;

  return (
    <div role="alert" className="bg-theme-1 flex min-h-screen flex-col items-center justify-center gap-6 px-6 text-center">
      <p className="text-xl font-bold text-primary-900">v3 載入失敗</p>
      <div className="flex flex-wrap justify-center gap-3">
        <button type="button" onClick={() => window.location.reload()} className="btn-primary">
          重新載入
        </button>
        {/* 用整頁跳轉：拿到最新的 index.html，避免舊版的 chunk 也已經過期 */}
        <a href={legacyHref} className="btn-secondary">
          回舊版
        </a>
      </div>
    </div>
  );
}
