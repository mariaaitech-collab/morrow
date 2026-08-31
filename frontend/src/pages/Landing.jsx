import { useState } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { Wand2, PenLine, CalendarClock } from 'lucide-react';
import { FaInstagram, FaLinkedin } from 'react-icons/fa';
import SEO from '../components/SEO';
import Footer from '../components/Footer';
import { isAuthenticated, clearAuth } from '../auth';
import { useLanguage } from '../i18n/LanguageContext';
import headphonesImg from '../assets/headphones.jpg';
import watchImg from '../assets/watch.jpg';
import coffeeImg from '../assets/coffee.jpg';
import productImg from '../assets/product.jpg';

const EASE = 'ease-[cubic-bezier(0.25,1,0.5,1)]';

const SOFTWARE_SCHEMA = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'SoftwareApplication',
      '@id': 'https://brandaura.meveryx.com/#software',
      name: 'BrandAura',
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      url: 'https://brandaura.meveryx.com/',
      description:
        'BrandAura is an AI social media manager and content calendar that helps creators and brands generate visuals, write captions, auto-schedule posts and track analytics.',
      offers: {
        '@type': 'Offer',
        price: '29.00',
        priceCurrency: 'USD',
        availability: 'https://schema.org/InStock',
      },
      featureList: [
        'AI content generation',
        'Social media auto-scheduling',
        'Content calendar planner',
        'Social media analytics',
        'Best time to post',
      ],
    },
    {
      '@type': 'Organization',
      '@id': 'https://brandaura.meveryx.com/#org',
      name: 'Meveryx',
      url: 'https://brandaura.meveryx.com/',
      logo: 'https://brandaura.meveryx.com/apple-touch-icon.png',
      contactPoint: {
        '@type': 'ContactPoint',
        email: 'hello@meveryx.com',
        contactType: 'customer support',
      },
    },
  ],
};

const CARDS = [
  {
    id: 'AIImage',
    icon: <Wand2 size={22} />,
    badge: 'AI',
    grad: 'from-pink-500/80 to-rose-500/80',
    shadow: 'hover:shadow-[0_20px_50px_-12px_rgba(236,72,153,0.6)]',
    rot: 'rotate-[-12deg]',
    dur: 5,
    delay: 0,
  },
  {
    id: 'ContentStudio',
    icon: <PenLine size={22} />,
    badge: 'Studio',
    grad: 'from-cyan-500/80 to-blue-500/80',
    shadow: 'hover:shadow-[0_20px_50px_-12px_rgba(6,182,212,0.6)]',
    rot: 'rotate-0',
    dur: 5.6,
    delay: 0.35,
  },
  {
    id: 'AutoScheduler',
    icon: <CalendarClock size={22} />,
    badge: 'Auto',
    grad: 'from-purple-500/80 to-indigo-500/80',
    shadow: 'hover:shadow-[0_20px_50px_-12px_rgba(168,85,247,0.6)]',
    rot: 'rotate-[12deg]',
    dur: 6.2,
    delay: 0.7,
  },
];

const SHOWCASE = [
  { platform: 'Instagram', icon: FaInstagram, id: '1', image: headphonesImg },
  { platform: 'LinkedIn', icon: FaLinkedin, id: '2', image: watchImg },
  { platform: 'Instagram', icon: FaInstagram, id: '3', image: coffeeImg },
  { platform: 'LinkedIn', icon: FaLinkedin, id: '4', image: productImg },
];
const showcaseLoop = [...SHOWCASE, ...SHOWCASE, ...SHOWCASE, ...SHOWCASE];

export default function Landing() {
  const { t } = useLanguage();
  const [authed, setAuthed] = useState(() => isAuthenticated());
  const scrollToFeatures = (e) => {
    e.preventDefault();
    document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' });
  };
  const handleLogout = () => {
    clearAuth();
    setAuthed(false);
    window.location.href = '/';
  };

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <SEO
        title="BrandAura | AI Social Media Manager &amp; Content Calendar"
        description="The AI social media manager that writes captions, generates AI content and auto-schedules posts across every channel. Plan, publish and analyze with BrandAura's content calendar and scheduler."
        path="/"
        keywords="AI social media manager, AI content calendar, social media scheduling tool, AI content generation, automated social media posting, social media analytics"
        jsonLd={SOFTWARE_SCHEMA}
      />

      {/* ===== Floating Pill Navbar ===== */}
      <header aria-label="Primary navigation" className="fixed left-1/2 top-4 z-50 -translate-x-1/2">
        <nav className="flex items-center gap-8 rounded-full border border-[#2A2A2A] bg-[#1C1C1E]/50 px-6 py-2.5 shadow-lg shadow-black/30 backdrop-blur-md">
          <Link to="/" className="text-lg font-bold tracking-tight text-white">
            Brand<span className="text-[#D6588A]">Aura</span>
          </Link>
          <div className="hidden items-center gap-7 text-sm text-[#9A9A9A] md:flex">
            <a href="#features" onClick={scrollToFeatures} className="transition-colors hover:text-white">
              {t('nav.features')}
            </a>
            <Link to="/about" className="transition-colors hover:text-white">
              {t('nav.about')}
            </Link>
          </div>
          {authed ? (
            <div className="flex items-center gap-2">
              <Link to="/dashboard" className="btn btn-primary btn-sm rounded-full">
                {t('nav.openDashboard')}
              </Link>
              <button onClick={handleLogout} className="btn btn-glass btn-sm rounded-full">
                {t('nav.logout')}
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link to="/register" className="btn btn-primary btn-sm rounded-full">
                {t('nav.getStarted')}
              </Link>
              <Link to="/login" className="btn btn-glass btn-sm rounded-full">
                {t('nav.login')}
              </Link>
            </div>
          )}
        </nav>
      </header>

      <main>
        {/* ===== Typography-Driven Hero ===== */}
        <section
          aria-labelledby="hero-heading"
          className="relative flex min-h-screen flex-col items-center justify-center px-6 text-center"
        >
          <div className="pointer-events-none absolute left-1/2 top-1/3 h-[420px] w-[820px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#D6588A]/30 blur-3xl" />

          <h1 id="hero-heading" className="relative z-10 text-5xl font-extrabold leading-[1.05] tracking-tight text-white md:text-7xl">
            {t('landing.hero1')}
            <br />
            <span
              className="font-serif italic text-[#D6588A]"
              style={{ textShadow: '0 0 45px rgba(214, 88, 138, 0.65)' }}
            >
              {t('landing.heroAccent')}
            </span>{' '}
            {t('landing.hero2')}
          </h1>
          <p className="relative z-10 mt-7 max-w-xl text-lg text-[#9A9A9A]">
            {t('landing.heroSub')}
          </p>
          <div className="relative z-10 mt-9 flex flex-wrap items-center justify-center gap-4">
            {authed ? (
              <Link to="/dashboard" className="btn btn-primary btn-lg rounded-full">
                {t('nav.openDashboard')}
              </Link>
            ) : (
              <>
                <Link to="/register" className="btn btn-primary btn-lg rounded-full">
                  {t('nav.getStarted')}
                </Link>
                <Link to="/login" className="btn btn-glass btn-lg rounded-full">
                  {t('nav.login')}
                </Link>
              </>
            )}
          </div>
        </section>

        {/* ===== 3D Floating Card Fan ===== */}
        <section
          id="features"
          aria-labelledby="features-heading"
          className="relative z-10 flex scroll-mt-24 items-end justify-center -space-x-8 px-6 pb-10"
          style={{ marginBottom: '-70px' }}
        >
          <h2 id="features-heading" className="sr-only">{t('nav.features')}</h2>
          {CARDS.map((c) => (
            <motion.div
              key={c.id}
              className="relative"
              animate={{ y: [0, -14, 0] }}
              transition={{
                duration: c.dur,
                repeat: Infinity,
                ease: 'easeInOut',
                delay: c.delay,
              }}
            >
              <div
                className={`group relative w-60 origin-bottom rounded-3xl border border-[#2A2A2A] bg-[#1C1C1E] p-6 text-left shadow-2xl shadow-black/50 transition-all duration-500 ${EASE} hover:-translate-y-[45px] hover:scale-105 hover:rotate-0 hover:z-20 hover:border-white/40 ${c.rot} ${c.shadow}`}
              >
                <div
                  className={`absolute inset-0 rounded-3xl bg-gradient-to-br ${c.grad} opacity-0 transition-opacity duration-500 ${EASE} group-hover:opacity-100`}
                />

                <span className="absolute -right-2 -top-2 z-20 rounded-full bg-[#E8558C] px-3 py-1 text-[0.65rem] font-bold uppercase tracking-wider text-white transition-all duration-300 group-hover:bg-white group-hover:text-[#1C1C1E] group-hover:shadow-[0_0_28px_rgba(255,255,255,0.7)]">
                  {t('landing.badge' + c.id)}
                </span>

                <div className="relative z-10">
                  <div className={`mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-[#D6588A] transition-all duration-500 ${EASE} group-hover:border-white/30 group-hover:bg-white/10 group-hover:text-white group-hover:[filter:drop-shadow(0_2px_10px_rgba(255,255,255,0.7))]`}>
                    {c.icon}
                  </div>
                  <h3 className={`text-base font-semibold text-white transition-all duration-500 ${EASE} group-hover:[text-shadow:0_2px_12px_rgba(255,255,255,0.6)]`}>
                    {t(`landing.feat${c.id}Title`)}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-[#9A9A9A] transition-colors duration-500 group-hover:text-white">
                    {t(`landing.feat${c.id}Desc`)}
                  </p>
                </div>
              </div>
            </motion.div>
          ))}
        </section>

        {/* ===== Campaign Showcase Carousel ===== */}
        <section aria-labelledby="showcase-heading" className="relative z-10 mx-auto w-full max-w-7xl px-6 py-24">
          <div className="mb-14 text-center">
            <p className="mb-3 text-sm font-semibold uppercase tracking-[0.25em] text-[#D6588A]">{t('landing.showcaseKicker')}</p>
            <h2 id="showcase-heading" className="text-3xl font-bold text-white md:text-5xl">{t('landing.showcaseTitle')}</h2>
            <p className="mx-auto mt-4 max-w-2xl text-[#B8A1A8]">
              {t('landing.showcaseSub')}
            </p>
          </div>

          <div className="group relative overflow-hidden rounded-3xl [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]">
            <div className="flex w-max gap-6 animate-marquee group-hover:[animation-play-state:paused]">
              {[...showcaseLoop, ...showcaseLoop].map((item, i) => {
                const Icon = item.icon;
                return (
                  <article
                    key={i}
                    className="group/card relative h-[400px] w-[300px] shrink-0 overflow-hidden rounded-2xl border border-white/10 shadow-2xl shadow-[0_25px_70px_-15px_rgba(214,88,138,0.45)] sm:w-[340px]"
                  >
                    <div className="absolute inset-0 bg-gradient-to-br from-[#D6588A]/30 to-[#7A2B52]/30" />
                    <img
                      src={item.image}
                      className="absolute inset-0 w-full h-full object-cover rounded-2xl"
                      alt={t('landing.showcaseAlt', { title: t('landing.showcase' + item.id + 'Title') })}
                      loading="lazy"
                      decoding="async"
                      onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = '';
                        e.target.className = 'absolute inset-0 w-full h-full bg-gradient-to-br from-[#D6588A]/20 to-[#1C1C1E]';
                      }}
                    />
                    <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#0A0A0A] via-black/20 to-transparent" />
                    <div className="absolute right-3 top-3 flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 backdrop-blur-md">
                      <Icon className="text-sm text-white" />
                      <span className="text-xs font-medium tracking-wide text-white">{item.platform}</span>
                    </div>
                     <div className="absolute bottom-4 left-4 right-4 translate-y-1 transition-transform duration-500 group-hover/card:translate-y-0">
                       <p className="text-base font-semibold text-white">{t('landing.showcase' + item.id + 'Title')}</p>
                       <p className="text-xs text-white/60">{t('landing.aiCampaign')}</p>
                     </div>
                  </article>
                );
              })}
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
