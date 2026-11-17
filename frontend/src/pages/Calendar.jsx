import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { ensureToken } from '../api/tokens';
import { useLanguage } from '../i18n/LanguageContext';
import WorkspaceShell from '../components/WorkspaceShell';
import { useDialog } from '../components/ui';

const PLATFORMS = [
  { value: 'facebook', label: 'Facebook', color: 'var(--platform-facebook)' },
  { value: 'linkedin', label: 'LinkedIn', color: 'var(--platform-linkedin)' },
  { value: 'instagram', label: 'Instagram', color: 'var(--platform-instagram)' },
];

const WEEKDAYS = ['weekdayMon', 'weekdayTue', 'weekdayWed', 'weekdayThu', 'weekdayFri', 'weekdaySat', 'weekdaySun'];

// Industry-standard best posting times (shown as smart recommendations)
const BEST_TIMES = [
  { platform: 'LinkedIn', key: 'bestTimeLinkedIn' },
  { platform: 'Instagram', key: 'bestTimeInstagram' },
  { platform: 'Facebook', key: 'bestTimeFacebook' },
];

const toLocalInput = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const pad = (n) => String(n).padStart(2, '0');
const toDateTimeLocal = (d) => `${toLocalInput(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const dayKey = (d) => `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;

function Calendar({ user, onLogout }) {
  const { t, language } = useLanguage();
  const [posts, setPosts] = useState([]);
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('month');
  const [refDate, setRefDate] = useState(new Date());
  const [modal, setModal] = useState(false);
  const qmRef = useDialog(modal, () => setModal(false));
  const [modalTab, setModalTab] = useState('note');
  const [selDate, setSelDate] = useState(new Date());
  const [pageTab, setPageTab] = useState('calendar'); // calendar | notes

  const [bulkText, setBulkText] = useState('');
  const [saving, setSaving] = useState(false);

  // note form
  const [noteText, setNoteText] = useState('');
  const [notify, setNotify] = useState(false);
  const [notifyAt, setNotifyAt] = useState('');

  const fetchPosts = async () => {
    try {
      const { data } = await api.get('/calendar/posts');
      setPosts(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || t('calendar.loadError'));
    } finally {
      setLoading(false);
    }
  };

  const fetchNotes = async () => {
    try {
      const { data } = await api.get('/calendar/notes');
      setNotes(data);
    } catch {
      /* non-fatal */
    }
  };

  useEffect(() => {
    fetchPosts();
    fetchNotes();
    const t = setInterval(() => { fetchPosts(); fetchNotes(); }, 30000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Notification simulation: fire reminders that are due ----
  useEffect(() => {
    const fireDue = async () => {
      const now = Date.now();
      for (const n of notes) {
        if (!n.notify || n.notified || !n.notify_at) continue;
        const due = new Date(n.notify_at).getTime();
        if (!isNaN(due) && due <= now) {
          toast(t('calendar.reminderToast', { note: n.note }), { icon: '🔔', duration: 8000 });
          try {
            if ('Notification' in window && Notification.permission === 'granted') {
              new Notification(t('calendar.notificationTitle'), { body: n.note });
            }
          } catch { /* ignore */ }
          try {
            await api.patch(`/calendar/notes/${n.id}/notify`);
            setNotes((prev) => prev.map((x) => (x.id === n.id ? { ...x, notified: true } : x)));
          } catch { /* ignore */ }
        }
      }
    };
    fireDue();
    const iv = setInterval(fireDue, 20000);
    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notes]);

  const postsByDay = useMemo(() => {
    const map = {};
    for (const p of posts) {
      const k = dayKey(new Date(p.scheduled_at));
      (map[k] = map[k] || []).push(p);
    }
    return map;
  }, [posts]);

  const notesByDay = useMemo(() => {
    const map = {};
    for (const n of notes) {
      if (!n.date) continue;
      (map[n.date] = map[n.date] || []).push(n);
    }
    return map;
  }, [notes]);

  // ---- Month grid ----
  const monthCells = useMemo(() => {
    const y = refDate.getFullYear();
    const m = refDate.getMonth();
    const first = new Date(y, m, 1);
    const offset = (first.getDay() + 6) % 7;
    const start = new Date(y, m, 1 - offset);
    return Array.from({ length: 42 }, (_, i) =>
      new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
  }, [refDate]);
  const monthLabel = refDate.toLocaleDateString(language, { month: 'long', year: 'numeric' });
  const localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Local time';

  // ---- Week grid ----
  const weekCells = useMemo(() => {
    const offset = (refDate.getDay() + 6) % 7;
    const monday = new Date(refDate.getFullYear(), refDate.getMonth(), refDate.getDate() - offset);
    return Array.from({ length: 7 }, (_, i) =>
      new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i));
  }, [refDate]);

  const shift = (dir) => {
    setRefDate((d) => {
      const n = new Date(d);
      if (view === 'month') n.setMonth(n.getMonth() + dir);
      else n.setDate(n.getDate() + dir * 7);
      return n;
    });
  };

  const openDay = (d) => {
    setSelDate(d);
    setBulkText('');
    setNoteText(''); setNotify(false);
    setNotifyAt(`${toLocalInput(d)}T10:00`);
    setModalTab('note');
    setModal(true);
  };

  const submitBulk = async () => {
    const lines = bulkText.split('\n').map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) return toast.error(t('calendar.enterOneLine'));
    const postsArr = [];
    for (const line of lines) {
      const parts = line.split('|').map((s) => s.trim());
      if (parts.length < 3) continue;
      const [datetime, plats, ...rest] = parts;
      const content = rest.join('|').trim();
      const dt = new Date(datetime.replace(' ', 'T'));
      if (isNaN(dt)) continue;
      postsArr.push({
        scheduled_at: dt.toISOString(),
        platforms: plats.split(',').map((s) => s.trim()).filter((p) => PLATFORMS.some((x) => x.value === p)),
        content,
      });
    }
    if (postsArr.length === 0) return toast.error(t('calendar.noValidLines'));
    if (!ensureToken()) return;
    setSaving(true);
    try {
      const { data } = await api.post('/calendar/bulk', { posts: postsArr });
      toast.success(t('calendar.bulkQueued', { count: data.count }));
      setModal(false);
      setBulkText('');
      await fetchPosts();
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Bulk queue failed');
    } finally {
      setSaving(false);
    }
  };

  const submitNote = async () => {
    if (!noteText.trim()) return toast.error(t('calendar.writeNoteOrReminder'));
    setSaving(true);
    try {
      if (notify && 'Notification' in window && Notification.permission === 'default') {
        try { await Notification.requestPermission(); } catch { /* ignore */ }
      }
      const body = {
        date: toLocalInput(selDate),
        note: noteText.trim(),
        notify,
        notify_at: notify && notifyAt ? new Date(notifyAt).toISOString() : null,
      };
      await api.post('/calendar/notes', body);
      toast.success(t('calendar.noteSaved'));
      setModal(false);
      await fetchNotes();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('calendar.saveNoteError'));
    } finally {
      setSaving(false);
    }
  };

  const deletePost = async (id) => {
    if (!window.confirm(t('calendar.confirmDeletePost'))) return;
    try {
      await api.delete(`/calendar/post/${id}`);
      toast.success(t('calendar.deleted'));
      await fetchPosts();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('calendar.deleteFailed'));
    }
  };

  const deleteNote = async (id) => {
    try {
      await api.delete(`/calendar/notes/${id}`);
      toast.success(t('calendar.noteRemoved'));
      await fetchNotes();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('calendar.deleteFailed'));
    }
  };

  const toggleNoteComplete = async (n) => {
    try {
      await api.put(`/calendar/notes/${n.id}`, { completed: !n.completed });
      setNotes((prev) => prev.map((x) => (x.id === n.id ? { ...x, completed: !x.completed } : x)));
    } catch {
      toast.error(t('calendar.couldNotUpdateNote'));
    }
  };

  const PostChip = ({ p }) => (
    <div className={`month-post ${p.status === 'published' ? 'pub' : ''}`} title={p.content}>
      <span className="mp-time">{new Date(p.scheduled_at).toLocaleTimeString(language, { hour: 'numeric', minute: '2-digit' })}</span>
      {p.content.slice(0, 24)}
      {p.recurring && ' 🔁'}
    </div>
  );

  const NoteChip = ({ n }) => (
    <div
      className={`cal-note ${n.notified ? 'done' : ''}`}
      title={n.note}
        onClick={(e) => { e.stopPropagation(); if (window.confirm(t('calendar.confirmDeleteNote'))) deleteNote(n.id); }}
    >
      {n.notify && <span className="note-bell">🔔</span>}
      {n.note.slice(0, 22)}
    </div>
  );

  const BestTimes = () => (
    <div className="best-times">
      {BEST_TIMES.map((b) => (
        <span key={b.platform} className="best-time-badge">
          <span className="bt-ico">✨</span> <b>{b.platform}</b>: {t('calendar.' + b.key)}
        </span>
      ))}
    </div>
  );

  return (
    <>
      <WorkspaceShell user={user} onLogout={onLogout} active="calendar">
      <div className="m-page calendar-page">
        <div className="cal-header">
          <div className="cal-title">
            <h1>{t('calendar.title')}</h1>
            <p>{t('calendar.subtitle')}</p>
          </div>
          {pageTab === 'calendar' && (
            <div className="cal-controls">
              <div className="cal-toggle" role="group" aria-label={`${t('calendar.month')} / ${t('calendar.week')}`}>
                <button type="button" className={view === 'month' ? 'active' : ''} aria-pressed={view === 'month'} onClick={() => setView('month')}>{t('calendar.month')}</button>
                <button type="button" className={view === 'week' ? 'active' : ''} aria-pressed={view === 'week'} onClick={() => setView('week')}>{t('calendar.week')}</button>
              </div>
              <div className="cal-nav">
                <button type="button" className="cal-btn" aria-label="Previous" onClick={() => shift(-1)}>←</button>
                <span className="month-label">{view === 'month' ? monthLabel : `${weekCells[0].toLocaleDateString(language, { month: 'short', day: 'numeric' })} – ${weekCells[6].toLocaleDateString(language, { month: 'short', day: 'numeric' })}`}</span>
                <button type="button" className="cal-btn" aria-label="Next" onClick={() => shift(1)}>→</button>
                <button type="button" className="cal-btn cal-btn--today" onClick={() => setRefDate(new Date())}>{t('calendar.today')}</button>
              </div>
            </div>
          )}
        </div>

        <div className="cal-subtabs">
          <button type="button" className={`cal-subtab ${pageTab === 'calendar' ? 'active' : ''}`} aria-pressed={pageTab === 'calendar'} onClick={() => setPageTab('calendar')}>{t('calendar.tabCalendar')}</button>
          <button type="button" className={`cal-subtab ${pageTab === 'notes' ? 'active' : ''}`} aria-pressed={pageTab === 'notes'} onClick={() => setPageTab('notes')}>{t('calendar.tabNotes')}</button>
        </div>

        {pageTab === 'calendar' ? (
          <>
            <div className="legend calendar-legend" style={{ display: 'flex', gap: '1.2rem', marginBottom: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              <span><span style={{ color: 'var(--accent)' }}>●</span> {t('calendar.legendScheduled')}</span>
              <span><span style={{ color: 'var(--success)' }}>●</span> {t('calendar.legendPublished')}</span>
              <span><span style={{ color: 'var(--accent-2)' }}>●</span> {t('calendar.legendNote')}</span>
              <span className="calendar-timezone">Times shown in {localTimeZone}</span>
            </div>

            {loading ? (
              <p className="sched-empty">{t('common.loading')}</p>
            ) : (
              <>
            {view === 'month' ? (
              <div className="month-scroll">
                <div className="month-board">
                <div className="month-weekdays">
                  {WEEKDAYS.map((w) => <span key={w}>{t('calendar.' + w)}</span>)}
                </div>
                <div className="month-grid">
                  {monthCells.map((d) => {
                    const k = dayKey(d);
                    const dayPosts = postsByDay[k] || [];
                    const dayNotes = notesByDay[k] || [];
                    const isOther = d.getMonth() !== refDate.getMonth();
                    const isToday = dayKey(d) === dayKey(new Date());
                    return (
                      <div
                        key={d.toISOString()}
                        className={`month-cell ${isOther ? 'other' : ''} ${isToday ? 'today' : ''}`}
                        onClick={() => openDay(d)}
                      >
                        <div className="month-cell-num">{d.getDate()}</div>
                        <div className="month-cell-posts">
                          {dayPosts.slice(0, 3).map((p) => <PostChip key={p.id} p={p} />)}
                          {dayNotes.slice(0, 2).map((n) => <NoteChip key={n.id} n={n} />)}
                          {dayPosts.length + dayNotes.length > 5 && (
                            <span className="month-more">+{dayPosts.length + dayNotes.length - 5} {t('calendar.more')}</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
                </div>
              </div>
            ) : (
              <div className="week-cal">
                {weekCells.map((d) => {
                  const k = dayKey(d);
                  const dayPosts = postsByDay[k] || [];
                  const dayNotes = notesByDay[k] || [];
                  const isToday = dayKey(d) === dayKey(new Date());
                  return (
                    <div key={d.toISOString()} className={`week-cal-col ${isToday ? 'today' : ''}`} onClick={() => openDay(d)}>
                      <div className="wc-head">
                        <span className="wc-name">{t('calendar.' + WEEKDAYS[(d.getDay() + 6) % 7])}</span>
                        <span className="wc-date">{d.getDate()}</span>
                      </div>
                      <div className="wc-add">{t('calendar.add')}</div>
                      <div className="wc-posts">
                        {dayPosts.slice(0, 3).map((p) => (
                          <div key={p.id} className={`month-post ${p.status === 'published' ? 'pub' : ''}`} title={p.content}>
                            <span className="mp-time">{new Date(p.scheduled_at).toLocaleTimeString(language, { hour: 'numeric', minute: '2-digit' })}</span>
                            {p.content.slice(0, 16)}{p.recurring ? ' 🔁' : ''}
                          </div>
                        ))}
                        {dayNotes.slice(0, 2).map((n) => <NoteChip key={n.id} n={n} />)}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
          </>
        ) : (
          <NotesView notes={notes} onDelete={deleteNote} onToggle={toggleNoteComplete} onAdd={() => openDay(new Date())} />
        )}
      </div>
      </WorkspaceShell>

      {modal && (
        <div className="qm-overlay" onClick={() => setModal(false)}>
          <div className="qm" ref={qmRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="qm-title" onClick={(e) => e.stopPropagation()}>
            <div className="qm-head">
              <h3 id="qm-title">{selDate.toLocaleDateString(language, { weekday: 'long', month: 'short', day: 'numeric' })}</h3>
              <button type="button" className="qm-close" aria-label={t('common.close')} onClick={() => setModal(false)}>✕</button>
            </div>

            <div className="qm-tabs">
              <button className={`qm-tab ${modalTab === 'note' ? 'active' : ''}`} onClick={() => setModalTab('note')}>{t('calendar.modalPersonalNote')}</button>
              <button className={`qm-tab ${modalTab === 'bulk' ? 'active' : ''}`} onClick={() => setModalTab('bulk')}>{t('calendar.modalBulkQueue')}</button>
            </div>

            {modalTab === 'note' && (
              <div className="qm-body">
                <div style={{ gridColumn: '1 / -1' }}>
                  <div className="note-field">
                    <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{t('calendar.modalPersonalNote')} / Reminder</label>
                    <textarea placeholder={t('calendar.notePlaceholder')} value={noteText} onChange={(e) => setNoteText(e.target.value)} />
                  </div>
                  <div className="notify-row">
                    <div>
                      <div className="nr-label">🔔 {t('calendar.notifyMe')}</div>
                      <div className="nr-sub">{t('calendar.notifySub')}</div>
                    </div>
                    <label className="notify-switch">
                      <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
                      <span className="notify-slider" />
                    </label>
                  </div>
                  {notify && (
                    <div className="notify-datetime form-field">
                      <label>{t('calendar.remindMeAt')}</label>
                      <input type="datetime-local" value={notifyAt} onChange={(e) => setNotifyAt(e.target.value)} />
                    </div>
                  )}
                  <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginTop: '1rem' }}>{t('calendar.bestTimeToPost')}</label>
                  <BestTimes />
                  <div className="qm-actions">
                    <button className="btn btn-outline btn-lg" onClick={() => setModal(false)}>{t('calendar.cancel')}</button>
                    <button className="btn btn-primary btn-lg" onClick={submitNote} disabled={saving}>
                      {saving ? <><span className="spinner-sm" /> {t('common.loading')}</> : `💾 ${t('calendar.saveNote')}`}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {modalTab === 'bulk' && (
              <div className="qm-body">
                <div style={{ gridColumn: '1 / -1' }}>
                  <div className="form-field">
                    <label>{t('calendar.bulkTitle')}</label>
                    <textarea className="bulk-area" placeholder={t('calendar.bulkPlaceholder')}
                      value={bulkText} onChange={(e) => setBulkText(e.target.value)} />
                    <p className="bulk-hint">{t('calendar.bulkHint')}</p>
                  </div>
                  <div className="qm-actions">
                    <button className="btn btn-outline btn-lg" onClick={() => setModal(false)}>{t('calendar.cancel')}</button>
                    <button className="btn btn-primary btn-lg" onClick={submitBulk} disabled={saving}>
                      {saving ? <><span className="spinner-sm" /> {t('common.loading')}</> : `⚡ ${t('calendar.queueAll')}`}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function NotesView({ notes, onDelete, onToggle, onAdd }) {
  const { t, language } = useLanguage();
  const sorted = [...notes].sort((a, b) => {
    if ((a.date || '') < (b.date || '')) return -1;
    if ((a.date || '') > (b.date || '')) return 1;
    return (a.completed ? 1 : 0) - (b.completed ? 1 : 0);
  });
  const pending = sorted.filter((n) => !n.completed).length;

  if (sorted.length === 0) {
    return (
      <div className="notes-view">
        <div className="notes-head">
          <div>
            <h2>{t('calendar.notesTitle')}</h2>
            <p className="notes-sub">{t('calendar.notesSub')}</p>
          </div>
          <button className="btn btn-primary" onClick={onAdd}>＋ {t('calendar.addNote')}</button>
        </div>
        <div className="notes-empty">
          <div className="ne-ico">🗒️</div>
          <h3>{t('calendar.noNotes')}</h3>
          <p>{t('calendar.noNotesSub')}</p>
        </div>
      </div>
    );
  }

  const fmt = (d) => {
    if (!d) return '';
    const dt = new Date(d);
    if (isNaN(dt)) return d;
    return dt.toLocaleDateString(language, { month: 'short', day: 'numeric', year: 'numeric' });
  };
  const fmtTime = (tm) => {
    if (!tm) return '';
    const dt = new Date(tm);
    if (isNaN(dt)) return tm;
    return dt.toLocaleString(language, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  };

  return (
    <div className="notes-view">
      <div className="notes-head">
        <div>
          <h2>{t('calendar.notesTitle')}</h2>
          <p className="notes-sub">
            {t('calendar.totalNotes', { count: sorted.length })} · <b style={{ color: 'var(--accent-text)' }}>{t('calendar.pendingNotes', { count: pending })}</b>
            {pending !== sorted.length && ` · ${t('calendar.completedNotes', { count: sorted.length - pending })}`}
          </p>
        </div>
        <button className="btn btn-primary" onClick={onAdd}>＋ {t('calendar.addNote')}</button>
      </div>

      <div className="notes-grid">
        {sorted.map((n) => (
          <div key={n.id} className={`note-card ${n.completed ? 'done' : ''}`}>
            <div className="nc-top">
              <span className="nc-date">{fmt(n.date)}</span>
              {n.notify && (
                <span className={`nc-bell ${n.notified ? 'fired' : ''}`} title={n.notified ? t('calendar.reminderSent') : t('calendar.reminderSet')}>
                  🔔
                </span>
              )}
            </div>
            <p className="nc-body">{n.note}</p>
            {n.best_time && (
              <span className="nc-best">✨ {t('calendar.bestTime', { time: n.best_time })}</span>
            )}
            {n.notify && n.notify_at && (
              <span className="nc-remind">⏰ {t('calendar.reminder', { time: fmtTime(n.notify_at) })}</span>
            )}
            <div className="nc-actions">
              <button className="nc-btn nc-complete" onClick={() => onToggle(n)}>
                {n.completed ? `↺ ${t('calendar.reopen')}` : `✓ ${t('calendar.complete')}`}
              </button>
              <button className="nc-btn nc-delete" onClick={() => onDelete(n.id)}>🗑 {t('calendar.deleteNote')}</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Calendar;
