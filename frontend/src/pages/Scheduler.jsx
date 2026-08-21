import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import Navbar from '../components/Navbar';
import CropModal from '../components/CropModal';

const PLATFORMS = [
  { value: 'facebook', label: 'Facebook', icon: 'f', color: '#1877f2' },
  { value: 'linkedin', label: 'LinkedIn', icon: 'in', color: '#0a66c2' },
  { value: 'instagram', label: 'Instagram', icon: 'ig', color: '#dc2743' },
];

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const STATUS_META = {
  pending: { label: 'Pending', cls: 'pending' },
  processing: { label: 'Publishing', cls: 'processing' },
  published: { label: 'Published', cls: 'published' },
  failed: { label: 'Failed', cls: 'failed' },
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

  const fileInputRef = useRef(null);
  const formRef = useRef(null);

  const connected = accounts.filter((a) => a.connected).map((a) => a.platform);

  const fetchAccounts = async () => {
    try {
      const { data } = await api.get('/social/accounts');
      setAccounts(data);
      const connectedOnes = data.filter((a) => a.connected).map((a) => a.platform);
      setSelectedPlatforms(connectedOnes);
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || 'Failed to load social accounts');
    }
  };

  const fetchPosts = async () => {
    try {
      const { data } = await api.get('/schedule');
      setPosts(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || 'Failed to load scheduled posts');
    }
  };

  const refresh = async () => {
    setLoading(true);
    try {
      await Promise.all([fetchAccounts(), fetchPosts()]);
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
      toast.success(`Selected: ${file.name}`);
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
    toast.success(`Cropped: ${blob.name}`);
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
      toast.error('Enter a topic or prompt for the post');
      return;
    }
    if (targets.length === 0) {
      toast.error('None of the selected platforms are connected');
      return;
    }
    const [h, m] = (formTime || '09:00').split(':').map(Number);
    const local = new Date(selectedDay);
    local.setHours(h, m, 0, 0);
    // Accept anything within 1 minute of now (up to 60s past skew tolerated)
    if (local.getTime() < Date.now() - 60000) {
      toast.error('Scheduled time must be at least 1 minute in the future');
      return;
    }
    if (mediaMode === 'ai' && !aiPrompt.trim()) {
      toast.error('Enter an AI prompt for image generation');
      return;
    }
    if (mediaMode === 'upload' && mediaType === 'video' && !mediaFile) {
      toast.error('Attach a media file first');
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
      await api.post('/schedule', fd, { timeout: 300000 });
      toast.success(mediaMode === 'ai'
        ? 'Scheduled! AI image generated and uploaded.'
        : 'Post scheduled successfully!');
      setFormOpen(false);
      await fetchPosts();
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Failed to schedule post';
      toast.error(typeof detail === 'string' ? detail : 'Failed to schedule post');
    } finally {
      setSaving(false);
    }
  };

  const deletePost = async (post) => {
    if (!window.confirm(`Delete ${STATUS_META[post.status]?.label || post.status} post on ${new Date(post.scheduled_at).toLocaleString()}?`)) return;
    try {
      await api.delete(`/schedule/${post.id}`);
      toast.success('Scheduled post removed');
      await fetchPosts();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete post');
    }
  };

  return (
    <>
      <Navbar user={user} onLogout={onLogout} active="scheduler" />
      <div className="scheduler-page">
        <div className="scheduler-head">
          <h2>Auto Scheduler</h2>
          <div className="week-nav">
            <button className="btn btn-outline btn-sm" onClick={() => setWeekOffset((w) => w - 1)}>← Prev</button>
            <span className="week-label">
              {weekDays[0].toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} – {weekDays[6].toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
            </span>
            <button className="btn btn-outline btn-sm" onClick={() => setWeekOffset((w) => w + 1)}>Next →</button>
          </div>
        </div>

        {loading ? (
          <p className="sched-empty">Loading scheduled posts…</p>
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
                    <span className="day-name">{WEEKDAYS[(day.getDay() + 6) % 7]}</span>
                    <span className="day-date">{day.getDate()}</span>
                  </div>
                  <span className="day-add">+ Add</span>
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
                            {new Date(p.scheduled_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                          </span>
                          <span className={`sched-status ${STATUS_META[p.status]?.cls || 'pending'}`}>
                            {STATUS_META[p.status]?.label || p.status}
                          </span>
                        </div>
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
                              <img src={p.media_url} alt="" className="sched-thumb" />
                            )}
                          </div>
                        )}
                        <p className="sched-caption">{p.content}</p>
                        {(p.status === 'pending' || p.status === 'failed') && (
                          <button className="sched-delete" onClick={() => deletePost(p)}>✕</button>
                        )}
                      </div>
                    ))}
                    {dayPosts.length === 0 && <span className="day-empty">No posts</span>}
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {formOpen && (
          <div className="sched-form" ref={formRef}>
            <div className="sched-form-head">
              <h3>Schedule a Post</h3>
              <button className="btn btn-outline btn-sm" onClick={() => setFormOpen(false)}>Close</button>
            </div>

            <div className="sched-form-grid">
              <div className="form-field">
                <label>Date</label>
                <input
                  type="date"
                  value={toLocalDateInput(selectedDay)}
                  onChange={(e) => setSelectedDay(new Date(`${e.target.value}T12:00:00`))}
                />
              </div>
              <div className="form-field">
                <label>Time</label>
                <input type="time" value={formTime} onChange={(e) => setFormTime(e.target.value)} step="300" />
              </div>
            </div>

            <div className="form-field">
              <label>Platforms</label>
              <div className="platform-selector">
                {PLATFORMS.map((p) => {
                  const isConnected = connected.includes(p.value);
                  const active = selectedPlatforms.includes(p.value);
                  return (
                    <button
                      key={p.value}
                      type="button"
                      className={`platform-btn ${active ? 'active' : ''} ${isConnected ? 'connected' : 'disconnected'}`}
                      style={active ? { borderColor: p.color, background: `${p.color}22` } : undefined}
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
                <p className="sched-note">Pay attention: disconnected platform selections are ignored.</p>
              )}
            </div>

            <div className="form-field">
              <label>Topic / Prompt</label>
              <textarea
                className="ai-image-prompt"
                rows={3}
                placeholder="Enter a topic or prompt — e.g. '5 productivity tips for remote teams'"
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
              />
              <div className="sched-tip">
                <span>💡</span>
                <span><strong>AI formats your caption.</strong> The scheduler converts your topic into a polished post with hashtags and emojis — that's the exact text that gets published.</span>
              </div>
            </div>

            <div className="form-field">
              <label>Media</label>
              <div className="media-toggle">
                <button
                  type="button"
                  className={`media-toggle-btn ${mediaMode === 'upload' ? 'active' : ''}`}
                  onClick={() => setMediaMode('upload')}
                >
                  📁 Option A: Upload Media
                </button>
                <button
                  type="button"
                  className={`media-toggle-btn ${mediaMode === 'ai' ? 'active' : ''}`}
                  onClick={() => setMediaMode('ai')}
                >
                  ✨ Option B: AI Generation
                </button>
              </div>

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
                    {mediaFile ? 'Replace Media' : 'Browse & Attach'}
                  </label>
                  {mediaFile && (
                    <button className="btn btn-danger btn-sm" onClick={removeMedia}>Remove</button>
                  )}
                  {mediaPreview && (
                    <div className="media-preview">
                      {mediaType === 'video' ? (
                        <video src={mediaPreview} controls className="media-preview-video" />
                      ) : (
                        <img src={mediaPreview} alt="Preview" className="media-preview-img" />
                      )}
                    </div>
                  )}
                  <p className="sched-note">Images open in the cropper. Leave empty for a text-only post.</p>
                </div>
              ) : (
                <div className="ai-image-section">
                  <textarea
                    className="ai-image-prompt"
                    rows={2}
                    placeholder="Describe the image to generate, e.g. 'A luxury office at sunset, purple neon branding'"
                    value={aiPrompt}
                    onChange={(e) => setAiPrompt(e.target.value)}
                  />
                  <div className="sched-tip">
                    <span>💡</span>
                    <span><strong>Suggestion:</strong> AI images are generated automatically in the background. If you want to preview, crop, or adjust an image before scheduling, please save it first and use the <strong>'Upload File'</strong> option.</span>
                  </div>
                </div>
              )}
            </div>

            <div className="sched-actions">
              <button className="btn btn-primary btn-lg" onClick={submitSchedule} disabled={saving}>
                {saving ? <><span className="spinner-sm" /> Scheduling…</> : '📅 Schedule Post'}
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
    </>
  );
}

export default Scheduler;