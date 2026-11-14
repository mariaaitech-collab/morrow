import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import { ensureToken } from '../api/tokens';
import { useLanguage } from '../i18n/LanguageContext';
import WorkspaceShell from '../components/WorkspaceShell';
import CropModal from '../components/CropModal';

const PLATFORMS = [
  { value: 'facebook', label: 'Facebook', icon: 'f', color: 'var(--platform-facebook)' },
  { value: 'linkedin', label: 'LinkedIn', icon: 'in', color: 'var(--platform-linkedin)' },
  { value: 'instagram', label: 'Instagram', icon: 'ig', color: 'var(--platform-instagram)' },
];

const WEEKDAYS = ['weekdayMon', 'weekdayTue', 'weekdayWed', 'weekdayThu', 'weekdayFri', 'weekdaySat', 'weekdaySun'];

const STATUS_META = {
  pending: { cls: 'pending' },
  processing: { cls: 'processing' },
  published: { cls: 'published' },
  failed: { cls: 'failed' },
};

const toLocalDateInput = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

function Scheduler({ user, onLogout }) {
  const [accounts, setAccounts] = useState([]);
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);

  const [weekOffset, setWeekOffset] = useState(0);
  const [selectedDay, setSelectedDay] = useState(() => new Date());
  const [formOpen, setFormOpen] = useState(false);

  const [formTime, setFormTime] = useState('10:00');
  const [selectedPlatforms, setSelectedPlatforms] = useState([]);
  const [caption, setCaption] = useState('');

  const [mediaMode, setMediaMode] = useState('upload');
  const [aiPrompt, setAiPrompt] = useState('');
  const [mediaFile, setMediaFile] = useState(null);
  const [mediaPreview, setMediaPreview] = useState(null);
  const [mediaType, setMediaType] = useState(null);
  const [cropModal, setCropModal] = useState(null);
  const [saving, setSaving] = useState(false);
  // Whether "Option B: AI Generation" can be used right now (GET /content/image-provider).
  const [imageProvider, setImageProvider] = useState(null);
  const [now, setNow] = useState(() => Date.now());

  const fileInputRef = useRef(null);
  const formRef = useRef(null);
  const { t, language } = useLanguage();

  const connected = accounts.filter((a) => a.connected).map((a) => a.platform);

  const statusLabel = (s) =>
    t('scheduler.status' + (s ? s.charAt(0).toUpperCase() + s.slice(1) : ''));

  const fetchAccounts = async () => {
    try {
      const { data } = await api.get('/social/accounts');
      setAccounts(data);
      const connectedOnes = data.filter((a) => a.connected).map((a) => a.platform);
      setSelectedPlatforms(connectedOnes);
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || t('scheduler.loadAccountsError'));
    }
  };

  const fetchPosts = async () => {
    try {
      const { data } = await api.get('/schedule');
      setPosts(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || t('scheduler.loadPostsError'));
    }
  };

  const fetchImageProvider = async () => {
    try {
      const { data } = await api.get('/content/image-provider');
      setImageProvider(data);
    } catch {
      // Unknown status: leave Option B as it was rather than block it.
    }
  };

  const refresh = async () => {
    setLoading(true);
    try {
      await Promise.all([fetchAccounts(), fetchPosts(), fetchImageProvider()]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(fetchPosts, 30000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const aiBlocked = Boolean(imageProvider && !imageProvider.available);
  const retryAt = imageProvider?.retry_at ? new Date(imageProvider.retry_at).getTime() : null;

  // While AI generation is paused, tick once a second for the countdown and
  // re-check the provider when the pause ends.
  useEffect(() => {
    if (!retryAt) return undefined;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const recheck = setTimeout(fetchImageProvider, Math.min(Math.max(retryAt - Date.now(), 0) + 1000, 2147483647));
    return () => { clearInterval(tick); clearTimeout(recheck); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryAt]);

  useEffect(() => {
    if (aiBlocked && mediaMode === 'ai') setMediaMode('upload');
  }, [aiBlocked, mediaMode]);

  const aiOffLine = () => {
    if (!aiBlocked) return '';
    const parts = [t('scheduler.aiOff', { reason: imageProvider.headline || imageProvider.reason })];
    if (retryAt) {
      const secs = Math.max(0, Math.ceil((retryAt - now) / 1000));
      parts.push(secs <= 120
        ? t('scheduler.aiBackIn', { seconds: secs })
        : t('scheduler.aiBackAt', { time: new Date(retryAt).toLocaleTimeString(language, { hour: 'numeric', minute: '2-digit' }) }));
    }
    parts.push(t('scheduler.aiUseUpload'));
    return parts.join(' ');
  };

  // Clean up object URL on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (mediaPreview) URL.revokeObjectURL(mediaPreview);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mediaPreview]);

  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const addDays = (d, n) => {
    const r = new Date(d);
    r.setDate(r.getDate() + n);
    return r;
  };
  const mondayOf = (d) => {
    const dow = (d.getDay() + 6) % 7;
    return startOfDay(addDays(d, -dow));
  };

  const weekStart = addDays(mondayOf(new Date()), weekOffset * 7);
  const weekDays = WEEKDAYS.map((_, i) => addDays(weekStart, i));

  const postsByDay = (day) =>
    posts
      .filter((p) => new Date(p.scheduled_at).toDateString() === day.toDateString())
      .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime());

  const openDay = (day) => {
    setSelectedDay(day);
    setFormTime('10:00');
    setCaption('');
    setMediaMode('upload');
    setAiPrompt('');
    setMediaFile(null);
    setMediaPreview(null);
    setMediaType(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    fetchImageProvider();
    setFormOpen(true);
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
  };

  const togglePlatform = (p) =>
    setSelectedPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setMediaMode('upload');
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');
    // Clean up previous object URL if exists
    if (mediaPreview) URL.revokeObjectURL(mediaPreview);
    if (isImage) {
      const url = URL.createObjectURL(file);
      setMediaPreview(url);
      setCropModal({ url, name: file.name });
      setMediaType('image');
      e.target.value = '';
    } else if (isVideo) {
      const url = URL.createObjectURL(file);
      setMediaPreview(url);
      setMediaFile(file);
      setMediaType('video');
      toast.success(t('scheduler.selected', { name: file.name }));
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
    toast.success(t('scheduler.cropped', { name: blob.name }));
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

  const submitSchedule = async () => {
    const targets = selectedPlatforms.filter((p) => connected.includes(p));
    if (!caption.trim()) {
      toast.error(t('scheduler.enterTopic'));
      return;
    }
    if (targets.length === 0) {
      toast.error(t('scheduler.noneConnected'));
      return;
    }
    if (!ensureToken()) return;
    const [h, m] = (formTime || '09:00').split(':').map(Number);
    const local = new Date(selectedDay);
    local.setHours(h, m, 0, 0);
    // Accept anything within 1 minute of now (up to 60s past skew tolerated)
    if (local.getTime() < Date.now() - 60000) {
      toast.error(t('scheduler.futureTime'));
      return;
    }
    if (mediaMode === 'ai' && !aiPrompt.trim()) {
      toast.error(t('scheduler.enterAiPrompt'));
      return;
    }
    if (mediaMode === 'upload' && mediaType === 'video' && !mediaFile) {
      toast.error(t('scheduler.attachMedia'));
      return;
    }

    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('scheduled_at', local.toISOString());
      fd.append('platforms', JSON.stringify(targets));
      fd.append('content', caption.trim());
      if (mediaMode === 'ai') {
        fd.append('ai_prompt', aiPrompt.trim());
      } else if (mediaFile) {
        fd.append('media', mediaFile);
      }
      const { data } = await api.post('/schedule', fd, { timeout: 300000 });
      if (data?.media_error) {
        // Saved anyway: the post goes out text-only. Say exactly why the image failed.
        toast(t('scheduler.scheduledImageFailed', { reason: data.media_error }), { icon: '⚠️', duration: 12000 });
      } else {
        toast.success(mediaMode === 'ai'
          ? t('scheduler.scheduledAI')
          : t('scheduler.scheduledOk'));
      }
      setFormOpen(false);
      if (mediaMode === 'ai') fetchImageProvider();
      await fetchPosts();
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || t('scheduler.failedSchedule');
      toast.error(typeof detail === 'string' ? detail : t('scheduler.failedSchedule'));
    } finally {
      setSaving(false);
    }
  };

  const deletePost = async (post) => {
    if (!window.confirm(t('scheduler.deleteConfirm', { label: statusLabel(post.status), date: new Date(post.scheduled_at).toLocaleString(language) }))) return;
    try {
      await api.delete(`/schedule/${post.id}`);
      toast.success(t('scheduler.removed'));
      await fetchPosts();
    } catch (err) {
      toast.error(err.response?.data?.detail || t('scheduler.failedDelete'));
    }
  };

  return (
    <>
      <WorkspaceShell user={user} onLogout={onLogout} active="scheduler">
      <div className="m-page scheduler-page">
        <div className="scheduler-head">
          <h1>{t('scheduler.title')}</h1>
          <div className="week-nav">
            <button className="btn btn-outline btn-sm" onClick={() => setWeekOffset((w) => w - 1)}>{t('scheduler.prev')}</button>
            <span className="week-label">
              {weekDays[0].toLocaleDateString(language, { month: 'short', day: 'numeric' })} – {weekDays[6].toLocaleDateString(language, { month: 'short', day: 'numeric' })}
            </span>
            <button className="btn btn-outline btn-sm" onClick={() => setWeekOffset((w) => w + 1)}>{t('scheduler.next')}</button>
          </div>
        </div>

        {loading ? (
          <p className="sched-empty">{t('scheduler.loading')}</p>
        ) : (
          <div className="week-grid">
            {weekDays.map((day) => {
              const dayPosts = postsByDay(day);
              return (
                <button
                  key={day.toISOString()}
                  className="day-column"
                  onClick={() => openDay(day)}
                >
                  <div className={`day-header ${day.toDateString() === new Date().toDateString() ? 'today' : ''}`}>
                    <span className="day-name">{t('scheduler.' + WEEKDAYS[(day.getDay() + 6) % 7])}</span>
                    <span className="day-date">{day.getDate()}</span>
                  </div>
                   <span className="day-add">{t('scheduler.add')}</span>
                  <div className="day-posts">
                    {dayPosts.map((p) => (
                      <div
                        key={p.id}
                        className={`sched-card ${STATUS_META[p.status]?.cls || 'pending'}`}
                        onClick={(e) => e.stopPropagation()}
                        title={p.content}
                      >
                        <div className="sched-card-top">
                          <span className="sched-card-time">
                            {new Date(p.scheduled_at).toLocaleTimeString(language, { hour: 'numeric', minute: '2-digit' })}
                          </span>
                          {!(p.media_error && p.status === 'pending') && (
                            <span className={`sched-status ${STATUS_META[p.status]?.cls || 'pending'}`}>
                              {statusLabel(p.status)}
                            </span>
                          )}
                        </div>
                        {p.media_error && p.status === 'pending' && (
                          <span className="sched-status image-failed">{t('scheduler.statusImageFailed')}</span>
                        )}
                        {p.media_error && (
                          <p className="sched-media-error" title={p.media_error}>
                            {t('scheduler.imageFailedReason', { reason: p.media_error })}
                          </p>
                        )}
                        <div className="sched-card-platforms">
                          {p.platforms.map((pl) => (
                            <span key={pl} className="sched-chip">{PLATFORMS.find((x) => x.value === pl)?.label || pl}</span>
                          ))}
                        </div>
                        {p.media_url && (
                          <div className="sched-thumb-wrap">
                            {p.media_type === 'video' ? (
                              <video src={p.media_url} muted playsInline className="sched-thumb" />
                            ) : (
                              <img src={p.media_url} alt="" loading="lazy" decoding="async" className="sched-thumb" />
                            )}
                          </div>
                        )}
                        <p className="sched-caption">{p.content}</p>
                        {(p.status === 'pending' || p.status === 'failed') && (
                          <button className="sched-delete" onClick={() => deletePost(p)}>✕</button>
                        )}
                      </div>
                    ))}
                    {dayPosts.length === 0 && <span className="day-empty">{t('scheduler.noPosts')}</span>}
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {formOpen && (
          <div className="sched-form" ref={formRef}>
            <div className="sched-form-head">
              <h3>{t('scheduler.schedulePost')}</h3>
              <button className="btn btn-outline btn-sm" onClick={() => setFormOpen(false)}>{t('scheduler.close')}</button>
            </div>

            <div className="sched-form-grid">
              <div className="form-field">
                <label>{t('scheduler.date')}</label>
                <input
                  type="date"
                  value={toLocalDateInput(selectedDay)}
                  onChange={(e) => setSelectedDay(new Date(`${e.target.value}T12:00:00`))}
                />
              </div>
              <div className="form-field">
                <label>{t('scheduler.time')}</label>
                <input type="time" value={formTime} onChange={(e) => setFormTime(e.target.value)} step="300" />
              </div>
            </div>

            <div className="form-field">
              <label>{t('scheduler.platforms')}</label>
              <div className="platform-selector">
                {PLATFORMS.map((p) => {
                  const isConnected = connected.includes(p.value);
                  const active = selectedPlatforms.includes(p.value);
                  return (
                    <button
                      key={p.value}
                      type="button"
                      className={`platform-btn ${active ? 'active' : ''} ${isConnected ? 'connected' : 'disconnected'}`}
                      style={active ? { borderColor: p.color, background: `color-mix(in srgb, ${p.color} 14%, var(--surface))` } : undefined}
                      onClick={() => togglePlatform(p.value)}
                    >
                      <span className="platform-btn-icon" style={{ background: p.color }}>
                        {p.icon}
                      </span>
                      <span className="platform-btn-name">{p.label}</span>
                      <span className={`connected-dot ${isConnected ? 'on' : ''}`} />
                    </button>
                  );
                })}
              </div>
              {selectedPlatforms.filter((p) => !connected.includes(p)).length > 0 && (
                <p className="sched-note">{t('scheduler.disconnectedNote')}</p>
              )}
            </div>

            <div className="form-field">
              <label>{t('scheduler.topicPrompt')}</label>
              <textarea
                className="ai-image-prompt"
                rows={3}
                placeholder={t('scheduler.topicPromptExample')}
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
              />
              <div className="sched-tip">
                <span>💡</span>
                <span>{t('scheduler.tipAI')}</span>
              </div>
            </div>

            <div className="form-field">
              <label>{t('scheduler.media')}</label>
              <div className="media-toggle">
                <button
                  type="button"
                  className={`media-toggle-btn ${mediaMode === 'upload' ? 'active' : ''}`}
                  onClick={() => setMediaMode('upload')}
                >
                  {t('scheduler.optionUpload')}
                </button>
                <button
                  type="button"
                  className={`media-toggle-btn ${mediaMode === 'ai' ? 'active' : ''}`}
                  onClick={() => setMediaMode('ai')}
                  disabled={aiBlocked}
                  title={aiBlocked ? imageProvider.reason : undefined}
                >
                  {t('scheduler.optionAI')}
                </button>
              </div>
              {aiBlocked && (
                <p className="sched-note warn" role="status" title={imageProvider.reason}>⚠️ {aiOffLine()}</p>
              )}

              {mediaMode === 'upload' ? (
                <div className="media-upload-section">
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="file-input"
                    accept="image/*,video/*"
                    onChange={handleFileSelect}
                  />
                  <label className="btn btn-outline btn-upload">
                    {mediaFile ? t('scheduler.replaceMedia') : t('scheduler.browseAttach')}
                  </label>
                  {mediaFile && (
                    <button className="btn btn-danger btn-sm" onClick={removeMedia}>{t('scheduler.remove')}</button>
                  )}
                  {mediaPreview && (
                    <div className="media-preview">
                      {mediaType === 'video' ? (
                        <video src={mediaPreview} controls className="media-preview-video" />
                      ) : (
                        <img src={mediaPreview} alt={t('scheduler.previewAlt')} decoding="async" className="media-preview-img" />
                      )}
                    </div>
                  )}
                  <p className="sched-note">{t('scheduler.imagesOpenCropper')}</p>
                </div>
              ) : (
                <div className="ai-image-section">
                  <textarea
                    className="ai-image-prompt"
                    rows={2}
                    placeholder={t('scheduler.aiPlaceholder')}
                    value={aiPrompt}
                    onChange={(e) => setAiPrompt(e.target.value)}
                  />
                  <div className="sched-tip">
                    <span>💡</span>
                    <span>{t('scheduler.aiSuggestion')}</span>
                  </div>
                </div>
              )}
            </div>

            <div className="sched-actions">
              <button type="button" className="btn btn-highlight btn-lg" onClick={submitSchedule} disabled={saving}>
                {saving ? <><span className="spinner-sm" /> {t('scheduler.schedulePost')}…</> : '📅 ' + t('scheduler.scheduleBtn')}
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
      </WorkspaceShell>
    </>
  );
}

export default Scheduler;