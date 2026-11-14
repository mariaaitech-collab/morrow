import { createContext, useContext } from 'react';
import { FaFacebookF, FaInstagram, FaLinkedinIn, FaTiktok } from 'react-icons/fa';

// Which platforms the AI Responder works on is decided by the backend
// (RESPONDER_PLATFORMS in backend/.env) and arrives with /responder/modes as
// { platforms, coming_soon }. AIResponder provides it; components read it with
// useResponderPlatforms() and never keep a list of their own.
export const ResponderPlatformsContext = createContext({ platforms: [], coming_soon: [] });
export function useResponderPlatforms() {
  return useContext(ResponderPlatformsContext).platforms;
}
export function useComingSoonPlatforms() {
  return useContext(ResponderPlatformsContext).coming_soon;
}

// Display names and icons only (which platforms are on comes from the backend).
// `noun` is what auto-replies work on, for sentences about the responder's scope.
export const PLATFORM_META = {
  facebook: { label: 'Facebook', noun: 'Facebook Pages', icon: <FaFacebookF /> },
  instagram: { label: 'Instagram', noun: 'Instagram', icon: <FaInstagram /> },
  linkedin: { label: 'LinkedIn', noun: 'LinkedIn', icon: <FaLinkedinIn /> },
  tiktok: { label: 'TikTok', noun: 'TikTok', icon: <FaTiktok /> },
};

// "A", "A and B", "A, B and C"
export function joinNames(names) {
  return names.length < 3 ? names.join(' and ') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

export const STATUS_META = {
  received: { label: 'Received', tone: 'muted' },
  processing: { label: 'Analyzing', tone: 'muted' },
  sending: { label: 'Sending', tone: 'muted' },
  pending_approval: { label: 'Needs attention', tone: 'warn' },
  auto_replied: { label: 'Auto-replied', tone: 'ok' },
  reply_deleted: { label: 'Reply deleted', tone: 'muted' },
  liked: { label: 'Liked (emoji only)', tone: 'ok' },
  approved_sent: { label: 'Approved & sent', tone: 'ok' },
  manual_sent: { label: 'Manual reply sent', tone: 'ok' },
  declined: { label: 'Declined', tone: 'muted' },
  ignored: { label: 'Ignored', tone: 'muted' },
  skipped: { label: 'Skipped', tone: 'muted' },
  failed: { label: 'Failed', tone: 'danger' },
};

// The two reply modes, as the user sees them everywhere.
export const MODE_META = {
  instant: { label: 'Instant Auto-Reply', short: 'Instant', desc: 'Comments that match a rule are answered within seconds, with no human step.' },
  review: { label: 'Review Before Posting', short: 'Review', desc: 'Every comment gets a suggested reply in Needs your attention. Nothing posts until you click.' },
};

export const DECISION_META = {
  auto_posted: 'Auto-posted',
  queued: 'Sent to review',
  declined: 'Declined',
  ignored: 'Ignored',
};

export const NO_MATCH_OPTIONS = [
  { id: 'queue', label: 'Send to Needs your attention', hint: 'Safest. You see it with the fallback reply drafted, and decide.', tag: 'Recommended' },
  { id: 'fallback', label: 'Post the generic fallback reply', hint: 'Posted instantly, without you. Write it under “Fallback reply” below.' },
  { id: 'ignore', label: 'Do nothing, mark as ignored', hint: 'No reply. It is logged in Activity as Ignored.' },
];

export const MATCH_TYPES = [
  { id: 'smart', label: 'Smart', hint: 'Keywords and trigger phrases, small misspellings caught' },
  { id: 'contains', label: 'Contains', hint: 'The comment contains a keyword or phrase (whole words)' },
  { id: 'starts_with', label: 'Starts with', hint: 'The comment starts with a keyword or phrase' },
  { id: 'exact', label: 'Exact', hint: 'The whole comment is exactly a keyword or phrase' },
];

// "Mode used" for one event, e.g. "Instant · this channel".
export function modeLabel(mode, source) {
  if (!MODE_META[mode]) return '';
  return `${MODE_META[mode].short}${source === 'channel' ? ' (channel setting)' : source === 'workspace' ? ' (workspace default)' : ''}`;
}

export function channelName(channels, key) {
  return (channels || []).find((c) => c.key === key)?.name || '';
}

export function PlatformBadge({ platform, size = 'md' }) {
  const meta = PLATFORM_META[platform] || { label: platform, icon: platform?.[0]?.toUpperCase() };
  return (
    <span className={`ar-platform ar-platform-${size} ${platform}`} title={meta.label} aria-label={meta.label}>
      {meta.icon}
    </span>
  );
}

export function StatusPill({ status }) {
  const meta = STATUS_META[status] || { label: status, tone: 'muted' };
  return <span className={`ar-pill ar-pill-${meta.tone}`}>{meta.label}</span>;
}

// Timestamp helpers now live in utils/time.js; re-exported for existing imports.
export { parseUtc, formatLocal, timeAgo } from '../../utils/time';

// Reply languages a rule answer can be written for.
export const LANG_OPTIONS = [
  { id: 'any', label: 'Any language' },
  { id: 'en', label: 'English' },
  { id: 'ur', label: 'Roman Urdu' },
  { id: 'ur-Arab', label: 'اردو (Urdu script)' },
];
