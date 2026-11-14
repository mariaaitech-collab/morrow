import { useEffect, useState } from 'react';
import { ArrowUpRight, CheckCircle2, Globe, Shield, Sparkles } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import WorkspaceShell from '../components/WorkspaceShell';
import { Badge, Button, Card, PageHeader, PlatformTile, platformLabel, Skeleton } from '../components/ui';

const PLATFORM_DETAILS = {
  instagram: {
    description: 'Auto-publish images, reels, and carousels directly to your Instagram Professional account.',
    capabilities: ['Direct publishing', 'Hashtag analytics', 'AI auto-responder', 'Story scheduling'],
  },
  facebook: {
    description: 'Publish updates, photos, and links to your Facebook business pages and track engagement.',
    capabilities: ['Page post sync', 'Multi-image posts', 'Comment replies', 'Audience insights'],
  },
  linkedin: {
    description: 'Share professional thought leadership, company news, and industry articles to your profile or page.',
    capabilities: ['Professional reach', 'Article scheduling', 'Network engagement', 'PDF carousels'],
  },
  tiktok: {
    description: 'Plan, schedule, and optimize viral short-form video content directly for your TikTok audience.',
    capabilities: ['Short video publishing', 'Sound trends', 'Caption generation', 'Viral tracking'],
  },
};

export default function Channels({ user, onLogout }) {
  const { t } = useLanguage();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(null);

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

    // Check query params if redirected back from OAuth
    const params = new URLSearchParams(window.location.search);
    const status = params.get('connection_success');
    if (status !== null) {
      if (status === 'true') {
        toast.success(t('dashboard.platformConnected') || 'Channel connected successfully!');
      } else {
        toast.error(t('dashboard.connectionFailed') || 'Could not connect channel.');
      }
      const url = new URL(window.location.href);
      url.searchParams.delete('connection_success');
      url.searchParams.delete('platform');
      url.searchParams.delete('error');
      window.history.replaceState({}, '', url.pathname + url.search);
      fetchAccounts();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConnect = async (platform) => {
    setActing(platform);
    try {
      const { data } = await api.get(`/social/connect/${platform}`, { withCredentials: true }); // lets the API set the TikTok state cookie
      if (data.auth_url) {
        window.location.href = data.auth_url;
      } else {
        toast.error(t('dashboard.noAuthUrl', { platform }) || `No auth URL for ${platform}`);
        setActing(null);
      }
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || t('dashboard.connectFailed', { platform });
      toast.error(detail);
      setActing(null);
    }
  };

  const handleDisconnect = async (platform) => {
    setActing(platform);
    try {
      await api.delete(`/social/disconnect/${platform}`);
      toast.success(t('dashboard.disconnected', { platform }) || `${platform} disconnected`);
      fetchAccounts();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('dashboard.disconnectFailed', { platform }));
    } finally {
      setActing(null);
    }
  };

  const connectedCount = accounts.filter((a) => a.connected).length;

  return (
    <WorkspaceShell user={user} onLogout={onLogout} active="channels">
      <div className="m-page">
        <PageHeader
          title={t('dashboard.channelsLabel') || 'Connected Channels'}
          subtitle={t('dashboard.channelsSummary', { connected: connectedCount, total: accounts.length || 4 })}
          actions={
            <Badge tone="accent" icon={Shield}>
              {connectedCount > 0 ? `${connectedCount} channels active` : 'Ready to connect'}
            </Badge>
          }
        />

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {[1, 2, 3, 4].map((i) => (
              <Card key={i} className="p-6">
                <Skeleton width="40%" height={24} />
                <Skeleton width="80%" height={16} className="mt-3" />
                <Skeleton width="100%" height={40} className="mt-6" />
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {accounts.map((account) => {
              const info = PLATFORM_DETAILS[account.platform] || {
                description: 'Manage and sync your content automatically.',
                capabilities: ['Automated publishing', 'AI generation'],
              };
              const isWorking = acting === account.platform;

              return (
                <Card key={account.platform} className="p-6 flex flex-col justify-between hover:shadow-md transition-shadow">
                  <div>
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <PlatformTile platform={account.platform} size="md" />
                        <div>
                          <h3 className="font-semibold text-base m-0 leading-tight">
                            {platformLabel(account.platform)}
                          </h3>
                          <p className="text-xs text-muted-foreground mt-0.5 m-0">
                            {account.connected
                              ? (account.account_name || 'Connected Account')
                              : 'Not connected'}
                          </p>
                        </div>
                      </div>
                      <Badge tone={account.connected ? 'success' : 'default'} dot={account.connected}>
                        {account.connected ? 'Active' : 'Offline'}
                      </Badge>
                    </div>

                    <p className="text-xs text-muted-foreground mt-4 mb-4 leading-relaxed">
                      {info.description}
                    </p>

                    <div className="flex flex-wrap gap-1.5 mb-5">
                      {info.capabilities.map((cap) => (
                        <span
                          key={cap}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-[var(--surface-2)] text-[var(--text-muted)]"
                        >
                          <CheckCircle2 size={11} className="text-[var(--accent)]" />
                          {cap}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="pt-4 border-t border-[var(--border)] flex items-center justify-between">
                    <span className="text-xs text-[var(--text-muted)] flex items-center gap-1">
                      <Globe size={13} />
                      OAuth 2.0 Secure
                    </span>
                    {account.connected ? (
                      <Button
                        variant="secondary"
                        onClick={() => handleDisconnect(account.platform)}
                        disabled={isWorking}
                        className="text-xs"
                      >
                        {isWorking ? 'Disconnecting…' : t('common.disconnect') || 'Disconnect'}
                      </Button>
                    ) : (
                      <Button
                        variant="primary"
                        onClick={() => handleConnect(account.platform)}
                        disabled={isWorking}
                        iconRight={ArrowUpRight}
                        className="text-xs"
                      >
                        {isWorking ? 'Connecting…' : t('common.connect') || 'Connect Channel'}
                      </Button>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </WorkspaceShell>
  );
}
