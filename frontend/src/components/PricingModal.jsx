import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { useLanguage } from '../i18n/LanguageContext';
import { useDialog } from './ui';

// Freemium token paywall — Static: Free / Standard / Premium.
// Checkout is NOT wired yet. Morrow is in development mode, so clicking an
// upgrade button shows a professional "contact us for manual activation"
// message instead of a broken payment link.
const ADMIN_EMAIL = 'meveryx@gmail.com';

const PLANS = [
  {
    id: 'starter',
    name: 'Starter',
    price: '1,200 PKR',
    per: '1,000 – 1,500 PKR · 30 days',
    tokens: '50 credits',
    tier: 'starter',
    features: [
      '50 AI content & image generation credits',
      'Multi-platform caption studio (Instagram, LinkedIn, FB)',
      'Scheduled & calendar post planning',
      'Live platform post previews',
      'Standard AI generation speed',
    ],
  },
  {
    id: 'plus',
    name: 'Plus',
    price: '2,800 PKR',
    per: '2,000 – 4,000 PKR · 30 days',
    tokens: '150 credits',
    tier: 'plus',
    featured: true,
    features: [
      '150 AI content & image generation credits',
      'Everything in Starter plan',
      'Brand voice presets & tone customization',
      'Automated recurring post scheduler',
      'Competitive hashtag & trend analysis',
      'Priority queue & faster processing',
    ],
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: '6,500 PKR',
    per: 'Starting 6,000+ PKR · Custom tailored',
    tokens: '500+ credits',
    tier: 'enterprise',
    features: [
      '500+ credits / Custom monthly allotment',
      'Everything in Plus plan',
      'Multi-brand workspaces & team collaboration',
      'Custom fine-tuned AI prompts & API access',
      'Dedicated Account Manager & SLA guarantee',
      '24/7 priority VIP assistance',
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
  const dialogRef = useDialog(open, () => setOpen(false));

  useEffect(() => {
    const syncUser = () => setUser(getCurrentUser());
    const onRequired = (e) => {
      setOpen(true);
      if (e?.detail?.planId) {
        const found = PLANS.find((p) => p.id === e.detail.planId);
        if (found) setSelectedPlan(found);
      }
    };
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

  const userPlan = (user?.plan || 'trial').toLowerCase();

  const mailto = `mailto:${ADMIN_EMAIL}?subject=${encodeURIComponent(
    `Morrow ${selectedPlan?.name || 'Plan'} Activation Request (${selectedPlan?.tokens || ''})`
  )}&body=${encodeURIComponent(
    `Hello Morrow team,\n\nI would like to activate the ${selectedPlan?.name} plan (${selectedPlan?.tokens} for ${selectedPlan?.price}).\nMy registered account email is: ${user?.email || ''}\n\nThank you!`
  )}`;

  return (
    <div className="upgrade-modal-overlay" onClick={() => setOpen(false)}>
      <div className="pricing-modal" ref={dialogRef} tabIndex={-1} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="pricing-title">

        {selectedPlan ? (
          <div className="pricing-modal__body pricing-contact">
            <div className="pricing-contact-icon">✦</div>
            <span className="pricing-contact-plan">
              {selectedPlan.name} · {selectedPlan.price} · {selectedPlan.tokens}
            </span>
            <h3 className="pricing-contact-title" id="pricing-title">Development Mode</h3>
            <p className="pricing-contact-msg">
              Morrow is currently in development mode. To activate your{' '}
              <strong>{selectedPlan.name}</strong> plan ({selectedPlan.tokens} for {selectedPlan.price}), please contact us at{' '}
              <a className="pricing-contact-email" href={mailto}>{ADMIN_EMAIL}</a>{' '}
              and our team will manually upgrade your account.
            </p>
            <div className="pricing-contact-actions">
              <a className="btn btn-primary btn-lg" href={mailto}>
                Contact our team
              </a>
              <button
                type="button"
                className="btn btn-glass btn-lg"
                onClick={() => setSelectedPlan(null)}
              >
                Back to plans
              </button>
            </div>
          </div>
        ) : (
          <>
            <header className="pricing-modal__head">
              <div>
                <h3 className="pricing-title" id="pricing-title">Choose your plan</h3>
                <p className="pricing-sub">
                  Every core action (AI content, image generation, auto-post) uses{' '}
                  <strong>1 credit</strong>. Upgrading adds more credits so you can keep creating without interruptions.
                </p>
              </div>
              <button type="button" className="pricing-close" aria-label="Close" onClick={() => setOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>

            <div className="pricing-modal__body">
            <div className="pricing-grid">
              {PLANS.map((plan) => {
                const isCurrent = userPlan === plan.id ||
                  (plan.id === 'starter' && userPlan === 'standard') ||
                  (plan.id === 'plus' && userPlan === 'premium') ||
                  (plan.id === 'enterprise' && (userPlan === 'pro' || userPlan === 'enterprise'));
                return (
                  <div
                    key={plan.id}
                    className={`pricing-card pricing-card--${plan.tier} ${plan.featured ? 'pricing-featured' : ''} ${isCurrent ? 'pricing-current' : ''}`}
                  >
                    {plan.featured && <span className="pricing-ribbon">Most Popular</span>}
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
                    <button
                      type="button"
                      className={`btn btn-lg ${plan.featured ? 'btn-purple' : 'btn-primary'}`}
                      onClick={() => setSelectedPlan(plan)}
                    >
                      {isCurrent ? 'Extend credits' : `Choose · ${plan.price}`}
                    </button>
                  </div>
                );
              })}
            </div>
            </div>

            <footer className="pricing-modal__foot">
              <p className="pricing-note">
                You keep any unused credits — upgrading adds to your balance.
              </p>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
