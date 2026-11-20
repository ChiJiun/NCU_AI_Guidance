import { BrowserRouter as Router, Navigate, Routes, Route, useLocation } from 'react-router-dom';
import { lazy, Suspense, useEffect } from 'react';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import AssessmentPage from './pages/AssessmentPage';
import ProjectsPage from './pages/ProjectsPage';
import CoursesPage from './pages/CoursesPage';
import CourseSearchPage from './pages/CourseSearchPage';
import ResourcesPage from './pages/ResourcesPage';
import CurriculumPage from './pages/CurriculumPage';
import AnalyticsPage from './pages/AnalyticsPage';
import MonitorPage from './pages/MonitorPage';
import { AuthProvider } from './auth/AuthContext';
import LoadErrorBoundary from './components/LoadErrorBoundary';
import V2LoadError from './v2/V2LoadError';
import V3LoadError from './v3/V3LoadError';

// 新版前端（/v2/*）獨立成一個 chunk，只有進到 /v2 才會載入，不影響舊版
const V2App = lazy(() => import('./v2/V2App'));
// 第三版前端（/v3/*）：v2 的版面＋舊版的風格，同樣獨立成一個 chunk
const V3App = lazy(() => import('./v3/V3App'));

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

/**
 * 舊的獨立示範案例頁（/demo、/demo/:caseId）已改成在課程助理、研究計畫頁內直接看示範對話；
 * 舊連結導到對應的頁面（?assistant=research → 研究計畫，其餘 → 課程助理）。
 */
function DemoRedirect() {
  const { search } = useLocation();
  const assistant = new URLSearchParams(search).get('assistant');
  return <Navigate to={assistant === 'research' ? '/projects' : '/course-search'} replace />;
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <ScrollToTop />
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/assessment" element={<AssessmentPage />} />
            <Route path="/resources" element={<ResourcesPage />} />
            <Route path="/profile" element={<AnalyticsPage />} />
            <Route path="/demo" element={<DemoRedirect />} />
            <Route path="/demo/:caseId" element={<DemoRedirect />} />
          </Route>
          <Route element={<Layout noPad />}>
            <Route path="/monitor" element={<MonitorPage />} />
          </Route>
          <Route element={<Layout fullHeight />}>
            <Route path="/courses" element={<CoursesPage />} />
            <Route path="/course-search" element={<CourseSearchPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/curriculum" element={<CurriculumPage />} />
          </Route>
          <Route
            path="/v2/*"
            element={
              <LoadErrorBoundary fallback={<V2LoadError />}>
                <Suspense fallback={<div className="min-h-screen" style={{ background: '#f5f2ea' }} />}>
                  <V2App />
                </Suspense>
              </LoadErrorBoundary>
            }
          />
          <Route
            path="/v3/*"
            element={
              <LoadErrorBoundary fallback={<V3LoadError />}>
                <Suspense fallback={<div className="bg-theme-1 min-h-screen" />}>
                  <V3App />
                </Suspense>
              </LoadErrorBoundary>
            }
          />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
