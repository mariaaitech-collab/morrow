import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';

const TYPE_ICON = {
  image_generation: '🎨',
  competitive_analysis: '📊',
  content_generation: '✍️',
  scheduled_post: '📅',
};

const fmtDate = (iso, locale) =>
  iso
    ? new Date(iso).toLocaleString(locale, {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      })
    : '';

export default function ActivityHistory() {
  const { t, language } = useLanguage();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);

  const fetchHistory = async () => {
    try {
      const { data } = await api.get('/user/history');
      setItems(data.items || []);
    } catch (err) {
      if (err.response?.status !== 401) {
        console.error('History load failed:', err);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const clearAll = async () => {
    if (!window.confirm(t('activityHistory.clearConfirm'))) return;
    setClearing(true);
    try {
      const { data } = await api.delete('/user/history');
      setItems([]);
      toast.success(t('activityHistory.cleared', { count: data.deleted_count }));
    } catch (err) {
      toast.error(err.response?.data?.detail || t('activityHistory.clearFailed'));
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="glass history-card">
      <div className="history-head">
        <h3>
          {t('activityHistory.title')}
          <span className="history-count">{t('activityHistory.records', { count: items.length })}</span>
        </h3>
        <button
          className="btn btn-sm bg-gradient-to-r from-rose-500/10 to-red-500/10 text-rose-200 border border-rose-500/30 transition-all duration-200 ease-out hover:from-rose-500/20 hover:to-red-500/20 hover:border-rose-400/50 hover:shadow-[0_0_22px_rgba(244,63,94,0.25)] active:scale-95"
          onClick={clearAll}
          disabled={clearing || items.length === 0}
          title={items.length === 0 ? t('activityHistory.nothingToClear') : t('activityHistory.clearAllTitle')}
        >
          {clearing ? <><span className="spinner-sm" /> {t('activityHistory.clearing')}</> : `🗑 ${t('activityHistory.clearAll')}`}
        </button>
      </div>

      {loading ? (
        <div className="history-empty">{t('common.loading')}</div>
      ) : items.length === 0 ? (
        <div className="history-empty">
          <span className="big">✦</span>
          {t('activityHistory.empty')}
        </div>
      ) : (
        <div className="history-list">
          {items.map((item) => {
            const icon = TYPE_ICON[item.type] || '•';
            const label = t('activityHistory.type_' + item.type);
            return (
              <div className="history-item" key={item.id}>
                <div className="history-icon">{icon}</div>
                <div className="history-body">
                  <h4>{item.title || label}</h4>
                  {item.detail && <span>{item.detail}</span>}
                </div>
                <div className="history-time">{fmtDate(item.created_at, language)}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}