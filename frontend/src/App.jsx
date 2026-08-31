import { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Lenis from 'lenis';
import { isAuthenticated } from './auth';
import { LanguageProvider } from './i18n/LanguageContext';
import ErrorBoundary from './components/ErrorBoundary';
import UpgradeModal from './components/UpgradeModal';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Callback from './pages/Callback';
import About from './pages/About';
import Privacy from './pages/Privacy';
import Terms from './pages/Terms';

// Code-split the heavier app pages so the public landing loads faster
// (smaller initial JS bundle -> better LCP / Core Web Vitals).
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Scheduler = lazy(() => import('./pages/Scheduler'));
const Calendar = lazy(() => import('./pages/Calendar'));
const History = lazy(() => import('./pages/History'));
const Admin = lazy(() => import('./pages/Admin'));

function ProtectedRoute({ children }) {
  // Ironclad: reject missing OR expired tokens. The backend still
  // enforces real authorization on every API call.
  return isAuthenticated() ? children : <Navigate to="/login" replace />;
}

function AppContent() {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('brandora_user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const handleLogout = useCallback(() => {
    localStorage.removeItem('brandora_token');
    localStorage.removeItem('brandora_user');
    setUser(null);
    window.location.href = '/login';
  }, []);

  useEffect(() => {
    const lenis = new Lenis({
      duration: 1.15,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
    });

    let rafId;
    const raf = (time) => {
      lenis.raf(time);
      rafId = requestAnimationFrame(raf);
    };
    rafId = requestAnimationFrame(raf);
    window.__lenis = lenis;

    return () => {
      cancelAnimationFrame(rafId);
      lenis.destroy();
      delete window.__lenis;
    };
  }, []);

  return (
    <>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#123346',
            color: '#eaf5f5',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: '12px',
          },
          success: { iconTheme: { primary: '#D6588A', secondary: '#eaf5f5' } },
          error: { iconTheme: { primary: '#ff5555', secondary: '#eaf5f5' } },
        }}
      />
      <div className="app">
        <Suspense fallback={<div className="app-loading" role="status">Loading…</div>}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/signup" element={<Navigate to="/register" replace />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/auth/callback/:platform" element={<Callback />} />
          <Route path="/about" element={<About />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <ErrorBoundary
                  label="dashboard"
                  reloadTo="/dashboard"
                  showDetail
                >
                  <Dashboard user={user} onLogout={handleLogout} />
                </ErrorBoundary>
              </ProtectedRoute>
            }
          />
          <Route
            path="/scheduler"
            element={
              <ProtectedRoute>
                <Scheduler user={user} onLogout={handleLogout} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/calendar"
            element={
              <ProtectedRoute>
                <Calendar user={user} onLogout={handleLogout} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/history"
            element={
              <ProtectedRoute>
                <History user={user} onLogout={handleLogout} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedRoute>
                <Admin user={user} onLogout={handleLogout} />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </div>
    </>
  );
}

function App() {
  return (
    <BrowserRouter>
      <LanguageProvider>
        <AppContent />
        <UpgradeModal />
      </LanguageProvider>
    </BrowserRouter>
  );
}

export default App;