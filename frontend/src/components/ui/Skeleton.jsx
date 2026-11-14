/** Loading placeholder block in --surface-2. Use instead of spinners. */
export default function Skeleton({ width = '100%', height = 14, radius, className = '' }) {
  return (
    <span
      className={`m-skeleton ${className}`.trim()}
      style={{ width, height, borderRadius: radius }}
      aria-hidden="true"
    />
  );
}
