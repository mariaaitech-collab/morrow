import { useState, useRef } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import CropModal from './CropModal';

const TONES = [
  { value: 'viral', label: 'Trending / Viral', icon: '🔥' },
  { value: 'professional', label: 'Professional', icon: '💼' },
  { value: 'educational', label: 'Educational', icon: '📚' },
  { value: 'promotional', label: 'Promotional', icon: '🎯' },
];

const PLATFORMS = [
  { value: 'facebook', label: 'Facebook', icon: 'f', color: '#1877f2' },
  { value: 'linkedin', label: 'LinkedIn', icon: 'in', color: '#0a66c2' },
  { value: 'instagram', label: 'Instagram', icon: 'ig', color: '#dc2743' },
];

const PLATFORM_META = {
  linkedin: { label: 'LinkedIn', badge: 'badge-linkedin' },
  instagram: { label: 'Instagram', badge: 'badge-instagram' },
  facebook: { label: 'Facebook', badge: 'badge-facebook' },
};

function ContentGenerator({ accounts }) {
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
      toast.success(`Selected: ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)}MB)`);
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
    toast.success(`Cropped: ${blob.name} (${(blob.size / (1024 * 1024)).toFixed(1)}MB)`);
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
      toast.error('Please enter a topic');
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
      toast.success('Content generated!');
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Generation failed';
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
      toast.success('Elite strategy ready! 9 trending competitors analyzed and your viral roadmap built.');
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Analysis failed';
      const msg = typeof detail === 'string' ? detail : 'Analysis failed';
      setCompetitorError(msg);
      toast.error(msg);
    } finally {
      setCompetitorLoading(false);
    }
  };

  const handleGenerateImage = async (mode) => {
    if (!imagePrompt.trim()) {
      toast.error('Please describe the image you want to create');
      return;
    }
    if (mode === 'pro' && proTrialCount >= 2) {
      setImageQuotaExceeded(true);
      toast.error('Pro limits reached. This is a paid feature. Please use the Free generator.', { duration: 6000 });
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
        toast.success(`Premium Image Generated (Trial ${nextCount} of 2 used)`);
      } else {
        toast.success('Free AI image generated and attached!');
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
        || (err.code === 'ECONNABORTED' ? 'Image generation timed out. Try again.' : 'Image generation failed');
      toast.error(typeof detail === 'string' ? detail : 'Image generation failed');
    } finally {
      setImageGenerating(false);
    }
  };

  const handlePublish = async () => {
    if (!content) return;
    const toPublish = selectedPlatforms.filter((p) => connectedPlatforms.includes(p));
    if (toPublish.length === 0) {
      toast.error('None of the selected platforms are connected');
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
        if (ok.length > 0) toast.success(`Published to ${ok.map(([p]) => p).join(', ')}!`);
        fail.forEach(([p, r]) => toast.error(`${p}: ${r.message}`));
      }
    } catch (err) {
      const detail = err.response?.data?.detail || (err.code === 'ECONNABORTED'
        ? 'Publishing timed out. Please check your social accounts and try again.'
        : 'Publish failed');
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
      <h3>Content Studio</h3>

      <div className="gen-form">
        <div className="form-group">
          <label>Topic</label>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Enter your topic — e.g., 'The future of remote work in 2026', 'How AI is transforming customer service', 'Summer flash sale announcement'"
            rows={3}
            disabled={loading}
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Tone & Style</label>
            <div className="tone-selector">
              {TONES.map((t) => (
                <button
                  key={t.value}
                  className={`tone-btn ${tone === t.value ? 'active' : ''}`}
                  onClick={() => setTone(t.value)}
                  disabled={loading}
                >
                  <span className="tone-icon">{t.icon}</span>
                  <span className="tone-label">{t.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>Platforms</label>
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

        <button className="btn btn-primary btn-generate" onClick={handleGenerate} disabled={loading || !topic.trim()}>
          {loading ? (
            <><span className="spinner-sm" /> Generating with AI...</>
          ) : (
            'Generate Content'
          )}
        </button>
      </div>

      {loading && (
        <div className="generating-indicator">
          <div className="spinner" />
          <div>
            <div className="gen-title">Crafting your {tone} content...</div>
            <div className="gen-sub">AI is optimizing for all platforms</div>
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
              <h5 className="competitor-section-title">Elite Competitive Analysis &amp; Smart Strategy</h5>
              <button
                className="btn btn-primary"
                onClick={handleCompetitiveAnalysis}
                disabled={competitorLoading}
              >
                {competitorLoading ? (
                  <><span className="spinner-sm" /> Scanning 9 viral creators &amp; building your strategy...</>
                ) : (
                  'Generate Elite Competitive Analysis'
                )}
              </button>
            </div>
            <p className="competitor-section-hint">
              Scans 9 trending creators winning with similar content across LinkedIn, Instagram and Facebook,
              tears down their weaknesses, upgrades your generated caption, and hands you a day-by-day viral
              deployment roadmap.
            </p>

            {competitorError && <div className="competitor-error">{competitorError}</div>}

            {strategyData && (
              <div className="strategy-results">
                <div className="strategy-providers">
                  <span className="live-chip">● LIVE</span>
                  Market scanned via {strategyData.providers?.search || 'Tavily'} · Analyzed with{' '}
                  {strategyData.providers?.analysis?.model || 'Gemini'} ·{' '}
                  {strategyData.search_meta?.total_raw_results || 0} raw results searched
                </div>

                <section className="strategy-section">
                  <div className="strategy-section-head">
                    <span className="strategy-section-icon">🔥</span>
                    <div>
                      <h5>Trending Competitors</h5>
                      <p>9 viral creators who won with content like yours — 3 per platform on LinkedIn, Instagram and Facebook.</p>
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
                          <div className="column-empty">No creators found for this platform.</div>
                        ) : (
                          cards.map((c, i) => (
                            <a
                              key={`${platform}-${i}`}
                              className="viral-card"
                              href={c.profile_link || '#'}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <div className="viral-card-name">{c.name || 'Unknown creator'}</div>
                              {c.viral_hook && (
                                <div className="viral-card-hook">
                                  <span className="q">“</span>{c.viral_hook}<span className="q">”</span>
                                </div>
                              )}
                              <div className="viral-card-link">Open profile ↗</div>
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
                      <h5>Your Content Teardown</h5>
                      <p>What your generated caption already does right — and exactly how to sharpen it into a hook machine.</p>
                    </div>
                  </div>
                  <div className="analysis-split">
                    <div className="analysis-card card-good">
                      <h6>✓ Strengths</h6>
                      {analysisStrengths.length === 0 ? (
                        <p className="analysis-empty">No strengths returned.</p>
                      ) : (
                        <ul className="analysis-list">
                          {analysisStrengths.map((s, i) => <li key={i}>{s}</li>)}
                        </ul>
                      )}
                    </div>
                    <div className="analysis-card card-warn">
                      <h6>→ Specific Improvements</h6>
                      {analysisImprovements.length === 0 ? (
                        <p className="analysis-empty">No improvements returned.</p>
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
                      <h5>Bonus: Competitor Weaknesses</h5>
                      <p>Where the viral creators drop the ball (weak CTAs, ignored comments, lazy repurposing) — and how you beat them.</p>
                    </div>
                  </div>
                  <div className="bonus-list">
                    {weaknesses.length === 0 ? (
                      <p className="analysis-empty">No weaknesses returned.</p>
                    ) : (
                      weaknesses.map((w, i) => {
                        if (typeof w === 'string') {
                          return <div className="bonus-item" key={i}><div className="bonus-weak">✗ {w}</div></div>;
                        }
                        return (
                          <div className="bonus-item" key={i}>
                            <div className="bonus-weak">✗ {w.weakness || w.title || 'Weakness'}</div>
                            {w.why_you_win && (
                              <div className="bonus-win"><b>You win because:</b> {w.why_you_win}</div>
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
                      <h5>Viral Roadmap</h5>
                      <p>Deploy this strategy day-by-day. Execute, measure the results, compound.</p>
                    </div>
                  </div>
                  <div className="roadmap-list">
                    {roadmap.length === 0 ? (
                      <p className="analysis-empty">No roadmap returned.</p>
                    ) : (
                      roadmap.map((r, i) => (
                        <div className="roadmap-step" key={i}>
                          <div className="roadmap-day">{r.day || `Step ${i + 1}`}</div>
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
            <h5 className="ai-image-title">AI Image Creation</h5>
            <textarea
              className="ai-image-prompt"
              value={imagePrompt}
              onChange={(e) => setImagePrompt(e.target.value)}
              placeholder="Describe the image you want to create — e.g., 'A futuristic office with holographic screens in purple tones'"
              rows={2}
              disabled={imageGenerating}
            />
            <div className="ai-image-methods">
              <button
                className="btn btn-primary"
                onClick={() => handleGenerateImage('pro')}
                disabled={imageGenerating}
              >
                {imageGenerating && imageMode === 'pro' ? (
                  <><span className="spinner-sm" /> Generating...</>
                ) : (
                  <><span className="ai-icon">✦</span> Pro / Default Generator</>
                )}
              </button>
              <button
                className="btn btn-success"
                onClick={() => handleGenerateImage('free')}
                disabled={imageGenerating}
              >
                {imageGenerating && imageMode === 'free' ? (
                  <><span className="spinner-sm" /> Generating...</>
                ) : (
                  <><span className="ai-icon">∞</span> Free Unlimited Generator</>
                )}
              </button>
            </div>
            {imageGenerating && (
              <div className="image-loading">
                <div className="spinner" />
                <div>
                  <div className="image-loading-title">Generating high-quality image...</div>
                  <div className="image-loading-sub">(This may take up to 20 seconds)</div>
                </div>
              </div>
            )}
            {imageQuotaExceeded && (
              <div className="image-quota-alert">
                Pro limits reached. This is a paid feature. Please use the Free generator.
              </div>
            )}
            {imageMode === 'pro' && proTrialCount < 2 && !imageGenerating && (
              <div className="trial-hint">Pro trial: {proTrialCount} of 2 images used</div>
            )}
          </div>

          <div className="media-upload-section">
            <label>Attach Image or Video (images open in the cropper)</label>
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
                Browse Files
              </label>
              {mediaFile && (
                <button className="btn btn-outline btn-sm" onClick={removeMedia}>Remove</button>
              )}
            </div>
            {mediaFile && (
              <div className="media-preview">
                {mediaType === 'image' && mediaPreview && (
                  <img src={mediaPreview} alt="Preview" className="media-preview-img" />
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
            <label>Publish to</label>
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
              {connectedCount} of {selectedPlatforms.length} selected connected
            </span>
            <button
              className="btn btn-primary"
              onClick={handlePublish}
              disabled={publishing || connectedCount === 0}
            >
              {publishing ? (
                <><span className="spinner-sm" /> Publishing to Meta... This may take a minute for videos</>
              ) : (
                `Publish to ${connectedCount > 0 ? connectedCount : ''} Platform${connectedCount !== 1 ? 's' : ''}`
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
