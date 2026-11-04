import { Link } from 'react-router-dom';
import { DEMO_MODE } from '../demo/config';

/** 展示模式下固定顯示在導覽列下方的說明條。 */
export default function DemoBanner() {
  if (!DEMO_MODE) return null;
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs leading-5 text-amber-800 sm:text-sm">
      <span className="font-semibold">比賽展示版</span>
      <span className="mx-1.5">·</span>
      AI 回答皆為預先產生的示範結果，不提供即時提問。
      <Link to="/demo" className="ml-1.5 font-semibold underline underline-offset-2 hover:text-amber-900">
        查看示範案例
      </Link>
    </div>
  );
}
