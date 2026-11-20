import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import './v2.css';
import V2Layout from './components/V2Layout';
import AssessmentV2 from './pages/AssessmentV2';
import CourseChatV2 from './pages/CourseChatV2';
import CoursesV2 from './pages/CoursesV2';
import CurriculumV2 from './pages/CurriculumV2';
import HomeV2 from './pages/HomeV2';
import MonitorV2 from './pages/MonitorV2';
import ProfileV2 from './pages/ProfileV2';
import ProjectsV2 from './pages/ProjectsV2';
import ResourcesV2 from './pages/ResourcesV2';
import { hasV2Page, toLegacyPath, toV2Path } from './paths';

/** 新版還沒有的頁面：導回舊版同一頁。 */
function BackToLegacy() {
  const { pathname, search, hash } = useLocation();
  return <Navigate to={`${toLegacyPath(pathname)}${search}${hash}`} replace />;
}

/** 新版前端（掛在 /v2/*）。整個模組由 App.tsx 以 lazy 載入，不影響舊版的首次載入。 */
export default function V2App() {
  const { pathname, search, hash } = useLocation();
  // react-router 比對不分大小寫，/V2/Courses、/v2/courses/ 也會進到新版頁面；
  // 先導到標準寫法，避免版面判斷（V2Layout 的 APP_PAGES）和「舊版」連結拿到大小寫不同的路徑
  const legacy = toLegacyPath(pathname);
  if (hasV2Page(legacy)) {
    const canonical = toV2Path(legacy);
    if (canonical !== pathname) return <Navigate to={`${canonical}${search}${hash}`} replace />;
  }

  return (
    <Routes>
      <Route element={<V2Layout />}>
        <Route index element={<HomeV2 />} />
        <Route path="assessment" element={<AssessmentV2 />} />
        <Route path="curriculum" element={<CurriculumV2 />} />
        <Route path="courses" element={<CoursesV2 />} />
        <Route path="course-search" element={<CourseChatV2 />} />
        <Route path="projects" element={<ProjectsV2 />} />
        <Route path="resources" element={<ResourcesV2 />} />
        <Route path="profile" element={<ProfileV2 />} />
        <Route path="monitor" element={<MonitorV2 />} />
      </Route>
      <Route path="*" element={<BackToLegacy />} />
    </Routes>
  );
}
