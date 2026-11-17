import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { isDeveloper } from '../../auth/developerUtils';
import { monitorAPI, type DBStats, type MonitorStats } from '../../api/services';
import {
  currentMonthISO,
  currentWeekISO,
  resolveFetchOpts,
  todayISO,
  type TimeRangeState,
} from './monitorUtils';

export type MonitorTabId = 'overview'|'course'|'pdf'|'database'|'activity';

/**
 * 系統監控頁的資料邏輯：只給開發者（isDeveloper，否則導回 homePath）、依時間範圍抓
 * /monitor/stats、倒數自動更新、切到資料庫分頁才抓 /monitor/db-stats。新舊版頁面共用這個 hook。
 */
export function useMonitor(homePath = '/') {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<MonitorTabId>('overview');
  const [timeState, setTimeState] = useState<TimeRangeState>({
    mode:'preset', preset:'7d', dayVal:todayISO(), weekVal:currentWeekISO(), monthVal:currentMonthISO(),
  });
  const [refreshSec, setRefreshSec]   = useState(60);
  const [countdown, setCountdown]     = useState(60);
  const [stats, setStats]             = useState<MonitorStats|null>(null);
  const [dbStats, setDbStats]         = useState<DBStats|null>(null);
  const [dbLoading, setDbLoading]     = useState(false);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState<string|null>(null);
  const [lastAt, setLastAt]           = useState<Date|null>(null);
  const seqRef    = useRef(0);
  const dbFetched = useRef(false);

  const fetchOpts = useMemo(() => resolveFetchOpts(timeState), [timeState]);

  const fetchStats = useCallback(async (opts: typeof fetchOpts) => {
    const id = ++seqRef.current;
    setLoading(true); setError(null);
    try {
      const d = await monitorAPI.getStats(opts);
      if (seqRef.current===id) { setStats(d); setLastAt(new Date()); }
    } catch (e: unknown) {
      if (seqRef.current===id) setError(e instanceof Error ? e.message : '載入失敗');
    } finally {
      if (seqRef.current===id) setLoading(false);
    }
  }, []);

  // 認證 + 初始 fetch
  useEffect(() => {
    if (authLoading) return;
    if (!isDeveloper(user?.email)) { navigate(homePath); return; }
    fetchStats(fetchOpts);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, authLoading, navigate, fetchStats, fetchOpts, homePath]);

  // auto-refresh
  useEffect(() => {
    const t = setInterval(() => {
      setCountdown(c => { if (c<=1) { fetchStats(fetchOpts); return refreshSec; } return c-1; });
    }, 1000);
    return () => clearInterval(t);
  }, [fetchOpts, refreshSec, fetchStats]);

  // DB stats：切到 database tab 時才 fetch
  useEffect(() => {
    if (activeTab==='database' && !dbFetched.current) {
      dbFetched.current = true;
      setDbLoading(true);
      monitorAPI.getDbStats()
        .then(setDbStats)
        .finally(() => setDbLoading(false));
    }
  }, [activeTab]);

  const doRefresh = () => {
    fetchStats(fetchOpts);
    setCountdown(refreshSec);
    if (activeTab==='database') {
      dbFetched.current = false;
      setDbLoading(true);
      monitorAPI.getDbStats().then(setDbStats).finally(()=>setDbLoading(false));
      dbFetched.current = true;
    }
  };

  return {
    user, authLoading,
    activeTab, setActiveTab,
    timeState, setTimeState,
    refreshSec, setRefreshSec,
    countdown, setCountdown,
    stats, dbStats, dbLoading,
    loading, error, lastAt,
    doRefresh,
  };
}
