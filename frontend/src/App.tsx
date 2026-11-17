import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
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
import DemoGalleryPage from './pages/DemoGalleryPage';
import DemoCasePage from './pages/DemoCasePage';
import { AuthProvider } from './auth/AuthContext';

// 新版前端（/v2/*）獨立成一個 chunk，只有進到 /v2 才會載入，不影響舊版
const V2App = lazy(() => import('./v2/V2App'));

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
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
            <Route path="/demo" element={<DemoGalleryPage />} />
            <Route path="/demo/:caseId" element={<DemoCasePage />} />
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
              <Suspense fallback={<div className="min-h-screen" style={{ background: '#f5f2ea' }} />}>
                <V2App />
              </Suspense>
            }
          />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
