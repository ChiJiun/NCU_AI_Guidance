import { useEffect, useRef, useState } from 'react';
import type { ComponentType, Dispatch, SetStateAction } from 'react';
import {
  HiBeaker,
  HiBookOpen,
  HiBriefcase,
  HiChevronDown,
  HiChevronLeft,
  HiChevronRight,
  HiChip,
  HiCog,
  HiGlobeAlt,
  HiLibrary,
  HiPlus,
  HiSearch,
  HiTrash,
  HiX,
} from 'react-icons/hi';
import { FaHeartbeat, FaLandmark, FaLeaf } from 'react-icons/fa';
import CourseCompareModal from '../components/CourseCompareModal';
import CourseDetailPanel from '../components/CourseDetailPanel';
import HighlightText from '../components/HighlightText';
import type { Course } from '../types';
import {
  COMPARE_LIMIT, FALLBACK_COLLEGE,
  courseKey, formatScore, getDetailPreview, metadataPreview, normalize, sameStringArray,
} from '../features/courses/catalog';
import type { SearchMode } from '../features/courses/catalog';
import { useCourseCatalog } from '../features/courses/useCourseCatalog';

const COLLEGE_CONFIG: Record<string, { icon: ComponentType<{ className?: string }>; color: string; badge: string; surface: string; headerSurface: string; border: string; selectedBorder: string }> = {
  文學院: { icon: HiBookOpen, color: 'bg-violet-500', badge: 'bg-violet-50 text-violet-700', surface: 'bg-violet-500/[0.045]', headerSurface: 'bg-violet-500/[0.09]', border: 'border-violet-200/50', selectedBorder: 'border-violet-500' },
  理學院: { icon: HiBeaker, color: 'bg-cyan-500', badge: 'bg-cyan-50 text-cyan-700', surface: 'bg-cyan-500/[0.045]', headerSurface: 'bg-cyan-500/[0.09]', border: 'border-cyan-200/50', selectedBorder: 'border-cyan-500' },
  工學院: { icon: HiCog, color: 'bg-orange-500', badge: 'bg-orange-50 text-orange-700', surface: 'bg-orange-500/[0.045]', headerSurface: 'bg-orange-500/[0.09]', border: 'border-orange-200/50', selectedBorder: 'border-orange-500' },
  管理學院: { icon: HiBriefcase, color: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700', surface: 'bg-emerald-500/[0.045]', headerSurface: 'bg-emerald-500/[0.09]', border: 'border-emerald-200/50', selectedBorder: 'border-emerald-500' },
  資訊電機學院: { icon: HiChip, color: 'bg-indigo-600', badge: 'bg-indigo-50 text-indigo-700', surface: 'bg-indigo-600/[0.045]', headerSurface: 'bg-indigo-600/[0.09]', border: 'border-indigo-200/50', selectedBorder: 'border-indigo-600' },
  地球科學學院: { icon: HiGlobeAlt, color: 'bg-teal-600', badge: 'bg-teal-50 text-teal-700', surface: 'bg-teal-600/[0.045]', headerSurface: 'bg-teal-600/[0.09]', border: 'border-teal-200/50', selectedBorder: 'border-teal-600' },
  客家學院: { icon: HiLibrary, color: 'bg-rose-400', badge: 'bg-rose-50 text-rose-700', surface: 'bg-rose-400/[0.05]', headerSurface: 'bg-rose-400/[0.10]', border: 'border-rose-200/50', selectedBorder: 'border-rose-400' },
  生醫理工學院: { icon: FaHeartbeat, color: 'bg-red-500', badge: 'bg-red-50 text-red-700', surface: 'bg-red-500/[0.045]', headerSurface: 'bg-red-500/[0.09]', border: 'border-red-200/50', selectedBorder: 'border-red-500' },
  永續與綠能科技研究學院: { icon: FaLeaf, color: 'bg-lime-500', badge: 'bg-lime-50 text-lime-700', surface: 'bg-lime-500/[0.05]', headerSurface: 'bg-lime-500/[0.10]', border: 'border-lime-200/50', selectedBorder: 'border-lime-500' },
  永續與綠能學院: { icon: FaLeaf, color: 'bg-lime-500', badge: 'bg-lime-50 text-lime-700', surface: 'bg-lime-500/[0.05]', headerSurface: 'bg-lime-500/[0.10]', border: 'border-lime-200/50', selectedBorder: 'border-lime-500' },
  '中心、處室': { icon: FaLandmark, color: 'bg-slate-400', badge: 'bg-slate-100 text-slate-600', surface: 'bg-slate-400/[0.06]', headerSurface: 'bg-slate-400/[0.12]', border: 'border-slate-200/60', selectedBorder: 'border-slate-400' },
};

function FilterPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-2 text-sm font-medium transition ${
        active ? 'border-primary-700 bg-primary-900 text-white' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
      }`}
    >
      {label}
    </button>
  );
}

export default function CoursesPage() {
  const {
    loading,
    searchQuery, setSearchQuery,
    selectedTypes, setSelectedTypes,
    selectedCredits, setSelectedCredits,
    selectedSemesters, setSelectedSemesters,
    selectedCollege,
    selectedDepartment, setSelectedDepartment,
    selectedCourse, setSelectedCourse,
    navigationLevel, setNavigationLevel,
    resultTab, setResultTab,
    searchMode, setSearchMode,
    semanticLoading, semanticMode, semanticMessage,
    compareCourses, compareOpen, setCompareOpen, compareNotice,
    selectedFieldFilters, setSelectedFieldFilters,
    courseLevel, setCourseLevel,
    groupedCourses, sortedColleges, currentDepartments,
    departmentFieldOptions, currentCourses, filteredCourses, groupedSearchResults,
    typeOptions, creditOptions, semesterOptions,
    hasActiveFilters, hasSearchQuery, activeTags,
    isCourseCompared, toggleCompareCourse, removeCompareCourse, clearCompareCourses,
    selectSearchResult, selectFlatSearchResult, selectCollege, selectDepartment,
  } = useCourseCatalog();
  const [isMobileNavigatorOpen, setIsMobileNavigatorOpen] = useState(true);
  const [showSearchPanel, setShowSearchPanel] = useState(false);
  const [draftSearchQuery, setDraftSearchQuery] = useState('');
  const [draftSelectedTypes, setDraftSelectedTypes] = useState<string[]>([]);
  const [draftSelectedCredits, setDraftSelectedCredits] = useState<string[]>([]);
  const [draftSelectedSemesters, setDraftSelectedSemesters] = useState<string[]>([]);
  const [draftSearchMode, setDraftSearchMode] = useState<SearchMode>('semantic');
  const [expandedDepartments, setExpandedDepartments] = useState<string[]>([]);
  const [isNavCollapsed, setIsNavCollapsed] = useState(false);
  const [isFieldDropdownOpen, setIsFieldDropdownOpen] = useState(false);
  const fieldDropdownRef = useRef<HTMLDivElement>(null);
  const contentPanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showSearchPanel) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [showSearchPanel]);

  const hasDraftSearchQuery = Boolean(draftSearchQuery.trim());
  const hasDraftChanges =
    draftSearchMode !== searchMode ||
    draftSearchQuery !== searchQuery ||
    !sameStringArray(draftSelectedTypes, selectedTypes) ||
    !sameStringArray(draftSelectedCredits, selectedCredits) ||
    !sameStringArray(draftSelectedSemesters, selectedSemesters);

  useEffect(() => {
    contentPanelRef.current?.scrollTo({ top: 0, behavior: 'instant' });
  }, [selectedCourse]);

  useEffect(() => {
    if (!isFieldDropdownOpen) return;
    const handleMouseDown = (event: MouseEvent) => {
      if (fieldDropdownRef.current && !fieldDropdownRef.current.contains(event.target as Node)) {
        setIsFieldDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [isFieldDropdownOpen]);

  const toggleValue = (value: string, setter: Dispatch<SetStateAction<string[]>>) =>
    setter((current) => (current.includes(value) ? current.filter((item) => item !== value) : [...current, value]));

  const openSearchPanel = () => {
    setDraftSearchMode(searchMode);
    setDraftSearchQuery(searchQuery);
    setDraftSelectedTypes(selectedTypes);
    setDraftSelectedCredits(selectedCredits);
    setDraftSelectedSemesters(selectedSemesters);
    setShowSearchPanel(true);
  };

  const clearDraftFilters = () => {
    setDraftSearchQuery('');
    setDraftSelectedTypes([]);
    setDraftSelectedCredits([]);
    setDraftSelectedSemesters([]);
  };

  const applySearchFilters = () => {
    setSearchMode(draftSearchMode);
    setSearchQuery(draftSearchQuery);
    setSelectedTypes(draftSelectedTypes);
    setSelectedCredits(draftSelectedCredits);
    setSelectedSemesters(draftSelectedSemesters);
    setShowSearchPanel(false);
  };

  const toggleExpandedDepartment = (key: string) => {
    setExpandedDepartments((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  };

  const navigationTitle = navigationLevel === 'colleges' ? '選擇學院' : navigationLevel === 'departments' ? selectedCollege || '選擇系所' : selectedDepartment || '選擇課程';
  const navigationHint = navigationLevel === 'colleges' ? '從學院開始瀏覽' : navigationLevel === 'departments' ? '查看各系所課程' : '選擇一門課程查看詳情';
  const selectedCollegeConfig = selectedCollege ? COLLEGE_CONFIG[selectedCollege] : undefined;
  const hasCollegeNavigationColor = navigationLevel !== 'colleges' && Boolean(selectedCollegeConfig);
  const navigationShellClass = hasCollegeNavigationColor
    ? `border-r ${selectedCollegeConfig!.border} bg-white`
    : 'border-r border-slate-200 bg-white';
  const navigationTopClass = hasCollegeNavigationColor
    ? `border-b ${selectedCollegeConfig!.border} ${selectedCollegeConfig!.surface}`
    : 'border-b border-slate-200 bg-white';
  const filterPanelClass = hasCollegeNavigationColor
    ? `space-y-3 border-t ${selectedCollegeConfig!.border} bg-white/35 px-4 py-3 backdrop-blur-sm`
    : 'space-y-3 border-t border-slate-200 px-4 py-3';
  const navigationHeaderClass = hasCollegeNavigationColor
    ? `border-white/50 ${selectedCollegeConfig!.headerSurface} px-4 py-3 backdrop-blur-sm`
    : 'border-slate-100 bg-slate-50 px-4 py-3';
  const navigationBackButtonClass = hasCollegeNavigationColor
    ? 'inline-flex h-8 w-8 items-center justify-center rounded-full bg-white/70 text-slate-700 shadow-sm ring-1 ring-white/60 transition hover:bg-white/90'
    : 'inline-flex h-8 w-8 items-center justify-center rounded-full bg-white text-slate-600 shadow-sm transition hover:bg-slate-50';
  const navigationTitleClass = hasCollegeNavigationColor
    ? 'text-sm font-bold text-slate-950'
    : 'text-sm font-bold text-slate-900';
  const navigationHintClass = hasCollegeNavigationColor
    ? 'mt-0.5 text-xs text-slate-700'
    : 'mt-0.5 text-xs text-slate-500';
  const navigationListClass = 'bg-white';
  const navigationRowClass = 'border-b border-slate-100 bg-white hover:bg-slate-50';
  const selectedCourseRowClass = hasCollegeNavigationColor
    ? `${selectedCollegeConfig!.selectedBorder} ${selectedCollegeConfig!.headerSurface}`
    : 'border-indigo-500 bg-indigo-50';
  const closeMobileNavigator = () => setIsMobileNavigatorOpen(false);
  const openMobileNavigator = () => setIsMobileNavigatorOpen(true);

  const handleSelectSearchResult = (college: string, department: string, course: Course) => {
    selectSearchResult(college, department, course);
    closeMobileNavigator();
  };

  const handleSelectFlatSearchResult = (course: Course) => {
    selectFlatSearchResult(course);
    closeMobileNavigator();
  };

  const handleSelectCollege = (college: string) => {
    selectCollege(college);
    openMobileNavigator();
  };

  const handleSelectDepartment = (department: string) => {
    selectDepartment(department);
    setIsFieldDropdownOpen(false);
    openMobileNavigator();
  };

  const handleSelectCourse = (course: Course) => {
    setSelectedCourse(course);
    closeMobileNavigator();
  };

  const renderCompareButton = (course: Course) => {
    const compared = isCourseCompared(course);
    return (
      <button
        type="button"
        onClick={() => toggleCompareCourse(course)}
        className={`mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition ${
          compared
            ? 'border-primary-300 bg-primary-50 text-primary-700 hover:bg-primary-100'
            : 'border-slate-200 bg-white text-slate-500 hover:border-primary-200 hover:bg-primary-50 hover:text-primary-700'
        }`}
        aria-label={`${compared ? '移除對比' : '加入對比'}：${course.course_name_zh}`}
        title={compared ? '移除對比' : '加入對比'}
      >
        {compared ? <HiX className="h-4 w-4" /> : <HiPlus className="h-4 w-4" />}
      </button>
    );
  };

  return (
    <>
      <div className="h-full bg-slate-50">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-b-2 border-primary-600"></div>
              <p className="text-gray-600">正在載入課程資料...</p>
            </div>
          </div>
        ) : (
          <div className="relative flex h-full min-h-0 flex-col md:flex-row">
            {/* Desktop sidebar toggle — matches CurriculumPage style */}
            <button
              type="button"
              onClick={() => setIsNavCollapsed(!isNavCollapsed)}
              className={`absolute z-30 top-24 hidden md:flex items-center justify-center w-5 h-20 bg-slate-50/95 backdrop-blur-md border-y border-r border-slate-300 rounded-r-xl shadow-[4px_0_12px_-2px_rgba(0,0,0,0.1)] hover:bg-slate-100 hover:border-slate-400 text-slate-500 transition-all duration-300 ${isNavCollapsed ? 'left-0' : 'left-[20rem]'}`}
              aria-label={isNavCollapsed ? '展開課程導航' : '收起課程導航'}
            >
              <svg className={`w-4 h-4 transition-transform duration-300 ${isNavCollapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <aside className={`relative z-10 min-h-0 w-full flex-col overflow-hidden ${navigationShellClass} ${isMobileNavigatorOpen ? 'flex flex-1' : 'hidden'} md:flex md:flex-none transition-all duration-300 ${isNavCollapsed ? 'md:w-0 md:min-w-0 md:max-w-0 md:opacity-0' : 'md:w-[20rem] md:min-w-[20rem] md:max-w-[20rem] md:opacity-100'}`}>
              <div className={`sticky top-0 z-10 ${navigationTopClass}`}>
                <div className="flex items-center justify-between gap-3 bg-white px-4 py-3">
                  <h2 className="text-sm font-bold tracking-wide text-slate-900">課程導航</h2>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={openSearchPanel} className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50" aria-label="開啟課程搜尋">
                      <HiSearch className="h-5 w-5" />
                    </button>
                    <button type="button" onClick={closeMobileNavigator} className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50 md:hidden" aria-label="收起課程導航">
                      <HiChevronLeft className="h-5 w-5" />
                    </button>
                  </div>
                </div>

                {hasActiveFilters ? (
                  <div className={filterPanelClass}>
                    {activeTags.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {activeTags.map((tag) => (
                          <button key={tag.key} type="button" onClick={tag.onRemove} className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100">
                            <span>{tag.label}</span>
                            <HiX className="h-3.5 w-3.5" />
                          </button>
                        ))}
                      </div>
                    ) : null}

                    {hasSearchQuery && searchMode === 'semantic' ? (
                      <div className={`rounded-lg px-3 py-2 text-xs ${semanticMode === 'fallback' ? 'bg-amber-50 text-amber-800' : 'bg-blue-50 text-blue-800'}`}>
                        {semanticLoading
                          ? '正在使用 Qdrant 關鍵字向量搜尋...'
                          : semanticMode === 'semantic'
                            ? `Qdrant 關鍵字向量搜尋結果：${filteredCourses.length} 門`
                            : semanticMessage || '關鍵字向量搜尋暫時不可用，已自動改用一般文字搜尋。'}
                      </div>
                    ) : null}

                    {hasSearchQuery && searchMode === 'keyword' ? (
                      <div className="flex w-full overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm">
                        <button type="button" onClick={() => setResultTab('course_name')} className={`min-w-0 flex-1 px-4 py-2 text-sm font-medium leading-none transition ${resultTab === 'course_name' ? 'bg-slate-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>
                          課名
                        </button>
                        <button type="button" onClick={() => setResultTab('detail_info')} className={`min-w-0 flex-1 border-l border-slate-200 px-4 py-2 text-sm font-medium leading-none transition ${resultTab === 'detail_info' ? 'border-l-slate-600 bg-slate-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>
                          詳細內容
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className={`border-t ${navigationHeaderClass}`}>
                    <div className="flex items-center gap-2">
                      {navigationLevel !== 'colleges' ? (
                        <button
                          type="button"
                          onClick={() => {
                            if (navigationLevel === 'courses') {
                              setSelectedCourse(null);
                              setNavigationLevel('departments');
                              return;
                            }
                            setSelectedDepartment(null);
                            setSelectedCourse(null);
                            setNavigationLevel('colleges');
                          }}
                          className={navigationBackButtonClass}
                          aria-label="返回上一層"
                        >
                          <HiChevronLeft className="h-5 w-5" />
                        </button>
                      ) : null}
                      <div className="min-w-0 flex-1">
                        <div className={navigationTitleClass}>{navigationTitle}</div>
                        {navigationLevel === 'courses' ? (
                          <div className="mt-0.5 flex items-center gap-3">
                            <span className="flex items-center gap-1 text-xs text-slate-500">
                              <span className="h-2 w-2 shrink-0 rounded-full bg-red-400" />
                              必修
                            </span>
                            <span className="flex items-center gap-1 text-xs text-slate-500">
                              <span className="h-2 w-2 shrink-0 rounded-full bg-green-400" />
                              選修
                            </span>
                          </div>
                        ) : (
                          <div className={navigationHintClass}>{navigationHint}</div>
                        )}
                      </div>
                      {navigationLevel === 'colleges' ? (
                        <div className="flex shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-50 text-xs font-semibold">
                          <button
                            type="button"
                            onClick={() => setCourseLevel('undergrad')}
                            className={`px-2.5 py-1.5 transition ${courseLevel === 'undergrad' ? 'bg-slate-800 text-white' : 'text-slate-500 hover:bg-slate-100'}`}
                          >
                            大學部
                          </button>
                          <button
                            type="button"
                            onClick={() => setCourseLevel('grad')}
                            className={`border-l border-slate-200 px-2.5 py-1.5 transition ${courseLevel === 'grad' ? 'bg-slate-800 text-white' : 'text-slate-500 hover:bg-slate-100'}`}
                          >
                            研究所
                          </button>
                        </div>
                      ) : null}
                      {navigationLevel === 'courses' && departmentFieldOptions.length > 1 ? (
                        <div ref={fieldDropdownRef} className="relative shrink-0">
                          <button
                            type="button"
                            onClick={() => setIsFieldDropdownOpen((v) => !v)}
                            className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${selectedFieldFilters.length > 0 ? (selectedCollegeConfig ? selectedCollegeConfig.badge : 'bg-indigo-50 text-indigo-700') : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                          >
                            <span className="max-w-[4.5rem] truncate">
                              {selectedFieldFilters.length === 0 ? '領域' : selectedFieldFilters.length === 1 ? selectedFieldFilters[0] : `${selectedFieldFilters.length} 個領域`}
                            </span>
                            <HiChevronDown className={`h-3 w-3 shrink-0 transition-transform duration-200 ${isFieldDropdownOpen ? 'rotate-180' : ''}`} />
                          </button>
                          {isFieldDropdownOpen ? (
                            <div className="absolute right-0 top-full z-50 mt-1 min-w-[9rem] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
                              <button
                                type="button"
                                onClick={() => setSelectedFieldFilters([])}
                                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition hover:bg-slate-50 ${selectedFieldFilters.length === 0 ? 'font-semibold text-indigo-600' : 'text-slate-700'}`}
                              >
                                <span className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border ${selectedFieldFilters.length === 0 ? 'border-indigo-500 bg-indigo-500' : 'border-slate-300'}`}>
                                  {selectedFieldFilters.length === 0 && <svg className="h-2.5 w-2.5 text-white" viewBox="0 0 10 10" fill="currentColor"><path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                                </span>
                                全部
                              </button>
                              <div className="border-t border-slate-100" />
                              {departmentFieldOptions.map((field) => {
                                const checked = selectedFieldFilters.includes(field);
                                return (
                                  <button
                                    key={field}
                                    type="button"
                                    onClick={() => setSelectedFieldFilters((prev) => checked ? prev.filter((f) => f !== field) : [...prev, field])}
                                    className={`flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition hover:bg-slate-50 ${checked ? 'font-semibold text-indigo-600' : 'text-slate-700'}`}
                                  >
                                    <span className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border ${checked ? 'border-indigo-500 bg-indigo-500' : 'border-slate-300'}`}>
                                      {checked && <svg className="h-2.5 w-2.5 text-white" viewBox="0 0 10 10" fill="currentColor"><path d="M1.5 5l2.5 2.5 4.5-4.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                                    </span>
                                    {field}
                                  </button>
                                );
                              })}
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>
                )}
              </div>

              <div className={`flex-1 overflow-y-auto bg-white ${compareCourses.length > 0 ? 'pb-44 md:pb-0' : ''}`}>
                {hasActiveFilters ? (
                  <div className="bg-white">
                    {hasSearchQuery && searchMode === 'semantic' ? (
                      semanticLoading ? (
                        <div className="p-8 text-center text-sm text-slate-500">正在搜尋相關課程...</div>
                      ) : filteredCourses.length > 0 ? (
                        <div className="divide-y divide-slate-200">
                          {filteredCourses.map((course) => {
                            const isSelected = selectedCourse ? courseKey(selectedCourse) === courseKey(course) : false;
                            const isRequired = normalize(course.required_elective) === '必修';
                            const scoreLabel = formatScore(course.relevance_score);
                            const preview = getDetailPreview(course, searchQuery);
                            const tags = metadataPreview(course);
                            return (
                              <div key={courseKey(course)} className={`flex gap-2 px-4 py-3 transition hover:bg-slate-50 ${isSelected ? 'border-l-4 border-indigo-600 bg-slate-50' : ''}`}>
                                <button type="button" onClick={() => handleSelectFlatSearchResult(course)} className="min-w-0 flex-1 text-left">
                                  <div className="text-sm font-semibold leading-snug text-slate-900">
                                    <HighlightText text={course.course_name_zh} keyword={searchQuery} />
                                  </div>
                                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                    {scoreLabel ? <span className="rounded-full bg-blue-50 px-2 py-0.5 font-medium text-blue-700">相關度 {scoreLabel}</span> : null}
                                    {course.required_elective ? <span className={`rounded-full px-2 py-0.5 font-medium ${isRequired ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{course.required_elective}</span> : null}
                                    <span>{course.credits} 學分</span>
                                    {course.semester_display ? <span>{course.semester_display}</span> : null}
                                    {course.department ? <span>{course.department}</span> : null}
                                    {course.instructor ? <span>{course.instructor}</span> : null}
                                  </div>
                                  {preview ? (
                                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">
                                      <HighlightText text={preview} keyword={searchQuery} />
                                    </p>
                                  ) : null}
                                  {tags.length > 0 ? (
                                    <div className="mt-2 flex flex-wrap gap-1.5">
                                      {tags.map((tag) => (
                                        <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                          <HighlightText text={tag} keyword={searchQuery} />
                                        </span>
                                      ))}
                                    </div>
                                  ) : null}
                                </button>
                                {renderCompareButton(course)}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="p-8 text-center text-sm text-slate-500">找不到符合條件的課程。</div>
                      )
                    ) : groupedSearchResults.length > 0 ? (
                      groupedSearchResults.map((group) => (
                        <div key={group.college} className="border-b border-slate-200">
                          <div className="bg-slate-50 px-4 py-2 text-sm text-slate-500">{group.college}．{group.count} 門</div>
                          {group.departments.map((department) => {
                            const departmentKey = `${group.college}-${department.name}`;
                            const isExpanded = expandedDepartments.includes(departmentKey);
                            return (
                              <div key={departmentKey} className="border-t border-slate-100">
                                <button type="button" onClick={() => toggleExpandedDepartment(departmentKey)} className="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-slate-50">
                                  <div className="truncate text-sm font-medium text-slate-900">{department.name}</div>
                                  <div className="ml-3 flex items-center gap-3 text-sm text-slate-400">
                                    <span>{department.count} 門</span>
                                    <HiChevronRight className={`h-4 w-4 transition ${isExpanded ? 'rotate-90' : ''}`} />
                                  </div>
                                </button>
                                {isExpanded ? (
                                  <div className="border-t border-slate-100">
                                    {department.courses.map((course) => {
                                      const isSelected = selectedCourse ? courseKey(selectedCourse) === courseKey(course) : false;
                                      const isRequired = normalize(course.required_elective) === '必修';
                                      const preview = getDetailPreview(course, searchQuery);
                                      const tags = metadataPreview(course);
                                      return (
                                        <div key={courseKey(course)} className={`flex gap-2 border-t border-slate-100 px-4 py-3 transition hover:bg-slate-50 ${isSelected ? 'border-l-4 border-indigo-600 bg-slate-50' : ''}`}>
                                          <button type="button" onClick={() => handleSelectSearchResult(group.college, department.name, course)} className="min-w-0 flex-1 text-left">
                                            <div className="text-sm font-semibold leading-snug text-slate-900">
                                              <HighlightText text={course.course_name_zh} keyword={searchQuery} />
                                            </div>
                                            {resultTab === 'course_name' ? (
                                              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                                {course.required_elective ? <span className={`rounded-full px-2 py-0.5 font-medium ${isRequired ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{course.required_elective}</span> : null}
                                                <span>{course.credits} 學分</span>
                                                {course.instructor ? <span>{course.instructor}</span> : null}
                                              </div>
                                            ) : (
                                              <div className="mt-1 space-y-1 text-xs text-slate-500">
                                                <div className="flex flex-wrap items-center gap-2">
                                                  {course.required_elective ? <span className={`rounded-full px-2 py-0.5 font-medium ${isRequired ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>{course.required_elective}</span> : null}
                                                  <span>{course.credits} 學分</span>
                                                  {course.instructor ? <span>{course.instructor}</span> : null}
                                                </div>
                                                {preview ? (
                                                  <p className="line-clamp-2 leading-5 text-slate-500">
                                                    <HighlightText text={preview} keyword={searchQuery} />
                                                  </p>
                                                ) : null}
                                                {tags.length > 0 ? (
                                                  <div className="flex flex-wrap gap-1.5">
                                                    {tags.map((tag) => (
                                                      <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                                        <HighlightText text={tag} keyword={searchQuery} />
                                                      </span>
                                                    ))}
                                                  </div>
                                                ) : null}
                                              </div>
                                            )}
                                          </button>
                                          {renderCompareButton(course)}
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      ))
                    ) : (
                      <div className="p-8 text-center text-sm text-slate-500">找不到符合條件的課程。</div>
                    )}
                  </div>
                ) : navigationLevel === 'colleges' ? (
                  <div className="space-y-2 bg-slate-50 p-3">
                    {sortedColleges.map((college) => {
                      const config = COLLEGE_CONFIG[college] || COLLEGE_CONFIG[FALLBACK_COLLEGE];
                      const Icon = config.icon;
                      return (
                        <button key={college} type="button" onClick={() => handleSelectCollege(college)} className="group flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-3 text-left shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md">
                          <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${config.color} shadow-sm shadow-slate-200 transition duration-200 group-hover:scale-105`}>
                            <Icon className="h-5 w-5 text-white" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm font-semibold text-slate-950">{college}</div>
                            <div className="mt-1 flex items-center gap-2">
                              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${config.badge}`}>{Object.keys(groupedCourses[college] || {}).length} 系所</span>
                              <span className="text-xs text-slate-400">探索課程</span>
                            </div>
                          </div>
                          <HiChevronRight className="h-5 w-5 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500" />
                        </button>
                      );
                    })}
                  </div>
                ) : navigationLevel === 'departments' ? (
                  <div className={navigationListClass}>
                    {currentDepartments.length > 0 ? (
                      currentDepartments.map((department) => {
                        const departmentCount = (groupedCourses[selectedCollege!]?.[department] || []).length;
                        return (
                          <button key={department} type="button" onClick={() => handleSelectDepartment(department)} className={`flex w-full items-center justify-between px-4 py-3 text-left transition ${navigationRowClass}`}>
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium text-slate-900">{department}</div>
                              <div className="text-xs text-slate-500">{departmentCount} 門課</div>
                            </div>
                            <HiChevronRight className="h-5 w-5 shrink-0 text-slate-400" />
                          </button>
                        );
                      })
                    ) : (
                      <div className="px-4 py-6 text-sm text-slate-500">這個學院目前沒有可顯示的系所。</div>
                    )}
                  </div>
                ) : (
                  <div className={navigationListClass}>
                    {currentCourses.length > 0 ? (
                      <div>
                        {currentCourses.map((course) => {
                          const isSelected = selectedCourse ? courseKey(selectedCourse) === courseKey(course) : false;
                          const isRequired = normalize(course.required_elective) === '必修';
                          const dotClass = isRequired
                            ? 'bg-red-400'
                            : course.required_elective
                              ? 'bg-green-400'
                              : 'bg-slate-300';
                          return (
                            <div key={courseKey(course)} className={`flex gap-2 px-4 py-3 transition ${isSelected ? `border-b border-l-4 ${selectedCourseRowClass}` : navigationRowClass}`}>
                              <button type="button" onClick={() => handleSelectCourse(course)} className="min-w-0 flex-1 text-left">
                                <div className={`mb-1 text-sm leading-snug ${isSelected ? 'font-bold text-slate-950' : 'font-semibold text-slate-900'}`}>
                                  <HighlightText text={course.course_name_zh} keyword={searchQuery} />
                                </div>
                                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                  {course.course_id ? (
                                    <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5">
                                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />
                                      <span className="font-mono text-[11px] text-slate-600">{course.course_id}</span>
                                    </span>
                                  ) : null}
                                  <span>{course.credits} 學分</span>
                                  {course.instructor ? <span>{course.instructor}</span> : null}
                                </div>
                              </button>
                              {renderCompareButton(course)}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="p-8 text-center text-slate-500">
                        <HiSearch className="mx-auto mb-3 h-10 w-10 text-slate-400" />
                        <p className="text-sm font-medium">目前找不到符合條件的課程。</p>
                        <p className="mt-1 text-sm text-slate-400">試著返回上一層，或調整搜尋與篩選條件。</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </aside>

<div ref={contentPanelRef} className={`relative z-0 min-h-0 min-w-0 flex-1 overflow-y-auto bg-slate-50 p-4 ${isMobileNavigatorOpen ? 'hidden md:block' : 'block'} ${compareCourses.length > 0 ? 'pb-44 md:pb-4' : ''}`}>
              <div className="mb-3 flex items-center justify-between md:hidden">
                <button type="button" onClick={openMobileNavigator} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50">
                  <HiChevronRight className="h-4 w-4" />
                  課程導航
                </button>
                {selectedCourse ? <span className="truncate pl-3 text-xs text-slate-500">{selectedCourse.course_name_zh}</span> : null}
              </div>
              <CourseDetailPanel
                course={selectedCourse}
                searchKeyword={searchQuery}
                isCompared={selectedCourse ? isCourseCompared(selectedCourse) : false}
                onToggleCompare={toggleCompareCourse}
              />
            </div>
          </div>
        )}
      </div>

      {compareCourses.length > 0 ? (
        <div className="fixed bottom-0 left-0 right-0 z-40 rounded-t-2xl border-t border-slate-200 bg-white px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-4 shadow-2xl md:bottom-4 md:left-auto md:right-4 md:w-96 md:rounded-2xl md:border md:pb-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-slate-950">課程對比</div>
              <div className="mt-0.5 text-xs text-slate-500">已選 {compareCourses.length} / {COMPARE_LIMIT} 門</div>
            </div>
            <button type="button" onClick={clearCompareCourses} className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition hover:bg-red-50 hover:text-red-600" aria-label="清空課程對比">
              <HiTrash className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {compareCourses.map((course) => (
              <button key={courseKey(course)} type="button" onClick={() => removeCompareCourse(course)} className="inline-flex max-w-full items-center gap-1 rounded-full border border-primary-100 bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-800 transition hover:bg-primary-100">
                <span className="truncate">{course.course_name_zh}</span>
                <HiX className="h-3.5 w-3.5 shrink-0" />
              </button>
            ))}
          </div>
          {compareNotice ? <div className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{compareNotice}</div> : null}
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={() => setCompareOpen(true)} disabled={compareCourses.length < 2} className="flex-1 rounded-xl bg-primary-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-primary-800 disabled:cursor-not-allowed disabled:bg-slate-300">
              開始對比
            </button>
          </div>
          {compareCourses.length < 2 ? <div className="mt-2 text-xs text-slate-500">至少選 2 門課才能開始對比。</div> : null}
        </div>
      ) : null}

      {showSearchPanel ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" onClick={() => setShowSearchPanel(false)}>
          <div className="w-full max-w-2xl rounded-[2rem] bg-white p-6 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold text-slate-950">搜尋與篩選課程</h3>
                <p className="mt-1 text-sm text-slate-500">選擇搜尋模式，並搭配學分、修別與學期條件快速找到課程。</p>
              </div>
              <button type="button" onClick={() => setShowSearchPanel(false)} className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600 transition hover:bg-slate-200" aria-label="關閉搜尋面板">
                <HiX className="h-5 w-5" />
              </button>
            </div>
            <div className="mt-5">
              <label className="mb-2 block text-sm font-medium text-slate-700">搜尋模式</label>
              <div className="flex w-full overflow-hidden rounded-xl border border-slate-300 bg-white shadow-sm">
                <button
                  type="button"
                  onClick={() => setDraftSearchMode('semantic')}
                  className={`min-w-0 flex-1 px-4 py-2.5 text-sm font-medium transition ${draftSearchMode === 'semantic' ? 'bg-primary-900 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
                >
                  關鍵字向量搜尋
                </button>
                <button
                  type="button"
                  onClick={() => setDraftSearchMode('keyword')}
                  className={`min-w-0 flex-1 border-l border-slate-200 px-4 py-2.5 text-sm font-medium transition ${draftSearchMode === 'keyword' ? 'border-l-primary-900 bg-primary-900 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
                >
                  一般文字搜尋
                </button>
              </div>
            </div>
            <div className="mt-5">
              <label className="mb-2 block text-sm font-medium text-slate-700">{draftSearchMode === 'semantic' ? '搜尋關鍵字' : '搜尋文字'}</label>
              <div className="relative">
                <HiSearch className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={draftSearchQuery}
                  onChange={(event) => setDraftSearchQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      applySearchFilters();
                    }
                  }}
                  placeholder={draftSearchMode === 'semantic' ? '例如：程式、Python、資料分析' : '例如：機器學習'}
                  className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-4 text-sm shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500"
                />
              </div>
              {hasDraftSearchQuery ? (
                <div className={`mt-3 rounded-lg px-3 py-2 text-xs ${!hasDraftChanges && draftSearchMode === 'semantic' && semanticMode === 'fallback' ? 'bg-amber-50 text-amber-800' : 'bg-blue-50 text-blue-800'}`}>
                  {hasDraftChanges
                    ? '條件尚未套用；按下「套用條件」後才會搜尋。'
                    : draftSearchMode === 'semantic'
                      ? semanticLoading
                        ? '正在使用 ncu_courses_ug / ncu_courses_grad 進行 Qdrant 關鍵字向量搜尋...'
                        : semanticMode === 'semantic'
                          ? `目前使用 Qdrant 關鍵字向量搜尋，找到 ${filteredCourses.length} 門課。`
                          : semanticMessage || '關鍵字向量搜尋暫時不可用，已自動改用一般文字搜尋。'
                      : `目前使用一般文字搜尋，找到 ${filteredCourses.length} 門課。`}
                </div>
              ) : null}
            </div>

            <div className="mt-5 space-y-5">
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">修別</label>
                <div className="flex flex-wrap gap-2">
                  {typeOptions.map((option) => (
                    <FilterPill key={option} label={option} active={draftSelectedTypes.includes(option)} onClick={() => toggleValue(option, setDraftSelectedTypes)} />
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">學分</label>
                <div className="flex flex-wrap gap-2">
                  {creditOptions.map((option) => (
                    <FilterPill key={option} label={`${option} 學分`} active={draftSelectedCredits.includes(option)} onClick={() => toggleValue(option, setDraftSelectedCredits)} />
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-700">學期</label>
                <div className="flex flex-wrap gap-2">
                  {semesterOptions.map((option) => (
                    <FilterPill key={option} label={option} active={draftSelectedSemesters.includes(option)} onClick={() => toggleValue(option, setDraftSelectedSemesters)} />
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-6 flex gap-3">
              <button type="button" onClick={clearDraftFilters} className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50">
                清除篩選
              </button>
              <button type="button" onClick={applySearchFilters} className="flex-1 rounded-xl bg-primary-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-primary-800">
                套用條件
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {compareOpen && compareCourses.length > 0 ? (
        <CourseCompareModal courses={compareCourses} onClose={() => setCompareOpen(false)} onRemove={removeCompareCourse} onClear={clearCompareCourses} />
      ) : null}
    </>
  );
}
