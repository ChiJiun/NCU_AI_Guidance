import { useEffect, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
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
export function useAnalytics() {
  const { user, loading: authLoading } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>('all');

  const [courseData, setCourseData] = useState<AnalyticsData | null>(null);
  const [courseLoading, setCourseLoading] = useState(false);
  const [courseError, setCourseError] = useState('');
  const [courseFetched, setCourseFetched] = useState(false);

  const [projectData, setProjectData] = useState<PdfAnalyticsData | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState('');
  const [projectFetched, setProjectFetched] = useState(false);

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

  // 切換 tab 時懶載入
  useEffect(() => {
    if (!user) return;
    if (activeTab === 'all') {
      void fetchCourse();
      void fetchProject();
    } else if (activeTab === 'course') {
      void fetchCourse();
    } else if (activeTab === 'project') {
      void fetchProject();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, activeTab]);

  return {
    user, authLoading,
    activeTab, setActiveTab,
    courseData, courseLoading, courseError,
    projectData, projectLoading, projectError,
  };
}
