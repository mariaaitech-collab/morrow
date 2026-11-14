import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import WorkspaceShell from '../components/WorkspaceShell';
import BusinessProfile from '../components/BusinessProfile';

export default function Profile({ user, onLogout }) {
  const { t } = useLanguage();
  const [profileUser, setProfileUser] = useState(user);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.get('/auth/me'), api.get('/social/accounts')])
      .then(([userResponse, accountsResponse]) => {
        if (cancelled) return;
        setProfileUser({ ...user, ...userResponse.data });
        setAccounts(Array.isArray(accountsResponse.data) ? accountsResponse.data : []);
      })
      .catch((error) => {
        if (!cancelled && error.response?.status !== 401) toast.error(t('profile.loadError'));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <WorkspaceShell user={profileUser} onLogout={onLogout} active="profile">
      <div className="m-page profile-page">
        {loading ? <div className="profile-page-loading">{t('common.loading')}</div> : <BusinessProfile user={profileUser} accounts={accounts} onProfileSaved={(profile) => setProfileUser((current) => ({ ...current, profile }))} onAccountsChanged={setAccounts} />}
      </div>
    </WorkspaceShell>
  );
}
