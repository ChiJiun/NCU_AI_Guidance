import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { AnalyticsData, PdfAnalyticsData } from '../../api/services';
import { useAuth } from '../../auth/AuthContext';
import { GoogleMark } from '../../components/GoogleLoginButton';
import {
  COMBINED_TYPE_LABELS,
  COURSE_TYPE_TEXT,
  activeDomainCount,
  collegeDomainAxes,
  combinedDomainAxes,
  diagnoseCombinedType,
  diagnoseCourseType,
  formatRelativeTime,
  interactionShare,
  uniqueCollegeCount,
  usagePreferenceText,
  type DomainAxis,
  type RadarMode,
} from '../../features/analytics/analysis';
import { useAnalytics, type TabId } from '../../features/analytics/useAnalytics';
import { Block, BarList, StatRow } from '../components/Charts';
import RovingGroup from '../components/RovingGroup';
import { v2Link } from '../paths';

const TABS: { id: TabId; label: string }[] = [
  { id: 'all', label: '全部' },
  { id: 'course', label: '課程助理' },
  { id: 'project', label: '研究計畫' },
];

/** 六個學術領域的佔比（依佔比由高到低） */
function DomainBars({ axes }: { axes: DomainAxis[] }) {
  if (axes.filter((axis) => axis.value > 0).length < 2) return <p className="v2-faint text-sm">需要更多對話資料</p>;
  const sorted = [...axes].sort((a, b) => b.pct - a.pct);
  return <BarList items={sorted.map((axis) => ({ label: axis.label, value: axis.pct, display: `${axis.pct}%` }))} />;
}

/** 探索型態：大字標籤＋一句說明＋關鍵數字 */
function TypeCard({ label, desc, facts }: { label: string; desc: string; facts: [string, string][] }) {
  return (
    <div>
      <p className="v2-serif text-3xl">{label}</p>
      <p className="v2-muted mt-2 leading-relaxed">{desc}</p>
      <dl className="mt-5 space-y-1.5 text-sm">
        {facts.map(([name, value]) => (
          <div key={name} className="flex justify-between gap-4 border-b pb-1.5" style={{ borderColor: 'var(--v2-line)' }}>
            <dt className="v2-muted">{name}</dt>
            <dd className="v2-num">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Loading() {
  return (
    <div aria-busy="true" className="space-y-8">
      <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="v2-skeleton h-16" />
        ))}
      </div>
      <div className="grid gap-10 md:grid-cols-2">
        <div className="v2-skeleton h-56" />
        <div className="v2-skeleton h-56" />
      </div>
      <span className="sr-only">載入分析中</span>
    </div>
  );
}

function ErrorText({ message }: { message: string }) {
  return (
    <p role="alert" style={{ color: 'var(--v2-danger)' }}>
      {message}
    </p>
  );
}

function Empty({ title, to, action }: { title: string; to: string; action: string }) {
  return (
    <div className="border-t pt-6" style={{ borderColor: 'var(--v2-ink)' }}>
      <p className="font-semibold">{title}</p>
      <Link to={v2Link(to)} className="v2-btn mt-5">
        {action}
      </Link>
    </div>
  );
}

function AllTab({ courseData, projectData, loading }: { courseData: AnalyticsData | null; projectData: PdfAnalyticsData | null; loading: boolean }) {
  const [radarMode, setRadarMode] = useState<RadarMode>('weighted');
  if (loading) return <Loading />;
  if (!courseData && !projectData) return <p className="v2-muted">切換到「課程助理」或「研究計畫」開始分析。</p>;

  const { courseInteractions, researchInteractions, totalInteractions, coursePct, researchPct } = interactionShare(courseData, projectData);
  const axes = combinedDomainAxes(courseData, projectData, radarMode, courseInteractions, totalInteractions);
  const combined = diagnoseCombinedType(courseData, projectData, coursePct, axes);
  const showAxes = axes.filter((axis) => axis.value > 0).length >= 2;

  return (
    <div className="space-y-14">
      <StatRow
        items={[
          { label: '課程對話', value: courseData?.overview.total_sessions ?? '—' },
          { label: '研究計畫對話', value: projectData?.overview.total_conversations ?? '—' },
          { label: '課程提問', value: courseData?.overview.total_turns ?? '—' },
          { label: '探索論文', value: projectData?.overview.total_documents_explored ?? '—' },
        ]}
      />

      <div className="grid gap-14 md:grid-cols-2 md:gap-10">
        {showAxes && (
          <Block
            title="學術領域"
            aside={
              <RovingGroup role="radiogroup" aria-label="計算方式" className="v2-seg">
                {(['weighted', 'equal'] as const).map((mode) => (
                  <button key={mode} type="button" role="radio" aria-checked={radarMode === mode} className="!min-h-8 !px-3 !text-sm" onClick={() => setRadarMode(mode)}>
                    {mode === 'weighted' ? '依使用量' : '各半'}
                  </button>
                ))}
              </RovingGroup>
            }
          >
            <DomainBars axes={axes} />
          </Block>
        )}

        {totalInteractions > 0 && (
          <Block title="探索型態">
            <TypeCard
              label={COMBINED_TYPE_LABELS[combined.id]}
              desc={combined.desc}
              facts={[
                ['課程助理提問', `${courseInteractions.toLocaleString()} 次`],
                ['研究計畫提問', `${researchInteractions.toLocaleString()} 次`],
                ['探索學院', `${uniqueCollegeCount(courseData, projectData)} 個`],
                ['研究計畫平均深度', `${projectData?.overview.avg_depth ?? '—'} 輪`],
              ]}
            />
          </Block>
        )}
      </div>

      {totalInteractions > 0 && (
        <Block title="使用比例">
          <div className="flex h-2 overflow-hidden rounded-full" aria-hidden="true">
            <span style={{ width: `${coursePct}%`, background: 'var(--v2-ink)' }} />
            <span style={{ width: `${researchPct}%`, background: 'var(--v2-line-2)' }} />
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-6">
            <div className="flex flex-col-reverse">
              <dt className="v2-muted text-sm">課程助理</dt>
              <dd className="v2-num text-3xl">{coursePct}%</dd>
            </div>
            <div className="flex flex-col-reverse">
              <dt className="v2-muted text-sm">研究計畫</dt>
              <dd className="v2-num text-3xl">{researchPct}%</dd>
            </div>
          </dl>
          <p className="v2-muted mt-4">{usagePreferenceText(coursePct, researchPct)}</p>
        </Block>
      )}
    </div>
  );
}

function CourseTab({ data, loading, error }: { data: AnalyticsData | null; loading: boolean; error: string }) {
  if (loading) return <Loading />;
  if (error) return <ErrorText message={error} />;
  if (!data || data.overview.total_turns <= 0) return <Empty title="還沒有課程助理的使用記錄" to="/course-search" action="開始問課程助理" />;

  const axes = collegeDomainAxes(data.college_distribution);
  const type = COURSE_TYPE_TEXT[diagnoseCourseType(data, axes)];
  const tags = [...data.top_domain_tags].sort((a, b) => b.count - a.count).slice(0, 10);
  const depts = data.dept_distribution.slice(0, 10);
  const ge = data.general_edu;

  return (
    <div className="space-y-14">
      <StatRow
        items={[
          { label: '對話', value: data.overview.total_sessions },
          { label: '提問', value: data.overview.total_turns },
          { label: '探索課程', value: data.overview.total_courses_explored },
          { label: '最常探索學院', value: <span className="text-2xl">{data.overview.fav_college || '—'}</span> },
        ]}
      />

      <div className="grid gap-14 md:grid-cols-2 md:gap-10">
        <Block title="學術領域">
          <DomainBars axes={axes} />
        </Block>
        <Block title="探索型態">
          <TypeCard
            label={type.label}
            desc={type.desc}
            facts={[
              ['探索系所', `${data.dept_distribution.length} 個`],
              ['最集中系所', `${data.dept_distribution[0]?.pct.toFixed(1) ?? 0}%`],
              ['跨域廣度', `${activeDomainCount(axes)} 個領域`],
            ]}
          />
        </Block>
      </div>

      <div className="grid gap-14 md:grid-cols-2 md:gap-10">
        <Block title="系所">
          <BarList items={depts.map((item) => ({ label: item.name, value: item.count, display: `${item.pct.toFixed(1)}%` }))} />
        </Block>
        <Block title="關注主題">
          <BarList items={tags.map((item) => ({ label: item.tag, value: item.count }))} />
        </Block>
      </div>

      {(data.top_course_domains.length > 0 || ge.categories.length > 0) && (
        <div className="grid gap-14 md:grid-cols-2 md:gap-10">
          {data.top_course_domains.length > 0 && (
            <Block title="課程領域">
              <BarList items={data.top_course_domains.slice(0, 10).map((item) => ({ label: item.domain, value: item.count }))} />
            </Block>
          )}
          {ge.categories.length > 0 && (
            <Block title="通識" aside={<span className="v2-faint text-sm">共 {ge.total} 次</span>}>
              <BarList items={ge.categories.map((item) => ({ label: item.name, value: item.count }))} />
            </Block>
          )}
        </div>
      )}
    </div>
  );
}

function ProjectTab({ data, loading, error }: { data: PdfAnalyticsData | null; loading: boolean; error: string }) {
  const [showAllDocs, setShowAllDocs] = useState(false);
  if (loading) return <Loading />;
  if (error) return <ErrorText message={error} />;
  if (!data || data.overview.total_conversations <= 0) return <Empty title="還沒有研究計畫的對話記錄" to="/projects" action="看研究計畫" />;

  const axes = collegeDomainAxes(data.college_distribution);
  const docs = showAllDocs ? data.document_list : data.document_list.slice(0, 5);

  return (
    <div className="space-y-14">
      <StatRow
        items={[
          { label: '對話', value: data.overview.total_conversations },
          { label: '提問', value: data.overview.total_questions },
          { label: '探索論文', value: data.overview.total_documents_explored },
          { label: '最常探索學院', value: <span className="text-2xl">{data.college_distribution[0]?.name || '—'}</span> },
        ]}
      />

      <div className="grid gap-14 md:grid-cols-2 md:gap-10">
        <Block title="研究領域">
          <DomainBars axes={axes} />
        </Block>
        {data.exploration_type.type && (
          <Block title="探索型態">
            <TypeCard
              label={data.exploration_type.type}
              desc={data.exploration_type.desc}
              facts={[
                ['探索論文', `${data.overview.total_documents_explored} 篇`],
                ['平均對話深度', `${data.overview.avg_depth} 輪`],
                ['涉及系所', `${data.dept_distribution.length} 個`],
              ]}
            />
          </Block>
        )}
      </div>

      <div className="grid gap-14 md:grid-cols-2 md:gap-10">
        <Block title="系所">
          <BarList items={data.dept_distribution.slice(0, 10).map((item) => ({ label: item.name, value: item.count, display: `${item.pct.toFixed(1)}%` }))} />
        </Block>
        <Block title="對話深度">
          <BarList items={data.depth_distribution.map((item) => ({ label: item.range, value: item.count, display: `${item.count} 次` }))} />
        </Block>
      </div>

      {data.document_list.length > 0 && (
        <Block title="看過的研究計畫" aside={<span className="v2-faint text-sm">{data.document_list.length} 篇</span>}>
          <ul>
            {docs.map((doc) => (
              <li key={doc.document_id} className="flex items-start gap-4 border-b py-3" style={{ borderColor: 'var(--v2-line)' }}>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold leading-snug">{doc.title || `${doc.department} 研究計畫`}</p>
                  <p className="v2-faint mt-0.5 text-sm">
                    {[doc.department, doc.year && `${doc.year} 學年度`].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <div className="flex-none text-right">
                  <p className="v2-num">{doc.conversation_count} 次</p>
                  {doc.last_viewed_at && <p className="v2-faint text-xs">{formatRelativeTime(doc.last_viewed_at)}</p>}
                </div>
              </li>
            ))}
          </ul>
          {data.document_list.length > 5 && (
            <button type="button" className="v2-btn v2-btn--ghost v2-btn--sm mt-4" onClick={() => setShowAllDocs((value) => !value)}>
              {showAllDocs ? '收起' : `全部 ${data.document_list.length} 篇`}
            </button>
          )}
        </Block>
      )}

      {data.recent_questions.length > 0 && (
        <Block title="最近的提問">
          <ul>
            {data.recent_questions.map((question, index) => (
              <li key={index} className="flex items-start gap-4 border-b py-3" style={{ borderColor: 'var(--v2-line)' }}>
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2">{question.question || '（無內容）'}</p>
                  {question.document_title && <p className="v2-faint mt-0.5 truncate text-sm">{question.document_title}</p>}
                </div>
                {question.created_at && <span className="v2-faint flex-none text-xs">{formatRelativeTime(question.created_at)}</span>}
              </li>
            ))}
          </ul>
        </Block>
      )}
    </div>
  );
}

export default function ProfileV2() {
  const { user, authLoading, activeTab, setActiveTab, courseData, courseLoading, courseError, projectData, projectLoading, projectError } =
    useAnalytics();
  const { loginWithGoogle } = useAuth();
  const [loginFailed, setLoginFailed] = useState(false);

  if (authLoading) {
    return (
      <div className="v2-container pb-20 pt-12 md:pt-16">
        <div className="v2-skeleton h-12 w-64" />
        <div className="mt-12">
          <Loading />
        </div>
      </div>
    );
  }

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
      <div className="v2-container pb-20 pt-12 md:pt-16">
        <h1 className="v2-serif text-4xl md:text-5xl">個人分析</h1>
        <p className="v2-muted mt-4">登入後，依你和課程助理、研究計畫的對話整理出興趣方向。</p>
        <button type="button" className="v2-btn mt-8" onClick={handleLogin}>
          <GoogleMark />
          登入
        </button>
        {loginFailed && (
          <p role="alert" className="mt-2 text-sm" style={{ color: 'var(--v2-danger)' }}>
            登入失敗，請再試一次
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="v2-container pb-20 pt-12 md:pt-16">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div className="flex min-w-0 items-center gap-4">
          {user.picture ? (
            <img src={user.picture} alt="" className="h-14 w-14 flex-none rounded-full object-cover" referrerPolicy="no-referrer" />
          ) : (
            <span className="flex h-14 w-14 flex-none items-center justify-center rounded-full text-xl font-bold text-white" style={{ background: 'var(--v2-ink)' }}>
              {user.name?.[0] ?? '?'}
            </span>
          )}
          <div className="min-w-0">
            <h1 className="v2-serif truncate text-3xl md:text-4xl">{user.name}</h1>
            <p className="v2-faint truncate text-sm">{user.email}</p>
          </div>
        </div>
        <RovingGroup role="tablist" aria-label="分析範圍" className="v2-seg">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`profile-tab-${tab.id}`}
              aria-selected={activeTab === tab.id}
              aria-controls="profile-panel"
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </RovingGroup>
      </header>

      <div id="profile-panel" role="tabpanel" aria-labelledby={`profile-tab-${activeTab}`} className="mt-12">
        {activeTab === 'all' && <AllTab courseData={courseData} projectData={projectData} loading={courseLoading || projectLoading} />}
        {activeTab === 'course' && <CourseTab data={courseData} loading={courseLoading} error={courseError} />}
        {activeTab === 'project' && <ProjectTab data={projectData} loading={projectLoading} error={projectError} />}
      </div>
    </div>
  );
}
