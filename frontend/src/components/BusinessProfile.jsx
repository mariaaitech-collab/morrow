import { useEffect, useState } from 'react';
import { Check, Pencil, Save, Users, X } from 'lucide-react';
import { FaFacebookF, FaInstagram, FaLinkedinIn, FaTiktok } from 'react-icons/fa';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';

const EMPTY_PROFILE = { business_name: '', business_type: '', industry: '', bio: '', website: '', location: '' };
const PLATFORM_ICONS = { facebook: <FaFacebookF />, linkedin: <FaLinkedinIn />, instagram: <FaInstagram />, tiktok: <FaTiktok /> };

export default function BusinessProfile({ user, accounts = [], onProfileSaved, onAccountsChanged }) {
  const { t } = useLanguage();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState({ ...EMPTY_PROFILE, ...(user?.profile || {}) });
  const [draft, setDraft] = useState(profile);

  useEffect(() => {
    const next = { ...EMPTY_PROFILE, ...(user?.profile || {}) };
    setProfile(next);
    if (!editing) setDraft(next);
  }, [user?.profile, editing]);

  const setField = (field) => (event) => setDraft((current) => ({ ...current, [field]: event.target.value }));
  const startEditing = () => { setDraft(profile); setEditing(true); };
  const cancelEditing = () => { setDraft(profile); setEditing(false); };

  const handleConnect = async (platform) => {
    try {
      const { data } = await api.get(`/social/connect/${platform}`, { withCredentials: true }); // lets the API set the TikTok state cookie
      if (data.auth_url) window.location.href = data.auth_url;
      else toast.error(t('profile.connectionFailed'));
    } catch (error) {
      toast.error(error.response?.data?.detail || t('profile.connectionFailed'));
    }
  };

  const handleDisconnect = async (platform) => {
    try {
      await api.delete(`/social/disconnect/${platform}`);
      toast.success(t('profile.disconnected', { platform }));
      const { data } = await api.get('/social/accounts');
      onAccountsChanged?.(Array.isArray(data) ? data : []);
      onProfileSaved?.(profile);
    } catch (error) {
      toast.error(error.response?.data?.detail || t('profile.disconnectFailed'));
    }
  };

  const saveProfile = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.patch('/user/profile', draft);
      const next = { ...EMPTY_PROFILE, ...(data.profile || draft) };
      setProfile(next);
      setDraft(next);
      setEditing(false);
      onProfileSaved?.(next);
      toast.success(t('profile.saved'));
    } catch (error) {
      toast.error(error.response?.data?.detail || t('profile.saveError'));
    } finally {
      setSaving(false);
    }
  };

  const connected = accounts.filter((account) => account.connected);
  const displayName = profile.business_name || t('profile.businessNameFallback');
  const initials = displayName.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word[0]).join('').toUpperCase() || 'B';

  return (
    <section className="business-profile-section" id="business-profile">
      <div className="business-profile-heading">
        <div><span className="eyebrow">{t('profile.eyebrow')}</span><h1>{t('profile.title')}</h1><p>{t('profile.subtitle')}</p></div>
        {!editing ? <button className="profile-edit-button" onClick={startEditing}><Pencil size={15} /> {t('profile.edit')}</button> : <button className="profile-edit-button" onClick={cancelEditing}><X size={15} /> {t('profile.cancel')}</button>}
      </div>
      {!editing ? (
        <div className="business-profile-card">
          <div className="business-profile-identity"><div className="business-profile-avatar">{initials}</div><div><h4>{displayName}</h4><p>{profile.business_type || t('profile.businessTypeFallback')}{profile.industry ? ` · ${profile.industry}` : ''}</p>{profile.location && <span>{profile.location}</span>}</div></div>
          {profile.bio && <p className="business-profile-bio">{profile.bio}</p>}
          <div className="business-profile-details">
            <div><span>{t('profile.owner')}</span><strong>{user?.username || t('profile.notAvailable')}</strong></div>
            <div><span>{t('profile.email')}</span><strong>{user?.email || t('profile.notAvailable')}</strong></div>
            <div><span>{t('profile.website')}</span><strong>{profile.website || t('profile.notAdded')}</strong></div>
          </div>
          <div className="profile-channels"><div className="profile-subheading"><span>{t('profile.connectedChannels')}</span><strong>{connected.length}/{accounts.length}</strong></div><div className="profile-channel-list">{accounts.length === 0 ? <span className="profile-muted">{t('profile.channelsLoading')}</span> : accounts.map((account) => <div className={`profile-channel ${account.connected ? 'connected' : ''}`} key={account.platform}><span className={`profile-channel-icon ${account.platform}`}>{PLATFORM_ICONS[account.platform] || <Users size={16} />}</span><span>{account.account_name || account.platform}</span>{account.connected ? <><Check size={15} /><button type="button" className="profile-channel-action disconnect" onClick={() => handleDisconnect(account.platform)}>{t('profile.disconnect')}</button></> : <button type="button" className="profile-channel-action" onClick={() => handleConnect(account.platform)}>{t('profile.connect')}</button>}</div>)}</div></div>
        </div>
      ) : (
        <form className="business-profile-card profile-form" onSubmit={saveProfile}>
          <div className="profile-form-grid">
            <label>{t('profile.businessName')}<input value={draft.business_name} onChange={setField('business_name')} placeholder={t('profile.businessNamePlaceholder')} /></label>
            <label>{t('profile.businessType')}<input value={draft.business_type} onChange={setField('business_type')} placeholder={t('profile.businessTypePlaceholder')} /></label>
            <label>{t('profile.industry')}<input value={draft.industry} onChange={setField('industry')} placeholder={t('profile.industryPlaceholder')} /></label>
            <label>{t('profile.location')}<input value={draft.location} onChange={setField('location')} placeholder={t('profile.locationPlaceholder')} /></label>
            <label>{t('profile.website')}<input type="url" value={draft.website} onChange={setField('website')} placeholder={t('profile.websitePlaceholder')} /></label>
            <label className="profile-form-wide">{t('profile.bio')}<textarea rows="3" value={draft.bio} onChange={setField('bio')} placeholder={t('profile.bioPlaceholder')} /></label>
          </div>
          <div className="profile-form-actions"><span>{t('profile.connectedChannelsHint')}</span><button className="btn btn-primary" disabled={saving}>{saving ? t('profile.saving') : <><Save size={16} /> {t('profile.save')}</>}</button></div>
        </form>
      )}
    </section>
  );
}
