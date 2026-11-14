import { Link } from 'react-router-dom';
import { useLanguage } from '../i18n/LanguageContext';
import { Logo } from './ui';

function Footer() {
  const { t } = useLanguage();
  return (
    <footer className="relative z-10 w-full border-t border-[var(--border)] bg-[var(--bg)]">
      <div className="mx-auto w-full max-w-7xl px-6 pb-10 pt-16 md:pt-20">
        <div className="mb-14 grid grid-cols-1 gap-10 md:grid-cols-[2fr_1fr_1fr_1fr] md:gap-12">
          <div>
            <div className="mb-3 text-[var(--text)]">
              <Logo size={30} />
            </div>
              <p className="mb-5 mt-1 text-[0.82rem] uppercase tracking-[0.3em] text-[var(--text-muted)]">{t('footer.tagline')}</p>
          </div>
          <div className="flex flex-col gap-3">
            <h4 className="mb-2 text-[0.82rem] font-bold uppercase tracking-[0.08em] text-[var(--text)]">{t('footer.product')}</h4>
            <a
              href="#features"
              onClick={(e) => {
                e.preventDefault();
                document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' });
              }}
              className="text-[0.88rem] leading-relaxed text-[var(--text-muted)] no-underline transition-colors hover:text-[var(--accent-text)]"
            >
              {t('footer.features')}
            </a>
            <Link to="/about" className="text-[0.88rem] leading-relaxed text-[var(--text-muted)] no-underline transition-colors hover:text-[var(--accent-text)]">
              {t('footer.about')}
            </Link>
            <Link to="/register" className="text-[0.88rem] leading-relaxed text-[var(--text-muted)] no-underline transition-colors hover:text-[var(--accent-text)]">
              {t('footer.getStarted')}
            </Link>
          </div>
          <div className="flex flex-col gap-3">
            <h4 className="mb-2 text-[0.82rem] font-bold uppercase tracking-[0.08em] text-[var(--text)]">{t('footer.company')}</h4>
            <Link to="/about" className="text-[0.88rem] leading-relaxed text-[var(--text-muted)] no-underline transition-colors hover:text-[var(--accent-text)]">
              {t('footer.about')}
            </Link>
            <a href="mailto:hello@meveryx.com" className="text-[0.88rem] leading-relaxed text-[var(--text-muted)] no-underline transition-colors hover:text-[var(--accent-text)]">
              {t('footer.contact')}
            </a>
            <a href="mailto:careers@meveryx.com" className="text-[0.88rem] leading-relaxed text-[var(--text-muted)] no-underline transition-colors hover:text-[var(--accent-text)]">
              {t('footer.careers')}
            </a>
          </div>
          <div className="flex flex-col gap-3">
            <h4 className="mb-2 text-[0.82rem] font-bold uppercase tracking-[0.08em] text-[var(--text)]">{t('footer.legal')}</h4>
            <Link to="/privacy" className="text-[0.88rem] leading-relaxed text-[var(--text-muted)] no-underline transition-colors hover:text-[var(--accent-text)]">
              {t('footer.privacy')}
            </Link>
            <Link to="/terms" className="text-[0.88rem] leading-relaxed text-[var(--text-muted)] no-underline transition-colors hover:text-[var(--accent-text)]">
              {t('footer.terms')}
            </Link>
          </div>
        </div>
        <div className="border-t border-[var(--border)] pt-8 text-center text-[0.8rem] text-[var(--text-muted)]">
          {t('footer.copyright')}
        </div>
      </div>
    </footer>
  );
}

export default Footer;
