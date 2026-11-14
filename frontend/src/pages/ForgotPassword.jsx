import { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/axios';
import SEO from '../components/SEO';
import { useLanguage } from '../i18n/LanguageContext';
import { AuthShell } from './Login';

export default function ForgotPassword() {
  const { t } = useLanguage();
  const [email, setEmail] = useState('');
  const [result, setResult] = useState(null); // null | { ok: true } | { ok: false, message }
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    try {
      await api.post('/auth/forgot-password', { email: email.trim().toLowerCase() });
      setResult({ ok: true });
    } catch (err) {
      setResult({
        ok: false,
        message: t('auth.resetError'),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
    <SEO
      title="Reset Password | Morrow — AI Social Media Manager"
      description="Forgot your password? Reset it to get back into Morrow, your AI social media manager and content scheduling platform."
      path="/forgot-password"
    />
    <AuthShell
      title={t('auth.forgotTitle')}
      sub={t('auth.forgotSub')}
      alt={<>{t('auth.backToSignIn')}</>}
    >
      {result && result.ok && (
        <div className="reset-success-card">
          <div className="reset-check-wrap">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
          </div>
          <h2 className="reset-title">{t('auth.resetSentTitle')}</h2>
          <p className="reset-sub">
            {t('auth.resetSentSub')}
          </p>
          <div className="reset-actions">
            <Link to="/login" className="auth-submit" style={{ textDecoration: 'none', display: 'inline-flex' }}>
              {t('auth.backToSignIn')}
            </Link>
          </div>
        </div>
      )}

      {result && !result.ok && (
        <div className="auth-result auth-result-error">
          <div className="auth-result-icon auth-result-icon-error">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
            </svg>
          </div>
            <p className="auth-result-text">{result.message}</p>
          <Link to="/login" className="auth-submit" style={{ textDecoration: 'none', marginTop: '1.5rem', display: 'flex' }}>
            {t('auth.backToSignIn')}
          </Link>
        </div>
      )}

      {!result && (
        <form onSubmit={handleSubmit}>
          <div className="auth-field">
            <input
              className="auth-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder=" "
              required
            />
            <label className="auth-label">{t('auth.email')}</label>
            <div className="auth-input-border" />
          </div>
          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? <><span className="spinner-sm" /> {t('common.loading')}</> : t('auth.sendReset')}
          </button>
        </form>
      )}
    </AuthShell>
    </>
  );
}
