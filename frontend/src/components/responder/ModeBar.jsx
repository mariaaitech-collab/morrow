import { useState } from 'react';
import { AlertTriangle, Loader2, PauseCircle, ShieldCheck, Zap } from 'lucide-react';
import { MODE_META } from './shared';

// Top of the AI Responder page: which mode is live, a toggle to switch it, and
// the "Pause all auto-replies" kill switch. Every change applies immediately.
export default function ModeBar({ modes, onUpdate }) {
  const [busy, setBusy] = useState('');
  if (!modes) {
    return <section className="ar-modebar is-loading" aria-busy="true"><Loader2 size={16} className="ar-spin" /> Loading reply mode…</section>;
  }

  const { workspace, channels = [], responder_on: responderOn, always_review_rules: alwaysRules = [] } = modes;
  const { mode, paused } = workspace;
  const overrides = channels.filter((c) => c.mode !== 'inherit');

  const change = async (key, fields) => {
    setBusy(key);
    try { await onUpdate(fields); } finally { setBusy(''); }
  };

  const live = paused ? 'paused' : mode;
  const headline = paused ? 'Auto-replies are paused' : `${MODE_META[mode].label} is live`;
  const detail = paused
    ? 'Nothing is posted automatically. Every comment waits in Needs your attention until you resume.'
    : MODE_META[mode].desc;

  return (
    <section className={`ar-modebar is-${live}`} aria-label="Reply mode">
      <div className="ar-modebar-status" aria-live="polite">
        <span className="ar-modebar-icon" aria-hidden="true">
          {paused ? <PauseCircle size={20} /> : mode === 'instant' ? <Zap size={20} /> : <ShieldCheck size={20} />}
        </span>
        <div>
          <strong>{headline}</strong>
          <p>{detail}</p>
          {(overrides.length > 0 || alwaysRules.length > 0) && (
            <small>
              {overrides.length > 0 && `${overrides.length} ${overrides.length === 1 ? 'channel uses' : 'channels use'} its own mode`}
              {overrides.length > 0 && alwaysRules.length > 0 && ' · '}
              {alwaysRules.length > 0 && `${alwaysRules.length} ${alwaysRules.length === 1 ? 'rule is' : 'rules are'} always reviewed`}
              {' · see Rules & Replies'}
            </small>
          )}
          {!responderOn && <small className="warn"><AlertTriangle size={12} /> The auto-responder is off, so incoming comments are only logged. Turn it on in Rules &amp; Replies.</small>}
        </div>
      </div>

      <div className="ar-mode-switch" role="radiogroup" aria-label="Workspace reply mode">
        {['instant', 'review'].map((m) => (
          <button
            type="button"
            key={m}
            role="radio"
            aria-checked={mode === m}
            className={mode === m ? 'active' : ''}
            disabled={!!busy}
            onClick={() => mode !== m && change(`mode-${m}`, { mode: m })}
          >
            <strong>{busy === `mode-${m}` ? <Loader2 size={13} className="ar-spin" /> : m === 'instant' ? <Zap size={13} /> : <ShieldCheck size={13} />} {MODE_META[m].label}</strong>
            <small>{m === 'instant' ? 'Matched comments post within seconds' : 'Nothing posts without your click'}</small>
          </button>
        ))}
      </div>

      <label className={`ar-killswitch ${paused ? 'on' : ''}`}>
        <span><strong>Pause all auto-replies</strong><small>{paused ? 'Paused: nothing posts on its own' : 'Emergency stop, applies instantly'}</small></span>
        <button
          type="button"
          role="switch"
          aria-checked={paused}
          aria-label="Pause all auto-replies"
          className="m-switch"
          disabled={!!busy}
          onClick={() => change('pause', { paused: !paused })}
        />
      </label>
    </section>
  );
}
