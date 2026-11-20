import { useAuth } from '../auth/AuthContext';
import { useLiveAiAccess } from './useLiveAiAccess';

export interface DemoView {
  /** 這個網站是展示版（後端 LIVE_AI_ACCESS=developers） */
  demoSite: boolean;
  /** 目前的使用者不能即時提問，改看預先錄製的示範（未登入訪客、或不在開放名單的帳號） */
  showDemo: boolean;
  loading: boolean;
}

/**
 * 展示版的顯示判斷，建立在 /api/ai-access 之上：
 * - showDemo：後端明確表示這位使用者不能用即時 AI → 各頁改顯示示範對話、示範學生分析
 * - demoSite：網站開了 developers 模式 → 導覽列顯示「示範學生」、隱藏版本切換
 * /ai-access 失敗時沿用 useLiveAiAccess 的 fail-open（照常顯示正式版畫面，由後端 403 把關）。
 */
export function useDemoView(): DemoView {
  const { loading: authLoading } = useAuth();
  const liveAi = useLiveAiAccess();
  return {
    demoSite: liveAi.mode === 'developers',
    showDemo: liveAi.status === 'restricted',
    loading: authLoading || liveAi.loading,
  };
}
