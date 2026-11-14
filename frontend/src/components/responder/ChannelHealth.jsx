import { AlertTriangle, CheckCircle2, Clock3, Loader2, RefreshCw } from 'lucide-react';
import { PlatformBadge, formatLocal, timeAgo } from './shared';

const ICON = {
  ok: <CheckCircle2 size={14} />,
  idle: <Clock3 size={14} />,
  broken: <AlertTriangle size={14} />,
};

// One row per connected channel: can it actually receive comments, when did
// the last one arrive, and if not, why. A dead channel is red, not just quiet.
export default function ChannelHealth({ channels, loading, onRefresh }) {
  if (!channels && loading) {
    return <section className="ar-health is-loading"><Loader2 size={14} className="ar-spin" /> Checking your channels…</section>;
  }
  if (!channels || channels.length === 0) return null;
  const broken = channels.filter((c) => c.status === 'broken').length;

  return (
    <section className="ar-health" aria-label="Channel health">
      <header>
        <strong>Channel health</strong>
        <span>{broken ? `${broken} ${broken === 1 ? 'channel is' : 'channels are'} not receiving comments` : 'Every channel can receive comments'}</span>
        <button type="button" className="ar-icon-btn" onClick={onRefresh} disabled={loading} aria-label="Check channels again">
          {loading ? <Loader2 size={14} className="ar-spin" /> : <RefreshCw size={14} />}
        </button>
      </header>
      <ul>
        {channels.map((c) => (
          <li key={c.key} className={`ar-health-item is-${c.status}`}>
            <PlatformBadge platform={c.platform} size="sm" />
            <div className="ar-health-body">
              <p className="ar-health-title">
                <strong>{c.name}</strong>
                <span className="ar-health-state">{ICON[c.status]} {c.headline}</span>
              </p>
              <small>
                Last comment: {c.last_event_at ? <time title={formatLocal(c.last_event_at)}>{timeAgo(c.last_event_at)}</time> : 'none received'}
                {' · '}via {c.method}
              </small>
              {c.status !== 'ok' && <p className="ar-health-detail">{c.detail}</p>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
