import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Bot, Building2, CalendarClock, CalendarDays, ChevronRight, CreditCard, History, LayoutDashboard,
  LogOut, LucideProvider, PanelLeftClose, PanelLeftOpen, PenLine, Plus, Settings, Users, X,
} from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import { Badge, IconButton, Logo } from './ui';
import LanguageSelector from './LanguageSelector';
import NotificationBell from './NotificationBell';
import './WorkspaceShell.css';

/**
 * App chrome: Canva-style purple icon rail + sticky topbar around every signed-in screen.
 *
 * `legacy` keeps screens that are not yet converted to the Morrow design on the
 * old dark canvas they were styled for. No screen uses it any more.
 */
export default function WorkspaceShell({ user, onLogout, children, active, legacy = false }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  // Desktop: full sidebar (labels) or slim icon rail. Remembered; tablets start collapsed.
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const saved = localStorage.getItem('morrow_sidebar_collapsed');
      if (saved !== null) return saved === '1';
    } catch { /* storage unavailable */ }
    return typeof window !== 'undefined' && window.innerWidth <= 1100;
  });
  const toggleSidebar = () => {
    if (window.matchMedia('(max-width: 767px)').matches) {
      setMobileOpen(true);
      return;
    }
    setCollapsed((c) => {
      try { localStorage.setItem('morrow_sidebar_collapsed', c ? '0' : '1'); } catch { /* ignore */ }
      return !c;
    });
  };
  const location = useLocation();
  const { t } = useLanguage();

  const currentPath = location.pathname.replace(/^\//, '') || 'dashboard';
  const activeRoute = active || currentPath;

  const navItems = [
    { label: t('nav.dashboard'), to: '/dashboard', icon: LayoutDashboard, key: 'dashboard' },
    { label: t('nav.createPost') || 'Create', to: '/create', icon: PenLine, key: 'create' },
    { label: t('nav.calendar'), to: '/calendar', icon: CalendarDays, key: 'calendar' },
    { label: t('nav.scheduler'), to: '/scheduler', icon: CalendarClock, key: 'scheduler' },
    { label: t('dashboard.channelsLabel') || 'Channels', to: '/channels', icon: Users, key: 'channels' },
    { label: t('nav.aiResponder'), to: '/ai-responder', icon: Bot, key: 'ai-responder' },
    { label: t('nav.history'), to: '/history', icon: History, key: 'history' },
    { label: t('profile.title'), to: '/profile', icon: Building2, key: 'profile' },
    ...(user?.is_admin || user?.email === 'maria.ai.tech@gmail.com'
      ? [{ label: t('nav.admin'), to: '/admin', icon: Settings, key: 'admin' }]
      : []),
  ];
  const current = navItems.find((item) => item.key === activeRoute) || navItems[0];

  const close = () => setMobileOpen(false);

  useEffect(() => {
    if (!mobileOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setMobileOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [mobileOpen]);

  const displayName = (user?.username || '').split('@')[0] || t('nav.workspaceUser');
  const businessName = user?.profile?.business_name || (user?.is_unlimited ? t('dashboard.proMember') : t('dashboard.freeWorkspace'));
  const credits = user?.is_unlimited ? t('nav.creditsUnlimited') : t('nav.credits', { count: user?.free_tokens ?? 0 });

  return (
    <LucideProvider size={18} strokeWidth={1.5}>
      <div className={`m-app ${collapsed ? 'is-collapsed' : ''}`}>
        <a className="m-skip-link" href="#main-content">{t('nav.skipToContent')}</a>

        {/* The scrim comes first so the drawer (same layer) paints above it. */}
        {mobileOpen && <button type="button" className="m-scrim" aria-label={t('nav.closeNavigation')} onClick={close} />}
        <aside className={`m-sidebar ${mobileOpen ? 'is-open' : ''}`} aria-label={t('nav.mainNavigation')}>
          <div className="m-sidebar__head">
            <Link to="/dashboard" className="m-sidebar__brand" onClick={close} aria-label="Morrow">
              <Logo size={36} tagline />
            </Link>
            <IconButton className="m-sidebar__close" icon={X} label={t('nav.closeNavigation')} onClick={close} />
          </div>

          <Link to="/create" className="m-rail-create" onClick={close} title={t('nav.createPost')}>
            <span className="m-rail-create__tile"><Plus size={22} strokeWidth={2} aria-hidden="true" /></span>
            <span className="m-nav__label">{t('nav.createPost')}</span>
          </Link>

          <nav className="m-nav" aria-label={t('dashboard.workspaceSection')}>
            {navItems.map(({ key, to, label, icon: Icon }) => (
              <Link
                key={key}
                to={to}
                className="m-nav__link"
                aria-current={activeRoute === key ? 'page' : undefined}
                title={label}
                onClick={close}
              >
                <span className="m-nav__tile"><Icon size={20} aria-hidden="true" /></span>
                <span className="m-nav__label">{label}</span>
              </Link>
            ))}
          </nav>

          <div className="m-sidebar__footer">
            <button
              type="button"
              className="m-nav__link"
              title={t('nav.billing')}
              onClick={() => window.dispatchEvent(new CustomEvent('brandora:upgrade-required'))}
            >
              <span className="m-nav__tile"><CreditCard size={20} aria-hidden="true" /></span>
              <span className="m-nav__label">{t('nav.billing')}</span>
            </button>
            <button type="button" className="m-nav__link" title={t('nav.logout')} onClick={onLogout}>
              <span className="m-nav__tile"><LogOut size={20} aria-hidden="true" /></span>
              <span className="m-nav__label">{t('nav.logout')}</span>
            </button>
          </div>
        </aside>

        <div className="m-main">
          <header className="m-topbar">
            <IconButton
              className="m-topbar__menu"
              icon={collapsed ? PanelLeftOpen : PanelLeftClose}
              label={collapsed ? t('nav.openNavigation') : t('nav.closeNavigation')}
              aria-expanded={!collapsed}
              onClick={toggleSidebar}
            />
            <nav className="m-breadcrumb" aria-label={t('nav.breadcrumb')}>
              <span>{t('dashboard.workspaceSection')}</span>
              <ChevronRight aria-hidden="true" />
              <span aria-current="page">{current?.label || t('nav.dashboard')}</span>
            </nav>
            <div className="m-topbar__actions">
              <Badge tone="highlight" className="m-topbar__credits">{credits}</Badge>
              <NotificationBell />
              <LanguageSelector />
              <div className="m-user">
                <span className="m-user__avatar" aria-hidden="true">{displayName.charAt(0).toUpperCase()}</span>
                <span className="m-user__text">
                  <span className="m-user__name">{displayName}</span>
                  <span className="m-user__meta">{businessName}</span>
                </span>
              </div>
            </div>
          </header>
          <main id="main-content" tabIndex={-1} className="m-content">
            {children}
          </main>
        </div>
      </div>
    </LucideProvider>
  );
}
