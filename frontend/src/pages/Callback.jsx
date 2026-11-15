import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useLanguage } from '../i18n/LanguageContext';
import { Logo } from '../components/ui';

function Callback() {
  const { platform } = useParams();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [status, setStatus] = useState(t('callback.connecting'));
  const hasRun = useRef(false);

  useEffect(() => {
    if (hasRun.current) return;
    hasRun.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const error = params.get('error');

    console.log(`[CALLBACK] Platform: ${platform}, Code: ${code ? 'YES' : 'NO'}, Error: ${error || 'none'}`);

    if (error) {
      console.error(`[CALLBACK] OAuth error from ${platform}:`, error);
      toast.error(t('callback.errorBody'));
      setStatus(t('callback.errorBody'));
      setTimeout(() => navigate('/'), 3000);
      return;
    }

    if (!code) {
      console.error(`[CALLBACK] No authorization code received for ${platform}`);
      toast.error(t('callback.errorBody'));
      setStatus(t('callback.errorBody'));
      setTimeout(() => navigate('/'), 3000);
      return;
    }

    // Full page-level navigation to the backend callback. The backend exchanges
    // the code, saves the account, and issues a 302 RedirectResponse back to
    // /dashboard?connection_success=... which the browser follows directly —
    // so the address bar lands on the Dashboard with the result params. The
    const base = import.meta.env.VITE_API_BASE_URL || '/api';
    // The backend resolves the owner from single-use OAuth state, so no session
    // credential is included in the callback URL.
    const state = params.get('state') || '';
    const callbackUrl =
      `${base}/social/callback/${platform}` +
      `?code=${encodeURIComponent(code)}` +
      `&state=${encodeURIComponent(state)}`;
    console.log(`[CALLBACK] Navigating to backend callback for ${platform}`);
    window.location.href = callbackUrl;
  }, [platform, navigate, t]);

  return (
    <>
      <nav className="navbar">
        <div className="navbar-brand"><Logo size={32} /></div>
      </nav>
      <div className="auth-container">
        <div className="auth-card" style={{ textAlign: 'center' }}>
          <h1>{platform?.charAt(0).toUpperCase() + platform?.slice(1)}</h1>
          <p className="subtitle" style={{ marginTop: '1rem' }}>{status}</p>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '1rem' }}>
            {t('callback.redirecting')}
          </p>
        </div>
      </div>
    </>
  );
}

export default Callback;
