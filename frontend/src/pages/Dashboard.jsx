import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { PenLine, CalendarClock, Wand2, BarChart3, CalendarDays, Crown } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import Navbar from '../components/Navbar';
import ContentGenerator from '../components/ContentGenerator';
import GuideBot from '../components/GuideBot';

const EASE = [0.25, 1, 0.5, 1];
const MAUVE = '#B8A1A8';

function ToolCard({ title, desc, icon, grad, shadow, iconColor, borderColor, alwaysGrad, to, onClick }) {
  const { t } = useLanguage();
  const card = (
    <motion.div
      whileHover={{ y: -10 }}
      transition={{ duration: 0.5, ease: EASE }}
      className={`group relative h-full overflow-hidden rounded-3xl border ${borderColor} bg-[#141414] p-7 transition-all duration-500 ease-[cubic-bezier(0.25,1,0.5,1)] hover:border-transparent ${shadow}`}
    >
      {/* Persistent "active" brand tint */}
      {alwaysGrad && (
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-[#D6588A] to-[#7A2B52] opacity-10" />
      )}
      {/* Vibrant hover reveal */}
      <div
        className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${grad} opacity-0 transition-opacity duration-500 ease-[cubic-bezier(0.25,1,0.5,1)] group-hover:opacity-100`}
      />
      <div className="relative z-10 flex h-full flex-col">
        <div
          className={`mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/5 ${iconColor} transition-all duration-500 group-hover:border-white/30 group-hover:bg-white/10 group-hover:text-white group-hover:[filter:drop-shadow(0_2px_10px_rgba(255,255,255,0.6))]`}
        >
          {icon}
        </div>
        <h3 className="text-lg font-semibold text-white transition-all duration-500 group-hover:[text-shadow:0_2px_12px_rgba(255,255,255,0.5)]">
          {title}
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-[#B8A1A8] transition-colors duration-500 group-hover:text-white">
          {desc}
        </p>
        <span className="mt-auto pt-6 text-sm font-semibold text-[#B8A1A8] transition-colors duration-500 group-hover:text-white">
          {t('common.open')} &rarr;
        </span>
      </div>
    </motion.div>
  );
  if (to) return <Link to={to} className="block h-full">{card}</Link>;
  return (
    <button type="button" onClick={onClick} className="block h-full w-full text-left">
      {card}
    </button>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-2xl border border-[#2A2A2A] bg-white/[0.03] p-6">
      <div className="text-sm" style={{ color: MAUVE }}>{label}</div>
      <div className="mt-2 text-3xl font-bold text-white">{value}</div>
    </div>
  );
}

function Dashboard({ user, onLogout }) {
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sub, setSub] = useState(null);
  const [me, setMe] = useState(user);
  const { t } = useLanguage();

  // Token + profile handshake: validate the JWT against the backend on mount
  // and pull the fresh user profile. A 401 means the session is dead -> log
  // out cleanly; a 402 means the trial ended -> show the upgrade modal.
  useEffect(() => {
    let cancelled = false;
    const validateSession = async () => {
      try {
        const { data } = await api.get('/auth/me');
        if (!cancelled) setMe({ ...user, ...data });
      } catch (err) {
        const status = err.response?.status;
        if (status === 401) {
          onLogout();
          return;
        }
        if (status === 402) {
          window.dispatchEvent(new CustomEvent('brandora:upgrade-required'));
        }
      }
    };
    validateSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchAccounts = async () => {
    try {
      const { data } = await api.get('/social/accounts');
      setAccounts(data);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || t('dashboard.loadAccountsError');
      toast.error(detail);
      console.error('Fetch accounts error:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchSub = async () => {
    try {
      const { data } = await api.get('/billing/status');
      setSub(data);
    } catch {
      /* non-fatal */
    }
  };

  useEffect(() => {
    fetchAccounts();
    fetchSub();
  }, []);

  // OAuth callback landing: the backend redirects here with
  // ?connection_success=true&platform=... after connecting a social account.
  // Show a premium toast, refresh the connected accounts live, then strip the
  // query params so the toast never re-fires on reload.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get('connection_success');
    if (status === null) return;

    if (status === 'true') {
      toast.success(t('dashboard.platformConnected'), {
        duration: 5000,
      });
    } else {
      toast.error(t('dashboard.connectionFailed'), { duration: 5000 });
    }

    fetchAccounts();

    const url = new URL(window.location.href);
    url.searchParams.delete('connection_success');
    url.searchParams.delete('platform');
    url.searchParams.delete('error');
    window.history.replaceState({}, '', url.pathname + url.search);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scrollToStudio = () => {
    document.getElementById('content-studio')?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleConnect = async (platform) => {
    try {
      const { data } = await api.get(`/social/connect/${platform}`);
      if (data.auth_url) {
        window.location.href = data.auth_url;
      } else {
        toast.error(t('dashboard.noAuthUrl', { platform }));
      }
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || t('dashboard.connectFailed', { platform });
      toast.error(detail);
    }
  };

  const handleDisconnect = async (platform) => {
    try {
      await api.delete(`/social/disconnect/${platform}`);
      toast.success(t('dashboard.disconnected', { platform }));
      fetchAccounts();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('dashboard.disconnectFailed', { platform }));
    }
  };

  const safeAccounts = Array.isArray(accounts) ? accounts : [];
  const connectedCount = safeAccounts.filter((a) => a.connected).length;

  const TOOLS = [
    {
      key: 'ContentStudio',
      icon: <PenLine size={22} />,
      grad: 'from-pink-500/80 to-rose-500/80',
      shadow: 'hover:shadow-[0_20px_50px_-12px_rgba(236,72,153,0.6)]',
      iconColor: 'text-[#D6588A]',
      borderColor: 'border-pink-500/20',
      onClick: scrollToStudio,
    },
    {
      key: 'AutoScheduler',
      icon: <CalendarClock size={22} />,
      grad: 'from-[#D6588A] to-[#7A2B52]',
      shadow: 'hover:shadow-[0_20px_50px_-12px_rgba(214,88,138,0.7)]',
      iconColor: 'text-cyan-300',
      borderColor: 'border-cyan-500/20',
      alwaysGrad: true,
      to: '/scheduler',
    },
    {
      key: 'Calendar',
      icon: <CalendarDays size={22} />,
      grad: 'from-violet-500/80 to-fuchsia-500/80',
      shadow: 'hover:shadow-[0_20px_50px_-12px_rgba(139,92,246,0.6)]',
      iconColor: 'text-violet-400',
      borderColor: 'border-violet-500/20',
      to: '/calendar',
    },
    {
      key: 'AIImage',
      icon: <Wand2 size={22} />,
      grad: 'from-fuchsia-500/80 to-purple-500/80',
      shadow: 'hover:shadow-[0_20px_50px_-12px_rgba(217,70,239,0.6)]',
      iconColor: 'text-fuchsia-400',
      borderColor: 'border-fuchsia-500/20',
      onClick: scrollToStudio,
    },
    {
      key: 'History',
      icon: <BarChart3 size={22} />,
      grad: 'from-violet-500/80 to-indigo-500/80',
      shadow: 'hover:shadow-[0_20px_50px_-12px_rgba(139,92,246,0.6)]',
      iconColor: 'text-purple-400',
      borderColor: 'border-purple-500/20',
      to: '/history',
    },
  ];

  return (
    <>
      <Navbar user={user} onLogout={onLogout} active="dashboard" />
      <div className="dashboard">
        {/* Greeting */}
        <div className="mb-10">
          <h2 className="text-3xl font-bold text-white">
            {t('dashboard.welcome')}{me?.username && ', '}
            {me?.username && (
              <span className="bg-gradient-to-r from-[#D6588A] to-[#E8558C] bg-clip-text text-transparent">
                {me.username}
              </span>
            )}
          </h2>
          <p className="mt-2" style={{ color: MAUVE }}>{t('dashboard.tagline')}</p>
        </div>

        {/* Free-trial / Pro paywall status bar */}
        {sub && (
          <div className="trial-bar">
            {sub.is_pro ? (
              <>
                <span className="trial-badge pro"><span className="dot" /><Crown size={14} /> {t('dashboard.proMember')}</span>
                <span className="trial-msg">{t('dashboard.fullAccess')}</span>
              </>
            ) : sub.is_trialing ? (
              <>
                <span className="trial-badge"><span className="dot" /> {t('dashboard.freeTrial', { days: sub.days_remaining })}</span>
                <span className="trial-msg">{t('dashboard.enjoyTrial')}</span>
                <button className="trial-upgrade-btn" onClick={() => window.dispatchEvent(new CustomEvent('brandora:upgrade-required'))}>{t('dashboard.upgradeBtn')}</button>
              </>
            ) : (
              <>
                <span className="trial-badge expired"><span className="dot" /> {t('dashboard.trialEnded')}</span>
                <span className="trial-msg">{t('dashboard.trialExpiredMsg')}</span>
                <button className="trial-upgrade-btn" onClick={() => window.dispatchEvent(new CustomEvent('brandora:upgrade-required'))}>{t('dashboard.upgradeProExpired')}</button>
              </>
            )}
          </div>
        )}

        {/* Interactive tool cards with ambient brand glow */}
        <div className="relative">
          <div
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 -z-0 h-[380px] w-[760px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-[#D6588A] to-[#7A2B52] opacity-[0.13] blur-[120px]"
          />
          <div className="relative z-10 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {TOOLS.map((tool) => (
              <ToolCard
                key={tool.key}
                title={t(`dashboard.tool${tool.key}Title`)}
                desc={t(`dashboard.tool${tool.key}Desc`)}
                {...tool}
              />
            ))}
          </div>
        </div>

        {/* Metrics */}
        <div className="mt-10 grid grid-cols-1 gap-5 sm:grid-cols-3">
          <Metric label={t('dashboard.metricLive')} value={connectedCount} />
          <Metric label={t('dashboard.metricAvailable')} value={safeAccounts.length} />
          <Metric label={t('dashboard.metricAwaiting')} value={safeAccounts.length - connectedCount} />
        </div>

        {/* Social accounts */}
        <div className="mt-12">
          <h3 className="mb-4 text-xl font-semibold text-white">{t('dashboard.socialAccounts')}</h3>
          {loading ? (
            <p style={{ color: MAUVE }}>{t('common.loading')}</p>
          ) : (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
               {safeAccounts.map((account) => (
                <div
                  key={account.platform}
                  className="flex items-center gap-4 rounded-2xl border border-[#2A2A2A] bg-white/[0.03] p-5 transition-all duration-300 hover:border-[#D6588A]/50"
                >
                  <div className={`social-icon ${account.platform}`}>
                    <span className="text-lg font-bold uppercase">{account.platform.charAt(0)}</span>
                  </div>
                  <div className="flex-1">
                    <h4 className="font-medium capitalize text-white">{account.platform}</h4>
                    <div
                      className="text-sm"
                      style={{ color: account.connected ? '#3ecf8e' : MAUVE }}
                    >
                      {account.connected ? t('dashboard.live', { name: account.account_name }) : t('dashboard.awaitingConnection')}
                    </div>
                  </div>
                  {account.connected ? (
                    <button
                      onClick={() => handleDisconnect(account.platform)}
                      className="btn btn-sm rounded-xl border border-[#7A2B52] bg-transparent text-[#B8A1A8] transition-all duration-200 hover:bg-[#7A2B52]/15 active:scale-95"
                    >
                      {t('common.disconnect')}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleConnect(account.platform)}
                      className="btn btn-sm rounded-xl border-0 bg-gradient-to-r from-[#D6588A] to-[#7A2B52] text-white transition-all duration-200 hover:shadow-[0_0_22px_rgba(214,88,138,0.45)] active:scale-95"
                    >
                      {t('common.connect')}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Content Studio */}
        <section id="content-studio" className="mt-16 scroll-mt-28">
          <ContentGenerator accounts={safeAccounts} />
        </section>
      </div>

      <GuideBot onNavigate={navigate} />
    </>
  );
}

export default Dashboard;
