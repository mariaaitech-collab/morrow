import { useEffect, useMemo, useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import Navbar from '../components/Navbar';

// Visual metadata per activity type (labels come from i18n via history.type.*).
const TYPE_ICON = {
  generated_image: '🖼️',
  analysis: '📊',
  generated_text: '✍️',
  scheduled_post: '🚀',
  social_connect: '🔗',
  social_disconnect: '✂️',
  login: '🔓',
  password_change: '🔑',
};

function formatDate(iso, locale) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function Checkbox({ checked, onChange, ariaLabel }) {
  return (
    <label className="relative inline-flex cursor-pointer select-none items-center">
      <input type="checkbox" className="sr-only" checked={checked} onChange={onChange} aria-label={ariaLabel} />
      <span
        className={`flex h-5 w-5 items-center justify-center rounded-md border transition-all duration-200 ${
          checked
            ? 'border-fuchsia-400 bg-fuchsia-400 shadow-[0_0_12px_rgba(45,212,191,0.45)]'
            : 'border-white/20 bg-[#0A1929] hover:border-white/40'
        }`}
      >
        {checked && (
          <svg className="h-3.5 w-3.5 text-[#063b30]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        )}
      </span>
    </label>
  );
}

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

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const ids = useMemo(() => items.map((i) => i.id), [items]);
  const allSelected = ids.length > 0 && selected.size === ids.length;
  const someSelected = selected.size > 0;

  const toggleOne = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    setSelected((prev) =>
      prev.size === ids.length && ids.length > 0 ? new Set() : new Set(ids)
    );
  }, [ids]);

  const deleteSelected = async () => {
    if (selected.size === 0) return;
    const idsToDelete = Array.from(selected);
    setBusy(true);
    try {
      const { data } = await api.delete('/user/history', { data: { record_ids: idsToDelete } });
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
    <>
      <Navbar user={user} onLogout={onLogout} active="history" />
      <div className="dashboard">
        <div className="mb-6">
          <h2>{t('history.title')}</h2>
          <p className="mt-1 text-sm text-slate-300">
            {t('history.subtitle')}
          </p>
        </div>

        <div className="sticky top-20 z-30 mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-[#0F2D3D]/80 px-4 py-3 shadow-lg shadow-black/30 backdrop-blur-2xl">
           <Checkbox checked={allSelected} onChange={toggleAll} ariaLabel={t('history.selectAll')} />
           <span className="select-none text-sm text-slate-300">{t('history.selectAll')}</span>
           <span className="text-sm text-slate-500">·</span>
           <span className="text-sm text-slate-400">{t('history.selected', { count: selected.size })}</span>

           <div className="ml-auto flex items-center gap-3">
             <button
               onClick={deleteSelected}
               disabled={!someSelected || busy}
               className="inline-flex items-center gap-2 rounded-xl border border-fuchsia-500/30 bg-gradient-to-r from-fuchsia-400/10 to-fuchsia-400/10 px-4 py-2 text-sm font-semibold text-fuchsia-100 transition-all duration-200 ease-out hover:border-fuchsia-400/50 hover:from-fuchsia-400/20 hover:to-fuchsia-400/20 hover:shadow-[0_0_22px_rgba(45,212,191,0.25)] active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:shadow-none disabled:active:scale-100"
             >
               {t('history.deleteSelected')}
             </button>
             <button
               onClick={clearAll}
               disabled={items.length === 0 || busy}
               className="inline-flex items-center gap-2 rounded-xl border border-rose-500/30 bg-gradient-to-r from-rose-500/10 to-red-500/10 px-4 py-2 text-sm font-semibold text-rose-200 transition-all duration-200 ease-out hover:border-rose-400/50 hover:from-rose-500/20 hover:to-red-500/20 hover:shadow-[0_0_22px_rgba(244,63,94,0.25)] active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
             >
               {t('history.clearAll')}
             </button>
           </div>
         </div>

         {loading ? (
           <div className="rounded-2xl border border-white/10 bg-[#0F2D3D]/60 px-4 py-10 text-center text-slate-400">
             {t('history.loading')}
           </div>
         ) : items.length === 0 ? (
           <div className="flex flex-col items-center gap-2 rounded-2xl border border-white/10 bg-[#0F2D3D]/60 px-4 py-16 text-center">
             <span className="text-3xl text-fuchsia-300/80">✦</span>
             <p className="text-slate-300">{t('history.noActivity')}</p>
             <p className="text-sm text-slate-400">{t('history.noActivityHint')}</p>
           </div>
         ) : (
          <div className="flex flex-col gap-2">
             {items.map((item) => {
                const metaIcon = TYPE_ICON[item.type] || '•';
                const metaLabel = t('history.type.' + item.type);
               const isSel = selected.has(item.id);
               return (
                 <div
                   key={item.id}
                   className={`group flex items-center gap-4 rounded-2xl border px-4 py-4 transition-all duration-200 ${
                     isSel ? 'border-fuchsia-400/40 bg-fuchsia-400/[0.06]' : 'border-white/10 bg-[#0F2D3D]/60 hover:border-white/20'
                   }`}
                 >
                    <Checkbox checked={isSel} onChange={() => toggleOne(item.id)} ariaLabel={t('history.selectItem', { title: item.title })} />
                   <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-lg">
                     {metaIcon}
                   </div>
                   <div className="min-w-0 flex-1">
                     <div className="truncate font-semibold text-white">{item.title || metaLabel}</div>
                     {item.detail && <div className="truncate text-sm text-slate-400">{item.detail}</div>}
                   </div>
                   <div className="shrink-0 text-xs text-slate-500">{formatDate(item.created_at, language)}</div>
                 </div>
               );
             })}
          </div>
        )}
      </div>
    </>
  );
}
