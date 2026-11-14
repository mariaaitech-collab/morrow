import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import WorkspaceShell from '../components/WorkspaceShell';
import ContentGenerator from '../components/ContentGenerator';

export default function Create({ user, onLogout }) {
  const { t } = useLanguage();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchAccounts = async () => {
      try {
        const { data } = await api.get('/social/accounts');
        if (!cancelled) setAccounts(data);
      } catch (err) {
        if (!cancelled) {
          const detail = err.response?.data?.detail || err.message || t('dashboard.loadAccountsError');
          toast.error(detail);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchAccounts();
    return () => {
      cancelled = true;
    };
  }, [t]);

  return (
    <WorkspaceShell user={user} onLogout={onLogout} active="create">
      <div className="m-page create-page">
        <div className="create-page__content">
          <ContentGenerator accounts={accounts} />
        </div>
      </div>
    </WorkspaceShell>
  );
}
