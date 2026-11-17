import { useCallback, useEffect, useMemo, useState } from 'react';
import { Info } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import api, { extractApiError } from '../api/axios';
import WorkspaceShell from '../components/WorkspaceShell';
import PersonaTraining from '../components/responder/PersonaTraining';
import ApprovalQueue, { ActivityLog } from '../components/responder/ApprovalQueue';
import ModeBar from '../components/responder/ModeBar';
import ChannelHealth from '../components/responder/ChannelHealth';
import { MODE_META, PLATFORM_META, ResponderPlatformsContext, joinNames } from '../components/responder/shared';
import '../components/responder/responder.css';

const TABS = [
  { id: 'persona', label: 'Rules & Replies' },
  { id: 'queue', label: 'Needs your attention' },
  { id: 'activity', label: 'Activity' },
];

export default function AIResponder({ user, onLogout }) {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((t) => t.id === params.get('tab')) ? params.get('tab') : 'persona';
  const [stats, setStats] = useState(null);
  const [pending, setPending] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [modes, setModes] = useState(null);
  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);

  const loadHealth = useCallback(() => {
    setHealthLoading(true);
    api.get('/responder/channel-health', { timeout: 30000 }).then(({ data }) => setHealth(data.channels))
      .catch(() => setHealth((h) => h || []))
      .finally(() => setHealthLoading(false));
  }, []);

  const loadStats = useCallback(() => {
    api.get('/responder/stats').then(({ data }) => { setStats(data); setPending(data.pending); }).catch(() => {});
  }, []);

  const loadModes = useCallback(() => {
    api.get('/responder/modes').then(({ data }) => setModes(data))
      .catch((err) => toast.error(extractApiError(err, 'Could not load the reply mode.')));
  }, []);

  useEffect(() => { loadStats(); }, [loadStats, refreshKey]);
  useEffect(() => { loadModes(); }, [loadModes]);
  useEffect(() => { loadHealth(); }, [loadHealth, refreshKey]);

  // Mode settings save immediately (they are not part of the rules' Save button).
  const updateWorkspace = useCallback(async (fields) => {
    try {
      const { data } = await api.put('/responder/modes/workspace', fields);
      setModes(data);
      if ('paused' in fields) toast.success(fields.paused ? 'All auto-replies are paused.' : 'Auto-replies resumed.');
      else if (fields.mode) toast.success(`${MODE_META[fields.mode].label} is now the workspace default.`);
      else toast.success('Saved.');
    } catch (err) {
      toast.error(extractApiError(err, 'Could not change the reply mode.'));
      throw err;
    }
  }, []);

  const updateChannel = useCallback(async (key, mode) => {
    try {
      const { data } = await api.put(`/responder/modes/channels/${encodeURIComponent(key)}`, { mode });
      setModes(data);
      toast.success(mode === 'inherit' ? 'The channel now follows the workspace default.' : `The channel now uses ${MODE_META[mode].label}.`);
    } catch (err) {
      toast.error(extractApiError(err, 'Could not change the channel’s mode.'));
    }
  }, []);

  const setAlwaysReview = useCallback(async ({ platform, author_id: authorId, name }, on) => {
    try {
      const { data } = await api.post('/responder/always-review', { platform, author_id: String(authorId), name: name || '', on });
      setModes((m) => (m ? { ...m, workspace: { ...m.workspace, always_review_accounts: data.always_review_accounts } } : m));
      toast.success(data.message);
    } catch (err) {
      toast.error(extractApiError(err, 'Could not update the always-review list.'));
    }
  }, []);
  useEffect(() => {
    const onNew = () => setRefreshKey((k) => k + 1);
    window.addEventListener('brandora:responder-updated', onNew);
    return () => window.removeEventListener('brandora:responder-updated', onNew);
  }, []);

  // Which platforms auto-replies work on: RESPONDER_PLATFORMS on the backend, sent with /responder/modes.
  const platformInfo = useMemo(
    () => ({ platforms: modes?.platforms || [], coming_soon: modes?.coming_soon || [] }),
    [modes],
  );
  const noun = (p) => PLATFORM_META[p]?.noun || p;
  const scopeLine = modes && platformInfo.coming_soon.length > 0
    ? (platformInfo.platforms.length
      ? `Auto-replies currently work on ${joinNames(platformInfo.platforms.map(noun))}.`
      : 'Auto-replies are not available on any platform yet.')
      + ` ${joinNames(platformInfo.coming_soon.map(noun))} ${platformInfo.coming_soon.length === 1 ? 'is' : 'are'} coming soon.`
    : '';

  const setTab = (id) => setParams(id === 'persona' ? {} : { tab: id }, { replace: true });
  const onQueueCount = useCallback((n) => { setPending(n); loadStats(); }, [loadStats]);
  const onSimulated = (item) => {
    setRefreshKey((k) => k + 1);
    window.dispatchEvent(new CustomEvent('brandora:notifications-refresh'));
    if (item?.status === 'pending_approval') setTab('queue');
  };

  return (
    <WorkspaceShell user={user} onLogout={onLogout} active="ai-responder">
      <ResponderPlatformsContext.Provider value={platformInfo}>
      <div className="m-page ar-page">
        <header className="ar-hero">
          <h1>Auto-Responder</h1>
          <p>Choose how to handle new comments. Set up reply rules, review replies, and check what has been sent.</p>
        </header>

        <nav className="ar-tabs" role="tablist" aria-label="Auto-responder sections">
          {TABS.map((t) => (
            <button type="button" role="tab" key={t.id} aria-selected={tab === t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>
              <span>{t.label}</span>{t.id === 'queue' && pending > 0 && <em className="ar-count">{pending}</em>}
            </button>
          ))}
        </nav>

        <ModeBar modes={modes} onUpdate={updateWorkspace} />
        {tab !== 'persona' && <>
          {scopeLine && <p className="ar-scope-note"><Info size={15} aria-hidden="true" /> {scopeLine}</p>}
          <ChannelHealth channels={health} loading={healthLoading} onRefresh={loadHealth} />

          {stats && (
            <section className="ar-ribbon" aria-label="Responder summary">
              <div><strong>{stats.auto_replied}</strong><span>Auto-replied</span></div>
              <div><strong>{stats.pending}</strong><span>Need your attention</span></div>
              <div><strong>{stats.approved}</strong><span>Sent by you</span></div>
              <div><strong>{stats.reply_deleted ?? 0}</strong><span>Deleted</span></div>
            </section>
          )}
        </>}

        <div className="ar-tab-body">
          {tab === 'persona' && (
            <PersonaTraining
              onSimulated={onSimulated}
              modes={modes}
              onWorkspaceChange={updateWorkspace}
              onChannelChange={updateChannel}
              onAlwaysReview={setAlwaysReview}
            />
          )}
          {tab === 'queue' && <ApprovalQueue refreshKey={refreshKey} onCountChange={onQueueCount} modes={modes} onAlwaysReview={setAlwaysReview} />}
          {tab === 'activity' && <ActivityLog refreshKey={refreshKey} modes={modes} onAlwaysReview={setAlwaysReview} />}
        </div>
      </div>
      </ResponderPlatformsContext.Provider>
    </WorkspaceShell>
  );
}
