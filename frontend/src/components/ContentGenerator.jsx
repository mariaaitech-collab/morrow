import { useState, useRef, useEffect } from 'react';
import toast from 'react-hot-toast';
import { FaFacebookF, FaLinkedinIn, FaInstagram, FaTiktok } from 'react-icons/fa';
import { ExternalLink } from 'lucide-react';
import api from '../api/axios';
import { ensureToken } from '../api/tokens';
import CropModal from './CropModal';
import MarketInsights from './MarketInsights';
import { useLanguage } from '../i18n/LanguageContext';
import { useDraft } from '../draft/DraftContext';
import '../styles/studio.css';

const TONES = [
  { value: 'viral' },
  { value: 'professional' },
  { value: 'educational' },
  { value: 'promotional' },
];

const PLATFORMS = [
  { value: 'facebook', label: 'Facebook', icon: <FaFacebookF />, color: 'var(--platform-facebook)' },
  { value: 'linkedin', label: 'LinkedIn', icon: <FaLinkedinIn />, color: 'var(--platform-linkedin)' },
  { value: 'instagram', label: 'Instagram', icon: <FaInstagram />, color: 'var(--platform-instagram)' },
  // TikTok accepts video only; the backend rejects image posts for it.
  { value: 'tiktok', label: 'TikTok', icon: <FaTiktok />, color: 'var(--platform-tiktok)' },
];

// A TikTok post finishes in the background after /content/publish returns
// "processing": follow it this often, and stop waiting after this long.
const TIKTOK_POLL_MS = 4000;
const TIKTOK_POLL_LIMIT_MS = 10 * 60 * 1000;

const platformName = (value) => PLATFORMS.find((x) => x.value === value)?.label || value;

const PREMIUM_BTN =
  'tech-action-btn transition-all duration-200 ease-out';
const SUCCESS_BTN =
  'tech-action-btn transition-all duration-200 ease-out';

const PLATFORM_META = {
  linkedin: { badge: 'badge-linkedin' },
  instagram: { badge: 'badge-instagram' },
  facebook: { badge: 'badge-facebook' },
};

// Map the UI language code to a full English language name so Gemini generates
// the actual content in the selected language instead of defaulting to English.
const LANGUAGE_NAMES = {
  en: 'English', es: 'Spanish', fr: 'French', de: 'German', pt: 'Portuguese',
  it: 'Italian', nl: 'Dutch', ru: 'Russian', zh: 'Chinese', ja: 'Japanese',
  ko: 'Korean', ar: 'Arabic', ur: 'Urdu', hi: 'Hindi', bn: 'Bengali',
  pa: 'Punjabi', ta: 'Tamil', te: 'Telugu', mr: 'Marathi', gu: 'Gujarati',
  kn: 'Kannada', ml: 'Malayalam', th: 'Thai', vi: 'Vietnamese', id: 'Indonesian',
  ms: 'Malay', fil: 'Filipino', jw: 'Javanese', su: 'Sundanese', my: 'Burmese',
  km: 'Khmer', lo: 'Lao', ne: 'Nepali', si: 'Sinhala', tr: 'Turkish',
  pl: 'Polish', uk: 'Ukrainian', cs: 'Czech', sk: 'Slovak', hu: 'Hungarian',
  ro: 'Romanian', el: 'Greek', bg: 'Bulgarian', hr: 'Croatian', sr: 'Serbian',
  sl: 'Slovenian', et: 'Estonian', lv: 'Latvian', lt: 'Lithuanian', he: 'Hebrew',
  fa: 'Persian', ps: 'Pashto', sd: 'Sindhi', ku: 'Kurdish', ug: 'Uyghur',
  yi: 'Yiddish', dv: 'Divehi', am: 'Amharic', sw: 'Swahili', yo: 'Yoruba',
  ig: 'Igbo', ha: 'Hausa', zu: 'Zulu', xh: 'Xhosa', af: 'Afrikaans',
  so: 'Somali', wo: 'Wolof', az: 'Azerbaijani', kk: 'Kazakh', uz: 'Uzbek',
  tg: 'Tajik', ka: 'Georgian', hy: 'Armenian', mk: 'Macedonian', sq: 'Albanian',
  bs: 'Bosnian', fo: 'Faroese', is: 'Icelandic', ga: 'Irish', cy: 'Welsh',
  gd: 'Scottish Gaelic', eu: 'Basque', ca: 'Catalan', gl: 'Galician',
  mt: 'Maltese', lb: 'Luxembourgish', be: 'Belarusian', mn: 'Mongolian',
  ky: 'Kyrgyz', tk: 'Turkmen', sv: 'Swedish', da: 'Danish', fi: 'Finnish',
  nb: 'Norwegian Bokmål',
};
function languageName(code) {
  return (code && LANGUAGE_NAMES[code]) || 'English';
}

function ContentGenerator({ accounts }) {
  const { t, language } = useLanguage();
  const { draft, setDraft, clearDraft } = useDraft();

  // Draft-backed fields: these survive navigation between pages and are only
  // wiped by the explicit "Clear all" button or logging out.
  const topic = draft.topic;
  const setTopic = (v) => setDraft({ topic: v });
  const tone = draft.tone;
  const setTone = (v) => setDraft({ tone: v });
  const selectedPlatforms = draft.selectedPlatforms;
  const setSelectedPlatforms = (v) => setDraft({ selectedPlatforms: v });
  const content = draft.content;
  const setContent = (v) => setDraft({ content: v });
  const imagePrompt = draft.imagePrompt;
  const setImagePrompt = (v) => setDraft({ imagePrompt: v });
  const imageMode = draft.imageMode;
  const setImageMode = (v) => setDraft({ imageMode: v });
  const publishResults = draft.publishResults;
  const setPublishResults = (v) => setDraft({ publishResults: v });
  const strategyData = draft.strategyData;
  const setStrategyData = (v) => setDraft({ strategyData: v });
  const competitorError = draft.competitorError;
  const setCompetitorError = (v) => setDraft({ competitorError: v });

  // Transient UI state (not worth persisting).
  const [loading, setLoading] = useState(false);
  const [mediaFile, setMediaFile] = useState(null);
  const [mediaPreview, setMediaPreview] = useState(null);
  const [mediaType, setMediaType] = useState(null);
  const [publishing, setPublishing] = useState(false);
  // Platforms in the current publish request (each chip shows a spinner).
  const [pendingPlatforms, setPendingPlatforms] = useState([]);
  // Blocks a second request before React re-renders the disabled button.
  const publishLockRef = useRef(false);
  // Identifies the running TikTok status poller; null stops it.
  const tiktokPollRef = useRef(null);
  const [cropModal, setCropModal] = useState(null);
  const [imageGenerating, setImageGenerating] = useState(false);
  const [imageQuotaExceeded, setImageQuotaExceeded] = useState(false);
  const [proTrialCount, setProTrialCount] = useState(() => {
    const stored = parseInt(localStorage.getItem('proTrialCount') || '0', 10);
    return Number.isFinite(stored) && stored > 0 ? stored : 0;
  });
  const [competitorLoading, setCompetitorLoading] = useState(false);
  const fileInputRef = useRef(null);

  // Restore an attached media file from the persisted draft on mount (only
  // when a base64 dataUrl survived — large files keep metadata only).
  useEffect(() => {
    if (!draft.media || !draft.media.dataUrl) return;
    let cancelled = false;
    const mime = draft.media.type || (draft.media.name && draft.media.name.endsWith('.mp4') ? 'video/mp4' : 'image/jpeg');
    fetch(draft.media.dataUrl)
      .then((r) => r.blob())
      .then((blob) => {
        if (cancelled) return;
        const ext = mime.includes('video') ? 'mp4' : mime.includes('png') ? 'png' : 'jpg';
        const f = new File([blob], draft.media.name || `restored-${Date.now()}.${ext}`, { type: mime });
        setMediaFile(f);
        setMediaType(mime.includes('video') ? 'video' : 'image');
        setMediaPreview(URL.createObjectURL(blob));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Mirror the live media into the persisted draft (blobs can't be serialized,
  // so we store a base64 dataUrl for small files and metadata for large ones).
  useEffect(() => {
    if (!mediaFile) {
      if (draft.media) setDraft({ media: null });
      return;
    }
    const meta = { name: mediaFile.name, size: mediaFile.size, type: mediaFile.type || (mediaType || '') };
    if (mediaFile.size > 3.5 * 1024 * 1024) {
      setDraft({ media: { ...meta, dataUrl: null } });
      return;
    }
    let cancelled = false;
    const reader = new FileReader();
    reader.onload = () => { if (!cancelled) setDraft({ media: { ...meta, dataUrl: reader.result } }); };
    reader.onerror = () => { if (!cancelled) setDraft({ media: { ...meta, dataUrl: null } }); };
    reader.readAsDataURL(mediaFile);
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mediaFile]);

  // Clean up object URL on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (mediaPreview) URL.revokeObjectURL(mediaPreview);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mediaPreview]);

  const connectedPlatforms = accounts.filter((a) => a.connected).map((a) => a.platform);

  const togglePlatform = (p) => {
    setSelectedPlatforms(
      selectedPlatforms.includes(p)
        ? selectedPlatforms.filter((x) => x !== p)
        : [...selectedPlatforms, p]
    );
  };

  const handleClearAll = () => {
    tiktokPollRef.current = null;
    removeMedia();
    setLoading(false);
    clearDraft();
    toast.success(t('contentGenerator.draftCleared'));
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');

    if (mediaPreview) URL.revokeObjectURL(mediaPreview);

    if (isImage) {
      const url = URL.createObjectURL(file);
      setMediaPreview(url);
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
    if (!ensureToken()) return;
    setLoading(true);
    setContent(null);
    setPublishResults({});
    try {
      const formData = new FormData();
      formData.append('topic', topic.trim());
      formData.append('tone', tone);
      formData.append('platforms', JSON.stringify(selectedPlatforms));
      formData.append('language', languageName(language));
      const { data } = await api.post('/content/generate', formData, { timeout: 300000 });
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
      formData.append('language', languageName(language));
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
    if (!ensureToken()) return;
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

  // Follow a TikTok post until TikTok reports a final result. Only one poller
  // runs at a time: starting another, clearing the draft or leaving the page
  // stops this one (its loop sees tiktokPollRef change and exits).
  const pollTikTok = async (publishId) => {
    const run = {};
    tiktokPollRef.current = run;
    const deadline = Date.now() + TIKTOK_POLL_LIMIT_MS;
    const setTikTokResult = (r) =>
      setDraft((prev) => ({ ...prev, publishResults: { ...(prev.publishResults || {}), tiktok: r } }));
    let failures = 0;
    while (tiktokPollRef.current === run) {
      await new Promise((resolve) => setTimeout(resolve, TIKTOK_POLL_MS));
      if (tiktokPollRef.current !== run) return;
      let next;
      try {
        const { data } = await api.get(`/content/tiktok/status/${encodeURIComponent(publishId)}`, { timeout: 30000 });
        failures = 0;
        next = data;
      } catch (err) {
        const code = err.response?.status;
        if (code >= 400 && code < 500) {
          const detail = err.response.data?.detail;
          next = { status: 'error', message: typeof detail === 'string' ? detail : t('contentGenerator.publishFailed') };
        } else {
          // Server or network hiccup: try a few more times before giving up.
          failures += 1;
          if (failures < 4 && Date.now() < deadline) continue;
          next = { status: 'timeout', message: t('contentGenerator.tiktokStatusUnreachable') };
        }
      }
      if (tiktokPollRef.current !== run) return;
      if (next.status === 'processing') {
        if (Date.now() < deadline) {
          setTikTokResult({ status: 'processing', publish_id: publishId, message: next.message });
          continue;
        }
        next = { status: 'timeout', message: t('contentGenerator.tiktokStillProcessing') };
      }
      tiktokPollRef.current = null;
      setTikTokResult({ status: next.status, publish_id: publishId, message: next.message });
      if (next.status === 'success') {
        toast.success(next.message || t('contentGenerator.publishSuccess', { platforms: 'TikTok' }));
      } else if (next.status === 'timeout') {
        toast(next.message, { icon: '⏳', duration: 8000 });
      } else {
        toast.error(t('contentGenerator.platformError', { platform: 'TikTok', message: next.message }), { duration: 8000 });
      }
      return;
    }
  };

  // Coming back to this page while a TikTok post was processing: keep following it.
  useEffect(() => {
    const tk = draft.publishResults?.tiktok;
    if (tk?.status === 'processing' && tk.publish_id) pollTikTok(tk.publish_id);
    return () => {
      tiktokPollRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A failed /content/publish call, as a message a person can act on.
  const publishErrorMessage = (err) => {
    const status = err.response?.status;
    // Our own request timeout, or a proxy giving up (Cloudflare tunnels answer
    // 524 after 100s): the server may still be publishing.
    if (err.code === 'ECONNABORTED' || [502, 504, 524].includes(status)) {
      return t('contentGenerator.publishTimeout');
    }
    if (!err.response && err.code === 'ERR_NETWORK') {
      return t('contentGenerator.publishConnectionLost');
    }
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail; // proxies may answer with an HTML page
    return err.message || t('contentGenerator.publishFailed');
  };

  const handlePublish = async () => {
    if (!content || publishLockRef.current) return;
    const toPublish = selectedPlatforms.filter((p) => connectedPlatforms.includes(p));
    if (toPublish.length === 0) {
      toast.error(t('contentGenerator.selectedConnected'));
      return;
    }
    if (!ensureToken()) return;
    publishLockRef.current = true;
    tiktokPollRef.current = null; // stop following an earlier TikTok post
    setPublishing(true);
    setPendingPlatforms(toPublish);
    setPublishResults({});
    try {
      const formData = new FormData();
      formData.append('content', content.body);
      formData.append('platforms', JSON.stringify(toPublish));
      if (mediaFile) {
        formData.append('media', mediaFile);
      }
      // TikTok answers within seconds now (it finishes in the background), but
      // an Instagram Reel can legitimately take ~10 minutes, hence 20.
      const { data } = await api.post('/content/publish', formData, {
        timeout: 1200000,
      });
      if (data.results) {
        setPublishResults(data.results);
        const entries = Object.entries(data.results);
        const ok = entries.filter(([, r]) => r.status === 'success');
        const fail = entries.filter(([, r]) => r.status !== 'success' && r.status !== 'processing');
        if (ok.length > 0) toast.success(t('contentGenerator.publishSuccess', { platforms: ok.map(([p]) => platformName(p)).join(', ') }));
        fail.forEach(([p, r]) => {
          const reason = r && r.message ? r.message : (r ? JSON.stringify(r) : 'Unknown error');
          toast.error(t('contentGenerator.platformError', { platform: platformName(p), message: reason }));
        });
        const tk = data.results.tiktok;
        if (tk?.status === 'processing' && tk.publish_id) {
          toast(t('contentGenerator.tiktokProcessingToast'), { icon: '⏳', duration: 6000 });
          pollTikTok(tk.publish_id);
        }
      }
    } catch (err) {
      toast.error(publishErrorMessage(err), { duration: 8000 });
    } finally {
      publishLockRef.current = false;
      setPublishing(false);
      setPendingPlatforms([]);
    }
  };

  const connectedCount = selectedPlatforms.filter((p) => connectedPlatforms.includes(p)).length;
  // Warn before publishing: a TikTok post without a video fails on the backend.
  const tiktokNeedsVideo = selectedPlatforms.includes('tiktok') && mediaType !== 'video';
  // TikTok accepted the post and is still finishing it: publishing again would duplicate it.
  const tiktokProcessing = publishResults.tiktok?.status === 'processing';

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
      <header className="studio-head">
        <div>
          <h1 className="studio-head__title">{t('contentGenerator.title')}</h1>
          <p className="studio-head__sub">{t('dashboard.contentStudioSub')}</p>
        </div>
        <button
          className="clear-btn"
          onClick={handleClearAll}
          disabled={loading || publishing}
          title={t('contentGenerator.clearAllTitle')}
        >
          {t('contentGenerator.clearAll')}
        </button>
      </header>

      <form
        className="studio-stack studio-composer"
        onSubmit={(event) => { event.preventDefault(); handleGenerate(); }}
      >
        <section className="studio-composer__brief">
          <div className="studio-step-heading">
            <span className="studio-step-number">01</span>
            <div>
              <h3 className="studio-card__title">{t('contentGenerator.createHeading')}</h3>
              <p className="studio-card__hint">{t('contentGenerator.createSubheading')}</p>
            </div>
          </div>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={t('contentGenerator.topicPlaceholder')}
            rows={4}
            disabled={loading}
            aria-label={t('contentGenerator.createHeading')}
          />
          <p className="studio-composer__keyboard-hint">Enter to generate <span>·</span> Shift + Enter for a new line</p>
        </section>

        <div className="studio-options-grid studio-composer__options">
          <section className="studio-composer__option">
            <div className="studio-step-heading">
              <span className="studio-step-number">02</span>
              <div>
                <h3 className="studio-card__title">{t('contentGenerator.toneLabel')}</h3>
                <p className="studio-card__hint">{t('contentGenerator.toneSubheading')}</p>
              </div>
            </div>
            <div className="tone-selector" role="radiogroup" aria-label={t('contentGenerator.toneLabel')}>
              {TONES.map((tt) => (
                <button
                  key={tt.value}
                  type="button"
                  role="radio"
                  aria-checked={tone === tt.value}
                  className={`tone-btn ${tone === tt.value ? 'active' : ''}`}
                  onClick={() => setTone(tt.value)}
                  disabled={loading}
                >
                  {t('contentGenerator.tone' + tt.value.charAt(0).toUpperCase() + tt.value.slice(1))}
                </button>
              ))}
            </div>
          </section>

          <section className="studio-composer__option">
            <div className="studio-step-heading">
              <span className="studio-step-number">03</span>
              <div>
                <h3 className="studio-card__title">{t('contentGenerator.platformsLabel')}</h3>
                <p className="studio-card__hint">{t('contentGenerator.platformsSubheading')}</p>
              </div>
            </div>
            <div className="platform-selector">
              {PLATFORMS.map((p) => {
                const on = selectedPlatforms.includes(p.value);
                const linked = connectedPlatforms.includes(p.value);
                return (
                  <button
                    key={p.value}
                    type="button"
                    role="switch"
                    aria-checked={on}
                    className={`platform-btn ${on ? 'active' : ''}`}
                    onClick={() => togglePlatform(p.value)}
                    disabled={loading}
                  >
                    <span className="platform-btn-icon" style={{ background: p.color }}>{p.icon}</span>
                    <span className="platform-btn-text">
                      <span className="platform-btn-name">{p.label}</span>
                      <span className="platform-btn-state">{linked ? (t('dashboard.connectedStatus') || 'Connected') : (t('dashboard.awaitingConnection') || 'Not connected')}</span>
                    </span>
                    <span className="m-switch" aria-hidden="true" data-on={on} />
                  </button>
                );
              })}
            </div>
          </section>
        </div>

        <div className="studio-actions">
          <span className="studio-composer__selected">{selectedPlatforms.length} platform{selectedPlatforms.length === 1 ? '' : 's'} selected</span>
          <button type="submit" className="m-btn m-btn--primary studio-generate-btn" disabled={loading || !topic.trim()}>
            {loading ? (
              <><span className="spinner-sm" /> {t('contentGenerator.generating')}</>
            ) : (
              t('contentGenerator.generateBtn')
            )}
          </button>
        </div>
      </form>

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
              <div className="studio-section-heading competitor-heading"><div><h4 className="competitor-section-title">{t('contentGenerator.eliteAnalysisTitle')}</h4><p>{t('contentGenerator.eliteHint')}</p></div></div>
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
                              href={c.search_url || c.profile_link || '#'}
                              target="_blank"
                              rel="noreferrer"
                            >
                               <div className="viral-card-name">{c.name || t('contentGenerator.unknownCreator')}</div>
                              <span className={`market-match-badge ${c.match_type === 'exact' ? 'exact' : 'related'}`}>{c.match_type === 'exact' ? 'Exact match' : 'Related post'}</span>
                              {c.post_title && <strong className="viral-card-post-title">{c.post_title}</strong>}
                              {c.viral_hook && (
                                <div className="viral-card-hook">
                                  <span className="q">“</span>{c.viral_hook}<span className="q">”</span>
                                </div>
                              )}
                              {c.post_snippet && <p className="viral-card-snippet">{c.post_snippet}</p>}
                              {c.match_type === 'related' && <small className="viral-card-related">Related because it mentions: {(c.matched_terms || []).join(', ')}</small>}
                              <div className="viral-card-link">Search {PLATFORM_META[platform].label} posts <ExternalLink size={13} /></div>
                            </a>
                          ))
                        )}
                      </div>
                    ))}
                  </div>
                </section>

                <section className="strategy-section">
                  <div className="strategy-section-head">
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

          <div className="ai-image-section studio-tool-section">
            <div className="studio-section-heading"><div><h4>{t('contentGenerator.aiImageTitle')}</h4><p>{t('contentGenerator.imagePromptPlaceholder')}</p></div></div>
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
                  t('contentGenerator.proGenerator')
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
                  t('contentGenerator.freeGenerator')
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

          <div className="media-upload-section studio-tool-section">
            <div className="studio-section-heading"><div><h4>{t('contentGenerator.attachMedia')}</h4><p>{t('contentGenerator.browseFiles')}</p></div></div>
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
                  <img
                    src={mediaPreview}
                    alt={t('scheduler.previewAlt')}
                    decoding="async"
                    className="media-preview-img"
                    onError={(e) => console.error('Image load failed:', e.target.src)}
                  />
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
                const inProgress = (publishing && pendingPlatforms.includes(p.value)) || result?.status === 'processing';
                return (
                  <label key={p.value} className={`publish-platform-chip ${isSelected ? 'selected' : ''} ${isConnected ? 'connected' : 'disconnected'}`}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => togglePlatform(p.value)}
                      disabled={publishing || tiktokProcessing}
                    />
                    <span className="chip-icon" style={{ background: p.color }}>{p.icon}</span>
                    <span className="chip-label">{p.label}</span>
                    {inProgress ? (
                      <span className="spinner-sm" role="img" aria-label={t('contentGenerator.publishing')} />
                    ) : result && (
                      <span className={`chip-result ${result.status === 'success' ? 'ok' : result.status === 'timeout' ? 'pending' : 'fail'}`}>
                        {result.status === 'success' ? '✓' : result.status === 'timeout' ? '?' : '✗'}
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
            {tiktokNeedsVideo && (
              <p className="publish-hint">{t('contentGenerator.tiktokNeedsVideo')}</p>
            )}
            {/* Failures stay visible (toasts fade) with the platform's exact error.
                A TikTok post still processing shows its progress here too. */}
            {Object.entries(publishResults)
              .filter(([, r]) => r && r.status !== 'success')
              .map(([p, r]) => {
                const waiting = r.status === 'processing' || r.status === 'timeout';
                return (
                  <div key={p} className={`publish-result ${r.status}`} role={waiting ? 'status' : 'alert'}>
                    <strong>{platformName(p)}:</strong> {r.message || (waiting ? t('contentGenerator.publishing') : 'Publishing failed.')}
                  </div>
                );
              })}
          </div>

          <div className="publish-actions">
            <span className="publish-info" aria-live="polite">
              {publishing
                ? t('contentGenerator.publishingTo', { platforms: pendingPlatforms.map(platformName).join(', ') })
                : tiktokProcessing
                  ? t('contentGenerator.tiktokProcessingInfo')
                  : t('contentGenerator.publishInfo', { connected: connectedCount, total: selectedPlatforms.length })}
            </span>
            <button
              className={"btn " + PREMIUM_BTN}
              onClick={handlePublish}
              disabled={publishing || tiktokProcessing || connectedCount === 0}
              aria-busy={publishing || tiktokProcessing}
            >
              {publishing ? (
                <><span className="spinner-sm" /> {t('contentGenerator.publishing')}</>
              ) : tiktokProcessing ? (
                <><span className="spinner-sm" /> {t('contentGenerator.tiktokProcessingBtn')}</>
              ) : (
                t('contentGenerator.publishBtn')
              )}
            </button>
          </div>
        </div>
      )}

      <MarketInsights />

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
