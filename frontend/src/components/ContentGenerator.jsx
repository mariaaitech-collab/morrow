import { useState, useRef } from 'react';
import toast from 'react-hot-toast';
import { FaFacebookF, FaLinkedinIn, FaInstagram } from 'react-icons/fa';
import api from '../api/axios';
import CropModal from './CropModal';
import { useLanguage } from '../i18n/LanguageContext';

const TONES = [
  { value: 'viral', icon: '🔥' },
  { value: 'professional', icon: '💼' },
  { value: 'educational', icon: '📚' },
  { value: 'promotional', icon: '🎯' },
];

const PLATFORMS = [
  { value: 'facebook', label: 'Facebook', icon: <FaFacebookF />, color: '#1877f2' },
  { value: 'linkedin', label: 'LinkedIn', icon: <FaLinkedinIn />, color: '#0a66c2' },
  { value: 'instagram', label: 'Instagram', icon: <FaInstagram />, color: '#dc2743' },
];

const PREMIUM_BTN =
  'bg-gradient-to-r from-fuchsia-400/10 to-fuchsia-400/10 text-fuchsia-100 border border-fuchsia-500/30 transition-all duration-200 ease-out hover:from-fuchsia-400/20 hover:to-fuchsia-400/20 hover:border-fuchsia-400/50 hover:shadow-[0_0_22px_rgba(45,212,191,0.25)] active:scale-95';
const SUCCESS_BTN =
  'bg-gradient-to-r from-emerald-400/10 to-fuchsia-400/10 text-emerald-100 border border-emerald-400/30 transition-all duration-200 ease-out hover:from-emerald-400/20 hover:to-fuchsia-400/20 hover:border-emerald-300/50 hover:shadow-[0_0_22px_rgba(16,185,129,0.25)] active:scale-95';

const PLATFORM_META = {
  linkedin: { badge: 'badge-linkedin' },
  instagram: { badge: 'badge-instagram' },
  facebook: { badge: 'badge-facebook' },
};

function ContentGenerator({ accounts }) {
  const { t } = useLanguage();
  const [topic, setTopic] = useState('');
  const [tone, setTone] = useState('professional');
  const [selectedPlatforms, setSelectedPlatforms] = useState(['facebook', 'linkedin', 'instagram']);
  const [loading, setLoading] = useState(false);
  const [content, setContent] = useState(null);
  const [mediaFile, setMediaFile] = useState(null);
  const [mediaPreview, setMediaPreview] = useState(null);
  const [mediaType, setMediaType] = useState(null);
  const [publishing, setPublishing] = useState(false);
  const [publishResults, setPublishResults] = useState({});
  const [cropModal, setCropModal] = useState(null);
  const [imagePrompt, setImagePrompt] = useState('');
  const [imageGenerating, setImageGenerating] = useState(false);
  const [imageMode, setImageMode] = useState('free');
  const [imageQuotaExceeded, setImageQuotaExceeded] = useState(false);
  const [proTrialCount, setProTrialCount] = useState(() => {
    const stored = parseInt(localStorage.getItem('proTrialCount') || '0', 10);
    return Number.isFinite(stored) && stored > 0 ? stored : 0;
  });
  const [competitorLoading, setCompetitorLoading] = useState(false);
  const [strategyData, setStrategyData] = useState(null);
  const [competitorError, setCompetitorError] = useState(null);
  const fileInputRef = useRef(null);

  const connectedPlatforms = accounts.filter((a) => a.connected).map((a) => a.platform);

  const togglePlatform = (p) => {
    setSelectedPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');

    if (mediaPreview) URL.revokeObjectURL(mediaPreview);

    if (isImage) {
      const url = URL.createObjectURL(file);
      setCropModal({ url, name: file.name });
      setMediaType('image');
      e.target.value = '';
    } else if (isVideo) {
      const url = URL.createObjectURL(file);
      setMediaFile(file);
      setMediaPreview(url);
      setMediaType('video');
      toast.success(t('contentGenerator.selectedFile', { name: file.name, size: (file.size / (1024 * 1024)).toFixed(1) }));
    } else {
      setMediaPreview(null);
      setMediaType(null);
    }
  };

  const handleApplyCrop = (blob) => {
    if (mediaPreview) URL.revokeObjectURL(mediaPreview);
    const url = URL.createObjectURL(blob);
    setMediaFile(blob);
    setMediaPreview(url);
    setMediaType('image');
    setCropModal(null);
    toast.success(t('contentGenerator.croppedFile', { name: blob.name, size: (blob.size / (1024 * 1024)).toFixed(1) }));
  };

  const handleCancelCrop = () => {
    setCropModal(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeMedia = () => {
    setMediaFile(null);
    if (mediaPreview) URL.revokeObjectURL(mediaPreview);
    setMediaPreview(null);
    setMediaType(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleGenerate = async () => {
    if (!topic.trim()) {
      toast.error(t('contentGenerator.pleaseTopic'));
      return;
    }
    setLoading(true);
    setContent(null);
    setPublishResults({});
    try {
      const formData = new FormData();
      formData.append('topic', topic.trim());
      formData.append('tone', tone);
      const { data } = await api.post('/content/generate', formData);
      setContent(data);
      toast.success(t('contentGenerator.contentGenerated'));
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || t('contentGenerator.optimizeError');
      toast.error(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleCompetitiveAnalysis = async () => {
    if (!content) return;
    setCompetitorLoading(true);
    setCompetitorError(null);
    setStrategyData(null);
    try {
      const formData = new FormData();
      formData.append('topic', topic.trim());
      formData.append('platforms', JSON.stringify(selectedPlatforms));
      formData.append('content', `${content.title}\n\n${content.body}`);
      const { data } = await api.post('/strategy', formData, { timeout: 300000 });
      setStrategyData(data);
      toast.success(t('contentGenerator.eliteStrategyReady'));
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || t('contentGenerator.analysisFailed');
      const msg = typeof detail === 'string' ? detail : t('contentGenerator.analysisFailed');
      setCompetitorError(msg);
      toast.error(msg);
    } finally {
      setCompetitorLoading(false);
    }
  };

  const handleGenerateImage = async (mode) => {
    if (!imagePrompt.trim()) {
      toast.error(t('contentGenerator.describeImage'));
      return;
    }
    if (mode === 'pro' && proTrialCount >= 2) {
      setImageQuotaExceeded(true);
      toast.error(t('contentGenerator.proLimitReached'), { duration: 6000 });
      return;
    }
    setImageQuotaExceeded(false);
    setImageMode(mode);
    setImageGenerating(true);
    try {
      const formData = new FormData();
      formData.append('prompt', imagePrompt.trim());
      formData.append('mode', mode);
      formData.append('width', 1080);
      formData.append('height', 1080);
      const { data } = await api.post('/content/generate-image', formData, {
        responseType: 'blob',
        timeout: 300000,
      });
      const mime = data.type || 'image/jpeg';
      const ext = mime.includes('png') ? 'png' : 'jpg';
      const file = new File([data], `ai-image-${Date.now()}.${ext}`, { type: mime });
      if (mediaPreview) URL.revokeObjectURL(mediaPreview);
      setMediaFile(file);
      setMediaPreview(URL.createObjectURL(data));
      setMediaType('image');
      if (mode === 'pro') {
        const nextCount = proTrialCount + 1;
        setProTrialCount(nextCount);
        localStorage.setItem('proTrialCount', String(nextCount));
        toast.success(t('contentGenerator.proImageGenerated', { count: nextCount }));
      } else {
        toast.success(t('contentGenerator.freeImageGenerated'));
      }
    } catch (err) {
      let realMessage = null;
      const resData = err.response?.data;
      if (resData && typeof resData.text === 'function') {
        try {
          const backendText = await resData.text();
          try {
            const parsed = JSON.parse(backendText);
            realMessage =
              (typeof parsed.message === 'string' && parsed.message) ||
              (typeof parsed.detail === 'string' ? parsed.detail : null);
          } catch (_) {
            realMessage = backendText;
          }
        } catch (_) {
          realMessage = null;
        }
      } else if (typeof resData === 'string') {
        realMessage = resData;
      } else if (resData && typeof resData.message === 'string') {
        realMessage = resData.message;
      }

      const detail = realMessage
        || err.response?.data?.detail
        || (err.code === 'ECONNABORTED' ? t('contentGenerator.imageTimeout') : t('contentGenerator.imageFailed'));
      toast.error(typeof detail === 'string' ? detail : t('contentGenerator.imageFailed'));
    } finally {
      setImageGenerating(false);
    }
  };

  const handlePublish = async () => {
    if (!content) return;
    const toPublish = selectedPlatforms.filter((p) => connectedPlatforms.includes(p));
    if (toPublish.length === 0) {
      toast.error(t('contentGenerator.selectedConnected'));
      return;
    }
    setPublishing(true);
    setPublishResults({});
    try {
      const formData = new FormData();
      formData.append('content', content.body);
      formData.append('platforms', JSON.stringify(toPublish));
      if (mediaFile) {
        formData.append('media', mediaFile);
      }
      const { data } = await api.post('/content/publish', formData, {
        timeout: 300000,
      });
      if (data.results) {
        setPublishResults(data.results);
        const ok = Object.entries(data.results).filter(([, r]) => r.status === 'success');
        const fail = Object.entries(data.results).filter(([, r]) => r.status !== 'success');
        if (ok.length > 0) toast.success(t('contentGenerator.publishSuccess', { platforms: ok.map(([p]) => p).join(', ') }));
        fail.forEach(([p, r]) => toast.error(t('contentGenerator.platformError', { platform: p, message: r.message })));
      }
    } catch (err) {
      const detail = err.response?.data?.detail || (err.code === 'ECONNABORTED'
        ? t('contentGenerator.publishTimeout')
        : t('contentGenerator.publishFailed'));
      toast.error(detail);
    } finally {
      setPublishing(false);
    }
  };

  const connectedCount = selectedPlatforms.filter((p) => connectedPlatforms.includes(p)).length;

  const trendingCompetitors = strategyData?.trending_competitors || [];
  const groupedByPlatform = ['linkedin', 'instagram', 'facebook'].map((p) => ({
    platform: p,
    cards: trendingCompetitors.filter((c) => (c.platform || '').toLowerCase() === p),
  }));
  const contentAnalysis = strategyData?.content_analysis || {};
  const analysisStrengths = Array.isArray(contentAnalysis.strengths) ? contentAnalysis.strengths : [];
  const analysisImprovements = Array.isArray(contentAnalysis.specific_improvements) ? contentAnalysis.specific_improvements : [];
  const weaknesses = Array.isArray(strategyData?.competitor_weaknesses) ? strategyData.competitor_weaknesses : [];
  const roadmap = Array.isArray(strategyData?.viral_roadmap) ? strategyData.viral_roadmap : [];

  return (
    <div className="content-generator">
      <h3>{t('contentGenerator.title')}</h3>

      <div className="gen-form">
        <div className="form-group">
          <label>{t('contentGenerator.topicLabel')}</label>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder={t('contentGenerator.topicPlaceholder')}
            rows={3}
            disabled={loading}
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>{t('contentGenerator.toneLabel')}</label>
            <div className="tone-selector">
              {TONES.map((tt) => (
                <button
                  key={tt.value}
                  className={`tone-btn ${tone === tt.value ? 'active' : ''}`}
                  onClick={() => setTone(tt.value)}
                  disabled={loading}
                >
                  <span className="tone-icon">{tt.icon}</span>
                  <span className="tone-label">{t('contentGenerator.tone' + tt.value.charAt(0).toUpperCase() + tt.value.slice(1))}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>{t('contentGenerator.platformsLabel')}</label>
            <div className="platform-selector">
              {PLATFORMS.map((p) => (
                <button
                  key={p.value}
                  className={`platform-btn ${selectedPlatforms.includes(p.value) ? 'active' : ''} ${connectedPlatforms.includes(p.value) ? 'connected' : ''}`}
                  onClick={() => togglePlatform(p.value)}
                  disabled={loading}
                  style={selectedPlatforms.includes(p.value) ? { borderColor: p.color, background: `${p.color}15` } : {}}
                >
                  <span className="platform-btn-icon" style={{ background: p.color }}>{p.icon}</span>
                  <span>{p.label}</span>
                  {connectedPlatforms.includes(p.value) && <span className="connected-dot" />}
                </button>
              ))}
            </div>
          </div>
        </div>

        <button className={"btn btn-generate " + PREMIUM_BTN} onClick={handleGenerate} disabled={loading || !topic.trim()}>
          {loading ? (
            <><span className="spinner-sm" /> {t('contentGenerator.generating')}</>
          ) : (
            t('contentGenerator.generateBtn')
          )}
        </button>
      </div>

      {loading && (
        <div className="generating-indicator">
          <div className="spinner" />
          <div>
            <div className="gen-title">{t('contentGenerator.genTitle', { tone })}</div>
            <div className="gen-sub">{t('contentGenerator.genSub')}</div>
          </div>
        </div>
      )}

      {content && (
        <div className="generated-content">
          <div className="content-header">
            <h4>{content.title}</h4>
          </div>

          <div className="content-body">
            <p>{content.body}</p>
          </div>

          <div className="competitor-section">
            <div className="competitor-section-header">
              <h5 className="competitor-section-title">{t('contentGenerator.eliteAnalysisTitle')}</h5>
              <button
                className={"btn " + PREMIUM_BTN}
                onClick={handleCompetitiveAnalysis}
                disabled={competitorLoading}
              >
                {competitorLoading ? (
                  <><span className="spinner-sm" /> {t('contentGenerator.scanning')}</>
                ) : (
                  t('contentGenerator.generateEliteBtn')
                )}
              </button>
            </div>
            <p className="competitor-section-hint">
              {t('contentGenerator.eliteHint')}
            </p>

            {competitorError && <div className="competitor-error">{competitorError}</div>}

            {strategyData && (
              <div className="strategy-results">
                <div className="strategy-providers">
                  <span className="live-chip">{t('contentGenerator.liveChip')}</span>
                  {t('contentGenerator.marketScanned', {
                    search: strategyData.providers?.search || 'Tavily',
                    model: strategyData.providers?.analysis?.model || 'Gemini',
                    count: strategyData.search_meta?.total_raw_results || 0,
                  })}
                </div>

                <section className="strategy-section">
                  <div className="strategy-section-head">
                    <span className="strategy-section-icon">🔥</span>
                    <div>
                      <h5>{t('contentGenerator.trendingCompetitors')}</h5>
                      <p>{t('contentGenerator.trendingCompetitorsSub')}</p>
                    </div>
                  </div>
                  <div className="competitors-3col">
                    {groupedByPlatform.map(({ platform, cards }) => (
                      <div className="competitor-column" key={platform}>
                        <div className="competitor-column-head">
                          <span className={`platform-badge ${PLATFORM_META[platform].badge}`}>
                            {PLATFORM_META[platform].label}
                            <span className="badge-count">· {cards.length}</span>
                          </span>
                        </div>
                        {cards.length === 0 ? (
                          <div className="column-empty">{t('contentGenerator.noCreators')}</div>
                        ) : (
                          cards.map((c, i) => (
                            <a
                              key={`${platform}-${i}`}
                              className="viral-card"
                              href={c.profile_link || '#'}
                              target="_blank"
                              rel="noreferrer"
                            >
                               <div className="viral-card-name">{c.name || t('contentGenerator.unknownCreator')}</div>
                              {c.viral_hook && (
                                <div className="viral-card-hook">
                                  <span className="q">“</span>{c.viral_hook}<span className="q">”</span>
                                </div>
                              )}
                               <div className="viral-card-link">{t('contentGenerator.openProfile')}</div>
                            </a>
                          ))
                        )}
                      </div>
                    ))}
                  </div>
                </section>

                <section className="strategy-section">
                  <div className="strategy-section-head">
                    <span className="strategy-section-icon">🎯</span>
                    <div>
                      <h5>{t('contentGenerator.yourTeardown')}</h5>
                      <p>{t('contentGenerator.yourTeardownSub')}</p>
                    </div>
                  </div>
                  <div className="analysis-split">
                    <div className="analysis-card card-good">
                      <h6>{t('contentGenerator.strengths')}</h6>
                      {analysisStrengths.length === 0 ? (
                        <p className="analysis-empty">{t('contentGenerator.analysisEmpty')}</p>
                      ) : (
                        <ul className="analysis-list">
                          {analysisStrengths.map((s, i) => <li key={i}>{s}</li>)}
                        </ul>
                      )}
                    </div>
                    <div className="analysis-card card-warn">
                      <h6>{t('contentGenerator.improvements')}</h6>
                      {analysisImprovements.length === 0 ? (
                        <p className="analysis-empty">{t('contentGenerator.noImprovements')}</p>
                      ) : (
                        <ul className="analysis-list">
                          {analysisImprovements.map((s, i) => <li key={i}>{s}</li>)}
                        </ul>
                      )}
                    </div>
                  </div>
                </section>

                <section className="strategy-section">
                  <div className="strategy-section-head">
                    <span className="strategy-section-icon">💣</span>
                    <div>
                      <h5>{t('contentGenerator.weaknessesTitle')}</h5>
                      <p>{t('contentGenerator.weaknessesSub')}</p>
                    </div>
                  </div>
                  <div className="bonus-list">
                    {weaknesses.length === 0 ? (
                      <p className="analysis-empty">{t('contentGenerator.noWeaknesses')}</p>
                    ) : (
                      weaknesses.map((w, i) => {
                        if (typeof w === 'string') {
                          return <div className="bonus-item" key={i}><div className="bonus-weak">✗ {w}</div></div>;
                        }
                        return (
                          <div className="bonus-item" key={i}>
                            <div className="bonus-weak">✗ {w.weakness || w.title || 'Weakness'}</div>
                            {w.why_you_win && (
                              <div className="bonus-win"><b>{t('contentGenerator.youWinBecause')}</b> {w.why_you_win}</div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </section>

                <section className="strategy-section">
                  <div className="strategy-section-head">
                    <span className="strategy-section-icon">🗺️</span>
                    <div>
                      <h5>{t('contentGenerator.roadmapTitle')}</h5>
                      <p>{t('contentGenerator.roadmapSub')}</p>
                    </div>
                  </div>
                  <div className="roadmap-list">
                    {roadmap.length === 0 ? (
                      <p className="analysis-empty">{t('contentGenerator.noRoadmap')}</p>
                    ) : (
                      roadmap.map((r, i) => (
                        <div className="roadmap-step" key={i}>
                          <div className="roadmap-day">{r.day || t('contentGenerator.step', { i: i + 1 })}</div>
                          <div className="roadmap-action">
                            {r.action || r.title || ''}
                            {r.platform && <span className="rm-platform">{r.platform}</span>}
                            {r.expected_outcome && (
                              <div className="roadmap-outcome">→ {r.expected_outcome}</div>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>
              </div>
            )}
          </div>

          <div className="ai-image-section">
            <h5 className="ai-image-title">{t('contentGenerator.aiImageTitle')}</h5>
            <textarea
              className="ai-image-prompt"
              value={imagePrompt}
              onChange={(e) => setImagePrompt(e.target.value)}
              placeholder={t('contentGenerator.imagePromptPlaceholder')}
              rows={2}
              disabled={imageGenerating}
            />
            <div className="ai-image-methods">
              <button
                className={"btn " + PREMIUM_BTN}
                onClick={() => handleGenerateImage('pro')}
                disabled={imageGenerating}
              >
                {imageGenerating && imageMode === 'pro' ? (
                  <><span className="spinner-sm" /> {t('contentGenerator.generatingImage')}</>
                ) : (
                  <><span className="ai-icon">✦</span> {t('contentGenerator.proGenerator')}</>
                )}
              </button>
              <button
                className={"btn " + SUCCESS_BTN}
                onClick={() => handleGenerateImage('free')}
                disabled={imageGenerating}
              >
                {imageGenerating && imageMode === 'free' ? (
                  <><span className="spinner-sm" /> {t('contentGenerator.generatingImage')}</>
                ) : (
                  <><span className="ai-icon">∞</span> {t('contentGenerator.freeGenerator')}</>
                )}
              </button>
            </div>
            {imageGenerating && (
              <div className="image-loading">
                <div className="spinner" />
                <div>
                  <div className="image-loading-title">{t('contentGenerator.imageLoadingTitle')}</div>
                  <div className="image-loading-sub">{t('contentGenerator.imageLoadingSub')}</div>
                </div>
              </div>
            )}
            {imageQuotaExceeded && (
              <div className="image-quota-alert">
                {t('contentGenerator.quotaAlert')}
              </div>
            )}
            {imageMode === 'pro' && proTrialCount < 2 && !imageGenerating && (
              <div className="trial-hint">{t('contentGenerator.trialHint', { count: proTrialCount })}</div>
            )}
          </div>

          <div className="media-upload-section">
            <label>{t('contentGenerator.attachMedia')}</label>
            <input
              ref={fileInputRef}
              type="file"
              accept="*/*"
              onChange={handleFileSelect}
              className="file-input"
              id="media-upload"
            />
            <div className="media-upload-row">
              <label htmlFor="media-upload" className="btn btn-outline btn-upload">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                {t('contentGenerator.browseFiles')}
              </label>
              {mediaFile && (
                <button className="btn btn-outline btn-sm" onClick={removeMedia}>{t('contentGenerator.removeMedia')}</button>
              )}
            </div>
            {mediaFile && (
              <div className="media-preview">
                {mediaType === 'image' && mediaPreview && (
                  <img src={mediaPreview} alt={t('scheduler.previewAlt')} decoding="async" className="media-preview-img" />
                )}
                {mediaType === 'video' && mediaPreview && (
                  <video src={mediaPreview} controls className="media-preview-video" />
                )}
                {!mediaType && (
                  <div className="media-preview-generic">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span>{mediaFile.name} ({(mediaFile.size / (1024 * 1024)).toFixed(1)}MB)</span>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="publish-platforms-section">
            <label>{t('contentGenerator.publishToLabel')}</label>
            <div className="publish-platforms-row">
              {PLATFORMS.map((p) => {
                const isSelected = selectedPlatforms.includes(p.value);
                const isConnected = connectedPlatforms.includes(p.value);
                const result = publishResults[p.value];
                return (
                  <label key={p.value} className={`publish-platform-chip ${isSelected ? 'selected' : ''} ${isConnected ? 'connected' : 'disconnected'}`}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => togglePlatform(p.value)}
                      disabled={publishing}
                    />
                    <span className="chip-icon" style={{ background: p.color }}>{p.icon}</span>
                    <span className="chip-label">{p.label}</span>
                    {result && (
                      <span className={`chip-result ${result.status === 'success' ? 'ok' : 'fail'}`}>
                        {result.status === 'success' ? '✓' : '✗'}
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          </div>

          <div className="publish-actions">
            <span className="publish-info">
              {t('contentGenerator.publishInfo', { connected: connectedCount, total: selectedPlatforms.length })}
            </span>
            <button
              className={"btn " + PREMIUM_BTN}
              onClick={handlePublish}
              disabled={publishing || connectedCount === 0}
            >
              {publishing ? (
                <><span className="spinner-sm" /> {t('contentGenerator.publishing')}</>
              ) : (
                t('contentGenerator.publishBtn', { count: connectedCount, plural: connectedCount !== 1 ? 's' : '' })
              )}
            </button>
          </div>
        </div>
      )}

      {cropModal && (
        <CropModal
          imageUrl={cropModal.url}
          originalName={cropModal.name}
          onCancel={handleCancelCrop}
          onApply={handleApplyCrop}
        />
      )}
    </div>
  );
}

export default ContentGenerator;
