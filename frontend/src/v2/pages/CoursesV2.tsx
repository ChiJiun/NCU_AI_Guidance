import { useState } from 'react';
import type { Dispatch, FormEvent, SetStateAction } from 'react';
import { HiAdjustments, HiArrowLeft, HiChevronDown, HiSearch, HiX } from 'react-icons/hi';
import CourseCompareModal from '../../components/CourseCompareModal';
import HighlightText from '../../components/HighlightText';
import { sortDeptsInCollege } from '../../constants/colleges';
import {
  COMPARE_LIMIT, FALLBACK_COLLEGE, FALLBACK_DEPARTMENT,
  courseKey, formatScore, getDetailPreview, normalize,
} from '../../features/courses/catalog';
import { useCourseCatalog } from '../../features/courses/useCourseCatalog';
import type { Course } from '../../types';
import { collegeHex } from '../colleges';
import CourseDetailV2 from '../components/CourseDetailV2';
import RovingGroup from '../components/RovingGroup';

const PAGE_SIZE = 80;

type Scope = 'semantic' | 'name' | 'full';
const SCOPES: { id: Scope; label: string }[] = [
  { id: 'semantic', label: '語意' },
  { id: 'name', label: '課名' },
  { id: 'full', label: '全文' },
];

const LEVELS = [
  { id: 'undergrad', label: '大學部' },
  { id: 'grad', label: '研究所' },
] as const;

const toggle = (value: string, setter: Dispatch<SetStateAction<string[]>>) =>
  setter((current) => (current.includes(value) ? current.filter((item) => item !== value) : [...current, value]));

export default function CoursesV2() {
  const catalog = useCourseCatalog();
  const {
    loading,
    searchQuery, setSearchQuery,
    selectedTypes, setSelectedTypes,
    selectedCredits, setSelectedCredits,
    selectedSemesters, setSelectedSemesters,
    selectedCollege,
    selectedDepartment, setSelectedDepartment,
    selectedCourse, setSelectedCourse,
    resultTab, setResultTab,
    searchMode, setSearchMode,
    semanticLoading, semanticMode, semanticMessage,
    compareCourses, compareOpen, setCompareOpen, compareNotice,
    selectedFieldFilters, setSelectedFieldFilters,
    courseLevel, setCourseLevel,
    groupedCourses, sortedColleges,
    departmentFieldOptions, currentCourses, filteredCourses, groupedSearchResults,
    typeOptions, creditOptions, semesterOptions,
    hasActiveFilters,
    isCourseCompared, toggleCompareCourse, removeCompareCourse, clearCompareCourses,
    selectFlatSearchResult, selectCollege, selectDepartment,
  } = catalog;

  // 搜尋框的草稿：按 Enter 才送出（語意搜尋每次都會呼叫後端）。null 表示沿用目前的搜尋字串。
  const [draft, setDraft] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  // 搜尋結果依學院／系所縮小範圍
  const [facet, setFacet] = useState<{ college: string; department?: string } | null>(null);
  const [more, setMore] = useState({ key: '', pages: 0 });

  const scope: Scope = searchMode === 'semantic' ? 'semantic' : resultTab === 'course_name' ? 'name' : 'full';
  const setScope = (next: Scope) => {
    setSearchMode(next === 'semantic' ? 'semantic' : 'keyword');
    if (next !== 'semantic') setResultTab(next === 'name' ? 'course_name' : 'detail_info');
  };

  const filterCount = selectedTypes.length + selectedCredits.length + selectedSemesters.length;
  const keyword = searchQuery.trim();
  const searching = hasActiveFilters;

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (draft === null) return;
    setSearchQuery(draft.trim());
    setDraft(null);
    setFacet(null);
  };

  const clearSearch = () => {
    setDraft(null);
    setSearchQuery('');
    setSelectedTypes([]);
    setSelectedCredits([]);
    setSelectedSemesters([]);
    setFacet(null);
  };

  // ── 左欄：學院／系所 ──
  const activeFacet = facet && groupedSearchResults.some((group) => group.college === facet.college) ? facet : null;
  const openCollege = searching ? activeFacet?.college ?? null : collapsed ? null : selectedCollege;
  const tree = searching
    ? groupedSearchResults.map((group) => ({
        college: group.college,
        count: group.count,
        departments: group.departments.map((dept) => ({ name: dept.name, count: dept.count })),
      }))
    : sortedColleges.map((college) => {
        const departments = groupedCourses[college] ?? {};
        return {
          college,
          count: Object.values(departments).reduce((sum, list) => sum + list.length, 0),
          departments: sortDeptsInCollege(Object.keys(departments)).map((name) => ({ name, count: departments[name].length })),
        };
      });

  const pickCollege = (college: string) => {
    if (searching) {
      setFacet(activeFacet?.college === college && !activeFacet.department ? null : { college });
      return;
    }
    if (college === selectedCollege) {
      setCollapsed((value) => !value);
      return;
    }
    setCollapsed(false);
    selectCollege(college);
  };

  const pickDepartment = (college: string, department: string) => {
    if (searching) {
      setFacet({ college, department });
      return;
    }
    selectDepartment(department);
  };

  // ── 中欄：課程清單 ──
  const list: Course[] = searching
    ? activeFacet
      ? filteredCourses.filter(
          (course) =>
            (normalize(course.college) || FALLBACK_COLLEGE) === activeFacet.college &&
            (!activeFacet.department || (normalize(course.department) || FALLBACK_DEPARTMENT) === activeFacet.department),
        )
      : filteredCourses
    : currentCourses;
  const listKey = `${searching}|${keyword}|${scope}|${activeFacet?.college ?? ''}|${activeFacet?.department ?? ''}|${selectedCollege}|${selectedDepartment}|${courseLevel}`;
  const visible = list.slice(0, PAGE_SIZE * ((more.key === listKey ? more.pages : 0) + 1));
  const listTitle = searching
    ? activeFacet?.department ?? activeFacet?.college ?? '搜尋結果'
    : selectedDepartment ?? '';
  const listBusy = searching && scope === 'semantic' && semanticLoading;
  const showList = searching || Boolean(selectedDepartment);

  // 手機一次只顯示一欄：詳情 > 清單 > 學院樹
  const pane = selectedCourse ? 'detail' : showList ? 'list' : 'tree';
  const paneClass = (name: typeof pane) => (pane === name ? 'flex' : 'hidden lg:flex');

  return (
    <div className="flex h-full flex-col">
      <h1 className="sr-only">課程</h1>

      {/* 搜尋與篩選 */}
      <div className="flex-none border-b" style={{ borderColor: 'var(--v2-line)' }}>
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 md:px-6">
          <form role="search" onSubmit={handleSearch} className="relative min-w-0 flex-1 basis-64">
            <HiSearch className="v2-faint pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2" aria-hidden="true" />
            <input
              type="search"
              className="v2-input !pl-10 !pr-11"
              aria-label="搜尋課程"
              placeholder="搜尋課程"
              enterKeyHint="search"
              value={draft ?? searchQuery}
              onChange={(event) => setDraft(event.target.value)}
            />
            {(draft ?? searchQuery) && (
              <button
                type="button"
                className="v2-iconbtn absolute right-0 top-0"
                aria-label="清除搜尋"
                onClick={() => {
                  setDraft(null);
                  setSearchQuery('');
                  setFacet(null);
                }}
              >
                <HiX className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </form>

          <div className="flex flex-wrap items-center gap-2">
            <RovingGroup role="radiogroup" aria-label="搜尋方式" className="v2-seg flex-none">
              {SCOPES.map((item) => (
                <button key={item.id} type="button" role="radio" aria-checked={scope === item.id} onClick={() => setScope(item.id)}>
                  {item.label}
                </button>
              ))}
            </RovingGroup>
            <button
              type="button"
              className="v2-iconbtn relative"
              aria-label={`篩選${filterCount ? `（已選 ${filterCount} 項）` : ''}`}
              aria-expanded={filtersOpen}
              aria-controls="v2-course-filters"
              aria-pressed={filtersOpen || filterCount > 0}
              onClick={() => setFiltersOpen((value) => !value)}
            >
              <HiAdjustments className="h-5 w-5" aria-hidden="true" />
              {filterCount > 0 && (
                <span className="v2-num absolute right-1 top-0.5 text-xs" aria-hidden="true">
                  {filterCount}
                </span>
              )}
            </button>
            <RovingGroup role="radiogroup" aria-label="學制" className="v2-seg flex-none">
              {LEVELS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="radio"
                  aria-checked={courseLevel === item.id}
                  onClick={() => {
                    setFacet(null);
                    setCourseLevel(item.id);
                  }}
                >
                  {item.label}
                </button>
              ))}
            </RovingGroup>
          </div>
        </div>

        {filtersOpen && (
          <div id="v2-course-filters" className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pb-3 md:px-6">
            {[
              { name: '修別', options: typeOptions, selected: selectedTypes, setter: setSelectedTypes, format: (value: string) => value },
              { name: '學分', options: creditOptions, selected: selectedCredits, setter: setSelectedCredits, format: (value: string) => `${value} 學分` },
              { name: '學期', options: semesterOptions, selected: selectedSemesters, setter: setSelectedSemesters, format: (value: string) => value },
            ].map((group) => (
              <div key={group.name} role="group" aria-label={group.name} className="flex flex-wrap gap-1.5">
                {group.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className="v2-chip v2-chip--sm"
                    aria-pressed={group.selected.includes(option)}
                    onClick={() => toggle(option, group.setter)}
                  >
                    {group.format(option)}
                  </button>
                ))}
              </div>
            ))}
            {searching && (
              <button type="button" className="v2-navlink !min-h-8 !px-1 underline underline-offset-4" onClick={clearSearch}>
                全部清除
              </button>
            )}
          </div>
        )}
      </div>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[17rem_23rem_1fr]">
        {/* 學院／系所 */}
        <nav
          aria-label={searching ? '依學院縮小搜尋結果' : '學院與系所'}
          className={`${paneClass('tree')} v2-scroll min-h-0 flex-col border-r`}
          style={{ borderColor: 'var(--v2-line)' }}
        >
          {loading ? (
            <div className="space-y-2 p-4" role="status">
              {Array.from({ length: 8 }, (_, index) => (
                <div key={index} className="v2-skeleton h-10" />
              ))}
              <span className="sr-only">載入中</span>
            </div>
          ) : (
            <ul>
              {tree.map((node) => {
                const open = openCollege === node.college;
                return (
                  <li key={node.college}>
                    <button
                      type="button"
                      className="v2-row !min-h-12 font-semibold"
                      aria-expanded={open}
                      onClick={() => pickCollege(node.college)}
                    >
                      <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: collegeHex(node.college) }} aria-hidden="true" />
                      <span className="min-w-0 flex-1 truncate">{node.college}</span>
                      <span className="v2-faint text-sm tabular-nums">{node.count}</span>
                      <HiChevronDown
                        className={`v2-faint h-4 w-4 flex-none transition-transform ${open ? '' : '-rotate-90'}`}
                        aria-hidden="true"
                      />
                    </button>
                    {open && (
                      <ul>
                        {node.departments.map((dept) => {
                          const current = searching
                            ? activeFacet?.department === dept.name
                            : selectedDepartment === dept.name;
                          return (
                            <li key={dept.name}>
                              <button
                                type="button"
                                className="v2-row !pl-9 text-[0.9375rem]"
                                aria-current={current ? 'true' : undefined}
                                onClick={() => pickDepartment(node.college, dept.name)}
                              >
                                <span className="min-w-0 flex-1 truncate">{dept.name}</span>
                                <span className="v2-faint v2-num text-sm">{dept.count}</span>
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </nav>

        {/* 課程清單 */}
        <section
          aria-label="課程清單"
          className={`${paneClass('list')} min-h-0 flex-col border-r`}
          style={{ borderColor: 'var(--v2-line)' }}
        >
          {showList && (
            <header className="flex-none border-b px-2 py-2" style={{ borderColor: 'var(--v2-line)' }}>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  className="v2-iconbtn lg:!hidden"
                  aria-label={searching ? '清除搜尋' : '回到學院'}
                  onClick={() => (searching ? clearSearch() : setSelectedDepartment(null))}
                >
                  <HiArrowLeft className="h-5 w-5" aria-hidden="true" />
                </button>
                <h2 className="min-w-0 flex-1 truncate pl-2 font-bold lg:pl-3">{listTitle}</h2>
                <p className="v2-num pr-3 text-lg" aria-live="polite">
                  {listBusy ? <span className="v2-spinner block" aria-label="搜尋中" /> : list.length}
                </p>
              </div>
              {searching && scope === 'semantic' && semanticMode === 'fallback' && semanticMessage && (
                <p role="status" className="v2-muted px-3 pb-1 text-sm">
                  {semanticMessage}
                </p>
              )}
              {!searching && departmentFieldOptions.length > 0 && (
                <div role="group" aria-label="課程領域" className="flex gap-1.5 overflow-x-auto px-3 pb-1 pt-1">
                  {departmentFieldOptions.map((field) => (
                    <button
                      key={field}
                      type="button"
                      className="v2-chip v2-chip--sm flex-none"
                      aria-pressed={selectedFieldFilters.includes(field)}
                      onClick={() => toggle(field, setSelectedFieldFilters)}
                    >
                      {field}
                    </button>
                  ))}
                </div>
              )}
            </header>
          )}

          <div className="v2-scroll min-h-0 flex-1">
            {showList ? (
              <>
                <ul>
                  {visible.map((course) => {
                    const score = searching && scope === 'semantic' ? formatScore(course.relevance_score) : null;
                    const preview = searching && scope === 'full' && keyword ? getDetailPreview(course, keyword) : '';
                    const required = normalize(course.required_elective) === '必修';
                    return (
                      <li key={courseKey(course)}>
                        <button
                          type="button"
                          className="v2-row !items-start !py-3"
                          aria-current={selectedCourse && courseKey(selectedCourse) === courseKey(course) ? 'true' : undefined}
                          onClick={() => (searching ? selectFlatSearchResult(course) : setSelectedCourse(course))}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block font-semibold leading-snug">
                              <HighlightText text={course.course_name_zh} keyword={scope === 'semantic' ? '' : keyword} />
                            </span>
                            <span className="v2-muted mt-0.5 flex flex-wrap gap-x-2 text-sm">
                              {searching && <span>{normalize(course.department) || FALLBACK_DEPARTMENT}</span>}
                              <span>{course.credits} 學分</span>
                              {course.required_elective && <span className={required ? 'v2-accent font-semibold' : ''}>{course.required_elective}</span>}
                              {course.instructor && <span className="truncate">{course.instructor}</span>}
                            </span>
                            {preview && (
                              <span className="v2-faint mt-1 block text-sm leading-snug">
                                <HighlightText text={preview} keyword={keyword} />
                              </span>
                            )}
                          </span>
                          {score && <span className="v2-num v2-faint text-sm">{score}</span>}
                        </button>
                      </li>
                    );
                  })}
                </ul>
                {visible.length < list.length && (
                  <div className="p-3">
                    <button
                      type="button"
                      className="v2-btn v2-btn--ghost w-full"
                      onClick={() => setMore({ key: listKey, pages: (more.key === listKey ? more.pages : 0) + 1 })}
                    >
                      再顯示 {Math.min(PAGE_SIZE, list.length - visible.length)} 門
                    </button>
                  </div>
                )}
                {!listBusy && list.length === 0 && (
                  <p className="v2-muted px-5 py-10 text-center">沒有符合的課程</p>
                )}
              </>
            ) : (
              <div className="v2-hero-art !relative h-full opacity-60" aria-hidden="true">
                <div className="v2-hero-static" />
              </div>
            )}
          </div>

          {compareCourses.length > 0 && (
            <footer
              className="flex flex-none items-center gap-2 border-t px-3 py-2"
              style={{ borderColor: 'var(--v2-line)', background: 'var(--v2-surface)' }}
            >
              <button type="button" className="v2-btn v2-btn--sm" disabled={compareCourses.length < 2} onClick={() => setCompareOpen(true)}>
                對比
                <span className="v2-num">
                  {compareCourses.length}/{COMPARE_LIMIT}
                </span>
              </button>
              <p role="status" className="min-w-0 flex-1 truncate text-sm" style={{ color: 'var(--v2-danger)' }}>
                {compareNotice}
              </p>
              <button type="button" className="v2-navlink !min-h-9 !px-2" onClick={clearCompareCourses}>
                清空
              </button>
            </footer>
          )}
        </section>

        {/* 課程詳情 */}
        <section aria-label="課程詳情" className={`${paneClass('detail')} min-h-0 min-w-0 flex-col`}>
          {selectedCourse ? (
            <>
              <div className="flex-none border-b px-2 py-1 lg:hidden" style={{ borderColor: 'var(--v2-line)' }}>
                <button type="button" className="v2-navlink gap-1.5" onClick={() => setSelectedCourse(null)}>
                  <HiArrowLeft className="h-4 w-4" aria-hidden="true" />
                  {listTitle || '返回'}
                </button>
              </div>
              <div key={courseKey(selectedCourse)} className="v2-scroll min-h-0 flex-1" style={{ background: 'var(--v2-surface)' }}>
                <div className="mx-auto max-w-3xl">
                  <CourseDetailV2
                    course={selectedCourse}
                    keyword={scope === 'semantic' ? '' : keyword}
                    isCompared={isCourseCompared(selectedCourse)}
                    onToggleCompare={toggleCompareCourse}
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="v2-hero-art !relative h-full opacity-60" aria-hidden="true">
              <div className="v2-hero-static" />
            </div>
          )}
        </section>
      </div>

      {compareOpen && (
        <CourseCompareModal
          courses={compareCourses}
          onClose={() => setCompareOpen(false)}
          onRemove={removeCompareCourse}
          onClear={clearCompareCourses}
        />
      )}
    </div>
  );
}
