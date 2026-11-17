import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { HiLockClosed } from 'react-icons/hi';
import { DEFAULT_LIVE_AI_RESTRICTED_MESSAGE } from '../../api/liveAi';
import { useAuth } from '../../auth/AuthContext';
import { GoogleMark } from '../../components/GoogleLoginButton';
import { DEMO_CASES } from '../../demo/cases';
import type { LiveAiAccessState } from '../../hooks/useLiveAiAccess';
import { useSite } from '../site';

interface LiveAiGateProps {
  liveAi: LiveAiAccessState;
  /** 連到示範案例頁時預先篩選的助理類型 */
  assistant?: 'course' | 'research';
  /** 可以使用即時 AI 時顯示的輸入區 */
  children: ReactNode;
}

/**
 * AI 輸入區的權限閘（判斷邏輯與舊版相同，來自 useLiveAiAccess）：
 * 確認中先佔位、不開放時換成說明、開放時才顯示輸入區。
 */
export default function LiveAiGate({ liveAi, assistant, children }: LiveAiGateProps) {
  const { user, loginWithGoogle } = useAuth();
  // v3 也重用這個元件：示範案例連結要跟著目前的版本（v3 沒有示範案例頁，連回舊版）
  const { link } = useSite();
  const [loginFailed, setLoginFailed] = useState(false);

  if (liveAi.loading) {
    return (
      <div aria-busy="true">
        <div className="v2-skeleton h-11" />
        <span className="sr-only">正在確認即時 AI 使用權限</span>
      </div>
    );
  }

  if (liveAi.allowed) return <>{children}</>;

  const handleLogin = async () => {
    setLoginFailed(false);
    try {
      await loginWithGoogle();
    } catch {
      setLoginFailed(true);
    }
  };

  return (
    <div role="status" className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <p className="flex min-w-0 flex-1 basis-56 items-center gap-2 text-sm font-medium">
        <HiLockClosed className="v2-faint h-4 w-4 shrink-0" aria-hidden="true" />
        {liveAi.message || DEFAULT_LIVE_AI_RESTRICTED_MESSAGE}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {!user && (
          <button type="button" onClick={handleLogin} className="v2-btn v2-btn--ghost v2-btn--sm">
            <GoogleMark />
            登入
          </button>
        )}
        {DEMO_CASES.length > 0 && (
          <Link to={`${link('/demo')}${assistant ? `?assistant=${assistant}` : ''}`} className="v2-btn v2-btn--sm">
            看示範案例
          </Link>
        )}
      </div>
      {loginFailed && (
        <p role="alert" className="w-full text-xs" style={{ color: 'var(--v2-danger)' }}>
          登入失敗，請再試一次
        </p>
      )}
    </div>
  );
}
