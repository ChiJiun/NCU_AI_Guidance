import { useEffect, useMemo, useState } from 'react';
import { HiArrowLeft, HiChevronDown, HiDocumentDownload, HiDocumentText, HiSwitchHorizontal, HiX } from 'react-icons/hi';
import { apiClient } from '../../api/client';
import CourseDetailModal from '../../components/CourseDetailModal';
import { deptSortKey } from '../../constants/colleges';
import { CATEGORIES_ORDER, REQUIRED_COURSE_FIELDS, findCrossMatches, groupBySem } from '../../features/curriculum/courseIndex';
import type { CourseEntry, DeptDetail, ElectiveGroup, GraduationRule, NotesEntry } from '../../features/curriculum/types';
import { useCurriculumData } from '../../features/curriculum/useCurriculumData';
import type { CourseCard } from '../../types';
import { collegeHex } from '../colleges';
import V2Dialog from '../components/V2Dialog';
import RovingGroup from '../components/RovingGroup';

type Tab = 'required' | 'elective' | 'rules';
const TAB_LABELS: Record<Tab, string> = { required: '必修', elective: '選修', rules: '畢業規定' };

const ELECTIVE_SECTIONS: { key: keyof DeptDetail; label: string }[] = [
  { key: 'core_elective_groups', label: '核心必選' },
  { key: 'college_required_elective_groups', label: '院訂必選' },
  { key: 'science_ability_groups', label: '科學能力必選' },
  { key: 'elective_groups', label: '選修群' },
  { key: 'other_elective_groups', label: '其他選修' },
];

interface CourseActions {
  onOpen: (course: CourseEntry) => void;
  onCross: (course: CourseEntry) => void;
}

function CourseItem({ course, actions }: { course: CourseEntry; actions: CourseActions }) {
  return (
    <li className="group flex items-stretch rounded-md border bg-[var(--v2-surface)]" style={{ borderColor: 'var(--v2-line)' }}>
      <button type="button" className="flex min-h-11 min-w-0 flex-1 items-center gap-2 px-3 py-1.5 text-left hover:bg-[var(--v2-paper-2)]" onClick={() => actions.onOpen(course)}>
        <span className="min-w-0 flex-1 leading-snug">{course.name}</span>
        <span className="v2-num shrink-0">{course.credits}</span>
      </button>
      <button
        type="button"
        className="v2-iconbtn !h-auto !w-10 !rounded-none border-l"
        style={{ borderColor: 'var(--v2-line)' }}
        aria-label={`「${course.name}」在其他系所`}
        title="其他系所"
        onClick={() => actions.onCross(course)}
      >
        <HiSwitchHorizontal className="h-4 w-4" aria-hidden="true" />
      </button>
    </li>
  );
}

function CourseGrid({ courses, actions }: { courses: CourseEntry[]; actions: CourseActions }) {
  return (
    <ul className="grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
      {courses.map((course, index) => (
        <CourseItem key={`${course.code}-${index}`} course={course} actions={actions} />
      ))}
    </ul>
  );
}

/** 必修依學期排成一列一學期：左邊是學期，右邊是那學期的課 */
function SemesterTimeline({ courses, actions }: { courses: CourseEntry[]; actions: CourseActions }) {
  const bySem = groupBySem(courses);
  return (
    <ol className="space-y-px">
      {[...bySem.entries()].map(([sem, list]) => (
        <li key={sem} className="grid gap-x-4 gap-y-2 border-t py-3 md:grid-cols-[4.5rem_1fr]" style={{ borderColor: 'var(--v2-line)' }}>
          <h4 className="v2-serif text-base">{sem === '未分配' ? '不限' : sem}</h4>
          <CourseGrid courses={list} actions={actions} />
        </li>
      ))}
    </ol>
  );
}

function GroupBlock({ group, actions }: { group: ElectiveGroup; actions: CourseActions }) {
  const rule = group.select ? `${group.select} 門` : group.select_credits ? `${group.select_credits} 學分` : '';
  const options = [
    { label: 'A', courses: group.option_a },
    { label: 'B', courses: group.option_b },
    { label: 'C', courses: group.option_c },
  ].filter((option) => option.courses && option.courses.length > 0);
  return (
    <section className="border-t py-4" style={{ borderColor: 'var(--v2-line)' }}>
      <h4 className="mb-3 flex items-baseline gap-3">
        <span className="font-bold">{group.name || '選修群'}</span>
        {rule && (
          <span className="v2-accent text-sm font-semibold">
            選 <span className="v2-num">{rule}</span>
          </span>
        )}
      </h4>
      {group.description && <p className="v2-muted mb-3 text-sm">{group.description}</p>}
      {(group.courses?.length ?? 0) > 0 && <CourseGrid courses={group.courses!} actions={actions} />}
      {group.slots?.map((slot, index) => (
        <div key={index} className="mt-3">
          <h5 className="v2-faint mb-1.5 text-sm font-semibold">{slot.slot_name}</h5>
          <CourseGrid courses={slot.courses} actions={actions} />
        </div>
      ))}
      {options.map((option) => (
        <div key={option.label} className="mt-3">
          <h5 className="v2-num v2-faint mb-1.5 text-sm">{option.label}</h5>
          <CourseGrid courses={option.courses!} actions={actions} />
        </div>
      ))}
    </section>
  );
}

function RuleRow({ rule, actions }: { rule: GraduationRule; actions: CourseActions }) {
  const amount = rule.credits !== undefined ? `${rule.credits} 學分` : rule.select !== undefined ? `${rule.select} 門` : '';
  const showType = rule.type && !/^[a-zA-Z_]+$/.test(rule.type);
  return (
    <li className="border-t py-3" style={{ borderColor: 'var(--v2-line)' }}>
      <div className="flex items-baseline gap-3">
        <p className="min-w-0 flex-1 leading-relaxed">
          {showType && <span className="mr-2 font-semibold">{rule.type}</span>}
          <span className="v2-muted">{rule.description ?? (rule.cert ? rule.cert : '')}</span>
        </p>
        {amount && <span className="v2-num shrink-0">{amount}</span>}
      </div>
      {(rule.courses?.length ?? 0) > 0 && (
        <div className="mt-2">
          <CourseGrid courses={rule.courses!} actions={actions} />
        </div>
      )}
      {(rule.course_codes?.length ?? 0) > 0 && (
        <p className="v2-faint mt-1 font-mono text-xs">{rule.course_codes!.join('  ')}</p>
      )}
      {(rule.options?.length ?? 0) > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {rule.options!.map((option, index) => (
            <li key={index} className="v2-tag">
              {option.name}
              {option.credits ? <span className="v2-num ml-1">{option.credits}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function DeptBody({ detail, defaultTab, actions }: { detail: DeptDetail; defaultTab?: Tab; actions: CourseActions }) {
  const required = REQUIRED_COURSE_FIELDS.map(({ key, label }) => ({
    label,
    courses: (detail[key] as CourseEntry[] | undefined) ?? [],
  })).filter((section) => section.courses.length > 0);
  const electiveSections = ELECTIVE_SECTIONS.map(({ key, label }) => ({
    label,
    groups: (detail[key] as ElectiveGroup[] | undefined) ?? [],
  })).filter((section) => section.groups.length > 0);
  const electiveCourses = detail.elective_courses ?? [];
  const rules = detail.graduation_rules ?? [];
  const ruleCategories = [...new Set([...CATEGORIES_ORDER, ...rules.map((rule) => rule.category ?? '其他規定')])]
    .map((category) => ({ category, rules: rules.filter((rule) => (rule.category ?? '其他規定') === category) }))
    .filter((group) => group.rules.length > 0);

  const tabs = (
    [
      required.length > 0 ? 'required' : null,
      electiveSections.length > 0 || electiveCourses.length > 0 ? 'elective' : null,
      rules.length > 0 || detail.graduation_notes ? 'rules' : null,
    ] as const
  ).filter((tab): tab is Tab => tab !== null);
  const [picked, setPicked] = useState<Tab | null>(null);
  const tab = picked && tabs.includes(picked) ? picked : defaultTab && tabs.includes(defaultTab) ? defaultTab : tabs[0];

  if (tabs.length === 0) return <p className="v2-muted py-10">這個系所還沒有修課資料</p>;

  return (
    <>
      {tabs.length > 1 && (
        <RovingGroup role="tablist" aria-label="修課內容" className="v2-seg mb-4">
          {tabs.map((item) => (
            <button key={item} type="button" role="tab" aria-selected={tab === item} onClick={() => setPicked(item)}>
              {TAB_LABELS[item]}
            </button>
          ))}
        </RovingGroup>
      )}

      <div role="tabpanel" aria-label={TAB_LABELS[tab]}>
        {tab === 'required' &&
          required.map((section) => (
            <section key={section.label} className="mb-6">
              {required.length > 1 && <h3 className="v2-serif mb-1 text-lg">{section.label}</h3>}
              <SemesterTimeline courses={section.courses} actions={actions} />
            </section>
          ))}

        {tab === 'elective' && (
          <>
            {electiveSections.map((section) => (
              <section key={section.label} className="mb-6">
                <h3 className="v2-serif mb-1 text-lg">{section.label}</h3>
                {section.groups.map((group, index) => (
                  <GroupBlock key={index} group={group} actions={actions} />
                ))}
              </section>
            ))}
            {electiveCourses.length > 0 && (
              <section className="mb-6">
                <h3 className="v2-serif mb-3 text-lg">
                  領域選修 <span className="v2-num v2-faint text-base">{electiveCourses.length}</span>
                </h3>
                <CourseGrid courses={electiveCourses} actions={actions} />
              </section>
            )}
          </>
        )}

        {tab === 'rules' && (
          <>
            {ruleCategories.map((group) => (
              <section key={group.category} className="mb-6">
                <h3 className="v2-serif mb-1 text-lg">{group.category}</h3>
                <ul>
                  {group.rules.map((rule, index) => (
                    <RuleRow key={`${rule.type}-${index}`} rule={rule} actions={actions} />
                  ))}
                </ul>
              </section>
            ))}
            {detail.graduation_notes && (
              <p className="v2-muted whitespace-pre-wrap border-t pt-4 leading-relaxed" style={{ borderColor: 'var(--v2-line)' }}>
                {detail.graduation_notes}
              </p>
            )}
          </>
        )}
      </div>
    </>
  );
}

/** 原始應修規定的文字（舊版的「參考文字」） */
function NotesDrawer({ deptId, onClose }: { deptId: string; onClose: () => void }) {
  const [result, setResult] = useState<{ deptId: string; entries: NotesEntry[] } | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get(`/curriculum/notes/by-id/${deptId}`)
      .then((res) => {
        if (!cancelled) setResult({ deptId, entries: res.data.entries ?? [] });
      })
      .catch(() => {
        if (!cancelled) setResult({ deptId, entries: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [deptId]);

  const entries = result?.deptId === deptId ? result.entries : null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" aria-hidden="true" onClick={onClose} />
      <V2Dialog
        aria-label="原始規定"
        onClose={onClose}
        className="v2-rise relative flex h-full w-full max-w-lg flex-col shadow-2xl"
        style={{ background: 'var(--v2-paper)' }}
      >
        <header className="flex items-center border-b py-2 pl-5 pr-2" style={{ borderColor: 'var(--v2-line)' }}>
          <h2 className="v2-serif flex-1 text-lg">原始規定</h2>
          <button type="button" className="v2-iconbtn" aria-label="關閉" onClick={onClose}>
            <HiX className="h-5 w-5" aria-hidden="true" />
          </button>
        </header>
        <div className="v2-scroll min-h-0 flex-1 space-y-6 px-5 py-5">
          {entries === null ? (
            <div role="status" className="flex justify-center py-10">
              <span className="v2-spinner" aria-hidden="true" />
              <span className="sr-only">載入中</span>
            </div>
          ) : entries.length === 0 ? (
            <p className="v2-muted">沒有原始規定文字</p>
          ) : (
            entries.map((entry) => (
              <section key={entry.key}>
                {entries.length > 1 && <h3 className="mb-2 font-bold">{entry.key}</h3>}
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{entry.raw_text}</p>
              </section>
            ))
          )}
        </div>
      </V2Dialog>
    </div>
  );
}

export default function CurriculumV2() {
  const {
    tree, childDeptIds,
    expandedColleges, toggleCollege,
    selectedId, detail,
    loadingTree, loadingDetail,
    isMobileMenuOpen, setIsMobileMenuOpen,
    courseIndex, indexReady,
    navigateTo, selectDept,
  } = useCurriculumData(collegeHex);
  const [openCourse, setOpenCourse] = useState<CourseCard | null>(null);
  const [crossCourse, setCrossCourse] = useState<CourseEntry | null>(null);
  const [notesOpen, setNotesOpen] = useState(false);
  const [groupPick, setGroupPick] = useState<{ deptId: string; groupId: string } | null>(null);

  const colleges = useMemo(
    () =>
      tree.map((college) => ({
        college,
        depts: [
          ...college.departments.map((dept) => ({
            id: dept.id,
            name: dept.name,
            subs: (dept.groups ?? []).map((group) => ({ id: group.id, name: group.group_label || group.name })),
          })),
          ...college.college_bachelor_programs.map((program) => ({
            id: program.id,
            name: program.name,
            subs: (program.specialization_tracks ?? []).map((track) => ({ id: track.id, name: track.name })),
          })),
        ].sort((a, b) => deptSortKey(a.name) - deptSortKey(b.name) || a.name.localeCompare(b.name, 'zh-Hant')),
      })),
    [tree],
  );
  const currentCollege = colleges.find(({ depts }) =>
    depts.some((dept) => dept.id === selectedId || dept.subs.some((sub) => sub.id === selectedId)),
  )?.college;
  const accent = currentCollege ? collegeHex(currentCollege.name) : 'var(--v2-ink)';

  const actions: CourseActions = {
    onOpen: (course) =>
      setOpenCourse({
        code: course.code || '',
        name: course.name,
        dept: detail?.name ?? '',
        credits: course.credits || 0,
        type: course.mandatory ? '必修' : '選修',
        teacher: '',
        summary: '',
      }),
    onCross: setCrossCourse,
  };

  const groups = detail?.groups ?? [];
  const activeGroup =
    detail && groupPick?.deptId === detail.id ? groups.find((group) => group.id === groupPick.groupId) ?? null : null;
  const cross = crossCourse && detail && indexReady ? findCrossMatches(crossCourse.name, detail.id, courseIndex) : null;
  const crossRows = cross
    ? [
        ...cross.exact.map((hit) => ({ hit, similar: false })),
        ...cross.similar.slice(0, 5).flatMap(({ hits }) => hits.map((hit) => ({ hit, similar: true }))),
      ]
    : [];
  const pdfHref = detail ? `${apiClient.defaults.baseURL}/curriculum/pdf/${detail.id}` : '';

  return (
    <div className="grid h-full min-h-0 lg:grid-cols-[18rem_1fr]">
      <h1 className="sr-only">系所修課</h1>

      {/* 學院與系所 */}
      <nav
        aria-label="學院與系所"
        className={`${isMobileMenuOpen || !selectedId ? 'block' : 'hidden'} v2-scroll min-h-0 border-r lg:block`}
        style={{ borderColor: 'var(--v2-line)' }}
      >
        {loadingTree ? (
          <div className="space-y-2 p-4" role="status">
            {Array.from({ length: 8 }, (_, index) => (
              <div key={index} className="v2-skeleton h-10" />
            ))}
            <span className="sr-only">載入中</span>
          </div>
        ) : (
          <ul>
            {colleges.map(({ college, depts }) => {
              const open = expandedColleges.has(college.id);
              return (
                <li key={college.id}>
                  <button type="button" className="v2-row !min-h-12 font-semibold" aria-expanded={open} onClick={() => toggleCollege(college.id)}>
                    <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: collegeHex(college.name) }} aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate">{college.name}</span>
                    <span className="v2-faint text-sm tabular-nums">{depts.length}</span>
                    <HiChevronDown className={`v2-faint h-4 w-4 flex-none transition-transform ${open ? '' : '-rotate-90'}`} aria-hidden="true" />
                  </button>
                  {open && (
                    <ul>
                      {depts.map((dept) => (
                        <li key={dept.id}>
                          <button
                            type="button"
                            className="v2-row !pl-9 text-[0.9375rem]"
                            aria-current={selectedId === dept.id ? 'true' : undefined}
                            onClick={() => selectDept(dept.id)}
                          >
                            <span className="min-w-0 flex-1 truncate">{dept.name}</span>
                          </button>
                          {dept.subs.length > 0 && (
                            <ul>
                              {dept.subs.map((sub) => (
                                <li key={sub.id}>
                                  <button
                                    type="button"
                                    className="v2-row v2-muted !min-h-10 !pl-14 text-sm"
                                    aria-current={selectedId === sub.id ? 'true' : undefined}
                                    onClick={() => selectDept(sub.id)}
                                  >
                                    <span className="min-w-0 flex-1 truncate">{sub.name}</span>
                                  </button>
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      {/* 系所內容 */}
      <section
        aria-label="系所修課內容"
        className={`${isMobileMenuOpen || !selectedId ? 'hidden' : 'block'} v2-scroll min-h-0 lg:block`}
      >
        {!selectedId ? (
          <div className="v2-hero-art !relative h-full opacity-60" aria-hidden="true">
            <div className="v2-hero-static" />
          </div>
        ) : loadingDetail || !detail ? (
          <div className="flex h-full items-center justify-center" role="status">
            <span className="v2-spinner" aria-hidden="true" />
            <span className="sr-only">載入中</span>
          </div>
        ) : (
          <div key={detail.id} className="v2-rise mx-auto max-w-5xl px-5 pb-16 pt-4 md:px-10 md:pt-8">
            <button type="button" className="v2-navlink -ml-3 gap-1.5 lg:!hidden" onClick={() => setIsMobileMenuOpen(true)}>
              <HiArrowLeft className="h-4 w-4" aria-hidden="true" />
              {currentCollege?.name ?? '系所'}
            </button>

            <header className="border-b pb-6" style={{ borderColor: 'var(--v2-line)' }}>
              <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: accent }}>
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: accent }} aria-hidden="true" />
                {currentCollege?.name}
              </p>
              <h2 className="v2-serif mt-1 text-3xl md:text-4xl">{detail.name}</h2>
              <div className="mt-5 flex flex-wrap items-end justify-between gap-6">
                <dl className="flex gap-10">
                  {detail.min_credits > 0 && (
                    <div className="flex flex-col-reverse">
                      <dt className="v2-muted text-sm">畢業學分</dt>
                      <dd className="v2-num text-5xl">{detail.min_credits}</dd>
                    </div>
                  )}
                  {detail.required_credits !== undefined && (
                    <div className="flex flex-col-reverse">
                      <dt className="v2-muted text-sm">必修學分</dt>
                      <dd className="v2-num text-5xl">{detail.required_credits}</dd>
                    </div>
                  )}
                </dl>
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="v2-btn v2-btn--ghost v2-btn--sm" onClick={() => setNotesOpen(true)}>
                    <HiDocumentText className="h-4 w-4" aria-hidden="true" />
                    原始規定
                  </button>
                  <a href={pdfHref} target="_blank" rel="noopener noreferrer" className="v2-btn v2-btn--ghost v2-btn--sm">
                    <HiDocumentDownload className="h-4 w-4" aria-hidden="true" />
                    應修科目表
                  </a>
                </div>
              </div>
            </header>

            {groups.length > 0 && (
              <RovingGroup role="radiogroup" aria-label="分組" className="mt-5 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  role="radio"
                  aria-checked={!activeGroup}
                  className="v2-chip v2-chip--sm"
                  onClick={() => setGroupPick(null)}
                >
                  共同
                </button>
                {groups.map((group) => (
                  <button
                    key={group.id}
                    type="button"
                    role="radio"
                    aria-checked={activeGroup?.id === group.id}
                    className="v2-chip v2-chip--sm"
                    onClick={() => setGroupPick({ deptId: detail.id, groupId: group.id })}
                  >
                    {group.name}
                  </button>
                ))}
              </RovingGroup>
            )}

            <div className="mt-6">
              <DeptBody
                key={activeGroup?.id ?? detail.id}
                detail={activeGroup ?? detail}
                defaultTab={childDeptIds.has(detail.id) ? 'elective' : undefined}
                actions={actions}
              />
            </div>
          </div>
        )}
      </section>

      {notesOpen && detail && <NotesDrawer deptId={detail.id} onClose={() => setNotesOpen(false)} />}

      {crossCourse && (
        <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
          <div className="absolute inset-0 bg-black/30" aria-hidden="true" onClick={() => setCrossCourse(null)} />
          <V2Dialog
            aria-labelledby="v2-cross-title"
            onClose={() => setCrossCourse(null)}
            className="v2-rise relative flex max-h-[80vh] w-full max-w-lg flex-col rounded-t-xl shadow-2xl sm:rounded-xl"
            style={{ background: 'var(--v2-paper)' }}
          >
            <header className="flex items-center border-b py-2 pl-5 pr-2" style={{ borderColor: 'var(--v2-line)' }}>
              <h2 id="v2-cross-title" className="v2-serif min-w-0 flex-1 truncate text-lg">
                {crossCourse.name}
              </h2>
              <button type="button" className="v2-iconbtn" aria-label="關閉" autoFocus onClick={() => setCrossCourse(null)}>
                <HiX className="h-5 w-5" aria-hidden="true" />
              </button>
            </header>
            <div className="v2-scroll min-h-0 flex-1">
              {!indexReady ? (
                <div role="status" className="flex justify-center py-10">
                  <span className="v2-spinner" aria-hidden="true" />
                  <span className="sr-only">建立索引中</span>
                </div>
              ) : crossRows.length === 0 ? (
                <p className="v2-muted px-5 py-10 text-center">其他系所沒有這門課</p>
              ) : (
                <ul>
                  {crossRows.map(({ hit, similar }, index) => (
                    <li key={`${hit.deptId}-${hit.originalCode}-${index}`}>
                      <button
                        type="button"
                        className="v2-row"
                        onClick={() => {
                          setCrossCourse(null);
                          navigateTo(hit.deptId);
                        }}
                      >
                        <span className="h-2 w-2 flex-none rounded-full" style={{ background: hit.accentHex }} aria-hidden="true" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{hit.deptName}</span>
                          {similar && <span className="v2-faint block truncate text-sm">{hit.originalName}</span>}
                        </span>
                        <span className={`shrink-0 text-sm ${hit.category === 'required' ? 'v2-accent font-semibold' : 'v2-muted'}`}>
                          {hit.category === 'required' ? '必修' : '選修'}
                        </span>
                        <span className="v2-num w-6 shrink-0 text-right">{hit.credits}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </V2Dialog>
        </div>
      )}

      {openCourse && <CourseDetailModal course={openCourse} onClose={() => setOpenCourse(null)} />}
    </div>
  );
}
