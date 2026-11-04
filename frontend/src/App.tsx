import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
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
import { DEMO_MODE } from './demo/config';
import { AuthProvider } from './auth/AuthContext';

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
            <Route path="/profile" element={DEMO_MODE ? <Navigate to="/" replace /> : <AnalyticsPage />} />
            <Route path="/demo" element={<DemoGalleryPage />} />
            <Route path="/demo/:caseId" element={<DemoCasePage />} />
          </Route>
          <Route element={<Layout noPad />}>
            <Route path="/monitor" element={<MonitorPage />} />
          </Route>
          <Route element={<Layout fullHeight />}>
            <Route path="/courses" element={<CoursesPage />} />
            <Route
              path="/course-search"
              element={DEMO_MODE ? <Navigate to="/demo?assistant=course" replace /> : <CourseSearchPage />}
            />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/curriculum" element={<CurriculumPage />} />
          </Route>
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
