import { Link } from 'react-router-dom';
import { isAuthenticated } from '../auth';
import { useLanguage } from '../i18n/LanguageContext';
import LanguageSelector from './LanguageSelector';

function Navbar({ user, onLogout, active }) {
  const authed = isAuthenticated();
  const { t } = useLanguage();
  return (
    <nav className="navbar">
      <Link to={authed ? '/dashboard' : '/'} className="navbar-brand">
        <span className="brand-mark">B</span>
        Brand<span style={{ color: 'var(--primary)' }}>Aura</span>
      </Link>
      <div className="nav-links">
        {authed ? (
          <>
            <Link to="/dashboard" className={`nav-link ${active === 'dashboard' ? 'active' : ''}`}>
              {t('nav.dashboard')}
            </Link>
            <Link to="/scheduler" className={`nav-link ${active === 'scheduler' ? 'active' : ''}`}>
              {t('nav.scheduler')}
            </Link>
            <Link to="/calendar" className={`nav-link ${active === 'calendar' ? 'active' : ''}`}>
              {t('nav.calendar')}
            </Link>
            <Link to="/history" className={`nav-link ${active === 'history' ? 'active' : ''}`}>
              {t('nav.history')}
            </Link>
            {user?.is_admin && (
              <Link to="/admin" className={`nav-link ${active === 'admin' ? 'active' : ''}`}>
                {t('nav.admin')}
              </Link>
            )}
            <LanguageSelector />
            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: '0 0.5rem' }}>
              {user?.username}
            </span>
            <button className="btn btn-glass btn-sm" onClick={onLogout}>
              {t('nav.logout')}
            </button>
          </>
        ) : (
          <>
            <Link to="/about" className={`nav-link ${active === 'about' ? 'active' : ''}`}>
              {t('nav.about')}
            </Link>
            <LanguageSelector />
            <Link to="/login" className="btn btn-glass btn-sm">
              {t('nav.login')}
            </Link>
            <Link to="/register" className="btn btn-primary btn-sm">
              {t('nav.getStarted')}
            </Link>
          </>
        )}
      </div>
    </nav>
  );
}

export default Navbar;
