import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import api, { extractApiError } from '../api/axios';
import SEO from '../components/SEO';
import { Logo } from '../components/ui';
import { useLanguage } from '../i18n/LanguageContext';

/* ─────────────────────────────────────────────
   AuthPanel — the left brand showcase
───────────────────────────────────────────── */
function AuthPanel() {
  const features = [
    { icon: '✦', label: 'AI-powered content generation' },
    { icon: '◈', label: 'Smart scheduling across platforms' },
    { icon: '◉', label: 'Real-time analytics dashboard' },
    { icon: '◆', label: 'Team collaboration tools' },
  ];

  return (
    <div className="auth-panel">
      <div className="auth-panel-content">
        {/* Logo */}
        <div className="auth-panel-brand">
          <Logo size={40} />
        </div>

        {/* Headline */}
        <div className="auth-panel-headline">
          <h2>Your brand,<br />amplified.</h2>
          <p>
            Create, schedule, and analyse stunning social content — all in one
            intelligent workspace.
          </p>
        </div>

        {/* Feature list */}
        <ul className="auth-panel-features">
          {features.map((f) => (
            <li key={f.label}>
              <span className="auth-panel-feature-icon">{f.icon}</span>
              <span>{f.label}</span>
            </li>
          ))}
        </ul>

        {/* Testimonial */}
        <figure className="auth-panel-quote">
          <blockquote>
            "Morrow tripled our engagement in 30 days. Absolutely essential."
          </blockquote>
          <figcaption>
            <span className="auth-panel-avatar">S</span>
            <span>
              <strong>Sarah K.</strong>
              <em>Head of Marketing, NovaTech</em>
            </span>
          </figcaption>
        </figure>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────
   AuthShell — shared split-screen shell
───────────────────────────────────────────── */
export function AuthShell({ title, sub, children, alt }) {
  return (
    <div className="auth-root">
      <AuthPanel />

      <div className="auth-form-side">
        {/* Top-right corner back-to-home link */}
        <Link to="/" className="auth-back-link" aria-label="Back to home">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          Home
        </Link>

        <div className="auth-form-wrap">
          {/* Card */}
          <div className="auth-card">
            {/* Brand (mobile only) */}
            <div className="auth-card-mobile-brand">
              <Logo size={32} />
            </div>

            <h1 className="auth-form-title">{title}</h1>
            {sub && <p className="auth-form-sub">{sub}</p>}

            {children}

            {alt && <div className="auth-alt">{alt}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────
   Login page
───────────────────────────────────────────── */
export default function Login() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post('/auth/login', {
        email: email.trim().toLowerCase(),
        password,
      });
      localStorage.setItem('brandora_token', data.access_token);
      localStorage.setItem(
        'brandora_user',
        JSON.stringify({ username: data.username, email, is_admin: !!data.is_admin })
      );
      toast.success(t('auth.welcomeBack', { username: data.username }));
      navigate('/dashboard');
    } catch (err) {
      if (err.response?.data?.detail) {
        toast.error(extractApiError(err, t('auth.loginFailed')));
      } else if (err.request) {
        toast.error(t('auth.serverUnreachable'));
      } else {
        toast.error(t('auth.loginFailed'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <SEO
        title="Log In | Morrow — AI Social Media Manager"
        description="Log in to Morrow, the AI social media manager and content calendar that schedules, generates and analyzes your social media content."
        path="/login"
      />
      <AuthShell
        title={t('auth.loginTitle')}
        sub={t('auth.loginSub')}
        alt={<>{t('auth.noAccount')} <Link to="/register">{t('auth.getStarted')}</Link></>}
      >
        <form onSubmit={handleSubmit} className="auth-form" noValidate>
          {/* Email */}
          <div className="auth-field-group">
            <label className="auth-field-label" htmlFor="login-email">
              {t('auth.email')}
            </label>
            <div className="auth-input-wrap">
              <span className="auth-input-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="4" width="20" height="16" rx="2" />
                  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
                </svg>
              </span>
              <input
                id="login-email"
                className="auth-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </div>
          </div>

          {/* Password */}
          <div className="auth-field-group">
            <div className="auth-field-row">
              <label className="auth-field-label" htmlFor="login-password">
                {t('auth.password')}
              </label>
              <Link className="auth-inline-link" to="/forgot-password">
                {t('auth.forgotLink')}
              </Link>
            </div>
            <div className="auth-input-wrap">
              <span className="auth-input-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              </span>
              <input
                id="login-password"
                className="auth-input"
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="auth-pw-toggle"
                onClick={() => setShowPw((v) => !v)}
                aria-label={showPw ? 'Hide password' : 'Show password'}
              >
                {showPw ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            className="auth-submit"
            type="submit"
            id="login-submit-btn"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner-sm" />
                {t('common.loading')}
              </>
            ) : (
              t('auth.loginBtn')
            )}
          </button>
        </form>
      </AuthShell>
    </>
  );
}
