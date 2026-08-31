import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import api from '../api/axios';
import SEO from '../components/SEO';
import { useLanguage } from '../i18n/LanguageContext';
import { AuthShell } from './Login';

export default function ResetPassword() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password.length < 6) {
      toast.error(t('auth.pwShort'));
      return;
    }
    if (password !== confirm) {
      toast.error(t('auth.pwMismatch'));
      return;
    }
    setLoading(true);
    try {
      await api.post('/auth/reset-password', { token, new_password: password });
      setDone(true);
      toast.success(t('auth.pwUpdated'));
      setTimeout(() => navigate('/login'), 2000);
      } catch (err) {
        const detail = err.response?.data?.detail;
        toast.error(detail || t('auth.resetError'));
      } finally {
      setLoading(false);
    }
  };

  return (
    <>
    <SEO
      title="Set New Password | BrandAura — AI Social Media Manager"
      description="Create a new password for your BrandAura account and get back to managing your social media content and schedule."
      path="/reset-password"
    />
    <AuthShell
      title={t('auth.resetTitle')}
      sub={token ? t('auth.resetSub') : t('auth.tokenRequired')}
      alt={<>{t('auth.backToSignIn')}</>}
    >
      {!done ? (
        <form onSubmit={handleSubmit}>
          <div className="auth-field">
            <input className="auth-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder=" " required />
            <label className="auth-label">{t('auth.newPassword')}</label>
            <div className="auth-input-border" />
          </div>
          <div className="auth-field">
            <input className="auth-input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder=" " required />
            <label className="auth-label">{t('auth.confirmPassword')}</label>
            <div className="auth-input-border" />
          </div>
          <button className="auth-submit" type="submit" disabled={loading || !token}>
            {loading ? <><span className="spinner-sm" /> {t('common.loading')}</> : t('auth.resetBtn')}
          </button>
        </form>
      ) : (
        <div className="auth-result">
          <div className="auth-result-icon">✓</div>
          <p className="auth-result-text">{t('auth.pwUpdatedSub')}</p>
        </div>
      )}
    </AuthShell>
    </>
  );
}
