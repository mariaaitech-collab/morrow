// Date helpers shared across screens.
//
// The API stores UTC. Some endpoints serialize naive ISO strings
// ("2026-10-17T11:02:03.632") with no offset, which `new Date()` would read as
// LOCAL time. Any timestamp without a zone is therefore treated as UTC.
const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i;

export function parseUtc(value) {
  if (value == null || value === '') return null;
  if (value instanceof Date) return value;
  if (typeof value === 'number') return new Date(value);
  const text = String(value).trim().replace(' ', 'T');
  const date = new Date(HAS_ZONE.test(text) ? text : `${text}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatLocal(value, options = { dateStyle: 'medium', timeStyle: 'short' }, locale) {
  const date = parseUtc(value);
  return date ? date.toLocaleString(locale, options) : '';
}

export function timeAgo(value) {
  const date = parseUtc(value);
  if (!date) return '';
  const diff = Math.max(0, (Date.now() - date.getTime()) / 1000); // small clock skew -> "just now"
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Local midnight of the Monday that starts the week containing `date`. */
export function startOfWeek(date = new Date()) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d;
}

export function isSameLocalDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}
