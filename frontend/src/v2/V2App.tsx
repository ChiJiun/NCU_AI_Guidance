import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import './v2.css';
import V2Layout from './components/V2Layout';
import AssessmentV2 from './pages/AssessmentV2';
import CourseChatV2 from './pages/CourseChatV2';
import CoursesV2 from './pages/CoursesV2';
import CurriculumV2 from './pages/CurriculumV2';
import HomeV2 from './pages/HomeV2';
import { hasV2Page, toLegacyPath, toV2Path } from './paths';

/** 新版還沒有的頁面（例如 /v2/projects）：導回舊版同一頁。 */
function BackToLegacy() {
  const { pathname, search, hash } = useLocation();
  const legacy = toLegacyPath(pathname);
  // 新版有這一頁、只是網址寫法不標準（例如 /v2//courses、/V2/Courses）：導到標準寫法的新版頁面
  const to = hasV2Page(legacy) ? toV2Path(legacy) : legacy;
  return <Navigate to={`${to}${search}${hash}`} replace />;
}

/** 新版前端（掛在 /v2/*）。整個模組由 App.tsx 以 lazy 載入，不影響舊版的首次載入。 */
export default function V2App() {
  return (
    <Routes>
      <Route element={<V2Layout />}>
        <Route index element={<HomeV2 />} />
        <Route path="assessment" element={<AssessmentV2 />} />
        <Route path="curriculum" element={<CurriculumV2 />} />
        <Route path="courses" element={<CoursesV2 />} />
        <Route path="course-search" element={<CourseChatV2 />} />
      </Route>
      <Route path="*" element={<BackToLegacy />} />
    </Routes>
  );
}
