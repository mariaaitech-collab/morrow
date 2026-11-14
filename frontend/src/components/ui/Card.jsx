import { ICON } from './icon';

/**
 * Card: surface background, 1px border, 12px radius, 20px padding, no shadow.
 * `interactive` cards (rendered as a button or link via `as`) gain a soft
 * shadow on hover. `flush` removes the padding for edge-to-edge lists.
 */
export function Card({ as: Component = 'div', interactive = false, flush = false, className = '', children, ...rest }) {
  const classes = ['m-card', interactive && 'm-card--interactive', flush && 'm-card--flush', className]
    .filter(Boolean)
    .join(' ');
  const extra = Component === 'button' && !rest.type ? { type: 'button' } : {};
  return (
    <Component className={classes} {...extra} {...rest}>
      {children}
    </Component>
  );
}

/** Section heading row inside a card: icon, title, subtitle and one action. */
export function CardHeader({ title, subtitle, icon: Icon, action, as: Heading = 'h2', id }) {
  return (
    <div className="m-card-header">
      <div className="m-card-header__text">
        <Heading className="m-card-header__title" id={id}>
          {Icon && <Icon {...ICON} aria-hidden="true" className="m-card-header__icon" />}
          {title}
        </Heading>
        {subtitle && <p className="m-card-header__subtitle">{subtitle}</p>}
      </div>
      {action && <div className="m-card-header__action">{action}</div>}
    </div>
  );
}

export default Card;
