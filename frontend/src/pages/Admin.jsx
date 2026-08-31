import { useState } from 'react';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import Navbar from '../components/Navbar';
import { isAuthenticated } from '../auth';

export default function Admin({ user, onLogout }) {
  const [email, setEmail] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const { t } = useLanguage();

  const handleActivate = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const { data } = await api.post('/admin/activate-user', { email: email.trim().toLowerCase() });
      setResult({ ok: true, data });
      setEmail('');
    } catch (err) {
      setResult({
        ok: false,
        message: err.response?.data?.detail || t('admin.failed'),
      });
    } finally {
      setLoading(false);
    }
  };

  if (!isAuthenticated()) {
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <h1>{t('admin.required')}</h1>
          <p className="auth-sub">{t('admin.signIn')}</p>
        </div>
      </div>
    );
  }

  if (!user?.is_admin) {
    return (
      <div className="auth-wrap">
        <Navbar user={user} onLogout={onLogout} />
        <div className="auth-card">
          <h1>{t('admin.notAuthorized')}</h1>
          <p className="auth-sub">{t('admin.restricted')}</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <Navbar user={user} onLogout={onLogout} active="admin" />
      <div className="admin-page">
        <div className="admin-card">
          <h2>{t('admin.title')}</h2>
          <p className="admin-sub">
            {t('admin.sub')}
          </p>

          <form onSubmit={handleActivate} className="admin-form">
            <div className="auth-field">
              <input
                className="auth-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder=" "
                required
              />
              <label className="auth-label">{t('admin.emailLabel')}</label>
              <div className="auth-input-border" />
            </div>
            <button className="btn btn-primary btn-lg" type="submit" disabled={loading}>
              {loading ? <><span className="spinner-sm" /> {t('admin.activating')}</> : t('admin.activate')}
            </button>
          </form>

          {result && (
            <div className={`admin-result ${result.ok ? 'admin-result-ok' : 'admin-result-err'}`}>
              {result.ok ? (
                <>
                  <p><b>{result.data.message}</b></p>
                  <ul className="admin-status">
                    <li>{t('admin.plan')}: <b>{result.data.plan}</b></li>
                    <li>{t('admin.subscribed')}: <b>{result.data.subscribed ? t('common.yes') : t('common.no')}</b></li>
                    <li>{t('admin.accessActive')}: <b>{result.data.access_active ? t('common.yes') : t('common.no')}</b></li>
                    <li>{t('admin.daysRemaining')}: <b>{result.data.days_remaining}</b></li>
                  </ul>
                </>
              ) : (
                <p>{result.message}</p>
              )}
            </div>
          )}

          <p className="admin-note">
            {t('admin.tip')}
          </p>
        </div>
      </div>
    </>
  );
}
