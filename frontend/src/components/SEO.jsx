import { Helmet } from 'react-helmet-async';

// Production origin — used for canonical URLs, OG/Twitter and the sitemap.
export const SITE_URL = 'https://brandaura.meveryx.com';

const DEFAULT_IMAGE = `${SITE_URL}/og-image.png`;

// <SEO /> is a drop-in component for any route. It injects <title>, meta
// description, canonical, Open Graph, Twitter Card and optional JSON-LD
// (structured data) into <head> for that page. Titles stay <= 60 chars and
// descriptions <= 155 chars so Google renders them cleanly.
export default function SEO({
  title = 'Morrow | AI Social Media Manager & Content Calendar',
  description = 'Manage social media, generate AI content and auto-schedule posts across every channel with Morrow — the all-in-one AI social media management platform.',
  path = '/',
  image = DEFAULT_IMAGE,
  type = 'website',
  keywords,
  jsonLd,
}) {
  const canonical = `${SITE_URL}${path === '/' ? '' : path}`.replace(/\/$/, path === '/' ? '/' : '');

  return (
    <Helmet>
      <title>{title}</title>
      <meta name="description" content={description} />
      {keywords && <meta name="keywords" content={keywords} />}
      <meta name="robots" content="index, follow" />
      <meta name="referrer" content="origin-when-cross-origin" />
      <link rel="canonical" href={canonical} />

      {/* Open Graph */}
      <meta property="og:type" content={type} />
      <meta property="og:site_name" content="Morrow" />
      <meta property="og:title" content={title} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={canonical} />
      <meta property="og:image" content={image} />
      <meta property="og:image:width" content="1200" />
      <meta property="og:image:height" content="630" />
      <meta property="og:image:alt" content="AI social media manager — schedule, generate and analyze content with Morrow" />

      {/* Twitter Card */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={title} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={image} />
      <meta name="twitter:image:alt" content="AI social media manager — schedule, generate and analyze content with Morrow" />

      {jsonLd && <script type="application/ld+json">{JSON.stringify(jsonLd)}</script>}
    </Helmet>
  );
}
