/** Page title row: optional eyebrow, 30px title, subtitle and action buttons. */
export default function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <header className="m-page-header">
      <div className="m-page-header__text">
        {eyebrow && <p className="m-page-header__eyebrow">{eyebrow}</p>}
        <h1 className="m-page-header__title">{title}</h1>
        {subtitle && <p className="m-page-header__subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="m-page-header__actions">{actions}</div>}
    </header>
  );
}
