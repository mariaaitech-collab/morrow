import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Check,
  Menu,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import FlowingMenu from '../components/FlowingMenu';
import SplashCursor from '../components/SplashCursor';
import Footer from '../components/Footer';
import { Logo } from '../components/ui';
import { isAuthenticated, clearAuth } from '../auth';
import headphonesImg from '../assets/headphones.jpg';
import watchImg from '../assets/watch.jpg';
import coffeeImg from '../assets/coffee.jpg';
import productImg from '../assets/product.jpg';

const FLOWING_ITEMS = [
  { link: '#create', text: 'Generate' },
  { link: '#write', text: 'Refine' },
  { link: '#schedule', text: 'Schedule' },
  { link: '#system', text: 'Reuse' },
];

const NAV_LINKS = [
  { href: '#features', label: 'Features' },
  { href: '#campaign-images', label: 'Showcase' },
  { href: '#pricing', label: 'Pricing' },
  { href: '/about', label: 'About' },
];

const CAMPAIGN_IMAGES = [
  ['Sonic One Launch', 'Instagram launch creative', headphonesImg],
  ['Elite Product Series', 'LinkedIn campaign visual', watchImg],
  ['Artisan Coffee Edit', 'Social ad concept', coffeeImg],
  ['Precision Product Drop', 'Multi-platform campaign image', productImg],
];

const PLANS = [
  {
    name: 'Starter',
    price: '1,200 PKR',
    range: '1,000 – 1,500 PKR range',
    credits: '50 Credits',
    badge: null,
    features: [
      '50 AI content & image generation credits',
      'Multi-platform caption studio',
      'Smart scheduling & calendar',
      'Live platform post previews',
      'Standard AI generation speed',
    ],
  },
  {
    name: 'Plus',
    price: '2,800 PKR',
    range: '2,000 – 4,000 PKR range',
    credits: '150 Credits',
    badge: 'Most Popular',
    features: [
      '150 AI content & image generation credits',
      'Everything in Starter plan',
      'Brand voice presets & tone matching',
      'Automated recurring post queue',
      'Competitive hashtag & trend analysis',
      'Priority generation processing',
    ],
  },
  {
    name: 'Enterprise',
    price: '6,500 PKR',
    range: 'Starting 6,000+ PKR / Custom',
    credits: '500+ Credits',
    badge: 'For Teams',
    features: [
      '500+ credits / Custom volume',
      'Everything in Plus plan',
      'Multi-brand workspaces & team seats',
      'Custom fine-tuned AI prompts & API access',
      'Dedicated Account Manager & SLA',
      '24/7 priority VIP assistance',
    ],
  },
];

const MOVING_STRIP = [
  'AI campaign copy for Instagram, LinkedIn, and Facebook',
  'Platform previews before publishing',
  'Publishing queue for launch weeks',
  'Brand voice aligned captions',
  'Content calendar planning',
  'AI-generated campaign ideas',
];

const CAMPAIGNS = [
  {
    title: 'Launch Week',
    channel: 'Instagram + LinkedIn',
    copy: 'A seven-day campaign system with hooks, captions, and platform-specific post angles.',
    metrics: ['12 drafts', '3 channels', 'Ready'],
  },
  {
    title: 'Founder Story',
    channel: 'LinkedIn',
    copy: 'Thought-leadership posts shaped around product insight, traction, and customer proof.',
    metrics: ['5 posts', 'Voice matched', 'Queued'],
  },
  {
    title: 'Offer Push',
    channel: 'Facebook + Instagram',
    copy: 'Conversion-focused campaign copy with short-form captions and scheduling structure.',
    metrics: ['8 variants', 'CTA tested', 'Approved'],
  },
];

function Eyebrow({ children }) {
  return <p className="text-xs font-bold uppercase tracking-[0.26em] text-[var(--accent-text)]">{children}</p>;
}

function Reveal({ children, className = '', delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function AbstractDashboard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.35 }}
      transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
      className="mx-auto w-full max-w-6xl overflow-hidden rounded-[8px] border border-[var(--border)] bg-[var(--surface)]"
    >
      <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--accent)]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--surface-2)]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[var(--surface-2)]" />
        </div>
        <span className="rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-4 py-1 text-xs text-[var(--text-muted)]">
          Morrow Studio
        </span>
      </div>

      <div className="grid lg:grid-cols-[240px_1fr_260px]">
        <aside className="border-b border-[var(--border)] p-5 lg:border-b-0 lg:border-r">
          <div className="mb-8">
            <p className="text-xs uppercase tracking-[0.22em] text-[var(--text-muted)]">Workspace</p>
            <p className="mt-2 text-lg font-bold text-[var(--text)]">Launch System</p>
          </div>
          {['Brief', 'Content', 'Channels', 'Calendar'].map((item, index) => (
            <div
              key={item}
              className={`mb-2 rounded-[8px] px-3 py-3 text-sm ${
                index === 1 ? 'bg-[var(--accent-soft)] text-[var(--text)]' : 'bg-[var(--surface-2)] text-[var(--text-muted)]'
              }`}
            >
              {item}
            </div>
          ))}
        </aside>

        <main className="min-h-[420px] border-b border-[var(--border)] p-5 lg:border-b-0 lg:border-r">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--accent-text)]">Campaign draft</p>
              <h3 className="mt-2 text-2xl font-black">Product launch sequence</h3>
            </div>
            <button className="btn btn-primary btn-sm rounded-full">
              <Sparkles size={15} />
              Generate
            </button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-[8px] border border-[var(--border)] bg-[var(--surface-2)] p-5">
              <div className="mb-8 h-2 w-16 rounded-full bg-[var(--accent)]" />
              <p className="text-sm uppercase tracking-[0.18em] text-[var(--text-muted)]">Primary angle</p>
              <p className="mt-4 text-2xl font-black leading-tight">Turn one idea into a full launch week.</p>
            </div>
            <div className="space-y-3">
              {['Instagram caption', 'LinkedIn launch note', 'Facebook campaign copy'].map((item, index) => (
                <div key={item} className="rounded-[8px] border border-[var(--border)] bg-[var(--surface-2)] p-4">
                  <div className="mb-4 flex items-center justify-between">
                    <p className="text-sm font-semibold">{item}</p>
                    <span className="text-xs text-[var(--text-muted)]">{index + 1}/3</span>
                  </div>
                  <div className="space-y-2">
                    <span className="block h-2 rounded-full bg-[var(--surface-2)]" />
                    <span className="block h-2 w-4/5 rounded-full bg-[var(--surface-2)]" />
                    <span className="block h-2 w-2/3 rounded-full bg-[var(--surface-2)]" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </main>

        <aside className="p-5">
          <p className="mb-5 text-sm font-bold">Queue</p>
          {['Mon', 'Wed', 'Fri'].map((day, index) => (
            <div key={day} className="mb-3 rounded-[8px] border border-[var(--border)] bg-[var(--surface-2)] p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold">{day}</span>
                <span className={`h-2 w-2 rounded-full ${index === 0 ? 'bg-[var(--accent)]' : 'bg-[var(--surface-2)]'}`} />
              </div>
              <div className="mt-5 h-2 rounded-full bg-[var(--surface-2)]">
                <div className="h-2 rounded-full bg-[var(--accent)]" style={{ width: `${58 + index * 14}%` }} />
              </div>
            </div>
          ))}
        </aside>
      </div>
    </motion.div>
  );
}

export default function Landing() {
  const [authed, setAuthed] = useState(() => isAuthenticated());
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const handleLogout = () => {
    clearAuth();
    setAuthed(false);
    window.location.href = '/';
  };

  const renderDesktopLinks = () =>
    NAV_LINKS.map((item) =>
      item.href.startsWith('/') ? (
        <Link key={item.label} to={item.href} className="nav-link">{item.label}</Link>
      ) : (
        <a key={item.label} href={item.href} className="nav-link">{item.label}</a>
      ),
    );

  const renderMobileLinks = () =>
    NAV_LINKS.map((item) =>
      item.href.startsWith('/') ? (
        <Link key={item.label} to={item.href} onClick={() => setMenuOpen(false)} className="rounded-lg px-3 py-2.5 text-sm text-[var(--text-muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--text)]">{item.label}</Link>
      ) : (
        <a key={item.label} href={item.href} onClick={() => setMenuOpen(false)} className="rounded-lg px-3 py-2.5 text-sm text-[var(--text-muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--text)]">{item.label}</a>
      ),
    );

  const menuToggle = (
    <button
      className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-[var(--border)] bg-[var(--surface-2)] text-[var(--text)] md:hidden"
      onClick={() => setMenuOpen((open) => !open)}
      aria-label={menuOpen ? 'Close menu' : 'Open menu'}
      aria-expanded={menuOpen}
    >
      {menuOpen ? <X size={17} /> : <Menu size={17} />}
    </button>
  );

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[var(--bg)] text-[var(--text)]">
      <header className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${scrolled ? 'py-2.5' : 'py-4'}`}>
        <div className="mx-auto w-[min(1160px,calc(100%-28px))]">
          <nav
            className={`flex items-center justify-between rounded-full border px-4 py-3 transition-all duration-300 md:px-5 ${scrolled ? 'border-[var(--border)] bg-[var(--surface)] shadow-xl backdrop-blur-2xl' : 'border-[var(--border)] bg-[var(--surface)] backdrop-blur-xl'}`}
          >
            <Link to="/" className="flex shrink-0 items-center text-[var(--text)]" aria-label="Morrow">
              <Logo size={40} />
            </Link>

            <div className="hidden items-center gap-1 md:flex">
              {renderDesktopLinks()}
            </div>

            {authed ? (
              <div className="flex items-center gap-2">
                <Link to="/dashboard" className="btn btn-primary btn-sm rounded-full">Dashboard</Link>
                <button onClick={handleLogout} className="btn btn-ghost btn-sm rounded-full hidden sm:inline-flex">Logout</button>
                {menuToggle}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link to="/login" className="btn btn-ghost btn-sm rounded-full hidden sm:inline-flex">Log in</Link>
                <Link to="/register" className="btn btn-primary btn-sm rounded-full">
                  Get Started
                  <ArrowRight size={15} />
                </Link>
                {menuToggle}
              </div>
            )}
          </nav>

          {menuOpen && (
            <div className="mt-2 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] backdrop-blur-2xl md:hidden">
              <nav className="flex flex-col p-2">
                {renderMobileLinks()}
              </nav>
              <div className="flex flex-col gap-2 border-t border-[var(--border)] p-3">
                {authed ? (
                  <>
                    <Link to="/dashboard" onClick={() => setMenuOpen(false)} className="btn btn-primary w-full rounded-full">Dashboard</Link>
                    <button onClick={() => { setMenuOpen(false); handleLogout(); }} className="btn btn-ghost w-full rounded-full">Logout</button>
                  </>
                ) : (
                  <>
                    <Link to="/login" onClick={() => setMenuOpen(false)} className="btn btn-ghost w-full rounded-full">Log in</Link>
                    <Link to="/register" onClick={() => setMenuOpen(false)} className="btn btn-primary w-full rounded-full">Get Started</Link>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </header>

      {/* ===== Hero ===== */}
      <section className="relative flex min-h-screen items-center overflow-hidden px-6 pb-24 pt-32 text-center" aria-labelledby="landing-hero-title">
        <div className="absolute inset-0 bg-[var(--bg)]" />
        <div className="absolute inset-0">
          <SplashCursor
            confine
            TRANSPARENT
            RAINBOW_MODE={false}
            SPLAT_RADIUS={0.22}
            SPLAT_FORCE={5200}
            DENSITY_DISSIPATION={3.2}
          />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="relative z-10 mx-auto max-w-6xl"
        >
          <h1 id="landing-hero-title" className="mx-auto max-w-5xl text-5xl font-extrabold leading-[0.96] tracking-tight md:text-7xl lg:text-8xl">
            Make your next campaign{' '}
            <span className="text-[var(--accent-text)]">impossible</span>{' '}
            to scroll past.
          </h1>
          <p className="mx-auto mt-7 max-w-2xl text-lg leading-8 text-[var(--text-muted)]">
            Morrow helps teams generate campaign copy, preview platform-ready posts, and schedule social media campaigns from one focused workspace.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
            <Link to={authed ? '/dashboard' : '/register'} className="btn btn-primary btn-lg rounded-full">
              {authed ? 'Open Dashboard' : 'Start Creating'}
              <ArrowRight size={18} />
            </Link>
            <a href="#preview" className="btn btn-glass btn-lg rounded-full">View Product</a>
          </div>
        </motion.div>
      </section>

      {/* ===== Moving Strip ===== */}
      <section className="border-y border-[var(--border)] bg-[var(--surface-2)] py-5" aria-label="Morrow campaign capabilities">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="overflow-hidden"
        >
          <div className="flex w-max animate-marquee items-center gap-8">
            {[...MOVING_STRIP, ...MOVING_STRIP, ...MOVING_STRIP].map((item, index) => (
              <div key={`${item}-${index}`} className="flex items-center gap-8">
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">{item}</p>
                <span className="h-2 w-2 rounded-full bg-[var(--accent)]" />
              </div>
            ))}
          </div>
        </motion.div>
      </section>

      {/* ===== Abstract Dashboard Preview ===== */}
      <section id="preview" className="scroll-mt-28 px-6 py-24">
        <Reveal className="mx-auto mb-12 max-w-3xl text-center">
          <Eyebrow>Preview</Eyebrow>
          <h2 className="mt-4 text-4xl font-black tracking-tight md:text-6xl">A clean control room for content.</h2>
          <p className="mt-5 text-lg leading-8 text-[var(--text-muted)]">
            No decorative screenshots or stock visuals. Just the product concept, reduced to the parts users actually need.
          </p>
        </Reveal>
        <AbstractDashboard />
      </section>

      {/* ===== Features / FlowingMenu ===== */}
      <section id="features" className="scroll-mt-28 px-6 py-24">
        <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.85fr_1.15fr]">
          <Reveal>
            <Eyebrow>Features</Eyebrow>
            <h2 className="mt-4 text-4xl font-black tracking-tight md:text-6xl">Everything your campaign needs, in motion.</h2>
          </Reveal>
          <div className="h-[480px] overflow-hidden rounded-[8px] border border-[var(--border)]">
            <FlowingMenu
              items={FLOWING_ITEMS}
              speed={12}
            />
          </div>
        </div>
      </section>

      {/* ===== AI Campaigns ===== */}
      <section id="campaigns" className="scroll-mt-28 px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <Reveal className="mb-12 grid gap-6 lg:grid-cols-[0.85fr_1.15fr] lg:items-end">
            <div>
              <Eyebrow>AI-Generated Campaigns</Eyebrow>
              <h2 className="mt-4 text-4xl font-black tracking-tight md:text-6xl">Campaign systems without visual clutter.</h2>
            </div>
            <p className="text-lg leading-8 text-[var(--text-muted)]">
              Morrow creates structured campaign copy, social media post variants, platform previews, and publishing queues for modern marketing teams.
            </p>
          </Reveal>

          <div className="grid gap-4 lg:grid-cols-3">
            {CAMPAIGNS.map((campaign, index) => (
              <motion.article
                key={campaign.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.35 }}
                transition={{ duration: 0.55, delay: index * 0.08 }}
                className="group relative overflow-hidden rounded-[8px] border border-[var(--border)] bg-[var(--surface-2)] p-6 transition hover:-translate-y-1 hover:border-[var(--accent)] hover:bg-[var(--accent-soft)]"
              >
                <div className="absolute right-5 top-5 h-16 w-16 rounded-full border border-[var(--border)] opacity-60 transition group-hover:scale-125" />
                <p className="text-xs font-bold uppercase tracking-[0.22em] text-[var(--accent-text)]">{campaign.channel}</p>
                <h3 className="mt-3 text-2xl font-black">{campaign.title}</h3>
                <p className="mt-4 text-sm leading-7 text-[var(--text-muted)]">{campaign.copy}</p>
                <div className="mt-6 flex flex-wrap gap-2">
                  {campaign.metrics.map((m) => (
                    <span key={m} className="rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1 text-xs font-semibold text-[var(--text-muted)]">
                      {m}
                    </span>
                  ))}
                </div>
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      {/* ===== Campaign Images ===== */}
      <section id="campaign-images" className="scroll-mt-28 px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <Reveal className="mb-12 max-w-3xl">
            <Eyebrow>Showcase</Eyebrow>
            <h2 className="mt-4 text-4xl font-black tracking-tight md:text-6xl">Visual concepts ready for every launch.</h2>
          </Reveal>
          <p className="text-lg leading-8 text-[var(--text-muted)]">
            Showcase AI campaign images for product launches, social media ads, and brand storytelling while keeping the page clean and modern.
          </p>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {CAMPAIGN_IMAGES.map(([title, label, image], index) => (
              <motion.article
                key={title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ duration: 0.55, delay: index * 0.06 }}
                whileHover={{ y: -6 }}
                className="group overflow-hidden rounded-[8px] border border-[var(--border)] bg-[var(--surface-2)]"
              >
                <div className="relative aspect-[4/5] overflow-hidden bg-[var(--surface)]">
                  <img
                    src={image}
                    alt={`${title} AI-generated campaign image for ${label}`}
                    className="h-full w-full object-cover transition duration-700 group-hover:scale-105"
                    loading="lazy"
                  />
                  <span className="absolute left-4 top-4 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1 text-xs font-semibold text-[var(--text)] backdrop-blur">
                    AI Generated
                  </span>
                </div>
                <div className="p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--accent-text)]">{label}</p>
                  <h3 className="mt-2 text-xl font-black">{title}</h3>
                </div>
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      {/* ===== Stats ===== */}
      <section className="border-y border-[var(--border)] bg-[var(--surface-2)] px-6 py-14">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-10 md:grid-cols-4">
          {[
            ['12k+', 'campaigns generated'],
            ['98%', 'drafts ready to publish'],
            ['3', 'platforms, one workspace'],
            ['4.9/5', 'creator satisfaction'],
          ].map(([value, label], index) => (
            <motion.div
              key={label}
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.55, delay: index * 0.08 }}
              className="text-center"
            >
              <p className="text-5xl font-black text-[var(--accent-text)]">
                {value}
              </p>
              <p className="mt-2 text-sm text-[var(--text-muted)]">{label}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ===== Pricing ===== */}
      <section id="pricing" className="scroll-mt-28 px-6 py-24">
        <Reveal className="mx-auto mb-14 max-w-3xl text-center">
          <Eyebrow>Pricing</Eyebrow>
          <h2 className="mt-4 text-4xl font-black md:text-6xl">Simple plans for consistent output.</h2>
        </Reveal>
        <div className="mx-auto grid max-w-7xl gap-8 md:grid-cols-3 md:gap-5">
          {PLANS.map((plan, index) => {
            const isPlus = index === 1;
            return (
              <motion.div
                key={plan.name}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ duration: 0.55, delay: index * 0.1 }}
                whileHover={{ y: -6 }}
                className="group relative h-full"
              >
                <div className={`relative h-full transition-transform duration-300 ${isPlus ? 'z-10 md:scale-[1.045]' : ''}`}>
                  <div className="relative h-full overflow-hidden rounded-[14px] p-px">
                    <div
                      className={`relative flex h-full min-h-[500px] flex-col rounded-[13px] border p-7 ${
                        isPlus
                          ? 'border-[var(--accent)] bg-[var(--surface)]'
                          : 'border-[var(--border)] bg-[var(--surface)]'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <p className="text-xl font-bold">{plan.name}</p>
                        {plan.badge && (
                          <span className="rounded-full px-3 py-0.5 text-xs font-bold text-[var(--on-accent)] shadow-md bg-[var(--accent)]">
                            {plan.badge}
                          </span>
                        )}
                      </div>

                      <div className="mt-3">
                        <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--accent-soft)] px-3 py-0.5 text-xs font-bold text-[var(--accent-text)]">
                          <Zap size={12} className="text-[var(--accent-text)]" /> {plan.credits}
                        </span>
                      </div>

                      <div className="mt-5 flex items-baseline gap-1.5">
                        <span className="text-3xl lg:text-4xl font-black">{plan.price}</span>
                        <span className="text-sm text-[var(--text-muted)]">/mo</span>
                      </div>
                      <p className="mt-1 text-xs text-[var(--text-muted)]">{plan.range}</p>

                      <div className="mt-7 flex-1 space-y-3.5">
                        {plan.features.map((feature) => (
                          <p key={feature} className="flex items-center gap-3 text-sm text-[var(--text-muted)]">
                            <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${isPlus ? 'bg-[var(--accent-soft)] text-[var(--accent-text)]' : 'bg-[var(--surface-2)] text-[var(--text-muted)]'}`}>
                              <Check size={12} />
                            </span>
                            {feature}
                          </p>
                        ))}
                      </div>
                      <Link
                        to={authed ? '/dashboard' : '/register'}
                        className={`btn mt-8 w-full rounded-full ${isPlus ? 'btn-primary' : 'btn-ghost'}`}
                      >
                        Choose {plan.name}
                      </Link>
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </section>

      {/* ===== FAQ ===== */}
      <section className="px-6 py-24">
        <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[0.75fr_1.25fr]">
          <Reveal>
            <Eyebrow>FAQ</Eyebrow>
            <h2 className="mt-4 text-4xl font-black">Clear answers. No clutter.</h2>
          </Reveal>
          <div className="space-y-3">
            {[
              ['What does Morrow generate?', 'Campaign copy, content directions, platform variants, and scheduling structure.'],
              ['Can I edit everything?', 'Yes. The AI output is a starting point, and every draft can be refined before publishing.'],
              ['Which channels are supported?', 'The current product focuses on Instagram, LinkedIn, and Facebook workflows.'],
            ].map(([q, a]) => (
              <details key={q} className="rounded-[8px] border border-[var(--border)] bg-[var(--surface-2)] p-5">
                <summary className="cursor-pointer list-none text-lg font-bold">{q}</summary>
                <p className="mt-4 leading-7 text-[var(--text-muted)]">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ===== CTA ===== */}
      <section className="px-6 py-28">
        <Reveal className="mx-auto max-w-5xl rounded-[8px] border border-[var(--border)] bg-[var(--surface-2)] p-10 text-center md:p-16">
          <Zap className="mx-auto mb-6 text-[var(--accent-text)]" size={36} />
          <h2 className="mx-auto max-w-3xl text-4xl font-black tracking-tight md:text-6xl">Build the next campaign without the messy middle.</h2>
          <div className="mt-8">
            <Link to={authed ? '/dashboard' : '/register'} className="btn btn-primary btn-lg rounded-full">
              {authed ? 'Open Dashboard' : 'Get Started'}
              <ArrowRight size={18} />
            </Link>
          </div>
        </Reveal>
      </section>

      <Footer />
    </div>
  );
}
