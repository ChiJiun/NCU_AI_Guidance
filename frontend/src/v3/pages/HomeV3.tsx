import { lazy, Suspense, useSyncExternalStore } from 'react';
import { Link } from 'react-router-dom';
import { HiArrowRight, HiExternalLink, HiLockClosed } from 'react-icons/hi';
import { useAuth } from '../../auth/AuthContext';
import { DEMO_CASES } from '../../demo/cases';
import LoadErrorBoundary from '../../components/LoadErrorBoundary';
import { v3Link } from '../paths';

const HeroGradient = lazy(() => import('../components/HeroGradient'));

// 版面與文案沿用 v2 首頁（HomeV2）：標題、兩個主要行動、數字、三段探索路線、資料來源。
// 外觀改用舊版首頁的語彙：粉彩漸層＋點格紋底、膠囊按鈕、左側色條數字、淡色大序號、深色 footer。

const STATS = [
  { value: '9', label: '學院' },
  { value: '4,500+', label: '課程' },
  { value: '459', label: '研究計畫' },
  { value: '40+', label: '量表題目' },
];

interface Stop {
  to: string;
  label: string;
  /** 需要登入才能使用 */
  locked?: boolean;
}

const STEPS: { no: string; title: string; stops: Stop[] }[] = [
  {
    no: '01',
    title: '認識自己',
    stops: [
      { to: '/assessment', label: '興趣量表' },
      { to: '/profile', label: '個人分析', locked: true },
    ],
  },
  {
    no: '02',
    title: '看懂系所',
    stops: [
      { to: '/curriculum', label: '系所修課' },
      { to: '/courses', label: '課程資訊' },
      { to: '/course-search', label: '課程助理' },
    ],
  },
  {
    no: '03',
    title: '做出決定',
    stops: [
      { to: '/projects', label: '研究計畫' },
      { to: '/resources', label: '資源連結' },
      ...(DEMO_CASES.length > 0 ? [{ to: '/demo', label: 'AI 示範案例' }] : []),
    ],
  },
];

const SOURCES = [
  { label: '中央大學選課系統', href: 'https://cis.ncu.edu.tw/Course/main/query/byYears' },
  { label: '中央大學教務處', href: 'https://pdc.adm.ncu.edu.tw/p/426-1019-7.php?Lang=zh-tw' },
  { label: '中央大學課務資訊網', href: 'https://course.ncu.edu.tw/p/412-1014-2059.php?Lang=zh-tw' },
  { label: '國科會學術補助獎勵查詢', href: 'https://wsts.nstc.gov.tw/STSWeb/Award/AwardMultiQuery.aspx' },
  { label: '大專校院校務資訊公開平臺', href: 'https://udb.moe.edu.tw/' },
  { label: 'ColleGo! 大學選才系統', href: 'https://collego.edu.tw/' },
];

/**
 * 動態漸層只在「不要求減少動態、螢幕夠寬」時才載入；
 * 其餘情況（以及瀏覽器不支援 WebGPU 時）一律顯示 CSS 畫的靜態漸層（和舊版首頁同一組顏色）。
 */
const HERO_QUERIES = ['(prefers-reduced-motion: no-preference)', '(min-width: 768px)'];

function subscribeHero(onChange: () => void) {
  const lists = HERO_QUERIES.map((query) => window.matchMedia(query));
  lists.forEach((list) => list.addEventListener('change', onChange));
  return () => lists.forEach((list) => list.removeEventListener('change', onChange));
}

const canAnimateHero = () =>
  'gpu' in navigator && HERO_QUERIES.every((query) => window.matchMedia(query).matches);

function useAnimatedHero(): boolean {
  return useSyncExternalStore(subscribeHero, canAnimateHero, () => false);
}

export default function HomeV3() {
  const { user } = useAuth();
  const animated = useAnimatedHero();

  return (
    <>
      <section className="relative overflow-hidden">
        <div className="v3-hero-art" aria-hidden="true">
          <div className="v3-hero-static" />
          {/* shader 純裝飾：載入或初始化失敗就只留下面的靜態漸層 */}
          {animated && (
            <LoadErrorBoundary fallback={null}>
              <Suspense fallback={null}>
                <HeroGradient />
              </Suspense>
            </LoadErrorBoundary>
          )}
          <div className="v3-hero-dots" />
          <div className="v3-hero-fade" />
        </div>

        <div className="relative mx-auto max-w-7xl px-6 pb-16 pt-16 md:px-10 md:pb-24 md:pt-28">
          <h1 className="v3-display v2-rise max-w-[11em] text-[2.75rem] leading-[1.12] md:text-7xl md:leading-[1.08]">
            在中大，
            <br />
            找到你的<span className="v3-underline">位置</span>。
          </h1>

          <div className="v2-rise mt-10 flex flex-wrap gap-3" style={{ animationDelay: '80ms' }}>
            <Link to={v3Link('/assessment')} className="v2-btn v2-btn--lg">
              開始興趣量表
              <HiArrowRight className="h-5 w-5" aria-hidden="true" />
            </Link>
            <Link to={v3Link('/curriculum')} className="v2-btn v2-btn--ghost v2-btn--lg">
              看系所修課
            </Link>
          </div>

          <dl
            className="v2-rise mt-16 grid max-w-3xl grid-cols-2 gap-x-6 gap-y-8 md:mt-24 md:grid-cols-4"
            style={{ animationDelay: '160ms' }}
          >
            {STATS.map((stat) => (
              <div key={stat.label} className="flex flex-col-reverse border-l-2 border-primary-300 pl-5">
                <dt className="mt-1.5 text-xs font-semibold tracking-widest text-slate-500">{stat.label}</dt>
                <dd className="text-[2rem] font-bold tabular-nums leading-tight text-primary-900">{stat.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section aria-label="探索路線" className="bg-white/70 py-14 md:py-20">
        <ol className="mx-auto grid max-w-7xl gap-12 px-6 md:grid-cols-3 md:gap-10 md:px-10">
          {STEPS.map((step) => (
            <li key={step.no} className="group">
              <p
                className="select-none text-[4.5rem] font-black leading-none text-primary-200 transition-colors duration-300 group-hover:text-primary-300"
                aria-hidden="true"
              >
                {step.no}
              </p>
              <h2 className="mt-2 text-2xl font-bold text-slate-950">
                <span className="sr-only">{step.no} </span>
                {step.title}
              </h2>
              <ul className="mt-5 border-t border-slate-200">
                {step.stops.map((stop) => {
                  const locked = stop.locked && !user;
                  return (
                    <li key={stop.to}>
                      <Link to={v3Link(stop.to)} className="v3-stop group/stop">
                        <span className="flex-1">{stop.label}</span>
                        {locked ? (
                          <>
                            <HiLockClosed className="h-4 w-4 text-slate-400" aria-hidden="true" />
                            <span className="sr-only">需要登入</span>
                          </>
                        ) : (
                          <HiArrowRight
                            className="h-4 w-4 text-primary-500 transition-transform group-hover/stop:translate-x-1"
                            aria-hidden="true"
                          />
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ol>
      </section>

      <footer className="bg-slate-900">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-10 md:flex-row md:items-start md:justify-between md:px-10">
          <nav aria-label="資料來源">
            <h2 className="text-sm font-semibold text-slate-300">資料來源</h2>
            <ul className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
              {SOURCES.map((source) => (
                <li key={source.href}>
                  <a
                    href={source.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group inline-flex min-h-11 items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-white"
                  >
                    {source.label}
                    <HiExternalLink className="h-3.5 w-3.5 text-slate-500 transition-colors group-hover:text-slate-300" aria-hidden="true" />
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <p className="shrink-0 text-sm text-slate-400">© 2026 國立中央大學科系探索平台</p>
        </div>
      </footer>
    </>
  );
}
