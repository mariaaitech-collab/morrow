// Platform identity without brand icon sets (lucide only): a monogram on a
// tile tinted with the platform colour. Text stays --text, so it passes AA.
export const PLATFORMS = {
  instagram: { label: 'Instagram', short: 'IG' },
  facebook: { label: 'Facebook', short: 'FB' },
  linkedin: { label: 'LinkedIn', short: 'IN' },
  tiktok: { label: 'TikTok', short: 'TT' },
};

export function platformLabel(platform) {
  return PLATFORMS[platform]?.label || platform;
}

export default function PlatformTile({ platform, size = 'md', showTitle = true }) {
  const meta = PLATFORMS[platform] || { label: platform, short: (platform || '?').slice(0, 2).toUpperCase() };
  return (
    <span
      className={`m-platform m-platform--${size} m-platform--${platform}`}
      title={showTitle ? meta.label : undefined}
      aria-label={meta.label}
      role="img"
    >
      {meta.short}
    </span>
  );
}
