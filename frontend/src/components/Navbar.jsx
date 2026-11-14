import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import { isAuthenticated } from '../auth';
import { useLanguage } from '../i18n/LanguageContext';
import LanguageSelector from './LanguageSelector';
import { Logo } from './ui';

function Navbar({ user, onLogout, active }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const authed = isAuthenticated();
  const { t } = useLanguage();
  const unlimited = !!user?.is_unlimited;
  const tokens = unlimited ? null : (user?.free_tokens ?? 0);
  const badgeClass = unlimited
    ? 'token-badge'
    : tokens <= 0
    ? 'token-badge token-badge-empty'
    : tokens <= 5
    ? 'token-badge token-badge-low'
    : 'token-badge';
  const openPricing = () => window.dispatchEvent(new CustomEvent('brandora:upgrade-required'));
  return (
    <nav className="navbar">
      <Link to={authed ? '/dashboard' : '/'} className="navbar-brand" aria-label="Morrow">
        <Logo size={32} />
      </Link>
      {authed && (
        <button className="nav-menu-toggle" onClick={() => setMenuOpen((open) => !open)} aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen}>
          {menuOpen ? <X size={19} /> : <Menu size={19} />}
        </button>
      )}
      <div className={`nav-links ${menuOpen ? 'nav-links-open' : ''}`}>
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
            {user?.email === 'maria.ai.tech@gmail.com' && (
              <Link to="/admin" className={`nav-link ${active === 'admin' ? 'active' : ''}`}>
                {t('nav.admin')}
              </Link>
            )}
            <LanguageSelector />
            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', padding: '0 0.5rem' }}>
              {user?.username}
            </span>
            <span
              className={badgeClass}
              title={unlimited ? 'Unlimited tokens' : 'Tokens left'}
              onClick={tokens === 0 ? openPricing : undefined}
            >
              {unlimited ? '∞ credits' : `${tokens} credits`}
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
