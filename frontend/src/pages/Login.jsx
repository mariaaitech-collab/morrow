import { useState, lazy, Suspense } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import api from '../api/axios';
import SEO from '../components/SEO';
import { useLanguage } from '../i18n/LanguageContext';

// AuthBackground is a Three.js scene (~600KB). Lazy-load it so the large 3D
// engine stays out of the public landing bundle — improves LCP / CWV.
const AuthBackground = lazy(() => import('../components/AuthBackground'));

export function AuthShell({ title, sub, children, alt }) {
  return (
    <>
      <Suspense fallback={null}>
        <AuthBackground />
      </Suspense>
      <div className="auth-wrap">
        <div className="auth-card">
          <div className="auth-brand">
            <span className="brand-mark">B</span>
            <b>Brand<span style={{ color: 'var(--primary)' }}>Aura</span></b>
          </div>
          <h1>{title}</h1>
          {sub && <p className="auth-sub">{sub}</p>}
          {children}
          {alt && <div className="auth-alt">{alt}</div>}
        </div>
      </div>
    </>
  );
}

export default function Login() {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post('/auth/login', { email: email.trim().toLowerCase(), password });
      localStorage.setItem('brandora_token', data.access_token);
      localStorage.setItem('brandora_user', JSON.stringify({ username: data.username, email, is_admin: !!data.is_admin }));
      toast.success(t('auth.welcomeBack', { username: data.username }));
      navigate('/dashboard');
    } catch (err) {
      if (err.response?.data?.detail) {
        toast.error(err.response.data.detail);
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
      title="Log In | BrandAura — AI Social Media Manager"
      description="Log in to BrandAura, the AI social media manager and content calendar that schedules, generates and analyzes your social media content."
      path="/login"
    />
    <AuthShell
      title={t('auth.loginTitle')}
      sub={t('auth.loginSub')}
      alt={<>{t('auth.noAccount')} <Link to="/register">{t('auth.getStarted')}</Link></>}
    >
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
        <div className="auth-field">
          <input
            className="auth-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder=" "
            required
          />
          <label className="auth-label">{t('auth.password')}</label>
          <div className="auth-input-border" />
        </div>
        <div style={{ textAlign: 'right', marginBottom: '1.4rem' }}>
          <Link className="auth-inline-link" to="/forgot-password">
            {t('auth.forgotLink')}
          </Link>
        </div>
        <button className="auth-submit" type="submit" disabled={loading}>
          {loading ? <><span className="spinner-sm" /> {t('common.loading')}</> : t('auth.loginBtn')}
        </button>
      </form>
    </AuthShell>
    </>
  );
}
