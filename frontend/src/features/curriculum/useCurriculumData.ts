import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import { COLLEGE_ORDER } from '../../constants/colleges';
import { buildCourseIndex } from './courseIndex';
import type { CollegeNode, CourseIndex, DeptDetail, DeptSummary } from './types';

/**
 * 系所修課頁的資料邏輯：學院／系所樹、系所詳情、背景建立跨系課程索引、系所比較清單。
 * 新舊版頁面共用這個 hook，各自只負責畫面。
 *
 * @param collegeHex 學院名稱 → 代表色（各版畫面自己的配色）；必須是穩定的函式參考（定義在模組層級）。
 */
export function useCurriculumData(collegeHex: (collegeName: string) => string) {
  const [tree, setTree] = useState<CollegeNode[]>([]);
  const [childDeptIds, setChildDeptIds] = useState<Set<string>>(new Set());
  const [expandedColleges, setExpandedColleges] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DeptDetail | null>(null);
  const [loadingTree, setLoadingTree] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(true);
  const [selectedCollegeHex, setSelectedCollegeHex] = useState<string>('#6366f1');
  const [sidebarMode, setSidebarMode] = useState<'dept' | 'search'>('dept');
  const [allDeptDetails, setAllDeptDetails] = useState<Map<string, DeptDetail>>(new Map());
  const [courseIndex, setCourseIndex] = useState<CourseIndex>(new Map());
  const [indexReady, setIndexReady] = useState(false);
  const [comparePool, setComparePool] = useState<DeptSummary[]>([]);

  // ── deptMetaMap: deptId → { collegeName, accentHex } ──
  const deptMetaMap = useMemo(() => {
    const map = new Map<string, { collegeName: string; accentHex: string }>();
    for (const college of tree) {
      const hex = collegeHex(college.name);
      for (const dept of [...college.departments, ...college.college_bachelor_programs]) {
        map.set(dept.id, { collegeName: college.name, accentHex: hex });
        for (const g of dept.groups ?? []) map.set(g.id, { collegeName: college.name, accentHex: hex });
        for (const t of (dept as { specialization_tracks?: { id: string }[] }).specialization_tracks ?? [])
          map.set(t.id, { collegeName: college.name, accentHex: hex });
      }
    }
    return map;
  }, [tree, collegeHex]);

  // ── 背景批次載入所有系所資料，建立課程索引 ──
  useEffect(() => {
    if (tree.length === 0) return;
    const allIds: string[] = [];
    for (const college of tree) {
      for (const dept of [...college.departments, ...college.college_bachelor_programs]) {
        allIds.push(dept.id);
        for (const g of dept.groups ?? []) allIds.push(g.id);
        for (const t of (dept as { specialization_tracks?: { id: string }[] }).specialization_tracks ?? []) allIds.push(t.id);
      }
    }
    let cancelled = false;
    (async () => {
      const acc = new Map<string, DeptDetail>();
      const batchSize = 6;
      for (let i = 0; i < allIds.length; i += batchSize) {
        if (cancelled) return;
        const batch = allIds.slice(i, i + batchSize);
        const results = await Promise.allSettled(batch.map(id => apiClient.get(`/curriculum/dept/${id}`)));
        results.forEach((r, j) => { if (r.status === 'fulfilled') acc.set(batch[j], r.value.data as DeptDetail); });
      }
      if (!cancelled) { setAllDeptDetails(acc); setIndexReady(true); }
    })();
    return () => { cancelled = true; };
  }, [tree]);

  // ── 索引就緒後建立 CourseIndex ──
  useEffect(() => {
    if (!indexReady || allDeptDetails.size === 0) return;
    setCourseIndex(buildCourseIndex(allDeptDetails, deptMetaMap));
  }, [indexReady, allDeptDetails, deptMetaMap]);

  // ── 比較功能 ──
  const toggleCompare = useCallback((dept: DeptSummary) => {
    setComparePool(prev => {
      if (prev.some(d => d.id === dept.id)) return prev.filter(d => d.id !== dept.id);
      if (prev.length >= 3) return prev;
      return [...prev, dept];
    });
  }, []);

  // ── navigateTo: 導航並展開對應學院 ──
  const navigateTo = useCallback((deptId: string) => {
    setIsMobileMenuOpen(false);
    setSidebarMode('dept');
    for (const college of tree) {
      const allDepts = [...college.departments, ...college.college_bachelor_programs];
      const found = allDepts.some(d => {
        if (d.id === deptId) return true;
        if ('groups' in d && d.groups?.some((g: { id: string }) => g.id === deptId)) return true;
        if ('specialization_tracks' in d && (d as { specialization_tracks?: { id: string }[] }).specialization_tracks?.some(t => t.id === deptId)) return true;
        return false;
      });
      if (found) {
        setExpandedColleges(prev => { const next = new Set(prev); next.add(college.id); return next; });
        break;
      }
    }
    setSelectedId(deptId);
    for (const college of tree) {
      const allDepts = [...college.departments, ...college.college_bachelor_programs];
      const found = allDepts.some(d => d.id === deptId || d.groups?.some((g: { id: string }) => g.id === deptId));
      if (found) {
        setSelectedCollegeHex(collegeHex(college.name));
        break;
      }
    }
    setDetail(null);
    setLoadingDetail(true);
    apiClient.get(`/curriculum/dept/${deptId}`)
      .then(res => {
        setDetail(res.data);
        setAllDeptDetails(prev => { if (prev.has(deptId)) return prev; const next = new Map(prev); next.set(deptId, res.data); return next; });
      })
      .catch(console.error)
      .finally(() => setLoadingDetail(false));
  }, [tree, collegeHex]);

  useEffect(() => {
    apiClient
      .get('/curriculum/tree')
      .then((res) => {
        const sorted = [...(res.data as CollegeNode[])].sort((a, b) => {
          const ia = COLLEGE_ORDER.indexOf(a.name as (typeof COLLEGE_ORDER)[number]);
          const ib = COLLEGE_ORDER.indexOf(b.name as (typeof COLLEGE_ORDER)[number]);
          if (ia === -1 && ib === -1) return a.name.localeCompare(b.name, 'zh-Hant');
          if (ia === -1) return 1;
          if (ib === -1) return -1;
          return ia - ib;
        });
        setTree(sorted);
        const ids = new Set<string>();
        res.data.forEach((college: CollegeNode) => {
          if (college.id !== 'college_liberal_arts') return;
          college.college_bachelor_programs.forEach((cbp) => {
            cbp.specialization_tracks?.forEach((t) => ids.add(t.id));
          });
        });
        setChildDeptIds(ids);
      })
      .catch(console.error)
      .finally(() => setLoadingTree(false));
  }, []);

  const selectDept = useCallback((id: string) => {
    setSelectedId(id);
    setIsMobileMenuOpen(false); // on mobile: switch to content view
    // 找出所屬學院，更新 accent 顏色
    for (const college of tree) {
      const allDepts = [...college.departments, ...college.college_bachelor_programs];
      const found = allDepts.some(d => {
        if (d.id === id) return true;
        if ('groups' in d && d.groups?.some((g: { id: string }) => g.id === id)) return true;
        if ('specialization_tracks' in d && (d as { specialization_tracks?: { id: string }[] }).specialization_tracks?.some(t => t.id === id)) return true;
        return false;
      });
      if (found) {
        setSelectedCollegeHex(collegeHex(college.name));
        break;
      }
    }
    setDetail(null);
    setLoadingDetail(true);
    apiClient
      .get(`/curriculum/dept/${id}`)
      .then((res) => {
        setDetail(res.data);
        setAllDeptDetails(prev => { if (prev.has(id)) return prev; const next = new Map(prev); next.set(id, res.data); return next; });
      })
      .catch(console.error)
      .finally(() => setLoadingDetail(false));
  }, [tree, collegeHex]);

  const toggleCollege = (id: string) => {
    setExpandedColleges((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return {
    tree, childDeptIds,
    expandedColleges, toggleCollege,
    selectedId, detail,
    loadingTree, loadingDetail,
    isMobileMenuOpen, setIsMobileMenuOpen,
    selectedCollegeHex,
    sidebarMode, setSidebarMode,
    allDeptDetails, courseIndex, indexReady,
    comparePool, setComparePool, toggleCompare,
    deptMetaMap,
    navigateTo, selectDept,
  };
}
