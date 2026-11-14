import { useEffect, useMemo, useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import WorkspaceShell from '../components/WorkspaceShell';

/* ── Type metadata ── */
const TYPE_META = {
  generated_image:      { label: 'Image',            color: 'hst-badge-image'   },
  analysis:             { label: 'Analysis',         color: 'hst-badge-analysis'},
  competitive_analysis: { label: 'Analysis',         color: 'hst-badge-analysis'},
  generated_text:       { label: 'Caption',          color: 'hst-badge-caption' },
  content_generation:   { label: 'Caption',          color: 'hst-badge-caption' },
  scheduled_post:       { label: 'Scheduled',        color: 'hst-badge-sched'   },
  social_connect:       { label: 'Connected',        color: 'hst-badge-conn'    },
  social_disconnect:    { label: 'Disconnected',     color: 'hst-badge-disc'    },
  login:                { label: 'Login',            color: 'hst-badge-login'   },
  password_change:      { label: 'Security',         color: 'hst-badge-sec'     },
};

const TYPE_ICON = {
  generated_image:      <IconImage />,
  analysis:             <IconAnalysis />,
  competitive_analysis: <IconAnalysis />,
  generated_text:       <IconText />,
  content_generation:   <IconText />,
  scheduled_post:       <IconScheduled />,
  social_connect:       <IconConnect />,
  social_disconnect:    <IconDisconnect />,
  login:                <IconLogin />,
  password_change:      <IconSecurity />,
};

/* ── SVG icons ── */
function IconImage() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2"/>
      <circle cx="8.5" cy="8.5" r="1.5"/>
      <polyline points="21 15 16 10 5 21"/>
    </svg>
  );
}
function IconAnalysis() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10"/>
      <line x1="12" y1="20" x2="12" y2="4"/>
      <line x1="6" y1="20" x2="6" y2="14"/>
    </svg>
  );
}
function IconText() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>
    </svg>
  );
}
function IconScheduled() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <polyline points="12 6 12 12 16 14"/>
    </svg>
  );
}
function IconConnect() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
    </svg>
  );
}
function IconDisconnect() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>
      <line x1="12" y1="2" x2="12" y2="12"/>
    </svg>
  );
}
function IconLogin() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
      <polyline points="10 17 15 12 10 7"/>
      <line x1="15" y1="12" x2="3" y2="12"/>
    </svg>
  );
}
function IconSecurity() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  );
}

function IconTrash() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/>
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
      <path d="M10 11v6"/><path d="M14 11v6"/>
      <path d="M9 6V4h6v2"/>
    </svg>
  );
}

/* ── Date formatter ── */
function formatDate(iso, locale) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(locale, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

/* ── Bare checkbox ── */
function Checkbox({ checked, onChange, ariaLabel }) {
  return (
    <label className="hst-checkbox-wrap">
      <input type="checkbox" className="sr-only" checked={checked} onChange={onChange} aria-label={ariaLabel} />
      <span className={`hst-checkbox ${checked ? 'hst-checkbox-on' : ''}`}>
        {checked && (
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        )}
      </span>
    </label>
  );
}

/* ── Main page ── */
export default function History({ user, onLogout }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const { t, language } = useLanguage();

  const fetchHistory = useCallback(async () => {
    try {
      const { data } = await api.get('/user/history');
      setItems(data.items || []);
    } catch (err) {
      if (err.response?.status !== 401) console.error('History load failed:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const ids = useMemo(() => items.map((i) => i.id), [items]);
  const allSelected = ids.length > 0 && selected.size === ids.length;
  const someSelected = selected.size > 0;

  const toggleOne = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    setSelected((prev) => prev.size === ids.length && ids.length > 0 ? new Set() : new Set(ids));
  }, [ids]);

  const deleteSelected = async () => {
    if (selected.size === 0) return;
    setBusy(true);
    try {
      const { data } = await api.delete('/user/history', { data: { record_ids: Array.from(selected) } });
      setItems((prev) => prev.filter((i) => !selected.has(i.id)));
      setSelected(new Set());
      toast.success(t('history.deleted', { count: data.deleted_count, plural: data.deleted_count === 1 ? '' : 's' }));
    } catch (err) {
      toast.error(err.response?.data?.detail || t('history.deleteSelectedError'));
    } finally {
      setBusy(false);
    }
  };

  const clearAll = async () => {
    if (items.length === 0) return;
    if (!window.confirm(t('history.confirmClear'))) return;
    setBusy(true);
    try {
      const { data } = await api.delete('/user/history', { data: { clear_all: true } });
      setItems([]);
      setSelected(new Set());
      toast.success(t('history.cleared', { count: data.deleted_count, plural: data.deleted_count === 1 ? '' : 's' }));
    } catch (err) {
      toast.error(err.response?.data?.detail || t('history.clearError'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <WorkspaceShell user={user} onLogout={onLogout} active="history">
      <div className="m-page history-page">

        {/* ── Page header ── */}
        <div className="hst-page-header">
          <div>
            <h1 className="hst-page-title">{t('history.title')}</h1>
            <p className="hst-page-sub">{t('history.subtitle')}</p>
          </div>
          <div className="hst-page-stat">
            <span className="hst-stat-num">{items.length}</span>
            <span className="hst-stat-label">total events</span>
          </div>
        </div>

        {/* ── Toolbar ── */}
        <div className="hst-toolbar">
          <div className="hst-toolbar-left">
            <Checkbox checked={allSelected} onChange={toggleAll} ariaLabel={t('history.selectAll')} />
            <span className="hst-toolbar-count">
              {someSelected ? `${selected.size} selected` : `${items.length} events`}
            </span>
          </div>
          <div className="hst-toolbar-right">
            <button
              className="hst-btn hst-btn-danger"
              onClick={deleteSelected}
              disabled={!someSelected || busy}
            >
              <IconTrash />
              {t('history.deleteSelected')}
            </button>
            <button
              className="hst-btn hst-btn-ghost"
              onClick={clearAll}
              disabled={items.length === 0 || busy}
            >
              {t('history.clearAll')}
            </button>
          </div>
        </div>

        {/* ── Table ── */}
        {loading ? (
          <div className="hst-empty">
            <div className="hst-empty-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            </div>
            <p>{t('history.loading')}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="hst-empty">
            <div className="hst-empty-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
            </div>
            <p>{t('history.noActivity')}</p>
            <span>{t('history.noActivityHint')}</span>
          </div>
        ) : (
          <div className="hst-table">
            {/* Table header */}
            <div className="hst-thead">
              <div className="hst-th hst-col-check" />
              <div className="hst-th hst-col-type">Type</div>
              <div className="hst-th hst-col-event">Event</div>
              <div className="hst-th hst-col-detail">Detail</div>
              <div className="hst-th hst-col-date">Timestamp</div>
            </div>

            {/* Rows */}
            <div className="hst-tbody">
              {items.map((item, idx) => {
                const meta   = TYPE_META[item.type] || { label: item.type, color: 'hst-badge-login' };
                const icon   = TYPE_ICON[item.type] || <span>•</span>;
                const isSel  = selected.has(item.id);
                return (
                  <div
                    key={item.id}
                    className={`hst-row ${isSel ? 'hst-row-selected' : ''} ${idx % 2 === 1 ? 'hst-row-alt' : ''}`}
                    onClick={() => toggleOne(item.id)}
                  >
                    <div className="hst-td hst-col-check" onClick={(e) => e.stopPropagation()}>
                      <Checkbox checked={isSel} onChange={() => toggleOne(item.id)} ariaLabel={t('history.selectItem', { title: item.title })} />
                    </div>
                    <div className="hst-td hst-col-type">
                      <span className={`hst-badge ${meta.color}`}>
                        {icon}
                        {meta.label}
                      </span>
                    </div>
                    <div className="hst-td hst-col-event">
                      <span className="hst-event-title">{item.title || meta.label}</span>
                    </div>
                    <div className="hst-td hst-col-detail">
                      {item.detail
                        ? <span className="hst-detail">{item.detail}</span>
                        : <span className="hst-detail-empty">—</span>
                      }
                    </div>
                    <div className="hst-td hst-col-date">
                      <span className="hst-date">{formatDate(item.created_at, language)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </WorkspaceShell>
  );
}
