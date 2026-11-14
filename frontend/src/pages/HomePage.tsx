import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  HiAcademicCap,
  HiArrowRight,
  HiBookOpen,
  HiChartBar,
  HiChevronLeft,
  HiChevronRight,
  HiClipboardList,
  HiCollection,
  HiDocumentText,
  HiExternalLink,
  HiLightningBolt,
  HiLockClosed,
} from 'react-icons/hi';
import { useAuth } from '../auth/AuthContext';
import { DEMO_CASES } from '../demo/cases';

// ── Google 圖示 ──────────────────────────────────────────────────────────────
function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 shrink-0">
      <path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.3-.2-1.9H12v3.6h5.4c-.2 1.2-.9 2.3-2 3v2.4h3.2c1.9-1.7 3-4.2 3-7.1z" />
      <path fill="#34A853" d="M12 22c2.7 0 5-.9 6.6-2.5l-3.2-2.4c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.5C4.8 19.8 8.1 22 12 22z" />
      <path fill="#FBBC05" d="M6.4 14c-.2-.6-.3-1.3-.3-2s.1-1.4.3-2V7.5H3.1C2.4 8.9 2 10.4 2 12s.4 3.1 1.1 4.5L6.4 14z" />
      <path fill="#EA4335" d="M12 5.9c1.5 0 2.8.5 3.8 1.5l2.8-2.8C16.9 3 14.7 2 12 2 8.1 2 4.8 4.2 3.1 7.5L6.4 10c.8-2.3 3-4.1 5.6-4.1z" />
    </svg>
  );
}

// ── CountUp（捲動進入畫面才觸發） ──────────────────────────────────────────
function CountUp({ value, suffix = '' }: { value: number; suffix?: string }) {
  const [displayValue, setDisplayValue] = useState(0);
  const [triggered, setTriggered] = useState(false);
  const spanRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = spanRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setTriggered(true); observer.disconnect(); } },
      { threshold: 0.4 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!triggered) return;
    let frameId = 0;
    let start: number | null = null;
    const duration = 2600;
    const tick = (timestamp: number) => {
      if (!start) start = timestamp;
      const progress = Math.min((timestamp - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayValue(Math.round(value * eased));
      if (progress < 1) frameId = window.requestAnimationFrame(tick);
    };
    frameId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frameId);
  }, [triggered, value]);

  return <span ref={spanRef}>{displayValue.toLocaleString()}{suffix}</span>;
}

// ── Scroll Reveal ──────────────────────────────────────────────────────────
function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); observer.disconnect(); } },
      { threshold: 0.07 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      style={{ transitionDelay: `${delay}ms` }}
      className={`transition-all duration-700 ease-out ${
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-5'
      } ${className}`}
    >
      {children}
    </div>
  );
}

// ── 靜態資料 ────────────────────────────────────────────────────────────────
const stats = [
  { value: 9,    suffix: '',  label: '個學院' },
  { value: 4500, suffix: '+', label: '門課程' },
  { value: 459,  suffix: '',  label: '份研究計畫' },
  { value: 40,   suffix: '+', label: '道量表題目' },
];

const highlights = [
  {
    icon: HiLightningBolt,
    title: 'AI 課程對話助理',
    description: '用自然語言描述你想學的方向，AI 自動搜尋相關課程並即時回答問題，省去逐頁翻找的時間。',
    path: '/course-search',
    cta: '試試 AI 搜尋',
    border:    'border-primary-200',
    iconColor: 'text-primary-400',
    ctaColor:  'text-primary-700 hover:text-primary-900',
  },
  {
    icon: HiAcademicCap,
    title: '興趣量表 × 系所推薦',
    description: '回答 40 道題目，系統分析學習偏好，推薦最值得深入了解的中央大學系所方向，不是泛用測驗。',
    path: '/assessment',
    cta: '開始測評',
    border:    'border-primary-200',
    iconColor: 'text-primary-400',
    ctaColor:  'text-primary-700 hover:text-primary-900',
  },
  {
    icon: HiDocumentText,
    title: '研究計畫 AI 問答',
    description: '瀏覽 459 份大專生研究計畫，遇到不懂的段落直接問 AI，快速掌握各系的研究方向與深度。',
    path: '/projects',
    cta: '查看研究計畫',
    border:    'border-primary-200',
    iconColor: 'text-primary-400',
    ctaColor:  'text-primary-700 hover:text-primary-900',
  },
];

const features = [
  {
    title: '興趣測評',
    description: '透過題目評估興趣與能力傾向，快速整理出較適合探索的學院與學系方向。',
    icon: HiChartBar,
    path: '/assessment',
    tag: '40+ 題目',
  },
  {
    title: '課程資訊',
    description: '瀏覽課程目標、內容、學分、授課教師與知識標籤，也能搜尋與對比多門課程。',
    icon: HiBookOpen,
    path: '/courses',
    tag: '4,500+ 課程',
  },
  {
    title: 'AI 課程助理',
    description: '用 AI 對話描述想學的主題或方向，取得相關課程推薦與延伸查詢結果。',
    icon: HiLightningBolt,
    path: '/course-search',
    tag: 'AI 對話',
  },
  {
    title: '研究計畫',
    description: '從歷年研究與專題成果中，看見不同學系的延伸發展與實作面向。',
    icon: HiAcademicCap,
    path: '/projects',
    tag: '459 份資料',
  },
  {
    title: '系所修課',
    description: '查詢各學院與學系的修課架構、畢業條件與課程規則，協助理解學習路徑。',
    icon: HiClipboardList,
    path: '/curriculum',
    tag: '修課規劃',
  },
  {
    title: '資源連結',
    description: '整理落點分析、升學參考平台與中央大學系所網站，集中管理常用外部資源。',
    icon: HiCollection,
    path: '/resources',
    tag: '整合入口',
  },
];

const paths = [
  {
    step: '01',
    title: '探索自己的興趣方向',
    description: '從量表了解你的學習傾向，取得量身推薦的系所清單。完成後登入即可查看個人探索歷程、領域分佈雷達圖與課程偏好分析。',
    links: [
      { label: '興趣量表', path: '/assessment',  sub: '40+ 題目', locked: false },
      { label: '個人分析', path: '/profile',     sub: '需登入',   locked: true  },
    ],
  },
  {
    step: '02',
    title: '深入了解課程與系所',
    description: '三個工具各有側重：課程資訊讓你循學院瀏覽比較，AI 助理用自然語言找課，系所修課呈現各系的畢業學分架構與修課規定。',
    links: [
      { label: '課程資訊',    path: '/courses',      sub: '4,500+ 課程', locked: false },
      { label: 'AI 課程助理', path: '/course-search', sub: 'AI 對話',     locked: false },
      { label: '系所修課',    path: '/curriculum',    sub: '修課規劃',     locked: false },
    ],
  },
  {
    step: '03',
    title: '研究方向與升學決策',
    description: '從 459 份大專研究計畫了解各系的延伸發展，再搭配落點分析工具與官方系所網站，做出更有根據的志願決定。',
    links: [
      { label: '研究計畫', path: '/projects',  sub: '459 份',  locked: false },
      { label: '資源連結', path: '/resources', sub: '升學入口', locked: false },
    ],
  },
];

const sources = [
  { label: '中央大學選課系統',        tag: '課程資訊', href: 'https://cis.ncu.edu.tw/Course/main/query/byYears' },
  { label: '中央大學教務處',          tag: '系所修課', href: 'https://pdc.adm.ncu.edu.tw/p/426-1019-7.php?Lang=zh-tw' },
  { label: '中央大學課務資訊網',      tag: '學分學程', href: 'https://course.ncu.edu.tw/p/412-1014-2059.php?Lang=zh-tw' },
  { label: '國科會學術補助獎勵查詢',  tag: '研究計畫', href: 'https://wsts.nstc.gov.tw/STSWeb/Award/AwardMultiQuery.aspx' },
  { label: '大專校院校務資訊公開平臺', tag: '教師資料', href: 'https://udb.moe.edu.tw/' },
  { label: 'ColleGo! 大學選才系統',   tag: '升學參考', href: 'https://collego.edu.tw/' },
];

// ── 主元件 ──────────────────────────────────────────────────────────────────
export default function HomePage() {
  const navigate  = useNavigate();
  const { user, loading, loginWithGoogle } = useAuth();
  const [isLeaving, setIsLeaving]                   = useState(false);
  const [activeFeatureIndex, setActiveFeatureIndex] = useState(0);
  const dragStateRef = useRef({ isDown: false, startX: 0, moved: false });
  const [loginError, setLoginError]                 = useState('');

  const navigateWithAnimation = (path: string) => {
    setIsLeaving(true);
    window.setTimeout(() => { navigate(path); setIsLeaving(false); }, 220);
  };

  const handleLogin = async () => {
    setLoginError('');
    try { await loginWithGoogle(); } catch { setLoginError('登入失敗，請再試一次'); }
  };

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!dragStateRef.current.isDown) setActiveFeatureIndex((prev) => (prev + 1) % features.length);
    }, 4500);
    return () => window.clearInterval(timer);
  }, []);

  const goToFeature = (index: number) => setActiveFeatureIndex((index + features.length) % features.length);

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    dragStateRef.current = { isDown: true, startX: event.clientX, moved: false };
  };
  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStateRef.current.isDown) return;
    if (Math.abs(event.clientX - dragStateRef.current.startX) > 20) dragStateRef.current.moved = true;
  };
  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStateRef.current.isDown) return;
    const delta = event.clientX - dragStateRef.current.startX;
    const moved = dragStateRef.current.moved;
    dragStateRef.current.isDown = false;
    if (delta <= -40) goToFeature(activeFeatureIndex + 1);
    if (delta >= 40)  goToFeature(activeFeatureIndex - 1);
    window.setTimeout(() => { dragStateRef.current.moved = false; }, 0);
    if (!moved && Math.abs(delta) < 10) return;
  };
  const handleFeatureClick = (path: string) => { if (!dragStateRef.current.moved) navigateWithAnimation(path); };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@700;900&display=swap');
        .font-serif-tc { font-family: 'Noto Serif TC', Georgia, serif; }

        @keyframes hero-up {
          from { opacity: 0; transform: translateY(20px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .h-anim-1  { animation: hero-up 0.50s 0.05s ease-out both; }
        .h-anim-2  { animation: hero-up 0.50s 0.18s ease-out both; }
        .h-anim-2b { animation: hero-up 0.55s 0.32s ease-out both; }
        .h-anim-2c { animation: hero-up 0.55s 0.46s ease-out both; }
        .h-anim-3  { animation: hero-up 0.50s 0.62s ease-out both; }
        .h-anim-4  { animation: hero-up 0.50s 0.76s ease-out both; }
        .h-anim-5  { animation: hero-up 0.50s 0.92s ease-out both; }

        @keyframes badge-float {
          0%, 100% { transform: translateY(0px); }
          50%       { transform: translateY(-5px); }
        }
        .badge-float { animation: badge-float 4s ease-in-out infinite; }

        @keyframes underline-slide {
          from { transform: scaleX(0); }
          to   { transform: scaleX(1); }
        }
        .ai-underline {
          animation: underline-slide 0.55s 0.75s cubic-bezier(0.22, 1, 0.36, 1) both;
          transform-origin: left;
        }
      `}</style>

      <div className={`transition duration-300 ${isLeaving ? 'translate-y-2 opacity-0' : 'translate-y-0 opacity-100'}`}>

        {/* ══════════════════════════════════════════════════════════════════
            1. HERO — 淺色（原始背景），非對稱雙欄，入場動畫
        ══════════════════════════════════════════════════════════════════ */}
        {/* 點格紋有 pointer-events-none，點擊會落到 section 本身，觸發換色 */}
        <section
          className="relative overflow-hidden pb-20 pt-24 md:pb-28 md:pt-32"
          onClick={(e) => { if (e.target === e.currentTarget) document.dispatchEvent(new CustomEvent('cycle-background')); }}
        >
          {/* 細點格紋背景 */}
          <div
            className="pointer-events-none absolute inset-0 opacity-[0.10]"
            style={{
              backgroundImage: 'radial-gradient(circle, #64748b 1.5px, transparent 1.5px)',
              backgroundSize: '28px 28px',
            }}
          />
          {/* 底部漸層消散（過渡到下一 section 的半透明白） */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-white/80 to-transparent" />

          <div className="relative mx-auto max-w-7xl px-6 md:px-10">
            <div className="grid items-center gap-12 lg:grid-cols-12">

              {/* 左欄：badge → H1 → 描述 → 按鈕（自然閱讀順序） */}
              <div className="lg:col-span-7">
                <div className="badge-float h-anim-1 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-slate-600 backdrop-blur-sm">
                  <HiCollection className="h-3.5 w-3.5 text-primary-700" />
                  AI 輔助 × 中大選系
                </div>
                <h1 className="font-serif-tc mt-6 tracking-tight">
                  {/* 引言：小字，AI 漸層打亮 */}
                  <span className="h-anim-2 block text-xl font-semibold leading-snug text-slate-400 md:text-2xl">
                    跟{' '}
                    <span className="relative inline-block font-black text-slate-900">
                      AI
                      <span className="ai-underline absolute -bottom-1 left-0 h-[3px] w-full rounded-full bg-gradient-to-r from-amber-400 to-orange-400" />
                    </span>
                    {' '}一起，
                  </span>
                  {/* 主標：最大、最重 */}
                  <span className="h-anim-2b mt-1 block text-4xl font-black leading-[1.12] text-slate-950 lg:text-5xl">
                    挖出每個系真正在學什麼，
                  </span>
                  {/* 收尾：中等，品牌主色 */}
                  <span className="h-anim-2c mt-1 block text-2xl font-black leading-snug text-primary-700 md:text-3xl">
                    在中大找到你的位置。
                  </span>
                </h1>
                <p className="h-anim-3 mt-6 max-w-xl text-base leading-7 text-slate-600">
                  量表分析學習偏好、AI 即時解答課程問題、研究計畫讓你看見各系的真實深度。
                  選系不靠感覺，靠資料。
                </p>
                <div className="h-anim-4 mt-8 flex flex-wrap gap-3">
                  <button type="button" onClick={() => navigateWithAnimation('/assessment')} className="btn-primary">
                    開始興趣量表
                    <HiArrowRight className="ml-2 h-5 w-5" />
                  </button>
                  <button type="button" onClick={() => navigateWithAnimation('/courses')} className="btn-secondary">
                    瀏覽課程資料
                  </button>
                  {DEMO_CASES.length > 0 && (
                    <button type="button" onClick={() => navigateWithAnimation('/demo')} className="btn-secondary">
                      查看 AI 示範案例
                    </button>
                  )}
                </div>
              </div>

              {/* 右欄：統計數字（獨立視覺區塊） */}
              <div className="lg:col-span-5">
                <div className="h-anim-5 grid grid-cols-2 gap-x-6 gap-y-8">
                  {stats.map((stat) => (
                    <div key={stat.label} className="border-l-2 border-primary-300 pl-5">
                      <div className="text-[2rem] font-bold tabular-nums leading-tight text-primary-900">
                        <CountUp value={stat.value} suffix={stat.suffix} />
                      </div>
                      <div className="mt-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                        {stat.label}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

            </div>
          </div>
        </section>

        {/* ══════════════════════════════════════════════════════════════════
            2. HIGHLIGHTS — 白底，彩色左邊框
        ══════════════════════════════════════════════════════════════════ */}
        <section className="bg-white/70 py-16 md:py-20">
          <div className="mx-auto max-w-7xl px-6 md:px-10">
            <Reveal>
              <div className="mb-12">
                <p className="text-xs font-semibold uppercase tracking-[0.25em] text-primary-500">
                  Platform Highlights
                </p>
                <h2 className="mt-2 text-3xl font-bold text-slate-950">三個獨特功能</h2>
                <p className="mt-2 text-sm text-slate-500">一般升學平台沒有的</p>
              </div>
            </Reveal>

            <div className="grid gap-10 md:grid-cols-3">
              {highlights.map((item, i) => {
                const Icon = item.icon;
                return (
                  <Reveal key={item.title} delay={i * 120}>
                    <div className={`border-l-4 ${item.border} py-1 pl-6`}>
                      <Icon className={`h-6 w-6 ${item.iconColor}`} />
                      <h3 className="mt-3 text-base font-bold text-slate-950">{item.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-slate-500">{item.description}</p>
                      <button
                        type="button"
                        onClick={() => navigateWithAnimation(item.path)}
                        className={`group/btn mt-4 inline-flex items-center gap-1.5 text-sm font-semibold transition ${item.ctaColor}`}
                      >
                        {item.cta}
                        <HiArrowRight className="h-4 w-4 transition-transform group-hover/btn:translate-x-1" />
                      </button>
                    </div>
                  </Reveal>
                );
              })}
            </div>
          </div>
        </section>

        {/* ══════════════════════════════════════════════════════════════════
            3. FEATURE CAROUSEL — 深一點的底色讓白色卡片浮起
        ══════════════════════════════════════════════════════════════════ */}
        <section className="bg-white/50 py-14 md:py-16">
          <div className="mx-auto max-w-7xl px-6 md:px-10">
            <Reveal>
              <div className="mb-8 flex items-end justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.25em] text-primary-500">
                    Core Modules
                  </p>
                  <h2 className="mt-2 text-2xl font-bold text-slate-950">平台功能總覽</h2>
                </div>
              </div>
            </Reveal>
          </div>

          <div
            className="feature-coverflow"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
          >
            <div className="feature-coverflow-stage">
              <button
                type="button"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => goToFeature(activeFeatureIndex - 1)}
                className="absolute left-1 top-1/2 z-20 inline-flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-soft transition hover:bg-white hover:text-slate-900 hover:shadow-medium sm:left-4 lg:left-10"
                aria-label="上一張"
              >
                <HiChevronLeft className="h-5 w-5" />
              </button>
              <button
                type="button"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => goToFeature(activeFeatureIndex + 1)}
                className="absolute right-1 top-1/2 z-20 inline-flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-soft transition hover:bg-white hover:text-slate-900 hover:shadow-medium sm:right-4 lg:right-10"
                aria-label="下一張"
              >
                <HiChevronRight className="h-5 w-5" />
              </button>

              {features.map((feature, index) => {
                const Icon = feature.icon;
                const offset = index - activeFeatureIndex;
                const wrappedOffset =
                  offset > features.length / 2  ? offset - features.length
                  : offset < -features.length / 2 ? offset + features.length
                  : offset;
                let positionClass = 'feature-coverflow-hidden';
                if (wrappedOffset === 0)  positionClass = 'feature-coverflow-center';
                if (wrappedOffset === -1) positionClass = 'feature-coverflow-left';
                if (wrappedOffset === 1)  positionClass = 'feature-coverflow-right';
                if (wrappedOffset === -2) positionClass = 'feature-coverflow-far-left';
                if (wrappedOffset === 2)  positionClass = 'feature-coverflow-far-right';
                const isCenter = wrappedOffset === 0;

                return (
                  <button
                    key={feature.title}
                    type="button"
                    onClick={() => isCenter ? handleFeatureClick(feature.path) : goToFeature(index)}
                    className={`feature-coverflow-card ${positionClass}`}
                  >
                    {/* 中央卡片加上邊框光暈與頂部色條，更突出 */}
                    <div className={`feature-coverflow-card-inner relative min-h-[232px] overflow-hidden rounded-3xl p-6 text-left transition-shadow duration-300 ${
                      isCenter
                        ? 'bg-white shadow-[0_8px_28px_rgba(0,0,0,0.10)] ring-2 ring-primary-200'
                        : 'card'
                    }`}>
                      {/* 中央卡片頂部裝飾條（漸層色系配合背景主題） */}
                      {isCenter && (
                        <div className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-primary-400 via-primary-300 to-primary-400" />
                      )}
                      <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${
                        isCenter ? 'bg-primary-50 text-primary-600' : 'bg-slate-100 text-slate-500'
                      }`}>
                        <Icon className="h-6 w-6" />
                      </div>
                      <div className="mt-5 flex items-center justify-between gap-4">
                        <h3 className={`text-lg font-semibold ${isCenter ? 'text-slate-950' : 'text-slate-700'}`}>
                          {feature.title}
                        </h3>
                        <span className={`rounded-full px-3 py-1 text-xs font-medium ${
                          isCenter ? 'bg-primary-50 text-primary-600' : 'bg-slate-100 text-slate-500'
                        }`}>
                          {feature.tag}
                        </span>
                      </div>
                      <p className="feature-card-description mt-3 text-sm leading-6 text-slate-600">
                        {feature.description}
                      </p>
                      <div className={`mt-6 inline-flex items-center text-sm font-medium ${
                        isCenter ? 'text-primary-700' : 'text-slate-400'
                      }`}>
                        前往功能
                        <HiArrowRight className="ml-2 h-4 w-4" />
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-6 flex justify-center gap-2">
            {features.map((feature, index) => (
              <button
                key={feature.title}
                type="button"
                onClick={() => goToFeature(index)}
                className={`h-2 rounded-full transition-all duration-300 ${
                  index === activeFeatureIndex ? 'w-6 bg-primary-700' : 'w-2 bg-slate-300 hover:bg-slate-400'
                }`}
                aria-label={`切換到 ${feature.title}`}
              />
            ))}
          </div>
        </section>

        {/* ══════════════════════════════════════════════════════════════════
            4. EXPLORE PATHS — 白底，超大步驟序號
        ══════════════════════════════════════════════════════════════════ */}
        <section className="bg-white/70 py-16">
          <div className="mx-auto max-w-5xl px-6 md:px-10">
            <Reveal>
              <div className="mb-10">
                <p className="text-xs font-semibold uppercase tracking-[0.25em] text-primary-500">
                  How to Start
                </p>
                <h2 className="mt-2 text-3xl font-bold text-slate-950">如何開始探索？</h2>
              </div>
            </Reveal>

            {paths.map((path, i) => (
              <Reveal key={path.step} delay={i * 90}>
                <div className="group flex flex-col gap-2 border-t border-slate-100 py-10 last:border-b sm:flex-row sm:gap-0">
                  <div className="shrink-0 select-none text-[5.5rem] font-black leading-none text-primary-200 transition-colors duration-300 group-hover:text-primary-300 sm:w-36 sm:text-[6.5rem]">
                    {path.step}
                  </div>
                  <div className="flex-1 sm:pt-5">
                    <h3 className="text-xl font-bold text-slate-950">{path.title}</h3>
                    <p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">{path.description}</p>
                    <div className="mt-5 flex flex-wrap gap-2.5">
                      {path.links.map((link) => (
                        <button
                          key={link.label}
                          type="button"
                          onClick={() => navigateWithAnimation(link.path)}
                          className={`group/chip inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-semibold transition-all duration-200 hover:-translate-y-0.5 hover:shadow-soft ${
                            link.locked
                              ? 'border-slate-200 bg-white/50 text-slate-400'
                              : 'border-primary-200 bg-primary-50/80 text-primary-700 hover:border-primary-300 hover:bg-white'
                          }`}
                        >
                          {link.locked && <HiLockClosed className="h-3 w-3 shrink-0" />}
                          {link.label}
                          <span className="text-[10px] font-normal opacity-60">{link.sub}</span>
                          <HiArrowRight className="h-3.5 w-3.5 transition-transform group-hover/chip:translate-x-0.5" />
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ══════════════════════════════════════════════════════════════════
            5. 登入提醒 / 已登入狀態
        ══════════════════════════════════════════════════════════════════ */}
        {!loading && !user && (
          <section className="px-6 py-4 md:px-10">
            <Reveal>
              <div className="mx-auto max-w-5xl overflow-hidden rounded-2xl bg-primary-900">
                <div className="flex flex-col items-start justify-between gap-5 px-8 py-7 md:flex-row md:items-center">
                  <div>
                    <p className="text-base font-bold text-white">個人分析功能需要登入才能使用</p>
                    <p className="mt-1 text-sm text-primary-300">
                      登入後可查看課程探索歷程、六大領域分佈雷達圖與系所偏好分析。
                    </p>
                    {loginError && <p className="mt-1 text-xs text-red-400">{loginError}</p>}
                  </div>
                  <button
                    type="button"
                    onClick={handleLogin}
                    className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-white/15 bg-white px-5 py-2.5 text-sm font-semibold text-slate-900 shadow transition hover:bg-slate-100 active:scale-[0.98]"
                  >
                    <GoogleMark />
                    使用 Google 登入
                  </button>
                </div>
              </div>
            </Reveal>
          </section>
        )}

        {/* 已登入：浮於漸層背景上，白底輕卡 */}
        {!loading && user && (
          <section className="bg-white/85 px-6 py-6 md:px-10">
            <Reveal>
              <div className="mx-auto max-w-5xl">
                <div className="flex flex-col items-start justify-between gap-5 rounded-2xl bg-white/70 px-7 py-5 shadow-soft ring-1 ring-emerald-200/70 md:flex-row md:items-center">
                  <div className="flex items-center gap-4">
                    {/* Avatar */}
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-base font-bold text-emerald-700">
                      {user.name?.[0]?.toUpperCase() ?? 'U'}
                    </div>
                    <div>
                      {/* 狀態 badge */}
                      <div className="mb-1.5 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-600">
                        <span className="relative flex h-1.5 w-1.5">
                          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        </span>
                        個人分析已解鎖
                      </div>
                      <p className="text-base font-bold text-slate-900">{user.name}</p>
                      <p className="mt-0.5 text-xs text-slate-500">查看課程探索歷程、六大領域雷達圖與系所偏好</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigateWithAnimation('/profile')}
                    className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-emerald-600 px-6 py-2.5 text-sm font-bold text-white transition hover:-translate-y-0.5 hover:bg-emerald-700 active:scale-[0.98]"
                  >
                    進入個人分析
                    <HiArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </Reveal>
          </section>
        )}

        {/* ══════════════════════════════════════════════════════════════════
            6. FOOTER — 深色，資料來源 + 版權
        ══════════════════════════════════════════════════════════════════ */}
        <footer className="bg-slate-900 px-6 pb-10 pt-12 md:px-10">
          <div className="mx-auto max-w-5xl">

            {/* 平台品牌列 */}
            <div className="mb-10 border-b border-slate-800 pb-8">
              <p className="text-lg font-bold text-white">國立中央大學科系探索平台</p>
              <p className="mt-1.5 text-sm text-slate-500">整合課程、研究、量表，協助高中生做出更清楚的志願決定。</p>
            </div>

            {/* 資料來源 */}
            <p className="mb-6 text-sm font-semibold text-slate-300">資料來源</p>
            <div className="grid grid-cols-1 gap-x-12 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
              {sources.map((source) => (
                <a
                  key={source.label}
                  href={source.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-start justify-between gap-4"
                >
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-600">
                      {source.tag}
                    </div>
                    <div className="mt-0.5 text-sm text-slate-400 transition-colors group-hover:text-white">
                      {source.label}
                    </div>
                  </div>
                  <HiExternalLink className="mt-1 h-3.5 w-3.5 shrink-0 text-slate-700 transition-colors group-hover:text-slate-400" />
                </a>
              ))}
            </div>

            {/* 版權 */}
            <div className="mt-10 border-t border-slate-800 pt-6">
              <p className="text-xs text-slate-600">© 2026 國立中央大學科系探索平台 — 所有資料均來自公開官方管道</p>
            </div>

          </div>
        </footer>

      </div>
    </>
  );
}
