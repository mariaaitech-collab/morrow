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
      localStorage.setItem('brandora_user', JSON.stringify({ username: data.username, email: form.email, is_admin: !!data.is_admin }));
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
      title="Start Free Trial | BrandAura — AI Social Media Manager"
      description="Create your free BrandAura account and try the AI social media manager: generate content, build a content calendar and auto-schedule posts across channels."
      path="/register"
    />
    <AuthShell
      title={t('auth.registerTitle')}
      sub={t('auth.registerSub')}
      alt={<>{t('auth.haveAccount')} <Link to="/login">{t('auth.loginBtn')}</Link></>}
    >
      <form onSubmit={handleSubmit}>
        <div className="auth-field">
          <input className="auth-input" type="text" value={form.username} onChange={set('username')} placeholder=" " required />
          <label className="auth-label">{t('auth.fullName')}</label>
          <div className="auth-input-border" />
        </div>
        <div className="auth-field">
          <input className="auth-input" type="email" value={form.email} onChange={set('email')} placeholder=" " required />
          <label className="auth-label">{t('auth.email')}</label>
          <div className="auth-input-border" />
        </div>
        <div className="auth-field">
          <input className="auth-input" type="password" value={form.password} onChange={set('password')} placeholder=" " required />
          <label className="auth-label">{t('auth.password')}</label>
          <div className="auth-input-border" />
        </div>
        <div className="auth-field">
          <input className="auth-input" type="password" value={form.confirm} onChange={set('confirm')} placeholder=" " required />
          <label className="auth-label">{t('auth.confirmPassword')}</label>
          <div className="auth-input-border" />
        </div>
        <button className="auth-submit" type="submit" disabled={loading}>
          {loading ? <><span className="spinner-sm" /> {t('common.loading')}</> : t('auth.registerBtn')}
        </button>
      </form>
    </AuthShell>
    </>
  );
}
