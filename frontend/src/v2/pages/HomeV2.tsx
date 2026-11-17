import { lazy, Suspense, useSyncExternalStore } from 'react';
import { Link } from 'react-router-dom';
import { HiArrowRight, HiLockClosed } from 'react-icons/hi';
import { useAuth } from '../../auth/AuthContext';
import { DEMO_CASES } from '../../demo/cases';
import LoadErrorBoundary from '../../components/LoadErrorBoundary';
import { v2Link } from '../paths';

const HeroShader = lazy(() => import('../components/HeroShader'));

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
 * 動態等高線只在「不要求減少動態、螢幕夠寬」時才載入；
 * 其餘情況（以及瀏覽器不支援 WebGPU 時）一律顯示 CSS 畫的靜態等高線。
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

export default function HomeV2() {
  const { user } = useAuth();
  const animated = useAnimatedHero();

  return (
    <>
      <section className="relative overflow-hidden border-b" style={{ borderColor: 'var(--v2-line)' }}>
        <div className="v2-hero-art" aria-hidden="true">
          <div className="v2-hero-static" />
          {/* shader 純裝飾：載入或初始化失敗就只留下面的靜態等高線 */}
          {animated && (
            <LoadErrorBoundary fallback={null}>
              <Suspense fallback={null}>
                <HeroShader />
              </Suspense>
            </LoadErrorBoundary>
          )}
        </div>

        <div className="v2-container relative pb-14 pt-16 md:pb-20 md:pt-28">
          <h1 className="v2-serif v2-rise max-w-[11em] text-[2.75rem] leading-[1.12] md:text-7xl md:leading-[1.08]">
            在中大，
            <br />
            找到你的<span className="v2-accent">位置</span>。
          </h1>

          <div className="v2-rise mt-10 flex flex-wrap gap-3" style={{ animationDelay: '80ms' }}>
            <Link to={v2Link('/assessment')} className="v2-btn v2-btn--lg">
              開始興趣量表
              <HiArrowRight className="h-5 w-5" aria-hidden="true" />
            </Link>
            <Link to={v2Link('/curriculum')} className="v2-btn v2-btn--ghost v2-btn--lg">
              看系所修課
            </Link>
          </div>

          <dl
            className="v2-rise mt-16 grid max-w-2xl grid-cols-2 gap-x-8 gap-y-6 md:mt-24 md:grid-cols-4"
            style={{ animationDelay: '160ms' }}
          >
            {STATS.map((stat) => (
              <div key={stat.label} className="flex flex-col-reverse">
                <dt className="v2-muted text-sm">{stat.label}</dt>
                <dd className="v2-num text-3xl md:text-4xl">{stat.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section aria-label="探索路線" className="v2-container py-14 md:py-20">
        <ol className="grid gap-12 md:grid-cols-3 md:gap-10">
          {STEPS.map((step) => (
            <li key={step.no}>
              <p className="v2-num v2-accent text-sm !tracking-widest">{step.no}</p>
              <h2 className="v2-serif mt-1 text-3xl">{step.title}</h2>
              <ul className="mt-5 border-t" style={{ borderColor: 'var(--v2-ink)' }}>
                {step.stops.map((stop) => {
                  const locked = stop.locked && !user;
                  return (
                    <li key={stop.to}>
                      <Link to={v2Link(stop.to)} className="v2-row group !min-h-14 !px-1 text-lg">
                        <span className="flex-1">{stop.label}</span>
                        {locked ? (
                          <>
                            <HiLockClosed className="v2-faint h-4 w-4" aria-hidden="true" />
                            <span className="sr-only">需要登入</span>
                          </>
                        ) : (
                          <HiArrowRight
                            className="v2-faint h-4 w-4 transition-transform group-hover:translate-x-1"
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

      <footer className="border-t" style={{ borderColor: 'var(--v2-line)' }}>
        <div className="v2-container flex flex-col gap-6 py-10 md:flex-row md:items-start md:justify-between">
          <nav aria-label="資料來源">
            <h2 className="v2-faint text-sm">資料來源</h2>
            <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
              {SOURCES.map((source) => (
                <li key={source.href}>
                  <a
                    href={source.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="v2-muted inline-flex min-h-11 items-center text-sm underline-offset-4 hover:underline"
                  >
                    {source.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <p className="v2-faint shrink-0 text-sm">© 2026 國立中央大學科系探索平台</p>
        </div>
      </footer>
    </>
  );
}
