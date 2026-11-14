import { Link } from 'react-router-dom';
import PublicLayout from '../components/PublicLayout';
import SEO from '../components/SEO';
import { useLanguage } from '../i18n/LanguageContext';
import { Boxes, TrendingUp, Sparkles, Users, ShieldCheck, Rocket, ArrowUpRight } from 'lucide-react';

const TEAM = [
  { key: 'team0', initials: 'M' },
  { key: 'team1', initials: 'ZI' },
  { key: 'team2', initials: 'MH' },
  { key: 'team3', initials: 'MA' },
];

const VALUES = [
  { key: 'innovation', icon: <Rocket size={22} /> },
  { key: 'trust', icon: <ShieldCheck size={22} /> },
  { key: 'customer', icon: <Users size={22} /> },
];

export default function About() {
  const { t } = useLanguage();
  return (
    <PublicLayout active="about">
      <SEO
        title="About Morrow — AI Social Media Manager &amp; Content Marketing"
        description="Meet Meveryx, the studio behind Morrow — an AI social media manager and content marketing platform that helps brands create content, schedule posts and grow their social presence."
        path="/about"
        keywords="about Morrow, AI marketing company, social media management platform, Meveryx"
      />
      <div className="mx-auto max-w-4xl px-6 pb-28 pt-32">
        <p className="mb-4 text-sm font-semibold uppercase tracking-[0.25em] text-[var(--accent-text)]">{t('about.aboutMeveryx')}</p>
        <h1 className="text-4xl font-extrabold leading-[1.1] text-[var(--text)] md:text-6xl">
          {t('about.buildAiPowers')}{' '}
          <span className="text-[var(--accent-text)]">
            {t('about.modernBrands')}
          </span>
          .
        </h1>
<p className="mt-8 text-lg leading-relaxed text-[var(--text-muted)]">
          <span className="font-semibold text-[var(--text)]">Meveryx</span> {t('about.meveryxIntro')}
        </p>
        <p className="mt-6 text-lg leading-relaxed text-[var(--text-muted)]">
          <span className="font-semibold text-[var(--text)]">Morrow</span> {t('about.brandAuraIntro')}
        </p>

        {/* Values */}
        <div className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-3">
          {VALUES.map((v) => (
            <div
              key={v.key}
              className="group rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-6 transition-all duration-500 ease-[cubic-bezier(0.25,1,0.5,1)] hover:-translate-y-1.5 hover:border-[var(--accent)]"
            >
              <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--surface-2)] text-[var(--accent-text)] transition-colors duration-500 group-hover:bg-[var(--accent-soft)]">
                {v.icon}
              </div>
               <h3 className="text-base font-semibold text-[var(--text)]">{t('about.' + v.key + 'Title')}</h3>
               <p className="mt-2 text-sm leading-relaxed text-[var(--text-muted)]">{t('about.' + v.key + 'Text')}</p>
            </div>
          ))}
        </div>

        {/* Leadership */}
        <h2 className="mt-20 text-3xl font-bold text-[var(--text)]">{t('about.leadership')}</h2>
        <p className="mt-3 text-[var(--text-muted)]">{t('about.leadershipSub')}</p>
        <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2">
          {TEAM.map((m) => (
            <div
              key={m.key}
              className="group flex items-start gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-6 transition-all duration-500 ease-[cubic-bezier(0.25,1,0.5,1)] hover:-translate-y-2 hover:border-[var(--accent)]"
            >
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-lg font-bold text-[var(--on-accent)] transition-transform duration-500 group-hover:scale-110 bg-[var(--accent)]">
                {m.initials}
              </div>
              <div>
                <h3 className="text-lg font-semibold text-[var(--text)]">{t('about.' + m.key + 'Name')}</h3>
                <p className="text-sm font-medium text-[var(--accent-text)]">{t('about.' + m.key + 'Role')}</p>
                <p className="mt-2 text-sm leading-relaxed text-[var(--text-muted)]">{t('about.' + m.key + 'Bio')}</p>
              </div>
            </div>
          ))}
        </div>

        {/* CTA */}
        <div className="mt-16 overflow-hidden rounded-3xl border border-[var(--border)] p-10 text-center bg-[var(--surface)]">
          <div className="mb-4 flex justify-center gap-3 text-[var(--accent-text)]">
            <Boxes size={26} />
            <TrendingUp size={26} />
            <Sparkles size={26} />
          </div>
           <h3 className="text-2xl font-bold text-[var(--text)]">{t('about.ctaTitle')}</h3>
           <p className="mx-auto mt-3 max-w-xl text-[var(--text-muted)]">
             {t('about.ctaText')}
           </p>
           <div className="mt-6 flex justify-center gap-3">
             <Link to="/register" className="btn btn-primary btn-sm rounded-full">
               {t('footer.getStarted')}
             </Link>
             <Link
               to="/privacy"
               className="btn btn-glass btn-sm rounded-full inline-flex items-center gap-1.5"
             >
               {t('footer.privacy')} <ArrowUpRight size={15} />
             </Link>
           </div>
        </div>
      </div>
    </PublicLayout>
  );
}
