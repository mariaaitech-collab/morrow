import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Bell, CheckCheck, ShieldAlert } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { isAuthenticated } from '../auth';
import { formatLocal, timeAgo } from '../utils/time';
import { Badge, Button, IconButton } from './ui';
import './NotificationBell.css';

const POLL_MS = 30000;

export default function NotificationBell() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const lastUnread = useRef(null);
  const boxRef = useRef(null);

  const load = useCallback(async () => {
    if (!isAuthenticated()) return;
    try {
      const { data } = await api.get('/responder/notifications');
      setItems(data.items || []);
      setUnread(data.unread || 0);
      if (lastUnread.current !== null && data.unread > lastUnread.current) {
        const newest = (data.items || []).find((n) => !n.read);
        if (newest) toast(newest.title, { icon: newest.type === 'reply_failed' ? '⚠️' : '🛡️' });
        window.dispatchEvent(new CustomEvent('brandora:responder-updated'));
      }
      lastUnread.current = data.unread || 0;
    } catch {
      /* the bell must never break the page */
    }
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(() => { if (document.visibilityState === 'visible') load(); }, POLL_MS);
    const refresh = () => load();
    window.addEventListener('brandora:notifications-refresh', refresh);
    return () => { window.clearInterval(id); window.removeEventListener('brandora:notifications-refresh', refresh); };
  }, [load]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [open]);

  const markAll = async () => {
    try {
      await api.post('/responder/notifications/read', {});
      setItems((list) => list.map((n) => ({ ...n, read: true })));
      setUnread(0);
      lastUnread.current = 0;
    } catch { /* ignore */ }
  };

  const openItem = async (n) => {
    setOpen(false);
    if (!n.read) {
      api.post('/responder/notifications/read', { ids: [n.id] }).catch(() => {});
      setItems((list) => list.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
      setUnread((u) => Math.max(0, u - 1));
      lastUnread.current = Math.max(0, (lastUnread.current || 1) - 1);
    }
    navigate('/ai-responder?tab=queue');
  };

  return (
    <div className="m-bell" ref={boxRef}>
      <IconButton
        icon={Bell}
        label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((o) => !o)}
      />
      {unread > 0 && <span className="m-bell__dot" aria-hidden="true" />}
      {open && (
        <div className="m-popover m-bell__panel" role="dialog" aria-label="Notifications">
          <div className="m-bell__head">
            <p className="m-bell__title">Alerts</p>
            {unread > 0 && <Badge tone="accent">{unread} unread</Badge>}
          </div>
          {items.length === 0 ? (
            <p className="m-bell__empty">No alerts yet. Messages that need your approval show up here.</p>
          ) : (
            <ul className="m-bell__list">
              {items.map((n) => {
                const failed = n.type === 'reply_failed';
                const Icon = failed ? AlertTriangle : ShieldAlert;
                return (
                  <li key={n.id}>
                    <button type="button" className="m-bell__item" onClick={() => openItem(n)}>
                      <span className={`m-bell__icon m-bell__icon--${failed ? 'danger' : 'warning'}`} aria-hidden="true">
                        <Icon size={16} strokeWidth={1.5} />
                      </span>
                      <span className="m-bell__copy">
                        <strong>{n.title}</strong>
                        <span>{n.body}</span>
                        <time dateTime={n.created_at} title={formatLocal(n.created_at)}>{timeAgo(n.created_at)}</time>
                      </span>
                      {!n.read && <span className="m-bell__unread"><span className="m-sr-only">Unread</span></span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="m-bell__foot">
            {unread > 0 && <Button variant="ghost" icon={CheckCheck} onClick={markAll}>Mark all read</Button>}
            <Button variant="ghost" onClick={() => { setOpen(false); navigate('/ai-responder?tab=queue'); }}>
              Open approval queue
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
