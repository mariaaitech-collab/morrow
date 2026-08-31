import { useState } from 'react';
import { useLanguage } from '../i18n/LanguageContext';

const PLATFORMS = [
  {
    key: 'instagram',
    label: 'Instagram',
    name: 'BrandAura',
    handle: '@brandaura',
    avatar: 'BA',
    accent: 'linear-gradient(45deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888)',
    ratio: '1 / 1',
    limit: 2200,
  },
  {
    key: 'linkedin',
    label: 'LinkedIn',
    name: 'BrandAura',
    handle: 'BrandAura · Company',
    avatar: 'BA',
    accent: 'linear-gradient(135deg,#0a66c2,#004182)',
    ratio: '1.91 / 1',
    limit: 3000,
  },
  {
    key: 'facebook',
    label: 'Facebook',
    name: 'BrandAura',
    handle: 'BrandAura',
    avatar: 'BA',
    accent: 'linear-gradient(135deg,#1877f2,#0a66c2)',
    ratio: '4 / 3',
    limit: 63206,
  },
];

function PreviewCard({ platform, caption, mediaUrl, mediaType }) {
  const { t, language } = useLanguage();
  const count = caption ? caption.length : 0;
  const over = count > platform.limit;
  const pct = Math.min(100, (count / platform.limit) * 100);
  const handle = platform.key === 'linkedin' ? t('platformPreview.companyHandle') : platform.handle;
  return (
    <div className="pp-card">
      <div className="pp-head">
        <div className="pp-avatar" style={{ background: platform.accent }}>{platform.avatar}</div>
        <div>
          <div className="pp-name">
            {platform.name} <span className="pp-verified">✓</span>
          </div>
          <div className="pp-handle">{handle}</div>
        </div>
      </div>
      <div className="pp-media empty" style={{ aspectRatio: platform.ratio }}>
        {mediaUrl ? (
          mediaType === 'video' ? (
            <video src={mediaUrl} muted playsInline />
          ) : (
            <img src={mediaUrl} alt={t('platformPreview.previewAlt')} decoding="async" />
          )
        ) : (
          <span>{t('platformPreview.noMedia')}</span>
        )}
      </div>
      <div className="pp-body">
        <p className="pp-caption">{caption || t('platformPreview.addCaption')}</p>
        <div className={`pp-counter ${over ? 'over' : ''}`}>
          <span className="count">{count.toLocaleString(language)}</span>
          <span className="bar"><i style={{ width: `${pct}%` }} /></span>
          <span>{t('platformPreview.maxChars', { count: platform.limit.toLocaleString(language) })}</span>
        </div>
      </div>
    </div>
  );
}

export default function PlatformPreview({ caption = '', mediaUrl = null, mediaType = null }) {
  const [active, setActive] = useState('instagram');
  const platform = PLATFORMS.find((p) => p.key === active) || PLATFORMS[0];
  return (
    <div className="pp">
      <div className="pp-tabs">
        {PLATFORMS.map((p) => (
          <button
            key={p.key}
            className={`pp-tab ${active === p.key ? 'active' : ''}`}
            onClick={() => setActive(p.key)}
          >
            <span className="pp-ico" style={{ background: p.accent }}>{p.avatar}</span>
            {p.label}
          </button>
        ))}
      </div>
      <PreviewCard platform={platform} caption={caption} mediaUrl={mediaUrl} mediaType={mediaType} />
    </div>
  );
}
