import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight, Bot, CalendarClock, CalendarDays, FileText, Film,
  Image as ImageIcon, LineChart, PenLine, Share2, Sparkles, TrendingUp, Users,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { FaFacebookF, FaInstagram, FaLinkedinIn, FaTiktok } from 'react-icons/fa';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import GuideBot from '../components/GuideBot';
import WorkspaceShell from '../components/WorkspaceShell';
import {
  Badge, Button, Card, CardHeader, EmptyState, PlatformTile,
  Skeleton, platformLabel,
} from '../components/ui';
import { formatLocal, isSameLocalDay, parseUtc, startOfWeek, timeAgo } from '../utils/time';
import campaign1 from '../assets/campaign-1.webp';
import campaign2 from '../assets/campaign-2.webp';
import campaign3 from '../assets/campaign-3.webp';
import campaign4 from '../assets/campaign-4.webp';
import './Dashboard.css';

const HERO_SLIDES = [campaign1, campaign2, campaign3, campaign4];
const HERO_INTERVAL_MS = 5000;

// Main dashboard card: campaign images cross-fade full-cover behind a dark purple gradient.
function HeroSlideshow() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduced || paused) return undefined;
    const id = setInterval(() => setIndex((i) => (i + 1) % HERO_SLIDES.length), HERO_INTERVAL_MS);
    return () => clearInterval(id);
  }, [paused]);
  return (
    <>
      <div className="dash-hero__slides" aria-hidden="true">
        {HERO_SLIDES.map((src, i) => (
          <img key={src} src={src} alt="" className={`dash-hero__slide dash-hero__slide--${i + 1} ${i === index ? 'is-active' : ''}`} loading={i === 0 ? 'eager' : 'lazy'} decoding="async" />
        ))}
      </div>
      <div className="dash-hero__dots" role="group" aria-label="Campaign images" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
        {HERO_SLIDES.map((src, i) => (
          <button key={src} type="button" className={`dash-hero__dot ${i === index ? 'is-active' : ''}`} aria-label={`Show campaign image ${i + 1}`} aria-pressed={i === index} onClick={() => setIndex(i)} />
        ))}
      </div>
    </>
  );
}

const POST_STATUS = {
  pending: { tone: 'pending', key: 'dashboard.statusPendingApproval', fallback: 'Pending Approval' },
  approved: { tone: 'approved', key: 'dashboard.statusApproved', fallback: 'Approved' },
  published: { tone: 'published', key: 'dashboard.statusPublished', fallback: 'Published' },
  draft: { tone: 'draft', key: 'dashboard.statusDrafts', fallback: 'Drafts' },
  failed: { tone: 'danger', key: 'dashboard.statusFailed', fallback: 'Failed' },
};
const FILTERS = ['all', 'pending', 'approved', 'published', 'draft'];

const ACTIVITY_TYPES = {
  content_generation: { icon: Sparkles, key: 'dashboard.generatedContent' },
  image_generation: { icon: ImageIcon, key: 'dashboard.imageProject' },
  scheduled_post: { icon: CalendarClock, key: 'dashboard.scheduledPost' },
  competitive_analysis: { icon: LineChart, key: 'dashboard.typeAnalysis' },
  market_insights: { icon: TrendingUp, key: 'dashboard.typeInsights' },
  auto_reply: { icon: Bot, key: 'dashboard.typeAutoReply' },
};

// Brand shortcut cards (the dashboard's one gradient moment besides the hero).
const TOOLS = [
  { key: 'create', to: '/create', icon: PenLine },
  { key: 'planner', to: '/calendar', icon: CalendarDays },
  { key: 'schedule', to: '/scheduler', icon: CalendarClock },
  { key: 'channels', to: '/channels', icon: Users },
];

function ToolCards() {
  const { t } = useLanguage();
  return (
    <nav className="dash-tools" aria-label={t('tools.label')}>
      {TOOLS.map(({ key, to, icon: Icon }) => (
        <Link key={key} to={to} className={`dash-tool dash-tool--${key}`}>
          <span className="dash-tool__icon"><Icon size={22} aria-hidden="true" /></span>
          <span className="dash-tool__text">
            <span className="dash-tool__title">{t(`tools.${key}Title`)}</span>
            <span className="dash-tool__desc">{t(`tools.${key}Desc`)}</span>
          </span>
          <ArrowRight className="dash-tool__arrow" size={18} aria-hidden="true" />
        </Link>
      ))}
    </nav>
  );
}

function ListSkeleton({ rows = 3 }) {
  return (
    <div className="dash-skeleton" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div className="dash-skeleton__row" key={i}>
          <Skeleton width={44} height={44} />
          <div className="dash-skeleton__lines">
            <Skeleton width="55%" />
            <Skeleton width="85%" height={12} />
          </div>
        </div>
      ))}
    </div>
  );
}

function PostThumb({ post }) {
  const [broken, setBroken] = useState(false);
  if (post.media_url && post.media_type !== 'video' && !broken) {
    return <img className="dash-thumb" src={post.media_url} alt="" loading="lazy" onError={() => setBroken(true)} />;
  }
  const Icon = post.media_type === 'video' ? Film : FileText;
  return <span className="dash-thumb dash-thumb--icon" aria-hidden="true"><Icon size={20} /></span>;
}

function PostRow({ post }) {
  const { t, language } = useLanguage();
  const [firstLine, ...rest] = (post.content || '').trim().split('\n');
  const caption = rest.join(' ').trim();
  const status = POST_STATUS[post.status] || POST_STATUS.pending;
  const slot = formatLocal(post.scheduled_at, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }, language);
  return (
    <li className="dash-post">
      <PostThumb post={post} />
      <div className="dash-post__body">
        <div className="dash-post__top">
          <p className="dash-post__title">{firstLine || t('dashboard.scheduledPost')}</p>
          <Badge tone={status.tone}>{t(status.key) !== status.key ? t(status.key) : status.fallback}</Badge>
        </div>
        {caption && <p className="dash-post__caption">{caption}</p>}
        <div className="dash-post__meta">
          <span className="dash-post__platforms">
            {(post.platforms || []).map((platform) => <PlatformTile key={platform} platform={platform} size="sm" />)}
          </span>
          <time className="dash-post__slot" dateTime={post.scheduled_at}>
            {slot}
          </time>
        </div>
      </div>
    </li>
  );
}

function UpcomingCard({ posts, allPosts, loading }) {
  const { t } = useLanguage();
  const [filter, setFilter] = useState('all');
  const label = (key) => {
    if (key === 'all') return t('dashboard.filterAll') !== 'dashboard.filterAll' ? t('dashboard.filterAll') : 'All';
    const s = POST_STATUS[key];
    return t(s.key) !== s.key ? t(s.key) : s.fallback;
  };
  const visible = filter === 'all' ? posts : allPosts.filter((p) => p.status === filter);
  const count = (key) => (key === 'all' ? posts.length : allPosts.filter((p) => p.status === key).length);
  return (
    <Card as="section" className="dash-card dash-card--purple" aria-labelledby="dash-upcoming-title">
      <CardHeader
        id="dash-upcoming-title"
        icon={CalendarClock}
        title={t('dashboard.upcomingPosts') || 'Upcoming Posts'}
        subtitle={t('dashboard.upcomingSubtitle') || 'Posts queued to go live'}
        action={<Button as={Link} to="/calendar" variant="secondary">{t('dashboard.viewCalendar') || 'Calendar'}</Button>}
      />
      <div className="dash-filters" role="group" aria-label="Filter posts by status">
        {FILTERS.map((key) => (
          <button
            key={key}
            type="button"
            className={`dash-filter dash-filter--${key} ${filter === key ? 'is-active' : ''}`}
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
          >
            {label(key)}<span className="dash-filter__count">{count(key)}</span>
          </button>
        ))}
      </div>
      {loading ? <ListSkeleton rows={3} /> : visible.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title={t('dashboard.noUpcomingTitle') || 'No scheduled posts'}
          description={t('dashboard.noUpcomingPosts') || 'Your queue is empty. Schedule your next campaign post now.'}
          action={{ label: t('dashboard.schedulePost') || 'Schedule Post', as: Link, to: '/scheduler' }}
        />
      ) : (
        <ul className="dash-posts">
          {visible.slice(0, 3).map((post) => <PostRow key={post.id} post={post} />)}
        </ul>
      )}
    </Card>
  );
}

function WeekPlanner({ posts, loading }) {
  const { t, language } = useLanguage();
  const today = new Date();
  const start = startOfWeek(today);
  const days = Array.from({ length: 7 }, (_, i) => {
    const day = new Date(start);
    day.setDate(start.getDate() + i);
    return day;
  });
  const end = new Date(days[6]);
  const range = `${start.toLocaleDateString(language, { month: 'short', day: 'numeric' })} – ${end.toLocaleDateString(language, { month: 'short', day: 'numeric' })}`;

  return (
    <Card as="section" className="dash-card dash-card--blue" aria-labelledby="dash-week-title">
      <CardHeader id="dash-week-title" icon={CalendarDays} title={t('dashboard.weeklyPlanner') || 'Week Planner'} subtitle={range} />
      {loading ? <Skeleton height={72} /> : (
        <ol className="dash-week">
          {days.map((day) => {
            const items = posts.filter((p) => {
              const at = parseUtc(p.scheduled_at);
              return at && isSameLocalDay(at, day);
            });
            const isToday = isSameLocalDay(day, today);
            return (
              <li
                key={day.toISOString()}
                className={`dash-day ${isToday ? 'is-today' : ''}`}
                aria-current={isToday ? 'date' : undefined}
                aria-label={`${day.toLocaleDateString(language, { weekday: 'long', month: 'long', day: 'numeric' })}: ${items.length}`}
              >
                <span className="dash-day__name" aria-hidden="true">{day.toLocaleDateString(language, { weekday: 'short' })}</span>
                <span className="dash-day__num" aria-hidden="true">{day.getDate()}</span>
                <span className="dash-day__dots" aria-hidden="true">
                  {items.slice(0, 3).map((p) => <i key={p.id} className={`dash-dot dash-dot--${['published', 'failed'].includes(p.status) ? p.status : 'pending'}`} />)}
                </span>
              </li>
            );
          })}
        </ol>
      )}
      <ul className="dash-legend">
        <li><i className="dash-dot dash-dot--published" aria-hidden="true" />{t('dashboard.statusPublished') || 'Published'}</li>
        <li><i className="dash-dot dash-dot--pending" aria-hidden="true" />{t('dashboard.scheduledStatus') || 'Scheduled'}</li>
        <li><i className="dash-dot dash-dot--failed" aria-hidden="true" />{t('dashboard.statusFailed') || 'Failed'}</li>
      </ul>
    </Card>
  );
}

const BRAND = {
  facebook: FaFacebookF,
  instagram: FaInstagram,
  linkedin: FaLinkedinIn,
  tiktok: FaTiktok,
};
const RING_R = 34;
const RING_C = 2 * Math.PI * RING_R;

function ChannelsCard({ accounts, loading, onConnect, onDisconnect }) {
  const { t } = useLanguage();
  const connected = accounts.filter((a) => a.connected).length;
  const total = accounts.length || 4;
  const pct = total ? connected / total : 0;
  const summary = t('dashboard.channelsSummary', { connected, total });
  return (
    <Card as="section" className="dash-channels dash-card dash-card--navy" aria-labelledby="dash-channels-title">
      <CardHeader
        id="dash-channels-title"
        icon={Share2}
        title={t('dashboard.channelsLabel') || 'Connected Channels'}
        action={<Button as={Link} to="/channels" variant="secondary">Manage</Button>}
      />
      {loading ? <ListSkeleton rows={4} /> : (
        <>
          <div className="dash-ch-summary">
            <div className="dash-ch-ring" role="img" aria-label={summary}>
              <svg viewBox="0 0 80 80" aria-hidden="true">
                <circle className="dash-ch-ring__track" cx="40" cy="40" r={RING_R} />
                <circle
                  className="dash-ch-ring__value"
                  cx="40"
                  cy="40"
                  r={RING_R}
                  style={{ '--ring-c': RING_C, '--ring-offset': RING_C * (1 - pct) }}
                />
              </svg>
              <span className="dash-ch-ring__num" aria-hidden="true">{connected}<small>/{total}</small></span>
            </div>
            <div className="dash-ch-summary__text">
              <p className="dash-ch-summary__title">{summary}</p>
              <div className="dash-ch-stack" aria-hidden="true">
                {accounts.map((a) => {
                  const Icon = BRAND[a.platform];
                  return Icon ? <span key={a.platform} className={`dash-ch-mini dash-ch-brand--${a.platform} ${a.connected ? '' : 'is-off'}`}><Icon /></span> : null;
                })}
              </div>
            </div>
          </div>
          <ul className="dash-channel-list">
            {accounts.map((account, i) => {
              const Icon = BRAND[account.platform];
              return (
                <li className={`dash-channel ${account.connected ? 'is-on' : ''}`} key={account.platform} style={{ '--i': i }}>
                  <span className={`dash-ch-tile dash-ch-brand--${account.platform}`} aria-hidden="true">
                    {Icon ? <Icon /> : <PlatformTile platform={account.platform} size="sm" />}
                  </span>
                  <div className="dash-channel__text">
                    <p className="dash-channel__name">{platformLabel(account.platform)}</p>
                    {account.connected ? (
                      <p className="dash-channel__status dash-channel__status--on">
                        <span className="dash-channel__dot" aria-hidden="true" />
                        {account.account_name || t('dashboard.connectedStatus') || 'Connected'}
                      </p>
                    ) : (
                      <p className="dash-channel__status">{t('dashboard.awaitingConnection') || 'Not connected'}</p>
                    )}
                  </div>
                  <button
                    type="button"
                    role="switch"
                    className="m-switch"
                    aria-checked={!!account.connected}
                    aria-label={`${platformLabel(account.platform)}: ${account.connected ? (t('common.disconnect') || 'Disconnect') : (t('common.connect') || 'Connect')}`}
                    onClick={() => (account.connected ? onDisconnect(account.platform) : onConnect(account.platform))}
                  />
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Card>
  );
}

export default function Dashboard({ user, onLogout }) {
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activity, setActivity] = useState([]);
  const [posts, setPosts] = useState([]);
  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [me, setMe] = useState(user);
  const { t, language } = useLanguage();

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
      setAccounts(Array.isArray(data) ? data : []);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || t('dashboard.loadAccountsError');
      toast.error(detail);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
    Promise.all([
      api.get('/user/history'),
      api.get('/calendar/posts'),
    ]).then(([historyResponse, postsResponse]) => {
      setActivity(historyResponse.data?.items || []);
      setPosts(Array.isArray(postsResponse.data) ? postsResponse.data : postsResponse.data?.posts || []);
    }).catch((err) => {
      if (err.response?.status !== 401) console.error('Workspace preview load failed:', err);
    }).finally(() => setWorkspaceLoading(false));
  }, []);

  const handleConnect = async (platform) => {
    try {
      const { data } = await api.get(`/social/connect/${platform}`, { withCredentials: true }); // lets the API set the TikTok state cookie
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

  const upcoming = useMemo(() => {
    const now = new Date();
    return posts
      .filter((post) => post.status !== 'published' && (parseUtc(post.scheduled_at) || 0) >= now)
      .sort((a, b) => parseUtc(a.scheduled_at) - parseUtc(b.scheduled_at));
  }, [posts]);


  const displayName = (me?.username || '').split('@')[0];

  return (
    <>
      <WorkspaceShell user={me} onLogout={onLogout} active="dashboard">
        <div className="m-page dash">
          <section className="dash-hero" aria-labelledby="dash-hero-title">
            <HeroSlideshow />
            <p className="dash-hero__tagline">The market of tomorrow</p>
            <p className="dash-hero__eyebrow">{new Date().toLocaleDateString(language, { weekday: 'long', month: 'long', day: 'numeric' })}</p>
            <h1 className="dash-hero__title" id="dash-hero-title">
              {displayName ? `${t('dashboard.welcome')}, ${displayName}` : t('dashboard.welcome')}
            </h1>
            <p className="dash-hero__sub">{t('dashboard.todaySubtitle')}</p>
          </section>

          <ToolCards />

          <div className="dash-layout">
            <div className="dash-col">
              <UpcomingCard posts={upcoming} allPosts={posts} loading={workspaceLoading} />
              <WeekPlanner posts={posts} loading={workspaceLoading} />
            </div>
            <div className="dash-col">
              <ChannelsCard
                accounts={safeAccounts}
                loading={loading}
                onConnect={handleConnect}
                onDisconnect={handleDisconnect}
              />
            </div>
          </div>
        </div>
      </WorkspaceShell>

      <GuideBot onNavigate={navigate} />
    </>
  );
}
