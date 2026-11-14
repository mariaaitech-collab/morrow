import { forwardRef } from 'react';
import { Loader2 } from 'lucide-react';
import { ICON } from './icon';

/**
 * Button: 40px high, 10px radius.
 *
 *   variant  'primary'   teal, navy text: the default main action (Save, Add, Generate, Connect).
 *            'purple'    purple, white text: secondary emphasis (featured plan, "Today").
 *            'highlight' yellow: RARE, only Create / Schedule post / Save rules-type commits.
 *            'secondary' white with a border (default): Cancel, Back, Manage, View all.
 *            'ghost'     no border; for low-emphasis and icon-only actions.
 *            'danger'    destructive actions.
 *   as       render a Link/anchor instead of <button> (pass `to`/`href`).
 *   icon     lucide icon component shown before the label.
 *   loading  shows a spinner and blocks clicks.
 */
const Button = forwardRef(function Button(
  {
    as: Component = 'button',
    variant = 'secondary',
    icon: Icon,
    iconRight: IconRight,
    loading = false,
    block = false,
    className = '',
    disabled,
    type,
    children,
    ...rest
  },
  ref,
) {
  const isNativeButton = Component === 'button';
  const iconOnly = !children && (Icon || loading);
  const classes = [
    'm-btn',
    `m-btn--${variant}`,
    iconOnly && 'm-btn--icon',
    block && 'm-btn--block',
    className,
  ].filter(Boolean).join(' ');

  return (
    <Component
      ref={ref}
      className={classes}
      type={isNativeButton ? type || 'button' : undefined}
      disabled={isNativeButton ? disabled || loading : undefined}
      aria-disabled={!isNativeButton && disabled ? true : undefined}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 {...ICON} className="m-spin" aria-hidden="true" /> : Icon && <Icon {...ICON} aria-hidden="true" />}
      {children}
      {IconRight && <IconRight {...ICON} aria-hidden="true" />}
    </Component>
  );
});

export default Button;

/** Square icon-only button. `label` is required: it becomes the accessible name. */
export const IconButton = forwardRef(function IconButton({ icon, label, variant = 'ghost', ...rest }, ref) {
  return <Button ref={ref} icon={icon} variant={variant} aria-label={label} title={label} {...rest} />;
});
