import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Check, ChevronDown, CircleSlash, Loader2, Plus, ShieldAlert, ShieldCheck, Trash2, X, Zap } from 'lucide-react';
import toast from 'react-hot-toast';
import api, { extractApiError } from '../../api/axios';
import { LANG_OPTIONS, MATCH_TYPES, MODE_META, NO_MATCH_OPTIONS, PLATFORM_META, PlatformBadge, modeLabel, timeAgo, useResponderPlatforms } from './shared';

let keySeq = 0;
const newKey = () => `rule-${++keySeq}`;

const EMPTY = {
  rules: [],
  fallback: { enabled: true, answers: [] },
  escalation_keywords: [],
  auto_reply: { enabled: false, reply_to_comments: true, reply_to_dms: true, review_all: false, platforms: { facebook: true, instagram: true, linkedin: true, tiktok: true } },
};

const RULE_DEFAULTS = {
  id: '', name: '', enabled: true, single_keyword: false, keywords: [], phrases: [], answers: [], platforms: [], source: '',
  match_type: 'smart', priority: 0, force_review: false,
};
const MATCH_TYPE_LABEL = Object.fromEntries(MATCH_TYPES.map((m) => [m.id, m.label]));
const clampPriority = (value) => Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));

// `previous` keeps each card's client key across a save, so open cards stay open.
function normalize(p, previous = []) {
  const base = { ...EMPTY, ...(p || {}) };
  base.auto_reply = { ...EMPTY.auto_reply, ...(p?.auto_reply || {}) };
  base.auto_reply.platforms = { ...EMPTY.auto_reply.platforms, ...(p?.auto_reply?.platforms || {}) };
  delete base.auto_reply.toxicity_threshold;
  base.fallback = { ...EMPTY.fallback, ...(p?.fallback || {}) };
  base.escalation_keywords = Array.isArray(base.escalation_keywords) ? base.escalation_keywords : [];
  base.rules = (Array.isArray(base.rules) ? base.rules : []).map((r, i) => ({ ...RULE_DEFAULTS, ...r, _key: previous[i]?._key || newKey() }));
  delete base.updated_at;
  return base;
}

const cleanAnswers = (answers) => (answers || [])
  .map((a) => ({ text: (a.text || '').trim(), lang: a.lang || 'any' }))
  .filter((a) => a.text);

function problemWith(rule) {
  if (!rule.name.trim()) return 'Give this rule a name.';
  if (!rule.keywords.length && !rule.phrases.length) return 'Add at least one keyword or trigger phrase.';
  if (!cleanAnswers(rule.answers).length) return 'Write at least one answer.';
  return '';
}

const ruleForApi = ({ _key, ...rule }) => ({ ...rule, name: rule.name.trim(), answers: cleanAnswers(rule.answers) });

function toApi(p) {
  return {
    rules: p.rules.map(ruleForApi),
    fallback: { enabled: p.fallback.enabled, answers: cleanAnswers(p.fallback.answers) },
    escalation_keywords: p.escalation_keywords,
    auto_reply: p.auto_reply,
  };
}

const sameText = (a, b) => (a || '').trim().toLowerCase() === (b || '').trim().toLowerCase();

function ChipInput({ values, onChange, placeholder, max = 30, maxLength = 200, splitOnComma = true, tone = '' }) {
  const [text, setText] = useState('');
  const add = (value) => {
    const v = (value ?? text).trim();
    if (!v) return;
    if (values.some((x) => sameText(x, v))) { setText(''); return; }
    if (values.length >= max) { toast.error(`You can add up to ${max} items.`); return; }
    onChange([...values, v]);
    setText('');
  };
  return (
    <div className="ar-chips-field">
      <div className="ar-chips">
        {values.map((v) => (
          <span key={v} className={`ar-chip ${tone}`} dir="auto">{v}<button type="button" onClick={() => onChange(values.filter((x) => x !== v))} aria-label={`Remove ${v}`}><X size={12} /></button></span>
        ))}
        <input
          value={text}
          dir="auto"
          maxLength={maxLength}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || (splitOnComma && e.key === ',')) { e.preventDefault(); add(); }
            else if (e.key === 'Backspace' && !text && values.length) onChange(values.slice(0, -1));
          }}
          onBlur={() => add()}
          placeholder={values.length ? '' : placeholder}
        />
      </div>
    </div>
  );
}

function Toggle({ checked, onChange, label, hint }) {
  return (
    <label className="ar-toggle-row">
      <span><strong>{label}</strong>{hint && <small>{hint}</small>}</span>
      <button type="button" role="switch" aria-checked={checked} className="m-switch" onClick={() => onChange(!checked)} />
    </label>
  );
}

function Section({ title, hint, action, children }) {
  return (
    <section className="ar-card">
      <header className="ar-card-head ar-card-head--row">
        <div><h4>{title}</h4>{hint && <p>{hint}</p>}</div>
        {action}
      </header>
      {children}
    </section>
  );
}

function AnswersEditor({ answers, onChange, answerRef, placeholder }) {
  const update = (i, patch) => onChange(answers.map((a, j) => (j === i ? { ...a, ...patch } : a)));
  return (
    <div className="ar-answers">
      {answers.map((a, i) => (
        <div className="ar-answer" key={i}>
          <textarea ref={i === answers.length - 1 ? answerRef : undefined} rows={2} dir="auto" maxLength={1000} value={a.text} onChange={(e) => update(i, { text: e.target.value })} placeholder={placeholder} />
          <select value={a.lang || 'any'} onChange={(e) => update(i, { lang: e.target.value })} aria-label="Reply language">
            {LANG_OPTIONS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
          <button type="button" className="ar-icon-btn" onClick={() => onChange(answers.filter((_, j) => j !== i))} aria-label="Remove answer"><Trash2 size={14} /></button>
        </div>
      ))}
      <button type="button" className="ar-add" disabled={answers.length >= 20} onClick={() => onChange([...answers, { text: '', lang: 'any' }])}><Plus size={14} /> Add answer</button>
    </div>
  );
}

function PlatformLimit({ value, onChange }) {
  const platforms = useResponderPlatforms();
  const all = value.length === 0;
  const toggle = (p) => {
    const next = value.includes(p) ? value.filter((x) => x !== p) : [...value, p];
    onChange(platforms.every((x) => next.includes(x)) ? [] : next);
  };
  return (
    <div className="ar-platform-toggles compact">
      <button type="button" className={all ? 'on' : ''} onClick={() => onChange([])} aria-pressed={all}>All platforms{all && <Check size={13} />}</button>
      {platforms.map((p) => {
        const on = value.includes(p);
        return <button type="button" key={p} className={on ? 'on' : ''} onClick={() => toggle(p)} aria-pressed={on}><PlatformBadge platform={p} size="sm" /> {PLATFORM_META[p].label}{on && <Check size={13} />}</button>;
      })}
    </div>
  );
}

function RuleCard({ rule, index, count, open, highlight, onToggle, onChange, onMove, onDelete, answerRef }) {
  const set = (key) => (value) => onChange({ ...rule, [key]: value });
  const problem = problemWith(rule);
  const answerCount = cleanAnswers(rule.answers).length;
  return (
    <div className={`ar-rule ${rule.enabled ? '' : 'is-off'} ${highlight ? 'is-hit' : ''}`} id={rule._key}>
      <div className="ar-rule-head">
        <button type="button" role="switch" aria-checked={rule.enabled} aria-label={`${rule.enabled ? 'Turn off' : 'Turn on'} ${rule.name || 'this rule'}`} className="m-switch" onClick={() => set('enabled')(!rule.enabled)} />
        <button type="button" className="ar-rule-title" onClick={onToggle} aria-expanded={open}>
          <strong dir="auto">{rule.name || 'Untitled rule'}</strong>
          <small>
            {rule.keywords.length} keywords · {rule.phrases.length} phrases · {answerCount} {answerCount === 1 ? 'answer' : 'answers'}
            {rule.match_type && rule.match_type !== 'smart' ? ` · ${MATCH_TYPE_LABEL[rule.match_type]} match` : ''}
            {rule.match_type === 'smart' && rule.single_keyword ? ' · one keyword is enough' : ''}
            {rule.priority > 0 ? ` · priority ${rule.priority}` : ''}
            {rule.platforms.length ? ` · ${rule.platforms.map((p) => PLATFORM_META[p].label).join(', ')} only` : ''}
          </small>
        </button>
        {rule.force_review && <span className="ar-badge review" title="Comments this rule answers always wait for your review"><ShieldCheck size={11} /> Always review</span>}
        {rule.source === 'faq' && <span className="ar-badge">Imported FAQ</span>}
        {problem && <span className="ar-badge warn" title={problem}>Unfinished</span>}
        <div className="ar-rule-tools">
          <button type="button" className="ar-icon-btn" disabled={index === 0} onClick={() => onMove(-1)} aria-label="Move up"><ArrowUp size={14} /></button>
          <button type="button" className="ar-icon-btn" disabled={index === count - 1} onClick={() => onMove(1)} aria-label="Move down"><ArrowDown size={14} /></button>
          <button type="button" className="ar-icon-btn" onClick={onToggle} aria-label={open ? 'Collapse rule' : 'Expand rule'}><ChevronDown size={14} className={`ar-chevron ${open ? 'open' : ''}`} /></button>
        </div>
      </div>
      {open && (
        <div className="ar-rule-body">
          <label className="ar-label">Rule name<input value={rule.name} maxLength={80} onChange={(e) => set('name')(e.target.value)} placeholder="e.g. Size guide" /></label>
          <div className="ar-grid-2">
            <label className="ar-label">How to match
              <select value={rule.match_type || 'smart'} onChange={(e) => set('match_type')(e.target.value)}>
                {MATCH_TYPES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
              </select>
              <small className="ar-select-hint">{(MATCH_TYPES.find((m) => m.id === (rule.match_type || 'smart')) || MATCH_TYPES[0]).hint}.</small>
            </label>
            <label className="ar-label">Priority <small>0–100. When several rules match, the highest wins; on a tie, the longest keyword.</small>
              <input type="number" min={0} max={100} step={1} value={rule.priority ?? 0} onChange={(e) => set('priority')(clampPriority(parseInt(e.target.value, 10)))} />
            </label>
          </div>
          <Toggle
            label="Always review"
            hint={rule.force_review ? 'Comments this rule answers always wait for you, even in Instant mode. Good for refunds or orders.' : 'Off: follows the channel’s or workspace’s reply mode.'}
            checked={!!rule.force_review}
            onChange={set('force_review')}
          />
          <div className="ar-label">Keywords <small>{rule.match_type && rule.match_type !== 'smart'
            ? `${MATCH_TYPE_LABEL[rule.match_type]}: ${MATCH_TYPES.find((m) => m.id === rule.match_type).hint.toLowerCase()}. Case, extra spaces and emoji are ignored.`
            : 'Whole words only, so “ai” never matches inside “email”. Small misspellings are caught.'}</small>
            <ChipInput values={rule.keywords} onChange={set('keywords')} max={80} maxLength={60} placeholder="Type a keyword and press Enter" />
          </div>
          {(rule.match_type || 'smart') === 'smart' && (
            <Toggle
              label="One keyword is enough"
              hint={rule.single_keyword ? 'Any single keyword answers. Good for greetings and praise.' : 'Needs 2 keywords, or 1 keyword of 6+ letters, or a trigger phrase.'}
              checked={!!rule.single_keyword}
              onChange={set('single_keyword')}
            />
          )}
          <div className="ar-label">Trigger phrases <small>{rule.match_type && rule.match_type !== 'smart'
            ? 'Matched the same way as keywords for this rule.'
            : 'Whole comments that should get this answer, e.g. “price kya hai”. Near-identical wording also matches.'}</small>
            <ChipInput values={rule.phrases} onChange={set('phrases')} max={80} maxLength={300} splitOnComma={false} placeholder="Type a full comment and press Enter" />
          </div>
          <div className="ar-label">Answers <small>One is picked at random. Give each a language so English, Roman Urdu and Urdu comments are answered in kind.</small>
            <AnswersEditor answers={rule.answers} onChange={set('answers')} answerRef={answerRef} placeholder="The reply customers will see" />
          </div>
          <div className="ar-label">Platforms<PlatformLimit value={rule.platforms} onChange={set('platforms')} /></div>
          <div className="ar-rule-foot">
            {problem ? <span className="ar-note danger">{problem}</span> : <span />}
            <button type="button" className="btn btn-glass btn-sm ar-decline" onClick={onDelete}><Trash2 size={14} /> Delete rule</button>
          </div>
        </div>
      )}
    </div>
  );
}

// Reply mode settings save immediately (not with "Save rules"). Resolution per
// comment: a rule set to "Always review" -> the channel's mode -> the workspace default.
function ReplyModeSection({ modes, fallbackReady, onWorkspaceChange, onChannelChange, onAlwaysReview }) {
  const [busy, setBusy] = useState('');
  if (!modes) return null;
  const ws = modes.workspace;
  const channels = modes.channels || [];
  const accounts = ws.always_review_accounts || [];
  const run = async (key, fn) => {
    setBusy(key);
    try { await fn(); } catch { /* the page already showed the error */ } finally { setBusy(''); }
  };

  return (
    <Section title="Reply mode" hint="How replies go out. Changes here apply immediately; they are not part of “Save rules”.">
      <div className="ar-label">Workspace default <small>Used by every channel below that has no setting of its own. Also switchable at the top of the page.</small>
        <div className="ar-mode-switch compact" role="radiogroup" aria-label="Workspace default">
          {['instant', 'review'].map((m) => (
            <button type="button" key={m} role="radio" aria-checked={ws.mode === m} className={ws.mode === m ? 'active' : ''} disabled={!!busy}
              onClick={() => ws.mode !== m && run(`mode-${m}`, () => onWorkspaceChange({ mode: m }))}>
              <strong>{busy === `mode-${m}` ? <Loader2 size={13} className="ar-spin" /> : m === 'instant' ? <Zap size={13} /> : <ShieldCheck size={13} />} {MODE_META[m].label}</strong>
              <small>{MODE_META[m].desc}</small>
            </button>
          ))}
        </div>
      </div>

      <div className="ar-label">Per channel <small>Give a channel its own mode, e.g. one account on Instant and another on Review. A rule set to “Always review” wins over both.</small>
        {channels.length === 0 ? <p className="ar-empty-line">No channels connected yet. Connect one on the Channels page.</p> : (
          <ul className="ar-channel-modes">
            {channels.map((c) => (
              <li key={c.key}>
                <PlatformBadge platform={c.platform} size="sm" />
                <span className="ar-channel-name" title={c.key}>{c.name}</span>
                <select value={c.mode} disabled={busy === c.key} onChange={(e) => run(c.key, () => onChannelChange(c.key, e.target.value))} aria-label={`Reply mode for ${c.name}`}>
                  <option value="inherit">Workspace default ({MODE_META[ws.mode].short})</option>
                  <option value="instant">{MODE_META.instant.label}</option>
                  <option value="review">{MODE_META.review.label}</option>
                </select>
              </li>
            ))}
          </ul>
        )}
      </div>

      <fieldset className="ar-label ar-radios">
        <legend>When no rule matches <small>Applies in Instant mode. In Review mode every comment waits for you anyway.</small></legend>
        {NO_MATCH_OPTIONS.map((o) => (
          <label key={o.id} className={`ar-radio ${ws.no_match_action === o.id ? 'on' : ''}`}>
            <input type="radio" name="no-match-action" checked={ws.no_match_action === o.id} disabled={!!busy}
              onChange={() => run(`nm-${o.id}`, () => onWorkspaceChange({ no_match_action: o.id }))} />
            <span><strong>{o.label}{o.tag && <em>{o.tag}</em>}</strong><small>{o.hint}</small></span>
          </label>
        ))}
        {ws.no_match_action === 'fallback' && !fallbackReady && (
          <p className="ar-note danger">There is no fallback reply yet, so unmatched comments will wait for you until you write one below.</p>
        )}
      </fieldset>

      <div className="ar-label">Always-review accounts <small>Comments from these people always wait for you, in any mode. Add someone from their comment in Needs your attention or Activity.</small>
        {accounts.length === 0 ? <p className="ar-empty-line">Nobody yet.</p> : (
          <ul className="ar-review-accounts">
            {accounts.map((a) => (
              <li key={`${a.platform}:${a.author_id}`}>
                <PlatformBadge platform={a.platform} size="sm" /><span className="ar-account-name">{a.name || a.author_id}</span>
                <button type="button" className="ar-icon-btn" onClick={() => onAlwaysReview(a, false)} aria-label={`Stop always reviewing ${a.name || a.author_id}`}><X size={14} /></button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  );
}

function GapsSection({ report, rules, onAddNew, onAddTo }) {
  const cov = report?.coverage;
  // A comment already added as a trigger phrase (saved or not) is hidden.
  const open = (report?.gaps || []).filter((g) => !rules.some((r) => r.phrases.some((p) => sameText(p, g.text))));
  return (
    <Section title="Comments no rule answered" hint="From the last 30 days, similar wording grouped. The fallback may have replied, but no rule did. Turn the common ones into rules.">
      {!report ? (
        <p className="ar-empty-line">Could not load unanswered comments.</p>
      ) : (
        <>
          <div className="ar-coverage">
            <strong>{cov.percent == null ? '—' : `${cov.percent}%`}</strong>
            <span>of comments matched a rule<small>{cov.analyzed ? `${cov.matched} of ${cov.analyzed} in the last ${report.days} days · fallback replies count as unmatched` : `No comments in the last ${report.days} days yet`}</small></span>
          </div>
          {cov.analyzed > 0 && open.length === 0 && <p className="ar-empty-line">Every comment in the last {report.days} days matched a rule.</p>}
          {open.length > 0 && (
            <ul className="ar-gaps">
              {open.map((g) => (
                <li key={g.event_ids[0] || g.text} className="ar-gap">
                  <div>
                    <p dir="auto">“{g.text}”</p>
                    <small>
                      {g.count > 1 ? `Asked ${g.count} times` : 'Asked once'}
                      {' · '}{!g.answered_by_fallback ? 'waited for you'
                        : g.answered_by_fallback === g.count ? 'fallback replied' : `fallback replied ${g.answered_by_fallback} of ${g.count}`}
                      {' · '}last {timeAgo(g.last_seen)}
                      {g.platforms.map((p) => <PlatformBadge key={p} platform={p} size="sm" />)}
                    </small>
                  </div>
                  <div className="ar-gap-actions">
                    <button type="button" className="m-btn m-btn--secondary" onClick={() => onAddNew(g)}><Plus size={14} /> Add as new rule</button>
                    <select value="" onChange={(e) => e.target.value && onAddTo(g, e.target.value)} aria-label="Add to an existing rule">
                      <option value="">Add to existing rule…</option>
                      {rules.map((r, i) => <option key={r._key} value={r._key}>{r.name || `Rule ${i + 1}`}</option>)}
                    </select>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Section>
  );
}

const LANG_LABEL = Object.fromEntries(LANG_OPTIONS.map((l) => [l.id, l.label]));

function howItMatched(r) {
  if (r.method === 'exact') return 'exact trigger phrase';
  if (r.method === 'fuzzy') return `close to the phrase “${r.phrase}”`;
  const words = [...r.keywords.filter((k) => !r.fuzzy_keywords.some((f) => f.endsWith(`~${k}`))), ...r.fuzzy_keywords.map((f) => f.replace('~', ' ≈ '))];
  return `keywords: ${words.join(', ')}`;
}

const VERDICT = {
  auto_reply: { icon: <Zap size={16} />, text: 'Would post now', tone: 'is-safe' },
  review: { icon: <ShieldAlert size={16} />, text: 'Would wait for you', tone: 'is-review' },
  ignore: { icon: <CircleSlash size={16} />, text: 'Would be ignored (nothing posted)', tone: 'is-review' },
};

function TestBox({ draft, dirty, channels = [], onSaveFirst, onSimulated, onShowRule }) {
  const [text, setText] = useState('price kya hai?');
  const platforms = useResponderPlatforms();
  const [platform, setPlatform] = useState('instagram');
  const [channelKey, setChannelKey] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);
  const [simulating, setSimulating] = useState(false);

  // Test only on a platform the AI Responder works on.
  useEffect(() => {
    if (platforms.length && !platforms.includes(platform)) { setPlatform(platforms[0]); setChannelKey(''); }
  }, [platforms, platform]);

  // Unfinished rules are left out, so the test runs while a rule is being written.
  const { payload, skipped } = useMemo(() => {
    const usable = draft.rules.filter((r) => !problemWith(r));
    return { payload: toApi({ ...draft, rules: usable }), skipped: draft.rules.length - usable.length };
  }, [draft]);

  useEffect(() => {
    if (!text.trim()) { setResult(null); return undefined; }
    if (!platforms.includes(platform)) return undefined; // the list is still loading, or being corrected
    let cancelled = false;
    const id = window.setTimeout(async () => {
      setChecking(true);
      try {
        const { data } = await api.post('/responder/persona/preview', { text, platform, kind: 'comment', persona: payload, channel_key: channelKey }, { timeout: 15000 });
        if (!cancelled) { setResult(data); setError(''); }
      } catch (err) {
        if (!cancelled) setError(extractApiError(err, 'The test could not run.'));
      } finally {
        if (!cancelled) setChecking(false);
      }
    }, 250);
    return () => { cancelled = true; window.clearTimeout(id); };
    // `channels` is included so a mode change at the top re-runs the test.
  }, [text, platform, platforms, channelKey, payload, channels]);

  const platformChannels = channels.filter((c) => c.platform === platform);

  const simulate = async () => {
    if (!text.trim()) return;
    setSimulating(true);
    try {
      if (dirty) await onSaveFirst();
      const { data } = await api.post('/responder/simulate', { text, kind: 'comment', platform, author_name: 'Test customer' }, { timeout: 30000 });
      const status = data.item?.status;
      toast.success(status === 'pending_approval' ? 'Simulated comment is waiting in Needs your attention.' : 'Simulated comment was answered (see Activity).');
      onSimulated?.(data.item);
    } catch (err) {
      toast.error(extractApiError(err, 'The simulation failed.'));
    } finally {
      setSimulating(false);
    }
  };

  const r = result;
  const terms = r ? [...r.flagged_terms, ...r.sensitive_terms, ...r.escalation_terms] : [];
  const nearMisses = r ? r.scored.filter((s) => s.rule_id !== r.rule_id && !s.passed).slice(0, 3) : [];
  return (
    <aside className="ar-card ar-playground">
      <header className="ar-card-head"><h4>Test a comment</h4><p>Type a comment and see which rule matches and what would be posted, with your current reply mode. Nothing is sent.</p></header>
      <div className="ar-platform-pick">
        {platforms.map((p) => <button type="button" key={p} className={platform === p ? 'active' : ''} onClick={() => { setPlatform(p); setChannelKey(''); }} title={PLATFORM_META[p].label}><PlatformBadge platform={p} size="sm" /></button>)}
      </div>
      {platformChannels.length > 1 && (
        <select className="ar-test-channel" value={channelKey || platformChannels[0].key} onChange={(e) => setChannelKey(e.target.value)} aria-label="Channel to test on">
          {platformChannels.map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
        </select>
      )}
      <textarea rows={3} dir="auto" value={text} maxLength={2000} onChange={(e) => setText(e.target.value)} placeholder="Type a customer comment…" />
      {skipped > 0 && <p className="ar-note">{skipped} unfinished {skipped === 1 ? 'rule is' : 'rules are'} left out of this test.</p>}
      {error && <p className="ar-note danger">{error}</p>}
      {r && text.trim() && (
        <div className={`ar-result ${(VERDICT[r.action] || VERDICT.review).tone}`} aria-live="polite">
          <div className="ar-result-head">
            {(VERDICT[r.action] || VERDICT.review).icon} {(VERDICT[r.action] || VERDICT.review).text}
            {checking && <Loader2 size={14} className="ar-spin" />}
          </div>
          <p className="ar-result-reason"><strong>Why:</strong> {r.reason}</p>
          {r.mode && <p className="ar-result-mode">Mode: {modeLabel(r.mode, r.mode_source)}{r.channel ? ` · ${r.channel.name}` : ''}{r.paused ? ' · auto-replies paused' : ''}</p>}
          <div className="ar-result-grid">
            <div><span>Rule</span>{r.outcome === 'matched'
              ? <button type="button" className="ar-linklike" onClick={() => onShowRule(r.rule_index)}>{r.rule_name}</button>
              : <strong>{r.outcome === 'fallback' ? 'None (fallback)' : 'None'}</strong>}</div>
            <div><span>Score</span><strong>{r.outcome === 'matched' ? r.score : '—'}</strong></div>
            <div><span>Language</span><strong>{LANG_LABEL[r.lang] || r.lang}</strong></div>
          </div>
          {r.outcome === 'matched' && <p className="ar-note">Matched by {howItMatched(r)}.</p>}
          {terms.length > 0 && <div className="ar-tags">{terms.map((t) => <span key={t} dir="auto">{t}</span>)}</div>}
          {r.reply && r.action !== 'ignore'
            ? <div className="ar-reply-bubble"><span>{r.action === 'auto_reply' ? 'Would be posted' : 'Suggested reply, waiting for your click'}{r.outcome === 'fallback' ? ' (fallback)' : ''}{r.answer_count > 1 ? ` · 1 of ${r.answer_count}, picked at random` : ''}</span><p dir="auto">{r.reply}</p></div>
            : <p className="ar-note">{r.action === 'ignore' ? 'No reply would be sent; it would be logged as Ignored.' : 'No reply would be drafted. The comment waits for you.'}</p>}
          {nearMisses.length > 0 && (
            <p className="ar-note">Almost matched: {nearMisses.map((s) => `${s.rule_name} (${s.keywords.join(', ')})`).join('; ')}. One short keyword isn’t enough unless the rule allows it.</p>
          )}
          {r.action === 'auto_reply' && <p className="ar-note">Live comments also wait if this would be the 3rd reply to the same person within an hour.</p>}
          {!r.auto_reply_on && r.action === 'auto_reply' && <p className="ar-note">The auto-responder is off, so live comments are not answered yet.</p>}
        </div>
      )}
      <button type="button" className="m-btn m-btn--secondary m-btn--block" disabled={simulating || !text.trim()} onClick={simulate} title="Runs the full pipeline, including Needs your attention and notifications">
        {simulating && <Loader2 size={16} className="ar-spin" />} Run as a simulated comment
      </button>
      {dirty && <p className="ar-note">Unsaved changes are saved before a simulation.</p>}
    </aside>
  );
}

export default function PersonaTraining({ onSimulated, modes = null, onWorkspaceChange, onChannelChange, onAlwaysReview }) {
  const platforms = useResponderPlatforms();
  const [persona, setPersona] = useState(EMPTY);
  const [saved, setSaved] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [gaps, setGaps] = useState(undefined);
  const [openKeys, setOpenKeys] = useState(() => new Set());
  const [focusKey, setFocusKey] = useState(null);
  const [hitKey, setHitKey] = useState(null);
  const answerRefs = useRef({});

  const loadGaps = useCallback(() => {
    api.get('/responder/gaps', { params: { days: 30 } })
      .then(({ data }) => setGaps(data))
      .catch(() => setGaps(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.get('/responder/persona').then(({ data }) => {
      if (cancelled) return;
      const p = normalize(data.persona);
      setPersona(p); setSaved(p);
    }).catch((err) => toast.error(extractApiError(err, 'Could not load your rules.')))
      .finally(() => !cancelled && setLoading(false));
    loadGaps();
    return () => { cancelled = true; };
  }, [loadGaps]);

  // Bring a rule into view (and its last answer into focus when asked).
  useEffect(() => {
    if (!focusKey) return;
    const { key, answer } = focusKey;
    window.requestAnimationFrame(() => {
      const el = answer ? answerRefs.current[key] : document.getElementById(key);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (answer) el?.focus({ preventScroll: true });
    });
    setFocusKey(null);
  }, [focusKey, persona.rules]);

  useEffect(() => {
    if (!hitKey) return undefined;
    const id = window.setTimeout(() => setHitKey(null), 1800);
    return () => window.clearTimeout(id);
  }, [hitKey]);

  const dirty = useMemo(() => JSON.stringify(persona) !== JSON.stringify(saved), [persona, saved]);
  const setAuto = (key, value) => setPersona((p) => ({ ...p, auto_reply: { ...p.auto_reply, [key]: value } }));
  const setPlatformOn = (platform, value) => setPersona((p) => ({ ...p, auto_reply: { ...p.auto_reply, platforms: { ...p.auto_reply.platforms, [platform]: value } } }));
  const setRules = (fn) => setPersona((p) => ({ ...p, rules: fn(p.rules) }));
  const openRule = (key, { answer = false } = {}) => {
    setOpenKeys((s) => new Set(s).add(key));
    setFocusKey({ key, answer });
  };
  const toggleOpen = (key) => setOpenKeys((s) => { const n = new Set(s); if (n.has(key)) n.delete(key); else n.add(key); return n; });

  const updateRule = (key, rule) => setRules((rules) => rules.map((r) => (r._key === key ? rule : r)));
  const moveRule = (key, dir) => setRules((rules) => {
    const i = rules.findIndex((r) => r._key === key);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= rules.length) return rules;
    const next = [...rules];
    [next[i], next[j]] = [next[j], next[i]];
    return next;
  });
  const deleteRule = (rule) => {
    if (!window.confirm(`Delete the rule “${rule.name || 'Untitled rule'}”? Save to make it permanent.`)) return;
    setRules((rules) => rules.filter((r) => r._key !== rule._key));
  };
  const addRule = (init = {}) => {
    const rule = { ...RULE_DEFAULTS, source: 'custom', answers: [{ text: '', lang: 'any' }], ...init, _key: newKey() };
    // New rules go first: they are usually more specific than the defaults, and the higher rule wins a tie.
    setRules((rules) => [rule, ...rules]);
    openRule(rule._key, { answer: !!init.phrases });
    return rule;
  };

  const addGapAsRule = (gap) => {
    addRule({ name: gap.text.trim().slice(0, 60), phrases: [gap.text.trim().slice(0, 300)] });
    toast('Write the answer, then save your rules.');
  };
  const addGapToRule = (gap, key) => {
    const rule = persona.rules.find((r) => r._key === key);
    if (!rule) return;
    if (!rule.phrases.some((p) => sameText(p, gap.text))) updateRule(key, { ...rule, phrases: [...rule.phrases, gap.text.trim().slice(0, 300)] });
    openRule(key);
    setHitKey(key);
    toast.success(`Added as a trigger phrase to “${rule.name || 'rule'}”. Save to apply.`);
  };
  const showRule = (index) => {
    const rule = persona.rules[index];
    if (!rule) return;
    openRule(rule._key);
    setHitKey(rule._key);
  };

  const save = async () => {
    const broken = persona.rules.find((r) => problemWith(r));
    if (broken) {
      openRule(broken._key, { answer: !cleanAnswers(broken.answers).length });
      const message = `${broken.name || 'Untitled rule'}: ${problemWith(broken)}`;
      toast.error(message);
      throw new Error(message);
    }
    if (modes?.workspace?.no_match_action === 'fallback' && !cleanAnswers(persona.fallback.answers).length) {
      const message = 'Add at least one fallback reply: “When no rule matches” is set to post it.';
      toast.error(message);
      throw new Error(message);
    }
    setSaving(true);
    try {
      const { data } = await api.put('/responder/persona', toApi(persona), { timeout: 20000 });
      const p = normalize(data.persona, persona.rules);
      setPersona(p); setSaved(p);
      loadGaps();
      toast.success('Rules saved. The next comment uses them.');
      return p;
    } catch (err) {
      toast.error(extractApiError(err, 'Could not save your rules.'));
      throw err;
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="ar-loading"><Loader2 size={18} className="ar-spin" /> Loading your rules…</div>;

  const auto = persona.auto_reply;
  return (
    <div className="ar-training">
      <div className="ar-training-main">
        <Section title="Settings" hint="Turn the auto-responder on and choose what it handles. Whether replies post instantly or wait for you is set under Reply mode.">
          <div className={`ar-master ${auto.enabled ? 'on' : ''}`}>
            <div><strong>{auto.enabled ? 'Auto-responder is ON' : 'Auto-responder is OFF'}</strong><small>{auto.enabled ? 'New comments and DMs are handled with your rules and reply mode.' : 'Incoming messages are logged but nothing is replied or queued.'}</small></div>
            <button type="button" role="switch" aria-checked={auto.enabled} className="m-switch m-switch--lg" onClick={() => setAuto('enabled', !auto.enabled)} />
          </div>
          <div className="ar-grid-2">
            <Toggle label="Reply to comments" checked={auto.reply_to_comments} onChange={(v) => setAuto('reply_to_comments', v)} />
            <Toggle label="Reply to direct messages" checked={auto.reply_to_dms} onChange={(v) => setAuto('reply_to_dms', v)} />
          </div>
          <div className="ar-platform-toggles">
            {platforms.map((p) => (
              <button type="button" key={p} className={auto.platforms[p] ? 'on' : ''} onClick={() => setPlatformOn(p, !auto.platforms[p])} aria-pressed={auto.platforms[p]}>
                <PlatformBadge platform={p} size="sm" /> {PLATFORM_META[p].label}{auto.platforms[p] ? <Check size={13} /> : null}
              </button>
            ))}
          </div>
        </Section>

        <ReplyModeSection
          modes={modes}
          fallbackReady={cleanAnswers(saved.fallback.answers).length > 0}
          onWorkspaceChange={onWorkspaceChange}
          onChannelChange={onChannelChange}
          onAlwaysReview={onAlwaysReview}
        />

        {gaps !== undefined && <GapsSection report={gaps} rules={persona.rules} onAddNew={addGapAsRule} onAddTo={addGapToRule} />}

        <Section
          title="Reply rules"
          hint="Rules are checked against every comment. If several match, the highest priority wins, then the most specific (longest keyword), then the higher rule in the list."
          action={<button type="button" className="m-btn m-btn--secondary" onClick={() => addRule()}><Plus size={14} /> Add rule</button>}
        >
          {persona.rules.length === 0 && <p className="ar-empty-line">No rules yet. Every comment will get the fallback reply.</p>}
          <div className="ar-rules">
            {persona.rules.map((rule, i) => (
              <RuleCard
                key={rule._key}
                rule={rule}
                index={i}
                count={persona.rules.length}
                open={openKeys.has(rule._key)}
                highlight={hitKey === rule._key}
                onToggle={() => toggleOpen(rule._key)}
                onChange={(next) => updateRule(rule._key, next)}
                onMove={(dir) => moveRule(rule._key, dir)}
                onDelete={() => deleteRule(rule)}
                answerRef={(el) => { answerRefs.current[rule._key] = el; }}
              />
            ))}
          </div>
        </Section>

        <Section
          title="Fallback reply"
          hint={modes?.workspace?.no_match_action === 'fallback'
            ? 'Posted instantly when no rule matches (your “When no rule matches” setting). One is picked at random, in the comment’s language.'
            : 'Never posted on its own with your current settings. It is the suggested reply on unmatched comments in Needs your attention.'}
        >
          <AnswersEditor answers={persona.fallback.answers} onChange={(answers) => setPersona((p) => ({ ...p, fallback: { ...p.fallback, answers } }))} placeholder="e.g. Thanks for reaching out! Please DM us." />
        </Section>

        <Section title="Blocklist: always review" hint="A comment containing any of these words always waits for you, in any mode, whatever rule matched. Offensive and sensitive words are always held too.">
          <ChipInput values={persona.escalation_keywords} onChange={(v) => setPersona((p) => ({ ...p, escalation_keywords: v }))} max={80} maxLength={60} tone="danger" placeholder="e.g. refund" />
        </Section>

        <div className={`ar-savebar ${dirty ? 'is-dirty' : ''}`}>
          <span>{dirty ? 'You have unsaved changes' : 'All changes saved'}</span>
          <div>
            {dirty && <button type="button" className="m-btn m-btn--secondary" onClick={() => setPersona(saved)} disabled={saving}>Discard</button>}
            <button type="button" className="m-btn m-btn--highlight" onClick={() => save().catch(() => {})} disabled={saving || !dirty}>{saving && <Loader2 size={16} className="ar-spin" />} Save rules</button>
          </div>
        </div>
      </div>
      <TestBox draft={persona} dirty={dirty} channels={modes?.channels || []} onSaveFirst={save} onSimulated={onSimulated} onShowRule={showRule} />
    </div>
  );
}
