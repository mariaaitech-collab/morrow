import Button from './Button';
import { ICON } from './icon';

/**
 * Empty state: muted circle icon, one heading, one sentence, one button.
 * `action` = { label, onClick } or { label, as: Link, to }.
 */
export default function EmptyState({ icon: Icon, title, description, action }) {
  const { label, ...actionProps } = action || {};
  return (
    <div className="m-empty">
      {Icon && (
        <span className="m-empty__icon" aria-hidden="true">
          <Icon {...ICON} />
        </span>
      )}
      <p className="m-empty__title">{title}</p>
      {description && <p className="m-empty__text">{description}</p>}
      {action && <Button variant="secondary" {...actionProps}>{label}</Button>}
    </div>
  );
}
