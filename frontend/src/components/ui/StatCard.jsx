import Card from './Card';
import Skeleton from './Skeleton';

/**
 * Stat card: label, optional title, large tabular number with a short meta
 * line, optional badge (top right) and optional progress bar.
 *
 *   progress  { value, max } -> accessible progress bar under the number
 *   icon      lucide icon shown in a tile next to the label
 *   tone      colour accent: 'purple' | 'teal' | 'blue' | 'navy' (optional)
 */
export default function StatCard({ label, title, value, meta, badge, progress, icon: Icon, tone, loading = false }) {
  const pct = progress && progress.max > 0 ? Math.min(100, Math.round((progress.value / progress.max) * 100)) : null;
  return (
    <Card className={`m-stat ${tone ? `m-stat--${tone}` : ''}`.trim()}>
      <div className="m-stat__top">
        <span className="m-stat__head">
          {Icon && <span className="m-stat__icon" aria-hidden="true"><Icon size={20} /></span>}
          <span className="m-stat__label">{label}</span>
        </span>
        {badge}
      </div>
      {title && <p className="m-stat__title">{title}</p>}
      <div className="m-stat__figure">
        {loading ? <Skeleton width={64} height={34} /> : <span className="m-stat__value">{value}</span>}
        {meta && <span className="m-stat__meta">{meta}</span>}
      </div>
      {pct !== null && (
        <div
          className="m-progress"
          role="progressbar"
          aria-label={label}
          aria-valuenow={progress.value}
          aria-valuemin={0}
          aria-valuemax={progress.max}
        >
          <span style={{ width: `${pct}%` }} />
        </div>
      )}
    </Card>
  );
}
