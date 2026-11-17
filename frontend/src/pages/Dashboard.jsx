import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowDownRight, ArrowUpRight, CalendarClock, CalendarDays, FileText, Film,
  Minus, Share2, TrendingUp,
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
import { formatLocal, parseUtc } from '../utils/time';
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
          <img key={src} src={src} alt="" className={`dash-hero__slide dash-hero__slide--${i + 1} ${i === index ? 'is-active' : ''}`} loading="eager" fetchPriority={i === 0 ? 'high' : 'auto'} decoding="async" />
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

const ANALYTICS_PLATFORMS = ['facebook', 'instagram', 'linkedin', 'tiktok'];
const ACTIVITY_RING_R = 19;
const ACTIVITY_RING_C = 2 * Math.PI * ACTIVITY_RING_R;

function WeeklyInsights({ posts, activity, accounts, loading }) {
  const now = Date.now();
  const week = 7 * 24 * 60 * 60 * 1000;
  const start = now - week;
  const previousStart = now - 2 * week;
  const createdAt = (item) => parseUtc(item.created_at)?.getTime() ?? null;
  const recentPosts = posts.filter((post) => {
    const date = createdAt(post);
    return date !== null && date >= start && date <= now;
  });
  const previousPosts = posts.filter((post) => {
    const date = createdAt(post);
    return date !== null && date >= previousStart && date < start;
  });
  const recentContent = activity.filter((item) => {
    const date = createdAt(item);
    return ['content_generation', 'image_generation'].includes(item.type) && date !== null && date >= start && date <= now;
  }).length;
  const platformCounts = Object.fromEntries(ANALYTICS_PLATFORMS.map((platform) => [
    platform,
    recentPosts.reduce((count, post) => count + ((post.platforms || []).includes(platform) ? 1 : 0), 0),
  ]));
  const maxPlatformCount = Math.max(1, ...Object.values(platformCounts));
  const linked = new Set(accounts.filter((account) => account.connected).map((account) => account.platform));
  const growth = previousPosts.length
    ? Math.round(((recentPosts.length - previousPosts.length) / previousPosts.length) * 100)
    : null;
  const GrowthIcon = growth === null ? Minus : growth >= 0 ? ArrowUpRight : ArrowDownRight;
  const growthText = growth === null
    ? (recentPosts.length ? 'New activity' : 'No change yet')
    : `${growth > 0 ? '+' : ''}${growth}%`;

  return (
    <section className="dash-insights" aria-labelledby="dash-insights-title">
      <div className="dash-insights__heading">
        <div>
          <p className="dash-insights__eyebrow">Your workspace at a glance</p>
          <h2 id="dash-insights-title">Weekly progress</h2>
          <p className="dash-insights__sub">Activity from the last 7 days, based on your workspace data.</p>
        </div>
        <span className="dash-insights__spark" aria-hidden="true"><TrendingUp size={19} /></span>
      </div>

      <div className="dash-insights__stats" aria-live="polite">
        <article className="dash-insight-stat dash-insight-stat--posts">
          <span className="dash-insight-stat__label">Posts created</span>
          <strong>{loading ? '—' : recentPosts.length}</strong>
          <span className="dash-insight-stat__note">this week</span>
        </article>
        <article className="dash-insight-stat dash-insight-stat--content">
          <span className="dash-insight-stat__label">AI generations</span>
          <strong>{loading ? '—' : recentContent}</strong>
          <span className="dash-insight-stat__note">captions and images</span>
        </article>
        <article className="dash-insight-stat dash-insight-stat--growth">
          <span className="dash-insight-stat__label">Posting growth</span>
          <strong className={`dash-insight-stat__value ${loading ? 'is-neutral' : growth < 0 ? 'is-negative' : growth > 0 ? 'is-positive' : 'is-neutral'}`}>
            <GrowthIcon size={21} aria-hidden="true" />{loading ? '—' : growthText}
          </strong>
          <span className="dash-insight-stat__note">compared with the previous 7 days</span>
        </article>
      </div>

      <div className="dash-insights__platforms">
        <div className="dash-insights__platform-heading">
          <h3>Platform activity</h3>
          <span>Relative activity · last 7 days</span>
        </div>
        <div className="dash-platform-grid">
          {ANALYTICS_PLATFORMS.map((platform) => {
            const Icon = BRAND[platform];
            const count = platformCounts[platform];
            const progress = (count / maxPlatformCount) * 100;
            const gradientId = `activity-${platform}-gradient`;
            return (
              <article className={`dash-platform dash-platform--${platform}`} key={platform}>
                <div className="dash-platform__top">
                  <span className="dash-platform__identity">
                    <span className="dash-platform__icon"><Icon aria-hidden="true" /></span>
                    <span className="dash-platform__name">{platformLabel(platform)}</span>
                  </span>
                  <span className={`dash-platform__state ${linked.has(platform) ? 'is-connected' : 'is-disconnected'}`}>
                    {linked.has(platform) ? 'Connected' : 'Not connected'}
                  </span>
                </div>
                <div className="dash-platform__activity">
                  <div className="dash-platform__ring" role="img" aria-label={`${platformLabel(platform)}: ${count} posts this week`}>
                    <svg viewBox="0 0 48 48" aria-hidden="true">
                      <defs>
                        <linearGradient id={gradientId} x1="0" y1="1" x2="1" y2="0">
                          <stop offset="0%" stopColor="var(--accent-2)" />
                          <stop offset="100%" stopColor="var(--sidebar-accent)" />
                        </linearGradient>
                      </defs>
                      <circle className="dash-platform__ring-track" cx="24" cy="24" r={ACTIVITY_RING_R} />
                      <circle
                        className="dash-platform__ring-value"
                        cx="24"
                        cy="24"
                        r={ACTIVITY_RING_R}
                        style={{ '--activity-gradient': `url(#${gradientId})`, '--ring-c': ACTIVITY_RING_C, '--ring-offset': ACTIVITY_RING_C * (1 - progress / 100) }}
                      />
                    </svg>
                    <strong aria-hidden="true">{loading ? '—' : count}</strong>
                  </div>
                  <div className="dash-platform__activity-copy">
                    <strong>{count === 1 ? 'post' : 'posts'}</strong>
                    <span>{progress ? `${Math.round(progress)}% of platform peak` : 'No posts this week'}</span>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
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
        action={<Button as={Link} to="/profile#business-profile" variant="secondary">Manage</Button>}
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

          <WeeklyInsights posts={posts} activity={activity} accounts={safeAccounts} loading={workspaceLoading || loading} />

          <div className="dash-layout">
            <UpcomingCard posts={upcoming} allPosts={posts} loading={workspaceLoading} />
            <ChannelsCard
              accounts={safeAccounts}
              loading={loading}
              onConnect={handleConnect}
              onDisconnect={handleDisconnect}
            />
          </div>
        </div>
      </WorkspaceShell>

      <GuideBot onNavigate={navigate} />
    </>
  );
}
