import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, BookmarkPlus, Check, ChevronDown, Inbox, Loader2, MessageCircle, MessageSquare, PenLine, RefreshCw, ShieldAlert, Trash2, UserCheck, UserX, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { extractApiError } from '../../api/axios';
import { DECISION_META, PLATFORM_META, PlatformBadge, StatusPill, channelName, formatLocal, modeLabel, timeAgo } from './shared';

const POSTED = ['auto_replied', 'approved_sent', 'manual_sent'];

function Flags({ analysis }) {
  if (!analysis) return null;
  return (
    <div className="ar-flags">
      {analysis.flagged_terms?.length > 0 && <span className="ar-flag danger" title="Offensive word filter"><ShieldAlert size={12} /> “{analysis.flagged_terms.slice(0, 3).join('”, “')}”</span>}
      {analysis.sensitive_terms?.length > 0 && <span className="ar-flag warn" title="Sensitive word filter"><AlertTriangle size={12} /> “{analysis.sensitive_terms.slice(0, 3).join('”, “')}”</span>}
      {analysis.escalation_terms?.length > 0 && <span className="ar-flag warn" title="Your blocklist">Blocklist: {analysis.escalation_terms.join(', ')}</span>}
      {analysis.outcome === 'matched' && analysis.keywords?.length > 0 && <span className="ar-flag ok" title={analysis.method}>Matched: {analysis.keywords.slice(0, 4).join(', ')}</span>}
    </div>
  );
}

// Always visible, collapsed or not: which mode handled the comment, which rule
// matched, and what was decided.
function EventMeta({ item, channels }) {
  const a = item.analysis || {};
  const channel = channelName(channels, item.channel_key);
  const rule = a.outcome === 'matched' ? a.rule_name
    : a.outcome === 'fallback' && item.decision === 'auto_posted' ? 'none (fallback reply posted)'
      : a.outcome ? 'none matched' : '';
  if (!item.mode_used && !rule && !item.decision) return null;
  return (
    <div className="ar-event-meta">
      {item.mode_used && <span title="Reply mode used for this comment">Mode: <strong>{modeLabel(item.mode_used, item.mode_source)}</strong>{channel ? ` · ${channel}` : ''}</span>}
      {rule && <span>Rule: <strong>{rule}</strong></span>}
      {item.decision && <span className={`ar-decision-tag ${item.decision}`}>{DECISION_META[item.decision] || item.decision}</span>}
    </div>
  );
}

function AlwaysReviewToggle({ item, modes, onAlwaysReview }) {
  const authorId = item.author?.id;
  if (!authorId || !onAlwaysReview || !modes) return null;
  const name = item.author?.name || 'this account';
  const onList = (modes.workspace?.always_review_accounts || [])
    .some((a) => a.platform === item.platform && String(a.author_id) === String(authorId));
  return (
    <button
      type="button"
      className="ar-linklike ar-review-toggle"
      onClick={() => onAlwaysReview({ platform: item.platform, author_id: authorId, name: item.author?.name }, !onList)}
      title={onList ? 'Their comments will follow your normal rules again' : 'Their comments will always wait for your review, even in Instant mode'}
    >
      {onList ? <><UserX size={13} /> Stop always reviewing {name}</> : <><UserCheck size={13} /> Always review {name}</>}
    </button>
  );
}

function History({ entries }) {
  // The first "posted" entry is the reply bubble itself; show the trail once something changed.
  if (!entries?.some((h) => h.action !== 'posted')) return null;
  return (
    <ol className="ar-history">
      {entries.map((h, i) => (
        <li key={`${h.action}-${h.at}-${i}`} className={`ar-history-${h.action}`}>
          <span className="ar-history-meta">
            {h.action === 'posted' ? 'Posted' : h.action === 'edited' ? 'Edited' : 'Deleted'} by {h.by || 'Auto-responder'} · <time title={formatLocal(h.at)}>{timeAgo(h.at)}</time>
            {h.action === 'edited' && h.mode === 'reposted' && ' · old reply deleted, new one posted'}
          </span>
          {h.action === 'edited' ? (
            <div className="ar-history-diff">
              <p><span>Before</span>{h.previous_text}</p>
              <p><span>After</span>{h.text}</p>
            </div>
          ) : <p className={h.action === 'deleted' ? 'ar-struck' : ''}>{h.text}</p>}
          {h.warning && <p className="ar-error"><AlertTriangle size={13} /> {h.warning}</p>}
        </li>
      ))}
    </ol>
  );
}

function PostedReplyActions({ item, onChanged }) {
  const [mode, setMode] = useState('');
  const [text, setText] = useState(item.final_reply || '');
  const [busy, setBusy] = useState('');
  const [offerSave, setOfferSave] = useState(false);
  const label = PLATFORM_META[item.platform]?.label || item.platform;
  const ruleLabel = item.match_outcome === 'fallback' ? 'the fallback reply' : item.analysis?.rule_name;
  const canSaveToRule = (item.match_outcome === 'matched' && item.rule_id) || item.match_outcome === 'fallback';

  useEffect(() => { setText(item.final_reply || ''); }, [item.final_reply]);

  const run = async (action) => {
    setBusy(action);
    try {
      if (action === 'edit') {
        const { data } = await api.post(`/responder/events/${item.id}/edit-reply`, { reply_text: text }, { timeout: 60000 });
        if (data.warning) toast.error(data.warning, { duration: 9000 });
        else toast.success(item.simulated ? 'Reply updated (simulated, nothing was posted).' : `Reply replaced on ${label}.`);
        setMode('');
        setOfferSave(!!canSaveToRule);
        onChanged?.(data.item);
      } else if (action === 'delete') {
        const { data } = await api.post(`/responder/events/${item.id}/delete-reply`, null, { timeout: 45000 });
        toast.success(item.simulated ? 'Reply deleted (simulated).' : `Reply deleted from ${label}.`);
        setMode('');
        onChanged?.(data.item);
      } else {
        const { data } = await api.post(`/responder/events/${item.id}/save-answer`);
        toast.success(data.message);
        setOfferSave(false);
      }
    } catch (err) {
      // The server leaves the event unchanged on any platform error; say exactly why.
      toast.error(extractApiError(err, 'That did not work. Nothing was changed.'), { duration: 9000 });
    } finally {
      setBusy('');
    }
  };

  if (item.change_blocked) return <p className="ar-note">{item.change_blocked}</p>;

  return (
    <div className="ar-posted-actions">
      {offerSave && (
        <div className="ar-save-offer">
          <span>Use this wording every time {ruleLabel} answers?</span>
          <button type="button" className="btn btn-glass btn-sm" disabled={!!busy} onClick={() => run('save')}>{busy === 'save' ? <Loader2 size={14} className="ar-spin" /> : <BookmarkPlus size={14} />} Save as the answer for {ruleLabel}</button>
          <button type="button" className="ar-icon-btn" onClick={() => setOfferSave(false)} aria-label="Dismiss"><X size={14} /></button>
        </div>
      )}
      {mode === 'edit' && (
        <div className="ar-decision">
          <label><span><PenLine size={13} /> Edit the posted reply</span>
            <textarea rows={3} value={text} maxLength={2000} onChange={(e) => setText(e.target.value)} />
          </label>
          <p className="ar-note">
            {item.simulated ? 'Simulated event: only the record changes.' : `${label} doesn't let apps edit a posted reply, so Morrow will delete the old reply and post this one in its place. If the old reply can't be removed, nothing is changed.`}
          </p>
          <div className="ar-decision-actions">
            <button type="button" className="btn btn-glass btn-sm" disabled={!!busy} onClick={() => { setMode(''); setText(item.final_reply || ''); }}>Cancel</button>
            <button type="button" className="btn btn-primary btn-sm" disabled={!!busy || !text.trim() || text.trim() === (item.final_reply || '').trim()} onClick={() => run('edit')}>{busy === 'edit' ? <Loader2 size={14} className="ar-spin" /> : <Check size={14} />} Replace reply</button>
          </div>
        </div>
      )}
      {mode === 'delete' && (
        <div className="ar-decision danger">
          <p>Delete this reply from {item.simulated ? 'the record' : label}? The customer will no longer see it.</p>
          <div className="ar-decision-actions">
            <button type="button" className="btn btn-glass btn-sm" disabled={!!busy} onClick={() => setMode('')}>Cancel</button>
            <button type="button" className="btn btn-primary btn-sm ar-danger-btn" disabled={!!busy} onClick={() => run('delete')}>{busy === 'delete' ? <Loader2 size={14} className="ar-spin" /> : <Trash2 size={14} />} Delete reply</button>
          </div>
        </div>
      )}
      {!mode && (
        <div className="ar-decision-actions start">
          <button type="button" className="btn btn-glass btn-sm" onClick={() => setMode('edit')}><PenLine size={14} /> Edit</button>
          <button type="button" className="btn btn-glass btn-sm" onClick={() => setMode('delete')}><Trash2 size={14} /> Delete</button>
        </div>
      )}
    </div>
  );
}

export function EventCard({ item, onChanged, actionable = false, modes = null, onAlwaysReview = null }) {
  const [draft, setDraft] = useState(item.suggested_reply || '');
  const [mode, setMode] = useState(item.status === 'declined' ? 'manual' : 'review');
  const [manual, setManual] = useState('');
  const [busy, setBusy] = useState('');
  const [open, setOpen] = useState(actionable);

  useEffect(() => { setDraft(item.suggested_reply || ''); }, [item.suggested_reply]);

  const act = async (action) => {
    setBusy(action);
    try {
      let data;
      if (action === 'accept') ({ data } = await api.post(`/responder/events/${item.id}/accept`, { reply_text: draft }, { timeout: 45000 }));
      else if (action === 'decline') ({ data } = await api.post(`/responder/events/${item.id}/decline`));
      else ({ data } = await api.post(`/responder/events/${item.id}/reply`, { reply_text: manual }, { timeout: 45000 }));
      if (action === 'decline') { toast.success('Suggestion discarded. You can still write your own reply.'); setMode('manual'); }
      else toast.success(item.simulated ? 'Reply recorded (simulated, nothing was posted).' : `Reply posted on ${PLATFORM_META[item.platform]?.label || item.platform}.`);
      onChanged?.(data.item);
    } catch (err) {
      toast.error(extractApiError(err, 'Action failed.'));
      onChanged?.();
    } finally {
      setBusy('');
    }
  };

  const a = item.analysis || {};
  const isOpenForAction = actionable && ['pending_approval', 'failed', 'declined'].includes(item.status);
  const edited = draft.trim() !== (item.suggested_reply || '').trim();
  const deleted = item.status === 'reply_deleted';

  return (
    <article className={`ar-event ${a.is_offensive ? 'is-offensive' : ''} ${item.status === 'failed' ? 'is-failed' : ''}`}>
      <header className="ar-event-head" onClick={() => !actionable && setOpen((o) => !o)}>
        <PlatformBadge platform={item.platform} />
        <div className="ar-event-who">
          <strong>{item.author?.name || 'Unknown user'}</strong>
          <span>{item.kind === 'dm' ? <><MessageCircle size={12} /> Direct message</> : <><MessageSquare size={12} /> Comment</>} · <time title={formatLocal(item.platform_timestamp || item.received_at)}>{timeAgo(item.platform_timestamp || item.received_at)}</time>{item.simulated && <em className="ar-sim">Simulated</em>}</span>
        </div>
        <StatusPill status={item.status} />
        {!actionable && <ChevronDown size={16} className={`ar-chevron ${open ? 'open' : ''}`} />}
      </header>

      <blockquote className="ar-original">{item.text}</blockquote>
      <EventMeta item={item} channels={modes?.channels} />
      {item.decision_reason && <p className="ar-why"><strong>Why: </strong>{item.decision_reason}</p>}

      {open && (
        <>
          <Flags analysis={a} />
          {item.error && <p className="ar-error"><AlertTriangle size={13} /> {item.error}</p>}
          <AlwaysReviewToggle item={item} modes={modes} onAlwaysReview={onAlwaysReview} />

          {isOpenForAction && mode === 'review' && item.status !== 'declined' && (
            <div className="ar-decision">
              <label>Suggested reply {edited && <em>edited</em>}
                <textarea rows={3} value={draft} maxLength={2000} onChange={(e) => setDraft(e.target.value)} placeholder="No rule matched. Write a reply, or decline." />
              </label>
              <div className="ar-decision-actions">
                <button type="button" className="btn btn-glass btn-sm ar-decline" disabled={!!busy} onClick={() => act('decline')}>{busy === 'decline' ? <Loader2 size={14} className="ar-spin" /> : <X size={14} />} Decline</button>
                <button type="button" className="btn btn-primary btn-sm" disabled={!!busy || !draft.trim()} onClick={() => act('accept')}>{busy === 'accept' ? <Loader2 size={14} className="ar-spin" /> : item.status === 'failed' ? <RefreshCw size={14} /> : <Check size={14} />} {item.status === 'failed' ? 'Retry' : 'Post'}{edited ? ' edited reply' : ' reply'}</button>
              </div>
            </div>
          )}

          {isOpenForAction && (mode === 'manual' || item.status === 'declined') && (
            <div className="ar-decision manual">
              <label><span><PenLine size={13} /> Write your own reply</span>
                <textarea rows={3} value={manual} maxLength={2000} onChange={(e) => setManual(e.target.value)} placeholder="Reply in your own words, or leave it unanswered." />
              </label>
              <div className="ar-decision-actions">
                <span className="ar-note">The suggestion was discarded.</span>
                <button type="button" className="btn btn-primary btn-sm" disabled={!!busy || !manual.trim()} onClick={() => act('reply')}>{busy === 'reply' ? <Loader2 size={14} className="ar-spin" /> : <Check size={14} />} Send reply</button>
              </div>
            </div>
          )}

          {item.final_reply && (
            <div className={`ar-reply-bubble sent ${deleted ? 'deleted' : ''}`}>
              <span>{deleted ? 'Reply deleted' : `Reply ${item.simulated ? 'recorded' : 'posted'}`} {item.replied_at && !deleted ? <time title={formatLocal(item.replied_at)}>{timeAgo(item.replied_at)}</time> : ''}</span>
              <p className={deleted ? 'ar-struck' : ''}>{item.final_reply}</p>
            </div>
          )}
          {!isOpenForAction && !item.final_reply && item.suggested_reply && (
            <div className="ar-reply-bubble"><span>Suggested reply (not posted)</span><p>{item.suggested_reply}</p></div>
          )}
          {POSTED.includes(item.status) && !actionable && <PostedReplyActions item={item} onChanged={onChanged} />}
          <History entries={item.reply_history} />
        </>
      )}
    </article>
  );
}

export default function ApprovalQueue({ refreshKey, onCountChange, modes = null, onAlwaysReview = null }) {
  const [items, setItems] = useState([]);
  const [declined, setDeclined] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/responder/queue');
      setItems(data.items || []);
      onCountChange?.(data.count || 0);
    } catch (err) {
      toast.error(extractApiError(err, 'Could not load the items that need you.'));
    } finally {
      setLoading(false);
    }
  }, [onCountChange]);

  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => {
    const id = window.setInterval(() => { if (document.visibilityState === 'visible') load(); }, 30000);
    return () => window.clearInterval(id);
  }, [load]);

  const onChanged = (updated) => {
    if (updated?.status === 'declined') {
      // Keep the card on screen so a manual reply can still be written.
      setDeclined((d) => [updated, ...d.filter((x) => x.id !== updated.id)]);
    } else if (updated) {
      setDeclined((d) => d.filter((x) => x.id !== updated.id));
    }
    load();
  };

  if (loading) return <div className="ar-loading"><Loader2 size={18} className="ar-spin" /> Loading…</div>;
  const all = [...declined, ...items.filter((i) => !declined.some((d) => d.id === i.id))];

  if (all.length === 0) {
    return (
      <div className="ar-empty">
        <Inbox size={26} />
        <h4>Nothing needs you right now</h4>
        <p>{modes?.workspace?.mode === 'review' && !modes?.workspace?.paused
          ? 'Review mode is on: every new comment will wait here with a suggested reply.'
          : 'In Instant mode, only comments no rule answered, blocklisted or always-review ones, and failed replies wait here.'}</p>
      </div>
    );
  }
  return (
    <div className="ar-queue">
      {all.map((item) => (
        <div key={item.id} className="ar-queue-item">
          <EventCard item={item} actionable onChanged={onChanged} modes={modes} onAlwaysReview={onAlwaysReview} />
          {item.status === 'declined' && <button type="button" className="ar-dismiss" onClick={() => setDeclined((d) => d.filter((x) => x.id !== item.id))}>Dismiss</button>}
        </div>
      ))}
    </div>
  );
}

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'replied', label: 'Replied' },
  { id: 'pending', label: 'Needs attention' },
  { id: 'deleted', label: 'Deleted' },
  { id: 'declined', label: 'Declined' },
  { id: 'ignored', label: 'Ignored' },
  { id: 'skipped', label: 'Skipped' },
];

export function ActivityLog({ refreshKey, modes = null, onAlwaysReview = null }) {
  const [filter, setFilter] = useState('all');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/responder/events', { params: { status: filter, limit: 100 } });
      setItems(data.items || []);
    } catch (err) {
      toast.error(extractApiError(err, 'Could not load activity.'));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load, refreshKey]);

  // Update one card in place, so an open card stays open after an edit.
  const onChanged = (updated) => {
    if (updated) setItems((list) => list.map((i) => (i.id === updated.id ? updated : i)));
    else load();
  };

  return (
    <div className="ar-activity">
      <div className="ar-filters">
        {FILTERS.map((f) => <button type="button" key={f.id} className={filter === f.id ? 'active' : ''} onClick={() => setFilter(f.id)}>{f.label}</button>)}
        <button type="button" className="ar-icon-btn" onClick={load} aria-label="Refresh"><RefreshCw size={14} /></button>
      </div>
      {loading ? <div className="ar-loading"><Loader2 size={18} className="ar-spin" /> Loading…</div>
        : items.length === 0 ? <div className="ar-empty"><Inbox size={24} /><h4>No messages yet</h4><p>Once webhooks are connected, every comment and DM appears here with what was replied.</p></div>
          : <div className="ar-queue">{items.map((item) => <EventCard key={item.id} item={item} onChanged={onChanged} modes={modes} onAlwaysReview={onAlwaysReview} />)}</div>}
    </div>
  );
}
