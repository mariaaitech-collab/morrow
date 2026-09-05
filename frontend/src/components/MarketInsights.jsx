import { useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import { useDraft } from '../draft/DraftContext';

const PREMIUM_BTN =
  'bg-gradient-to-r from-fuchsia-400/10 to-fuchsia-400/10 text-fuchsia-100 border border-fuchsia-500/30 transition-all duration-200 ease-out hover:from-fuchsia-400/20 hover:to-fuchsia-400/20 hover:border-fuchsia-400/50 hover:shadow-[0_0_22px_rgba(45,212,191,0.25)] active:scale-95';

const PLATFORM_META = {
  linkedin: { badge: 'badge-linkedin', label: 'LinkedIn' },
  instagram: { badge: 'badge-instagram', label: 'Instagram' },
  facebook: { badge: 'badge-facebook', label: 'Facebook' },
};

function MarketInsights() {
  const { t } = useLanguage();
  const { draft, setDraft } = useDraft();
  const [activePlatform, setActivePlatform] = useState('facebook');

  const profile = draft.brandProfile || {};
  const setProfile = (key) => (e) => setDraft({ brandProfile: { ...profile, [key]: e.target.value } });

  const togglePlatform = (p) => {
    const current = draft.selectedPlatforms || ['facebook', 'linkedin', 'instagram'];
    setDraft({
      selectedPlatforms: current.includes(p)
        ? current.filter((x) => x !== p)
        : [...current, p],
    });
  };

  const runScan = async () => {
    if (!(profile.niche || '').trim()) {
      toast.error(t('market.pleaseNiche'));
      return;
    }
    setDraft({ marketLoading: true, marketError: null, marketData: null });
    try {
      const formData = new FormData();
      formData.append('brand_niche', (profile.niche || '').trim());
      formData.append('target_audience', (profile.audience || '').trim());
      formData.append('business_type', (profile.businessType || '').trim());
      formData.append('core_offerings', (profile.offerings || '').trim());
      formData.append('location', (profile.location || '').trim());
      formData.append('topic', (draft.marketQuery || '').trim());
      formData.append('platforms', JSON.stringify(draft.selectedPlatforms || ['facebook', 'linkedin', 'instagram']));
      const { data } = await api.post('/market/competitor-insights', formData, { timeout: 300000 });
      setDraft({ marketData: data });
      toast.success(t('market.scanDone'));
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message || t('market.scanFailed');
      setDraft({ marketError: typeof detail === 'string' ? detail : t('market.scanFailed') });
      toast.error(typeof detail === 'string' ? detail : t('market.scanFailed'));
    } finally {
      setDraft({ marketLoading: false });
    }
  };

  const leaders = Array.isArray(draft.marketData?.market_leaders) ? draft.marketData.market_leaders : [];
  const positioning = Array.isArray(draft.marketData?.positioning_advice) ? draft.marketData.positioning_advice : [];
  const tactics = draft.marketData?.platform_tactics || {};
  const quickWins = Array.isArray(draft.marketData?.quick_wins) ? draft.marketData.quick_wins : [];

  return (
    <div className="market-panel">
      <div className="market-head">
        <div className="market-head-icon">📊</div>
        <div>
          <h4>{t('market.title')}</h4>
          <p>{t('market.subtitle')}</p>
        </div>
      </div>

      <div className="market-form">
        <div className="market-grid">
          <div className="form-group">
            <label>{t('market.niche')}</label>
            <input
              value={profile.niche || ''}
              onChange={setProfile('niche')}
              placeholder="e.g. Organic skincare for sensitive skin"
            />
          </div>
          <div className="form-group">
            <label>{t('market.audience')}</label>
            <input
              value={profile.audience || ''}
              onChange={setProfile('audience')}
              placeholder="e.g. Women 25-40, eczema-prone, clean beauty buyers"
            />
          </div>
          <div className="form-group">
            <label>{t('market.businessType')}</label>
            <input
              value={profile.businessType || ''}
              onChange={setProfile('businessType')}
              placeholder="e.g. DTC e-commerce brand"
            />
          </div>
          <div className="form-group">
            <label>{t('market.offerings')}</label>
            <input
              value={profile.offerings || ''}
              onChange={setProfile('offerings')}
              placeholder="e.g. Serums, moisturizers, 900+ 5-star reviews"
            />
          </div>
          <div className="form-group">
            <label>{t('market.location')}</label>
            <input
              value={profile.location || ''}
              onChange={setProfile('location')}
              placeholder={t('market.locationPlaceholder')}
            />
          </div>
          <div className="form-group">
            <label>{t('market.topicOptional')}</label>
            <input
              value={draft.marketQuery || ''}
              onChange={(e) => setDraft({ marketQuery: e.target.value })}
              placeholder={t('market.topicPlaceholder')}
            />
          </div>
        </div>

        <div className="form-group">
          <label>{t('market.platformsLabel')}</label>
          <div className="platform-selector">
            {['facebook', 'linkedin', 'instagram'].map((p) => (
              <button
                key={p}
                type="button"
                className={`platform-btn ${(draft.selectedPlatforms || []).includes(p) ? 'active' : ''}`}
                onClick={() => togglePlatform(p)}
              >
                <span className="platform-btn-icon">{p.charAt(0).toUpperCase()}</span>
                <span>{PLATFORM_META[p].label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="market-actions">
          <button className={"btn " + PREMIUM_BTN} onClick={runScan} disabled={draft.marketLoading}>
            {draft.marketLoading ? (
              <><span className="spinner-sm" /> {t('market.scanning')}</>
            ) : (
              t('market.scanBtn')
            )}
          </button>
        </div>
      </div>

      {draft.marketError && <div className="competitor-error">{draft.marketError}</div>}

      {draft.marketData && (
        <div className="strategy-results market-results">
          <div className="strategy-providers">
            <span className="live-chip">{t('market.liveChip')}</span>
            {t('market.scannedFor', {
              search: draft.marketData.providers?.search || 'Tavily',
              model: draft.marketData.providers?.analysis?.model || 'Gemini',
              count: draft.marketData.search_meta?.total_raw_results || 0,
            })}
          </div>

          {draft.marketData.market_overview && (
            <p className="market-overview">{draft.marketData.market_overview}</p>
          )}

          {leaders.length > 0 && (
            <section className="strategy-section">
              <div className="strategy-section-head">
                <span className="strategy-section-icon">🏆</span>
                <div>
                  <h5>{t('market.leaders')}</h5>
                  <p>{t('market.leadersSub')}</p>
                </div>
              </div>
              <div className="market-leader-list">
                {leaders.map((c, i) => (
                  <div className="market-leader-card" key={i}>
                    <div className="market-leader-top">
                      <strong>{c.name || t('market.unknownLeader')}</strong>
                      <span className={`platform-badge ${PLATFORM_META[c.platform]?.badge || 'badge-facebook'}`}>
                        {PLATFORM_META[c.platform]?.label || c.platform}
                      </span>
                    </div>
                    {c.positioning && <p className="market-leader-row"><b>{t('market.positioning')}:</b> {c.positioning}</p>}
                    {c.winning_move && <p className="market-leader-row good"><b>✓ {t('market.winning')}:</b> {c.winning_move}</p>}
                    {c.gap && <p className="market-leader-row warn"><b>✗ {t('market.gap')}:</b> {c.gap}</p>}
                    {c.link && (
                      <a href={c.link} target="_blank" rel="noreferrer" className="market-leader-link">
                        {t('market.openSource')} →
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {positioning.length > 0 && (
            <section className="strategy-section">
              <div className="strategy-section-head">
                <span className="strategy-section-icon">🧭</span>
                <div>
                  <h5>{t('market.positioningTitle')}</h5>
                  <p>{t('market.positioningSub')}</p>
                </div>
              </div>
              <ul className="analysis-list">
                {positioning.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </section>
          )}

          <section className="strategy-section">
            <div className="strategy-section-head">
              <span className="strategy-section-icon">🚀</span>
              <div>
                <h5>{t('market.tactics')}</h5>
                <p>{t('market.tacticsSub')}</p>
              </div>
            </div>
            <div className="tactics-tabs">
              {['facebook', 'instagram', 'linkedin'].map((p) => (
                <button
                  key={p}
                  className={`tactics-tab ${activePlatform === p ? 'active' : ''}`}
                  onClick={() => setActivePlatform(p)}
                >
                  {PLATFORM_META[p].label}
                </button>
              ))}
            </div>
            <ul className="analysis-list">
              {(tactics[activePlatform] || []).length === 0 ? (
                <li className="analysis-empty">{t('market.noTactics')}</li>
              ) : (
                (tactics[activePlatform] || []).map((s, i) => <li key={i}>{s}</li>)
              )}
            </ul>
          </section>

          {quickWins.length > 0 && (
            <section className="strategy-section">
              <div className="strategy-section-head">
                <span className="strategy-section-icon">⚡</span>
                <div>
                  <h5>{t('market.quickWins')}</h5>
                  <p>{t('market.quickWinsSub')}</p>
                </div>
              </div>
              <div className="bonus-list">
                {quickWins.map((w, i) => (
                  <div className="bonus-item" key={i}>
                    <div className="bonus-win"><b>{i + 1}.</b> {w}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

export default MarketInsights;