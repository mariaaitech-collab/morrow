import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation } from 'react-router-dom';
import {
  Bot, Building2, CalendarClock, CalendarDays, ChevronRight, CreditCard, History, LayoutDashboard,
  LogOut, LucideProvider, PanelLeftClose, PanelLeftOpen, PenLine, Plus, Settings, X,
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
  const [navTooltip, setNavTooltip] = useState(null);
  const sidebarRef = useRef(null);
  // Keep the workspace compact by default; the menu button can expand it on desktop.
  const [collapsed, setCollapsed] = useState(true);
  const toggleSidebar = () => {
    if (window.matchMedia('(max-width: 767px)').matches) {
      setMobileOpen(true);
      return;
    }
    setCollapsed((c) => !c);
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
    { label: t('nav.aiResponder'), to: '/ai-responder', icon: Bot, key: 'ai-responder' },
    { label: t('nav.history'), to: '/history', icon: History, key: 'history' },
    { label: t('profile.title'), to: '/profile', icon: Building2, key: 'profile' },
    ...(user?.is_admin || user?.email === 'maria.ai.tech@gmail.com'
      ? [{ label: t('nav.admin'), to: '/admin', icon: Settings, key: 'admin' }]
      : []),
  ];
  const current = navItems.find((item) => item.key === activeRoute) || navItems[0];

  const close = () => setMobileOpen(false);
  const showNavTooltip = (event, label) => {
    if (!collapsed || window.matchMedia('(max-width: 767px)').matches) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setNavTooltip({ label, top: rect.top + rect.height / 2 });
  };

  useEffect(() => {
    if (!collapsed) setNavTooltip(null);
  }, [collapsed]);

  useEffect(() => {
    if (!mobileOpen) return undefined;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const focusable = () => [...(sidebarRef.current?.querySelectorAll(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) || [])].filter((el) => el.getClientRects().length > 0);
    focusable()[0]?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setMobileOpen(false);
        return;
      }
      if (e.key !== 'Tab') return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || !sidebarRef.current?.contains(document.activeElement))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !sidebarRef.current?.contains(document.activeElement))) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
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
        <aside
          id="workspace-navigation"
          ref={sidebarRef}
          className={`m-sidebar ${mobileOpen ? 'is-open' : ''}`}
          aria-label={t('nav.mainNavigation')}
          role={mobileOpen ? 'dialog' : undefined}
          aria-modal={mobileOpen ? 'true' : undefined}
        >
          <div className="m-sidebar__head">
            <Link to="/dashboard" className="m-sidebar__brand" onClick={close} aria-label="Morrow">
              <Logo size={36} tagline />
            </Link>
            <IconButton className="m-sidebar__close" icon={X} label={t('nav.closeNavigation')} onClick={close} />
          </div>

          <Link
            to="/create"
            className="m-rail-create"
            onClick={close}
            onMouseEnter={(event) => showNavTooltip(event, t('nav.createPost'))}
            onMouseLeave={() => setNavTooltip(null)}
            onFocus={(event) => showNavTooltip(event, t('nav.createPost'))}
            onBlur={() => setNavTooltip(null)}
          >
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
                onClick={close}
                onMouseEnter={(event) => showNavTooltip(event, label)}
                onMouseLeave={() => setNavTooltip(null)}
                onFocus={(event) => showNavTooltip(event, label)}
                onBlur={() => setNavTooltip(null)}
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
              onMouseEnter={(event) => showNavTooltip(event, t('nav.billing'))}
              onMouseLeave={() => setNavTooltip(null)}
              onFocus={(event) => showNavTooltip(event, t('nav.billing'))}
              onBlur={() => setNavTooltip(null)}
              onClick={() => window.dispatchEvent(new CustomEvent('brandora:upgrade-required'))}
            >
              <span className="m-nav__tile"><CreditCard size={20} aria-hidden="true" /></span>
              <span className="m-nav__label">{t('nav.billing')}</span>
            </button>
            <button
              type="button"
              className="m-nav__link"
              onMouseEnter={(event) => showNavTooltip(event, t('nav.logout'))}
              onMouseLeave={() => setNavTooltip(null)}
              onFocus={(event) => showNavTooltip(event, t('nav.logout'))}
              onBlur={() => setNavTooltip(null)}
              onClick={onLogout}
            >
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
              aria-expanded={window.matchMedia('(max-width: 767px)').matches ? mobileOpen : !collapsed}
              aria-controls="workspace-navigation"
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
      {navTooltip && createPortal(
        <div
          key={navTooltip.label}
          className="m-nav-tooltip"
          style={{ top: navTooltip.top }}
          aria-hidden="true"
        >
          {navTooltip.label}
        </div>,
        document.body,
      )}
    </LucideProvider>
  );
}
