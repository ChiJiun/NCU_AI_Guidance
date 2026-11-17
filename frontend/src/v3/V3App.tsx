import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
// 先載入 v2 的元件樣式（頁面元件與 v2 共用），再用 v3.css 在 .v3 底下換成舊版（v1）的外觀
import '../v2/v2.css';
import './v3.css';
import AssessmentV2 from '../v2/pages/AssessmentV2';
import CourseChatV2 from '../v2/pages/CourseChatV2';
import CoursesV2 from '../v2/pages/CoursesV2';
import CurriculumV2 from '../v2/pages/CurriculumV2';
import { SiteContext, type SiteConfig } from '../v2/site';
import V3Layout from './components/V3Layout';
import HomeV3 from './pages/HomeV3';
import { collegeHexV3 } from './colleges';
import { hasV3Page, toV1Path, toV3Path, v3Link } from './paths';

/** v3 的站內連結與學院配色；定義在模組層級，參考穩定 */
const V3_SITE: SiteConfig = { link: v3Link, collegeHex: collegeHexV3 };

/** v3 還沒有的頁面（例如 /v3/projects）：導回舊版同一頁。 */
function BackToLegacy() {
  const { pathname, search, hash } = useLocation();
  return <Navigate to={`${toV1Path(pathname)}${search}${hash}`} replace />;
}

/**
 * 第三版前端（掛在 /v3/*）：版面、資訊架構與互動沿用 v2（直接重用 v2 的頁面元件與 features/* 的 hook），
 * 外觀改用舊版的風格。整個模組由 App.tsx 以 lazy 載入，不影響舊版與 v2 的首次載入。
 */
export default function V3App() {
  const { pathname, search, hash } = useLocation();
  // react-router 比對不分大小寫：/V3/Courses、/v3/courses/ 先導到標準寫法，版面判斷與切換連結才拿得到一致的路徑
  const legacy = toV1Path(pathname);
  if (hasV3Page(legacy)) {
    const canonical = toV3Path(legacy);
    if (canonical !== pathname) return <Navigate to={`${canonical}${search}${hash}`} replace />;
  }

  return (
    <SiteContext.Provider value={V3_SITE}>
      <Routes>
        <Route element={<V3Layout />}>
          <Route index element={<HomeV3 />} />
          <Route path="assessment" element={<AssessmentV2 />} />
          <Route path="curriculum" element={<CurriculumV2 />} />
          <Route path="courses" element={<CoursesV2 />} />
          <Route path="course-search" element={<CourseChatV2 />} />
        </Route>
        <Route path="*" element={<BackToLegacy />} />
      </Routes>
    </SiteContext.Provider>
  );
}
