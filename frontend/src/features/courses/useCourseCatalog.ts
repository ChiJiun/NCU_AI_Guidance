import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { courseAPI } from '../../api/services';
import { sortDeptsInCollege } from '../../constants/colleges';
import type { Course } from '../../types';
import {
  COLLEGE_ORDER, COMPARE_LIMIT, FALLBACK_COLLEGE, FALLBACK_DEPARTMENT,
  courseKey, normalize, splitFields,
} from './catalog';
import type { GroupedCourses, NavigationLevel, ResultTab, SearchMode, SemanticSearchMode } from './catalog';

/**
 * 課程資訊頁的資料邏輯：載入課程、學院／系所分組、搜尋與篩選（含語意搜尋與退回文字搜尋）、
 * 瀏覽層級與選取狀態、課程對比。新舊版頁面共用這個 hook，各自只負責畫面。
 */
export function useCourseCatalog() {
  const location = useLocation();
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [selectedCredits, setSelectedCredits] = useState<string[]>([]);
  const [selectedSemesters, setSelectedSemesters] = useState<string[]>([]);
  const [selectedCollege, setSelectedCollege] = useState<string | null>(null);
  const [selectedDepartment, setSelectedDepartment] = useState<string | null>(null);
  const [selectedCourse, setSelectedCourse] = useState<Course | null>(null);
  const [navigationLevel, setNavigationLevel] = useState<NavigationLevel>('colleges');
  const [resultTab, setResultTab] = useState<ResultTab>('course_name');
  const [searchMode, setSearchMode] = useState<SearchMode>('semantic');
  const [semanticCourses, setSemanticCourses] = useState<Course[]>([]);
  const [semanticLoading, setSemanticLoading] = useState(false);
  const [semanticMode, setSemanticMode] = useState<SemanticSearchMode>('idle');
  const [semanticMessage, setSemanticMessage] = useState('');
  const [compareCourses, setCompareCourses] = useState<Course[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareNotice, setCompareNotice] = useState('');
  const [selectedFieldFilters, setSelectedFieldFilters] = useState<string[]>([]);
  const [courseLevel, setCourseLevel] = useState<'undergrad' | 'grad'>('undergrad');

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const q = params.get('search');
    if (q && q.trim()) {
      setSearchQuery(q.trim());
      setSearchMode('keyword');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setLoading(true);
    setCourses([]);
    setSelectedCollege(null);
    setSelectedDepartment(null);
    setSelectedCourse(null);
    setNavigationLevel('colleges');
    setSelectedFieldFilters([]);
    courseAPI
      .getCourses({ level: courseLevel })
      .then(setCourses)
      .catch((error) => console.error('Failed to load courses:', error))
      .finally(() => setLoading(false));
  }, [courseLevel]);

  const groupedCourses = useMemo(() => {
    const grouped: GroupedCourses = {};
    courses.forEach((course) => {
      const college = normalize(course.college) || FALLBACK_COLLEGE;
      const department = normalize(course.department) || FALLBACK_DEPARTMENT;
      grouped[college] ??= {};
      grouped[college][department] ??= [];
      grouped[college][department].push(course);
    });
    return grouped;
  }, [courses]);

  const sortedColleges = useMemo(
    () =>
      Object.keys(groupedCourses).sort((a, b) => {
        const ai = COLLEGE_ORDER.indexOf(a as (typeof COLLEGE_ORDER)[number]);
        const bi = COLLEGE_ORDER.indexOf(b as (typeof COLLEGE_ORDER)[number]);
        if (ai === -1 && bi === -1) return a.localeCompare(b, 'zh-Hant');
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      }),
    [groupedCourses]
  );

  const currentDepartments = useMemo(
    () => (!selectedCollege ? [] : sortDeptsInCollege(Object.keys(groupedCourses[selectedCollege] || {}))),
    [groupedCourses, selectedCollege]
  );

  const departmentCourses = useMemo(() => {
    const list = !selectedCollege || !selectedDepartment ? [] : groupedCourses[selectedCollege]?.[selectedDepartment] ?? [];
    return [...list].sort((a, b) => (a.course_id ?? '').localeCompare(b.course_id ?? ''));
  }, [groupedCourses, selectedCollege, selectedDepartment]);

  const hasActiveFilters =
    Boolean(searchQuery.trim()) || selectedTypes.length > 0 || selectedCredits.length > 0 || selectedSemesters.length > 0;
  const hasSearchQuery = Boolean(searchQuery.trim());

  useEffect(() => {
    const query = searchQuery.trim();
    if (!query || searchMode !== 'semantic') {
      void (async () => {
        await Promise.resolve();
        setSemanticCourses([]);
        setSemanticLoading(false);
        setSemanticMode('idle');
        setSemanticMessage('');
      })();
      return;
    }

    let cancelled = false;
    void (async () => { await Promise.resolve(); setSemanticLoading(true); })();

    const runSearch = async () => {
      try {
        const response = await courseAPI.semanticSearch({
          query,
          selected_types: selectedTypes,
          selected_credits: selectedCredits,
          selected_semesters: selectedSemesters,
          limit: 50,
        });
        if (cancelled) return;

        if (response.mode === 'semantic') {
          setSemanticCourses(response.results);
          setSemanticMode('semantic');
          setSemanticMessage(response.message ?? '');
          return;
        }

        setSemanticCourses([]);
        setSemanticMode('fallback');
        setSemanticMessage(response.message || '關鍵字向量搜尋暫時不可用，已自動改用一般文字搜尋。');
      } catch (error) {
        if (cancelled) return;
        console.warn('Semantic course search failed, using keyword fallback:', error);
        setSemanticCourses([]);
        setSemanticMode('fallback');
        setSemanticMessage('關鍵字向量搜尋暫時不可用，已自動改用一般文字搜尋。');
      } finally {
        if (!cancelled) setSemanticLoading(false);
      }
    };

    void runSearch();

    return () => {
      cancelled = true;
    };
  }, [searchMode, searchQuery, selectedTypes, selectedCredits, selectedSemesters]);

  const searchableFields = useCallback((course: Course) =>
    resultTab === 'course_name'
      ? [course.course_name_zh, course.course_name_en]
      : [
          course.course_name_zh,
          course.course_name_en,
          course.course_objective,
          course.course_content,
          course.course_field,
          course.textbooks,
          course.grading,
          course.note,
          course.instructor,
          course.department,
          course.college,
          course.semantic_summary,
          course.eligibility_summary,
          ...(course.tools ?? []),
          ...(course.concepts ?? []),
          ...(course.topic_tags ?? []),
          ...(course.domain_tags ?? []),
          ...(course.languages ?? []),
          ...(course.simplified_concepts ?? []),
          ...(course.core_questions ?? []),
        ], [resultTab]);

  const matchesStructuredFilters = useCallback((course: Course) => {
    const matchesType = selectedTypes.length === 0 || selectedTypes.includes(normalize(course.required_elective));
    const matchesCredits = selectedCredits.length === 0 || selectedCredits.includes(String(course.credits));
    const matchesSemester = selectedSemesters.length === 0 || selectedSemesters.includes(normalize(course.semester_display));
    return matchesType && matchesCredits && matchesSemester;
  }, [selectedTypes, selectedCredits, selectedSemesters]);

  const matchesKeywordFilters = useCallback((course: Course) => {
    const query = searchQuery.trim().toLowerCase();
    const matchesQuery = !query || searchableFields(course).filter(Boolean).some((value) => value!.toLowerCase().includes(query));
    return matchesStructuredFilters(course) && matchesQuery;
  }, [searchQuery, matchesStructuredFilters, searchableFields]);

  const departmentFieldOptions = useMemo(
    () => Array.from(new Set(departmentCourses.flatMap((course) => splitFields(course.course_field)).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-Hant')),
    [departmentCourses]
  );

  const currentCourses = useMemo(() => {
    let list = departmentCourses.filter(matchesKeywordFilters);
    if (selectedFieldFilters.length > 0) {
      list = list.filter((course) => splitFields(course.course_field).some((f) => selectedFieldFilters.includes(f)));
    }
    return list;
  }, [departmentCourses, matchesKeywordFilters, selectedFieldFilters]);

  const filteredCourses = useMemo(
    () => {
      if (hasSearchQuery && searchMode === 'semantic') {
        if (semanticMode === 'semantic') return semanticCourses.filter(matchesStructuredFilters);
        if (semanticMode === 'fallback') return courses.filter(matchesKeywordFilters);
        return [];
      }
      return courses.filter(matchesKeywordFilters);
    },
    [courses, hasSearchQuery, searchMode, semanticCourses, semanticMode, matchesKeywordFilters, matchesStructuredFilters]
  );

  const groupedSearchResults = useMemo(() => {
    const map = new Map<string, Map<string, Course[]>>();
    filteredCourses.forEach((course) => {
      const college = normalize(course.college) || FALLBACK_COLLEGE;
      const department = normalize(course.department) || FALLBACK_DEPARTMENT;
      if (!map.has(college)) map.set(college, new Map<string, Course[]>());
      const deptMap = map.get(college)!;
      if (!deptMap.has(department)) deptMap.set(department, []);
      deptMap.get(department)!.push(course);
    });

    return Array.from(map.entries())
      .sort((a, b) => {
        const ai = COLLEGE_ORDER.indexOf(a[0] as (typeof COLLEGE_ORDER)[number]);
        const bi = COLLEGE_ORDER.indexOf(b[0] as (typeof COLLEGE_ORDER)[number]);
        if (ai === -1 && bi === -1) return a[0].localeCompare(b[0], 'zh-Hant');
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      })
      .map(([college, departments]) => ({
        college,
        count: Array.from(departments.values()).reduce((sum, list) => sum + list.length, 0),
        departments: Array.from(departments.entries())
          .sort((a, b) => a[0].localeCompare(b[0], 'zh-Hant'))
          .map(([name, list]) => ({ name, count: list.length, courses: [...list].sort((a, b) => (a.course_id ?? '').localeCompare(b.course_id ?? '')) })),
      }));
  }, [filteredCourses]);

  const typeOptions = useMemo(
    () => Array.from(new Set(courses.map((course) => normalize(course.required_elective)).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-Hant')),
    [courses]
  );

  const creditOptions = useMemo(
    () => Array.from(new Set(courses.map((course) => String(course.credits)).filter(Boolean))).sort((a, b) => Number(a) - Number(b)),
    [courses]
  );

  const semesterOptions = useMemo(
    () => Array.from(new Set(courses.map((course) => normalize(course.semester_display)).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-Hant')),
    [courses]
  );

  useEffect(() => {
    if (!selectedCollege && sortedColleges.length > 0) {
      void (async () => {
        await Promise.resolve();
        setSelectedCollege(sortedColleges[0]);
      })();
    }
  }, [sortedColleges, selectedCollege]);

  useEffect(() => {
    if (!selectedCollege) return;
    const departments = Object.keys(groupedCourses[selectedCollege] || {});
    const selectedCourseInFilteredResults =
      hasActiveFilters &&
      selectedCourse &&
      filteredCourses.some((course) => courseKey(course) === courseKey(selectedCourse));

    if (!departments.length) {
      void (async () => {
        await Promise.resolve();
        setSelectedDepartment(null);
      })();
      return;
    }
    if (selectedDepartment && departments.includes(selectedDepartment)) return;
    void (async () => {
      await Promise.resolve();
      setSelectedDepartment(null);
      if (!selectedCourseInFilteredResults) {
        setSelectedCourse(null);
      }
    })();
  }, [filteredCourses, groupedCourses, hasActiveFilters, selectedCollege, selectedCourse, selectedDepartment]);

  useEffect(() => {
    const source = hasActiveFilters ? filteredCourses : currentCourses;
    if (!selectedCourse) return;
    if (selectedCourse && source.some((course) => courseKey(course) === courseKey(selectedCourse))) return;
    void (async () => {
      await Promise.resolve();
      setSelectedCourse(null);
    })();
  }, [currentCourses, filteredCourses, hasActiveFilters, selectedCourse]);

  const isCourseCompared = (course: Course) => compareCourses.some((item) => courseKey(item) === courseKey(course));

  const toggleCompareCourse = (course: Course) => {
    if (isCourseCompared(course)) {
      setCompareCourses((current) => current.filter((item) => courseKey(item) !== courseKey(course)));
      setCompareNotice('');
      return;
    }

    if (compareCourses.length >= COMPARE_LIMIT) {
      setCompareNotice(`最多只能同時對比 ${COMPARE_LIMIT} 門課。`);
      return;
    }

    setCompareCourses((current) => [...current, course]);
    setCompareNotice('');
  };

  const removeCompareCourse = (course: Course) => {
    setCompareCourses((current) => current.filter((item) => courseKey(item) !== courseKey(course)));
    setCompareNotice('');
  };

  const clearCompareCourses = () => {
    setCompareCourses([]);
    setCompareOpen(false);
    setCompareNotice('');
  };

  const activeTags = [
    ...(searchQuery.trim() ? [{ key: `search-${searchQuery}`, label: `${searchMode === 'semantic' ? '關鍵字向量搜尋' : '一般文字搜尋'}：${searchQuery.trim()}`, onRemove: () => setSearchQuery('') }] : []),
    ...selectedTypes.map((value) => ({ key: `type-${value}`, label: value, onRemove: () => setSelectedTypes((current) => current.filter((item) => item !== value)) })),
    ...selectedCredits.map((value) => ({ key: `credit-${value}`, label: `${value} 學分`, onRemove: () => setSelectedCredits((current) => current.filter((item) => item !== value)) })),
    ...selectedSemesters.map((value) => ({ key: `semester-${value}`, label: value, onRemove: () => setSelectedSemesters((current) => current.filter((item) => item !== value)) })),
  ];

  // ── 瀏覽與選取（只處理資料狀態；手機導覽開合等畫面狀態由頁面自己處理） ──
  const selectSearchResult = (college: string, department: string, course: Course) => {
    setSelectedCollege(college);
    setSelectedDepartment(department);
    setSelectedCourse(course);
    setNavigationLevel('courses');
  };

  const selectFlatSearchResult = (course: Course) => {
    selectSearchResult(normalize(course.college) || FALLBACK_COLLEGE, normalize(course.department) || FALLBACK_DEPARTMENT, course);
  };

  const selectCollege = (college: string) => {
    setSelectedCollege(college);
    setSelectedDepartment(null);
    setSelectedCourse(null);
    setNavigationLevel('departments');
  };

  const selectDepartment = (department: string) => {
    setSelectedDepartment(department);
    setSelectedCourse(null);
    setSelectedFieldFilters([]);
    setNavigationLevel('courses');
  };

  const goBack = () => {
    if (navigationLevel === 'courses') {
      setSelectedCourse(null);
      setNavigationLevel('departments');
      return;
    }
    setSelectedDepartment(null);
    setSelectedCourse(null);
    setNavigationLevel('colleges');
  };

  return {
    courses, loading,
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
    selectSearchResult, selectFlatSearchResult, selectCollege, selectDepartment, goBack,
  };
}
