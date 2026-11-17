import { useState } from 'react';
import toast from 'react-hot-toast';
import { BarChart3, ExternalLink, Globe2, Lightbulb, Rocket, Search, Target, Trophy } from 'lucide-react';
import api from '../api/axios';
import { useLanguage } from '../i18n/LanguageContext';
import { useDraft } from '../draft/DraftContext';

const PREMIUM_BTN = 'tech-action-btn transition-all duration-200 ease-out';

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

  const selectedPlatforms = draft.selectedPlatforms || ['facebook', 'linkedin', 'instagram'];
  const leaders = Array.isArray(draft.marketData?.market_leaders) ? draft.marketData.market_leaders : [];
  const matchingPosts = Array.isArray(draft.marketData?.matching_posts) ? draft.marketData.matching_posts : [];
  const positioning = Array.isArray(draft.marketData?.positioning_advice) ? draft.marketData.positioning_advice : [];
  const tactics = draft.marketData?.platform_tactics || {};
  const quickWins = Array.isArray(draft.marketData?.quick_wins) ? draft.marketData.quick_wins : [];

  return (
    <section className="market-panel">
      <div className="market-head">
        <div className="market-head-title">
          <span className="market-head-icon"><BarChart3 size={22} /></span>
          <div>
            <h4>{t('market.title')}</h4>
            <p>{t('market.subtitle')}</p>
          </div>
        </div>
        <span className="market-head-chip"><Globe2 size={14} /> Live market</span>
      </div>

      <div className="market-form">
        <div className="market-grid">
          <div className="form-group market-field market-field-wide">
            <label>{t('market.niche')}</label>
            <input value={profile.niche || ''} onChange={setProfile('niche')} placeholder="e.g. Organic skincare for sensitive skin" />
          </div>
          <div className="form-group market-field">
            <label>{t('market.audience')}</label>
            <input value={profile.audience || ''} onChange={setProfile('audience')} placeholder="e.g. Women 25-40, clean beauty buyers" />
          </div>
          <div className="form-group market-field">
            <label>{t('market.businessType')}</label>
            <input value={profile.businessType || ''} onChange={setProfile('businessType')} placeholder="e.g. DTC e-commerce brand" />
          </div>
          <div className="form-group market-field">
            <label>{t('market.offerings')}</label>
            <input value={profile.offerings || ''} onChange={setProfile('offerings')} placeholder="e.g. Serums, moisturizers, 900+ reviews" />
          </div>
          <div className="form-group market-field">
            <label>{t('market.location')}</label>
            <input value={profile.location || ''} onChange={setProfile('location')} placeholder={t('market.locationPlaceholder')} />
          </div>
          <div className="form-group market-field market-field-wide">
            <label>{t('market.topicOptional')}</label>
            <input value={draft.marketQuery || ''} onChange={(e) => setDraft({ marketQuery: e.target.value })} placeholder={t('market.topicPlaceholder')} />
          </div>
        </div>

        <div className="market-controls">
          <div className="market-platform-block">
            <label>{t('market.platformsLabel')}</label>
            <div className="market-platform-row">
              {['facebook', 'linkedin', 'instagram'].map((p) => (
                <button key={p} type="button" className={`market-platform-pill ${selectedPlatforms.includes(p) ? 'active' : ''}`} onClick={() => togglePlatform(p)}>
                  <span className={`market-platform-dot ${p}`} />
                  <span>{PLATFORM_META[p].label}</span>
                </button>
              ))}
            </div>
          </div>
          <button className={`btn ${PREMIUM_BTN}`} onClick={runScan} disabled={draft.marketLoading}>
            {draft.marketLoading ? <><span className="spinner-sm" /> {t('market.scanning')}</> : <><Search size={16} /> {t('market.scanBtn')}</>}
          </button>
        </div>
      </div>

      {draft.marketError && <div className="competitor-error market-error">{draft.marketError}</div>}

      {draft.marketData && (
        <div className="strategy-results market-results">
          <div className="strategy-providers market-scan-meta">
            <span className="live-chip">{t('market.liveChip')}</span>
            <span>{t('market.scannedFor', {
              search: draft.marketData.providers?.search || 'Tavily',
              model: draft.marketData.providers?.analysis?.model || 'Gemini',
              count: draft.marketData.search_meta?.total_raw_results || 0,
            })}</span>
          </div>

          {draft.marketData.market_overview && (
            <div className="market-overview">
              <strong>{t('market.marketOverview')}</strong>
              <p>{draft.marketData.market_overview}</p>
            </div>
          )}

          {matchingPosts.length > 0 && (
            <section className="strategy-section market-result-section market-matches">
              <div className="strategy-section-head">
                <span className="strategy-section-icon"><Search size={18} /></span>
                <div>
                  <h5>Posts matching “{draft.marketData.query || draft.marketQuery || profile.niche}”</h5>
                  <p>{draft.marketData.search_meta?.exact_results || 0} exact matches · {draft.marketData.search_meta?.related_results || 0} related posts. Unrelated results are filtered out.</p>
                </div>
              </div>
              <div className="market-source-list">
                {matchingPosts.map((post, i) => (
                  <article className="market-source-card" key={`${post.platform}-${post.url || i}`}>
                    <div className="market-source-meta">
                      <span className={`platform-badge ${PLATFORM_META[post.platform]?.badge || 'badge-facebook'}`}>{PLATFORM_META[post.platform]?.label || post.platform}</span>
                      <span className={`market-match-badge ${post.match_type === 'exact' ? 'exact' : 'related'}`}>{post.match_type === 'exact' ? 'Exact match' : 'Related post'}</span>
                    </div>
                    <strong>{post.title || post.url}</strong>
                    {post.snippet && <p>{post.snippet}</p>}
                    {post.match_type === 'related' && <small>Related because it mentions: {(post.matched_terms || []).join(', ') || 'some of your topic'}</small>}
                    {post.search_url && <a href={post.search_url} target="_blank" rel="noreferrer" className="market-leader-link">Find on {PLATFORM_META[post.platform]?.label || post.platform} <ExternalLink size={13} /></a>}
                  </article>
                ))}
              </div>
            </section>
          )}

          {leaders.length > 0 && (
            <section className="strategy-section market-result-section">
              <div className="strategy-section-head">
                <span className="strategy-section-icon"><Trophy size={18} /></span>
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
                    {c.winning_move && <p className="market-leader-row good"><b>{t('market.winning')}:</b> {c.winning_move}</p>}
                    {c.gap && <p className="market-leader-row warn"><b>{t('market.gap')}:</b> {c.gap}</p>}
                    {(c.search_url || c.link) && (
                      <a href={c.search_url || c.link} target="_blank" rel="noreferrer" className="market-leader-link">
                        Search {PLATFORM_META[c.platform]?.label || c.platform} <ExternalLink size={13} />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {positioning.length > 0 && (
            <section className="strategy-section market-result-section">
              <div className="strategy-section-head">
                <span className="strategy-section-icon"><Target size={18} /></span>
                <div>
                  <h5>{t('market.positioningTitle')}</h5>
                  <p>{t('market.positioningSub')}</p>
                </div>
              </div>
              <ul className="analysis-list market-text-list">
                {positioning.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </section>
          )}

          <section className="strategy-section market-result-section">
            <div className="strategy-section-head">
              <span className="strategy-section-icon"><Rocket size={18} /></span>
              <div>
                <h5>{t('market.tactics')}</h5>
                <p>{t('market.tacticsSub')}</p>
              </div>
            </div>
            <div className="tactics-tabs market-tabs">
              {['facebook', 'instagram', 'linkedin'].map((p) => (
                <button key={p} className={`tactics-tab ${activePlatform === p ? 'active' : ''}`} onClick={() => setActivePlatform(p)}>
                  {PLATFORM_META[p].label}
                </button>
              ))}
            </div>
            <ul className="analysis-list market-text-list">
              {(tactics[activePlatform] || []).length === 0
                ? <li className="analysis-empty">{t('market.noTactics')}</li>
                : (tactics[activePlatform] || []).map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </section>

          {quickWins.length > 0 && (
            <section className="strategy-section market-result-section">
              <div className="strategy-section-head">
                <span className="strategy-section-icon"><Lightbulb size={18} /></span>
                <div>
                  <h5>{t('market.quickWins')}</h5>
                  <p>{t('market.quickWinsSub')}</p>
                </div>
              </div>
              <div className="bonus-list market-quick-list">
                {quickWins.map((w, i) => (
                  <div className="bonus-item" key={i}>
                    <span className="market-step">{i + 1}</span>
                    <div className="bonus-win">{w}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </section>
  );
}

export default MarketInsights;
