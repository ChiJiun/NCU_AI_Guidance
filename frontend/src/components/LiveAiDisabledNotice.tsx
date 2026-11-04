import { Link } from 'react-router-dom';
import { HiSparkles } from 'react-icons/hi';

interface LiveAiDisabledNoticeProps {
  /** 連到示範案例頁時預先篩選的助理類型 */
  assistant?: 'course' | 'research';
  compact?: boolean;
}

/** 展示模式下取代即時提問輸入框的提示。 */
export default function LiveAiDisabledNotice({ assistant, compact = false }: LiveAiDisabledNoticeProps) {
  const to = assistant ? `/demo?assistant=${assistant}` : '/demo';
  return (
    <div className={`border-t border-slate-200 ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex flex-col items-center gap-2 rounded-2xl bg-slate-50 px-4 py-4 text-center">
        <p className="text-sm font-semibold text-slate-700">比賽展示版目前不提供即時提問</p>
        <p className="text-xs leading-5 text-slate-500">
          為避免公開網站產生模型費用，AI 對話改以預先產生、經人工檢查的示範案例呈現。
        </p>
        <Link
          to={to}
          className="mt-1 inline-flex items-center gap-1.5 rounded-xl bg-primary-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-primary-800"
        >
          <HiSparkles className="h-4 w-4" />
          查看 AI 示範案例
        </Link>
      </div>
    </div>
  );
}
