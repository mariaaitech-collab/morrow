import { useEffect, useState } from 'react';
import { AlertTriangle, Check, Copy, Loader2, PlugZap, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { extractApiError } from '../../api/axios';
import { PLATFORM_META, PlatformBadge, useResponderPlatforms } from './shared';

function Check2({ ok, label }) {
  return <li className={ok ? 'ok' : 'missing'}>{ok ? <Check size={13} /> : <X size={13} />} {label}</li>;
}

export default function WebhookSetup() {
  const platforms = useResponderPlatforms();
  const [setup, setSetup] = useState(null);
  const [busy, setBusy] = useState('');

  const load = () => api.get('/responder/setup').then(({ data }) => setSetup(data)).catch((err) => toast.error(extractApiError(err, 'Could not load setup info.')));
  useEffect(() => { load(); }, []);

  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); toast.success('Copied'); } catch { toast.error('Copy failed. Select the text manually.'); }
  };

  const subscribe = async (platform) => {
    setBusy(platform);
    try {
      const { data } = await api.post(`/responder/subscribe/${platform}`, null, { timeout: 30000 });
      const ok = data.results.filter((r) => r.ok).length;
      toast.success(`Subscribed ${ok} Page${ok === 1 ? '' : 's'} to live ${PLATFORM_META[platform].label} events.`);
      load();
    } catch (err) {
      toast.error(extractApiError(err, 'Subscription failed.'));
    } finally {
      setBusy('');
    }
  };

  if (!setup) return <div className="ar-loading"><Loader2 size={18} className="ar-spin" /> Loading…</div>;

  return (
    <div className="ar-setup">
      {!setup.is_public_https && (
        <div className="ar-banner warn"><AlertTriangle size={16} /> Platforms can only deliver webhooks to a public HTTPS URL. Expose the backend (for example with ngrok) and set PUBLIC_BACKEND_URL in backend/.env. Until then, use “Simulate event” in the Persona tab to test.</div>
      )}
      <div className="ar-setup-grid">
        {platforms.filter((p) => setup.platforms[p]).map((p) => {
          const info = setup.platforms[p];
          return (
            <section className="ar-card ar-setup-card" key={p}>
              <header><PlatformBadge platform={p} /><div><h4>{PLATFORM_META[p].label}</h4><span>{info.connected ? 'Account connected' : 'Not connected'}</span></div></header>
              <div className="ar-url"><code>{info.webhook_url}</code><button type="button" className="ar-icon-btn" onClick={() => copy(info.webhook_url)} aria-label="Copy webhook URL"><Copy size={14} /></button></div>
              <ul className="ar-checks">
                <Check2 ok={info.connected} label="Account connected in Morrow" />
                {'verify_token_set' in info && <Check2 ok={info.verify_token_set} label="META_WEBHOOK_VERIFY_TOKEN set" />}
                <Check2 ok={info.secret_set} label="App secret set (signature check)" />
                {'subscribed' in info && <Check2 ok={info.subscribed} label="Pages subscribed to events" />}
              </ul>
              {info.fields && <p className="ar-note">Subscribe to: {info.fields.join(', ')}</p>}
              {info.note && <p className="ar-note">{info.note}</p>}
              {info.can_subscribe && (
                <button type="button" className="btn btn-glass btn-sm" disabled={busy === p} onClick={() => subscribe(p)}>{busy === p ? <Loader2 size={14} className="ar-spin" /> : <PlugZap size={14} />} {info.subscribed ? 'Re-subscribe Pages' : 'Subscribe Pages'}</button>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
