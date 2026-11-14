import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, Inbox, Loader2, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { extractApiError } from '../../api/axios';
import { PLATFORM_META, PlatformBadge, formatLocal, timeAgo, useResponderPlatforms } from './shared';

const OUTCOME_LABEL = {
  accepted: 'Accepted',
  duplicate: 'Duplicate',
  dropped: 'Dropped',
  unattributed: 'No workspace matched',
  rejected: 'Rejected',
  challenge: 'URL validated',
  error: 'Error',
  ignored: 'Ignored (auto-replies off)',
};
const OUTCOME_TONE = { accepted: 'ok', challenge: 'ok', duplicate: 'muted', dropped: 'muted', unattributed: 'warn', rejected: 'danger', error: 'danger', ignored: 'muted' };

function Row({ item }) {
  const [open, setOpen] = useState(false);
  let raw = item.raw;
  try { raw = raw ? JSON.stringify(JSON.parse(raw), null, 2) : ''; } catch { /* keep the text as is */ }
  return (
    <li className="ar-inbound-row">
      <button type="button" className="ar-inbound-head" onClick={() => setOpen((o) => !o)} aria-expanded={open} disabled={!raw}>
        <PlatformBadge platform={item.platform} size="sm" />
        <span className={`ar-pill ar-pill-${OUTCOME_TONE[item.outcome] || 'muted'}`}>{OUTCOME_LABEL[item.outcome] || item.outcome}</span>
        <span className="ar-inbound-reason">{item.reason}</span>
        <time title={formatLocal(item.received_at)}>{timeAgo(item.received_at)}</time>
        <small>{item.source}</small>
        {raw && <ChevronDown size={14} className={`ar-chevron ${open ? 'open' : ''}`} />}
      </button>
      {open && raw && <pre className="ar-inbound-raw">{raw}</pre>}
    </li>
  );
}

// Every webhook / poll delivery and what became of it, newest first, so you can
// tell "nothing arrived" from "it arrived and was dropped (and why)".
export default function InboundLog() {
  const platforms = useResponderPlatforms();
  const [picked, setPlatform] = useState('');
  const platform = platforms.includes(picked) ? picked : platforms[0];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!platform) return;
    setLoading(true);
    try {
      const { data: d } = await api.get('/responder/inbound-log', { params: { platform, limit: 20 } });
      setData(d);
    } catch (err) {
      toast.error(extractApiError(err, 'Could not load recent deliveries.'));
    } finally {
      setLoading(false);
    }
  }, [platform]);

  useEffect(() => { load(); }, [load]);

  if (!platform) return null;
  return (
    <section className="ar-card ar-inbound">
      <header className="ar-card-head ar-card-head--row">
        <div>
          <h4>Recent deliveries</h4>
          <p>The last 20 webhook or polling deliveries for {PLATFORM_META[platform].label}, and what happened to each. If this is empty, nothing has reached Morrow from {PLATFORM_META[platform].label}.</p>
        </div>
        <button type="button" className="ar-icon-btn" onClick={load} aria-label="Refresh"><RefreshCw size={14} /></button>
      </header>
      <div className="ar-platform-pick">
        {platforms.map((p) => (
          <button type="button" key={p} className={platform === p ? 'active' : ''} onClick={() => setPlatform(p)} title={PLATFORM_META[p].label}>
            <PlatformBadge platform={p} size="sm" />
          </button>
        ))}
      </div>
      {loading ? <div className="ar-loading"><Loader2 size={18} className="ar-spin" /> Loading…</div>
        : !data?.items?.length ? (
          <div className="ar-empty"><Inbox size={22} /><h4>Nothing received from {PLATFORM_META[platform].label}</h4>
            <p>No delivery has reached Morrow in the last 30 days{data?.includes_unattributed ? '' : ' for your workspace'}. See Channel health at the top for why.</p></div>
        ) : (
          <ul className="ar-inbound-list">{data.items.map((item) => <Row key={item.id} item={item} />)}</ul>
        )}
    </section>
  );
}
