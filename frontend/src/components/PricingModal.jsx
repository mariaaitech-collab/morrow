import { useState, useEffect } from 'react';
import { useLanguage } from '../i18n/LanguageContext';

// Freemium token paywall — Static: Free / Standard / Premium.
// Checkout is NOT wired yet. BrandAura is in development mode, so clicking an
// upgrade button shows a professional "contact us for manual activation"
// message instead of a broken payment link.
const ADMIN_EMAIL = 'meveryx@gmail.com';

const PLANS = [
  {
    id: 'free',
    name: 'Freemium',
    price: '$0',
    per: 'forever',
    tokens: '3 free tokens',
    color: 'var(--color-text-muted)',
    features: [
      'AI content generator (3 uses)',
      'AI image generation (3 uses)',
      'Manual post publishing',
    ],
  },
  {
    id: 'standard',
    name: 'Standard',
    price: '$1.99',
    per: `~${500} PKR · 14 days`,
    tokens: '50 tokens',
    color: 'var(--color-primary)',
    featured: true,
    features: [
      '50 content / image / auto-post actions',
      'Scheduled & calendar posts',
      'Competitive analysis',
    ],
  },
  {
    id: 'premium',
    name: 'Premium',
    price: '$3.99',
    per: `~${1000} PKR · 30 days`,
    tokens: '150 tokens',
    color: '#E8558C',
    features: [
      '150 content / image / auto-post actions',
      'Everything in Standard',
      'Priority support & future features',
    ],
  },
];

function getCurrentUser() {
  try {
    const raw = localStorage.getItem('brandora_user');
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export default function PricingModal() {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState(getCurrentUser);
  const [selectedPlan, setSelectedPlan] = useState(null);

  useEffect(() => {
    const syncUser = () => setUser(getCurrentUser());
    const onRequired = () => setOpen(true);
    window.addEventListener('brandora:upgrade-required', onRequired);
    window.addEventListener('brandora:tokens-updated', syncUser);
    window.addEventListener('storage', syncUser);
    return () => {
      window.removeEventListener('brandora:upgrade-required', onRequired);
      window.removeEventListener('brandora:tokens-updated', syncUser);
      window.removeEventListener('storage', syncUser);
    };
  }, []);

  if (!open) return null;

  const currentPlan = user?.plan || 'trial';

  const mailto = `mailto:${ADMIN_EMAIL}?subject=${encodeURIComponent(
    'BrandAura Plan Activation Request'
  )}&body=${encodeURIComponent(
    `Hello BrandAura team,\n\nI would like to activate the "${selectedPlan?.name}" plan.\nMy registered email is: ${user?.email || ''}\n\nThank you!`
  )}`;

  return (
    <div className="upgrade-modal-overlay" onClick={() => setOpen(false)}>
      <div className="pricing-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">

        {selectedPlan ? (
          <div className="pricing-contact">
            <div className="pricing-contact-icon">✦</div>
            <span className="pricing-contact-plan">
              {selectedPlan.name} · {selectedPlan.price} · {selectedPlan.tokens}
            </span>
            <h3 className="pricing-contact-title">Development Mode</h3>
            <p className="pricing-contact-msg">
              BrandAura is currently in development mode. To activate your{' '}
              <strong>{selectedPlan.name}</strong> plan, please contact us at{' '}
              <a className="pricing-contact-email" href={mailto}>{ADMIN_EMAIL}</a>{' '}
              and our team will manually upgrade your account.
            </p>
            <div className="pricing-contact-actions">
              <a className="btn btn-primary btn-lg" href={mailto}>
                Contact our team
              </a>
              <button
                className="btn btn-glass btn-lg"
                onClick={() => setSelectedPlan(null)}
              >
                Back to plans
              </button>
            </div>
          </div>
        ) : (
          <>
            <button className="pricing-close" aria-label="Close" onClick={() => setOpen(false)}>
              ×
            </button>
            <h3 className="pricing-title">Choose your plan</h3>
            <p className="pricing-sub">
              Every core action (AI content, image generation, auto-post) uses{' '}
              <strong>1 token</strong>. Upgrading adds more tokens so you can keep creating.
            </p>

            <div className="pricing-grid">
              {PLANS.map((plan) => {
                const isCurrent = currentPlan === plan.id;
                return (
                  <div
                    key={plan.id}
                    className={`pricing-card ${plan.featured ? 'pricing-featured' : ''} ${isCurrent ? 'pricing-current' : ''}`}
                    style={{ '--tier-color': plan.color }}
                  >
                    {plan.featured && <span className="pricing-ribbon">Popular</span>}
                    {isCurrent && <span className="pricing-current-tag">Current</span>}
                    <h4 className="pricing-name">{plan.name}</h4>
                    <div className="pricing-price">{plan.price}</div>
                    <div className="pricing-per">{plan.per}</div>
                    <div className="pricing-tokens">{plan.tokens}</div>
                    <ul className="pricing-feats">
                      {plan.features.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                    {plan.id === 'free' ? (
                      <button className="btn btn-glass btn-lg" disabled>
                        Current — Free
                      </button>
                    ) : (
                      <button
                        className="btn btn-primary btn-lg"
                        onClick={() => setSelectedPlan(plan)}
                      >
                        {isCurrent ? 'Extend tokens' : `Upgrade · ${plan.price}`}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>

            <p className="pricing-note">
              You keep any unused tokens — upgrading adds to your balance.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
