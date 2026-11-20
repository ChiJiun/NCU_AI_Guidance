import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { demoAPI } from '../../demo/demoCases';
import { useDemoView } from '../../hooks/useDemoView';
import {
  analyticsAPI,
  projectAnalyticsAPI,
  type AnalyticsData,
  type PdfAnalyticsData,
} from '../../api/services';

export type TabId = 'all' | 'course' | 'project';

/**
 * 個人分析頁的資料載入：依目前分頁懶載入課程助理分析（/chat/analytics）與研究計畫分析
 * （/projects/analytics），每種只抓一次。新舊版頁面共用這個 hook。
 */
export function useAnalytics({ demo = false }: { demo?: boolean } = {}) {
  const { user, loading: authLoading } = useAuth();
  // 展示版：不能即時提問的人沒有自己的紀錄，改看由示範對話算出的「示範學生」分析
  // （只有傳入 demo 的頁面才會顯示）
  const demoView = useDemoView();
  const showDemo = demo && demoView.showDemo;
  const demoViewLoading = demo && demoView.loading;
  const [demoInfo, setDemoInfo] = useState<{ generatedAt: string; course: number; research: number } | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('all');

  const [courseData, setCourseData] = useState<AnalyticsData | null>(null);
  const [courseLoading, setCourseLoading] = useState(false);
  const [courseError, setCourseError] = useState('');
  const [courseFetched, setCourseFetched] = useState(false);

  const [projectData, setProjectData] = useState<PdfAnalyticsData | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState('');
  const [projectFetched, setProjectFetched] = useState(false);

  // 換使用者、或在示範與真實分析之間切換時（例如訪客以開發團隊帳號登入），清掉已載入的資料重新抓
  const viewKey = `${showDemo ? 'demo' : 'real'}:${user?.id ?? ''}`;
  const [prevViewKey, setPrevViewKey] = useState(viewKey);
  if (prevViewKey !== viewKey) {
    setPrevViewKey(viewKey);
    setDemoInfo(null);
    setCourseData(null);
    setCourseError('');
    setCourseFetched(false);
    setProjectData(null);
    setProjectError('');
    setProjectFetched(false);
  }

  const fetchCourse = async () => {
    if (courseFetched) return;
    setCourseLoading(true);
    setCourseError('');
    try {
      const result = await analyticsAPI.get();
      setCourseData(result);
    } catch {
      setCourseError('載入課程分析失敗，請稍後再試');
    } finally {
      setCourseLoading(false);
      setCourseFetched(true);
    }
  };

  const fetchProject = async () => {
    if (projectFetched) return;
    setProjectLoading(true);
    setProjectError('');
    try {
      const result = await projectAnalyticsAPI.get();
      setProjectData(result);
    } catch {
      setProjectError('載入研究計畫分析失敗，請稍後再試');
    } finally {
      setProjectLoading(false);
      setProjectFetched(true);
    }
  };

  useEffect(() => {
    if (!showDemo) return;
    let cancelled = false;
    void (async () => {
      setCourseLoading(true);
      setProjectLoading(true);
      const demo = await demoAPI.analytics();
      if (cancelled) return;
      if (demo) {
        setCourseData(demo.course);
        setProjectData(demo.project);
        setDemoInfo({ generatedAt: demo.generated_at, course: demo.source.course_cases, research: demo.source.research_cases });
      } else {
        setCourseError('示範分析準備中');
        setProjectError('示範分析準備中');
      }
      setCourseLoading(false);
      setProjectLoading(false);
      setCourseFetched(true);
      setProjectFetched(true);
    })();
    return () => { cancelled = true; };
  }, [showDemo]);

  // 切換 tab 時懶載入
  useEffect(() => {
    if (!user || showDemo || demoViewLoading) return;
    if (activeTab === 'all') {
      void fetchCourse();
      void fetchProject();
    } else if (activeTab === 'course') {
      void fetchCourse();
    } else if (activeTab === 'project') {
      void fetchProject();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, activeTab, showDemo, demoViewLoading]);

  return {
    user, authLoading,
    showDemo, demoViewLoading, demoInfo,
    activeTab, setActiveTab,
    courseData, courseLoading, courseError,
    projectData, projectLoading, projectError,
  };
}
