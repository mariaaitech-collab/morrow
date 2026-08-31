import { useState, useEffect } from 'react';
import { useLanguage } from '../i18n/LanguageContext';

// Manual Pro activation is handled by the administrator only — there is no
// automated payment gateway. Every blocked Pro request points here.
const ADMIN_EMAIL = 'meveryx@gmail.com';

function getRegisteredEmail() {
  try {
    const raw = localStorage.getItem('brandora_user');
    if (!raw) return '';
    const u = JSON.parse(raw);
    return u && u.email ? u.email : '';
  } catch {
    return '';
  }
}

export default function UpgradeModal() {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onRequired = () => setOpen(true);
    window.addEventListener('brandora:upgrade-required', onRequired);
    return () => window.removeEventListener('brandora:upgrade-required', onRequired);
  }, []);

  if (!open) return null;

  const email = getRegisteredEmail();
  const mailto = `mailto:${ADMIN_EMAIL}?subject=${encodeURIComponent('BrandAura Pro Activation')}&body=${encodeURIComponent(
    `Hello admin,\n\nI would like to upgrade to BrandAura Pro ($29/mo).\nMy registered email is: ${email}\n\nThank you!`
  )}`;

  return (
    <div className="upgrade-modal-overlay" onClick={() => setOpen(false)}>
      <div className="upgrade-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <h3>{t('dashboard.upgradeTitle')}</h3>
        <div className="upgrade-admin-box">
          <p className="upgrade-admin-msg">{t('dashboard.upgradeMessage', { email: ADMIN_EMAIL })}</p>
          <a className="btn btn-primary btn-lg" href={mailto}>
            {t('dashboard.contactAdmin')}
          </a>
        </div>
        <div className="upgrade-actions">
          <button className="btn btn-outline btn-lg" onClick={() => setOpen(false)}>
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );
}
