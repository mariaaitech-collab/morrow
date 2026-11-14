/**
 * Badge / status chip: low-opacity tinted background with full-strength
 * matching text.
 *
 *   tone  'neutral' | 'accent' | 'accent-2' | 'success' | 'warning' | 'danger'
 *   dot   prefix with a small dot in the text colour
 *   icon  lucide icon (rendered at 14px to sit inside the 22px chip)
 */
export default function Badge({ tone = 'neutral', dot = false, icon: Icon, className = '', children, ...rest }) {
  return (
    <span className={`m-badge m-badge--${tone} ${className}`.trim()} {...rest}>
      {dot && <span className="m-badge__dot" aria-hidden="true" />}
      {Icon && <Icon size={14} strokeWidth={1.5} aria-hidden="true" />}
      {children}
    </span>
  );
}
