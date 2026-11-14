export const BRAND_NAME = 'Morrow';
export const BRAND_TAGLINE = 'The market of tomorrow';

/**
 * Brand lockup: logo mark + "Morrow" wordmark, optionally with the tagline.
 * Text colour is inherited, so it works on the dark sidebar and light pages.
 */
export default function Logo({ tagline = false, size = 32, className = '' }) {
  return (
    <span className={`m-logo ${className}`.trim()}>
      <img className="m-logo__mark" src="/logo.png" alt="" width={size} height={size} />
      <span className="m-logo__text">
        <span className="m-logo__name">{BRAND_NAME}</span>
        {tagline && <span className="m-logo__tagline">{BRAND_TAGLINE}</span>}
      </span>
    </span>
  );
}
