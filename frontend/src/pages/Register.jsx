import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import api, { extractApiError } from '../api/axios';
import SEO from '../components/SEO';
import { useLanguage } from '../i18n/LanguageContext';
import { AuthShell } from './Login';

export default function Register() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [form, setForm] = useState({ username: '', email: '', password: '', confirm: '' });
  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.username.trim()) {
      toast.error(t('auth.nameRequired'));
      return;
    }
    if (form.password.length < 6) {
      toast.error(t('auth.pwShort'));
      return;
    }
    if (form.password !== form.confirm) {
      toast.error(t('auth.pwMismatch'));
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post('/auth/register', {
        username: form.username.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
      });
      localStorage.setItem('brandora_token', data.access_token);
      localStorage.setItem(
        'brandora_user',
        JSON.stringify({ username: data.username, email: form.email, is_admin: !!data.is_admin })
      );
      toast.success(t('auth.welcomeRegister', { username: data.username }));
      navigate('/dashboard');
    } catch (err) {
      toast.error(extractApiError(err, t('auth.registrationFailed')));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <SEO
        title="Start Free Trial | Morrow — AI Social Media Manager"
        description="Create your free Morrow account and try the AI social media manager: generate content, build a content calendar and auto-schedule posts across channels."
        path="/register"
      />
      <AuthShell
        title={t('auth.registerTitle')}
        sub={t('auth.registerSub')}
        alt={<>{t('auth.haveAccount')} <Link to="/login">{t('auth.loginBtn')}</Link></>}
      >
        <form onSubmit={handleSubmit} className="auth-form" noValidate>
          {/* Full name */}
          <div className="auth-field-group">
            <label className="auth-field-label" htmlFor="reg-name">
              {t('auth.fullName')}
            </label>
            <div className="auth-input-wrap">
              <span className="auth-input-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </span>
              <input
                id="reg-name"
                className="auth-input"
                type="text"
                value={form.username}
                onChange={set('username')}
                placeholder="Jane Smith"
                autoComplete="name"
                required
              />
            </div>
          </div>

          {/* Email */}
          <div className="auth-field-group">
            <label className="auth-field-label" htmlFor="reg-email">
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
                id="reg-email"
                className="auth-input"
                type="email"
                value={form.email}
                onChange={set('email')}
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </div>
          </div>

          {/* Password */}
          <div className="auth-field-group">
            <label className="auth-field-label" htmlFor="reg-password">
              {t('auth.password')}
            </label>
            <div className="auth-input-wrap">
              <span className="auth-input-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              </span>
              <input
                id="reg-password"
                className="auth-input"
                type={showPw ? 'text' : 'password'}
                value={form.password}
                onChange={set('password')}
                placeholder="Min. 6 characters"
                autoComplete="new-password"
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

          {/* Confirm password */}
          <div className="auth-field-group">
            <label className="auth-field-label" htmlFor="reg-confirm">
              {t('auth.confirmPassword')}
            </label>
            <div className="auth-input-wrap">
              <span className="auth-input-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </span>
              <input
                id="reg-confirm"
                className="auth-input"
                type={showConfirm ? 'text' : 'password'}
                value={form.confirm}
                onChange={set('confirm')}
                placeholder="Repeat password"
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className="auth-pw-toggle"
                onClick={() => setShowConfirm((v) => !v)}
                aria-label={showConfirm ? 'Hide password' : 'Show password'}
              >
                {showConfirm ? (
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
            id="register-submit-btn"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner-sm" />
                {t('common.loading')}
              </>
            ) : (
              t('auth.registerBtn')
            )}
          </button>

          <p className="auth-terms-note">
            By signing up you agree to our{' '}
            <Link to="/terms">Terms</Link> and{' '}
            <Link to="/privacy">Privacy Policy</Link>.
          </p>
        </form>
      </AuthShell>
    </>
  );
}
