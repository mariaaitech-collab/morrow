import { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Lenis from 'lenis';
import { isAuthenticated } from './auth';
import api from './api/axios';
import { LanguageProvider } from './i18n/LanguageContext';
import { DraftProvider, useDraft } from './draft/DraftContext';
import ErrorBoundary from './components/ErrorBoundary';
import UpgradeModal from './components/PricingModal';
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
const Create = lazy(() => import('./pages/Create'));
const Scheduler = lazy(() => import('./pages/Scheduler'));
const Calendar = lazy(() => import('./pages/Calendar'));
const History = lazy(() => import('./pages/History'));
const Admin = lazy(() => import('./pages/Admin'));
const Profile = lazy(() => import('./pages/Profile'));
const AIResponder = lazy(() => import('./pages/AIResponder'));

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

  const { clearDraft } = useDraft();
  const handleLogout = useCallback(() => {
    localStorage.removeItem('brandora_token');
    localStorage.removeItem('brandora_user');
    clearDraft();
    setUser(null);
    window.location.href = '/login';
  }, [clearDraft]);

  // Live token counter: whenever the backend reports a new balance, update the
  // App-level user state (and the stored copy) so the Navbar re-renders at once.
  useEffect(() => {
    const onTokensUpdated = (e) => {
      const tokens = e?.detail?.tokens;
      const isUnlimited = e?.detail?.isUnlimited;
      setUser((prev) => {
        const next = { ...(prev || {}) };
        if (typeof tokens === 'number') next.free_tokens = tokens;
        if (typeof isUnlimited === 'boolean') next.is_unlimited = isUnlimited;
        return next;
      });
    };
    window.addEventListener('brandora:tokens-updated', onTokensUpdated);
    return () => window.removeEventListener('brandora:tokens-updated', onTokensUpdated);
  }, []);

  // On load, sync the stored profile against /auth/me so free_tokens / plan are
  // accurate for the Navbar counter even right after signing in.
  useEffect(() => {
    if (!isAuthenticated()) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get('/auth/me');
        if (cancelled || !data) return;
        const merged = { ...(user || {}), ...data };
        setUser(merged);
        try {
          localStorage.setItem('brandora_user', JSON.stringify(merged));
        } catch {
          /* ignore */
        }
      } catch {
        /* ignore transient failures */
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        containerStyle={{ zIndex: 'var(--z-toast)' }}
        toastOptions={{
          style: {
            background: 'var(--surface)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-card)',
            boxShadow: 'var(--shadow-popover)',
            fontFamily: 'var(--font-sans)',
            fontSize: 'var(--fs-body)',
          },
          success: { iconTheme: { primary: 'var(--success)', secondary: 'var(--surface)' } },
          error: { iconTheme: { primary: 'var(--danger)', secondary: 'var(--surface)' } },
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
            path="/create"
            element={
              <ProtectedRoute>
                <ErrorBoundary label="create" reloadTo="/create" showDetail>
                  <Create user={user} onLogout={handleLogout} />
                </ErrorBoundary>
              </ProtectedRoute>
            }
          />
          <Route path="/studio" element={<Navigate to="/create" replace />} />
          <Route path="/channels" element={<Navigate to="/profile#business-profile" replace />} />
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
            path="/profile"
            element={
              <ProtectedRoute>
                <Profile user={user} onLogout={handleLogout} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-responder"
            element={
              <ProtectedRoute>
                <ErrorBoundary label="AI responder" reloadTo="/ai-responder" showDetail>
                  <AIResponder user={user} onLogout={handleLogout} />
                </ErrorBoundary>
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
        <DraftProvider>
          <AppContent />
          <UpgradeModal />
        </DraftProvider>
      </LanguageProvider>
    </BrowserRouter>
  );
}

export default App;
