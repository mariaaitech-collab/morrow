import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';

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

    const exchangeCode = async () => {
      try {
        console.log(`[CALLBACK] Sending code to backend for ${platform}...`);
        const { data } = await api.get(`/social/callback/${platform}`, {
          params: { code },
        });
        console.log(`[CALLBACK] Backend response:`, data);
        toast.success(t('callback.successBody'));
        setStatus(t('callback.successTitle'));
        setTimeout(() => navigate('/'), 2000);
      } catch (err) {
        console.error(`[CALLBACK] Backend callback failed:`, err);
        console.error(`[CALLBACK] Response:`, err.response?.status, err.response?.data);
        const detail = err.response?.data?.detail || err.message || t('callback.errorBody');
        toast.error(detail);
        setStatus(t('callback.errorBody'));
        setTimeout(() => navigate('/'), 3000);
      }
    };

    exchangeCode();
  }, [platform, navigate, t]);

  return (
    <>
      <nav className="navbar">
        <div className="navbar-brand">Brandora<span>Social</span></div>
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
