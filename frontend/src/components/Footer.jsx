import { Link } from 'react-router-dom';
import { useLanguage } from '../i18n/LanguageContext';

function Footer() {
  const { t } = useLanguage();
  return (
    <footer className="relative z-10 w-full border-t border-[#2A2A2A] bg-[#0a0a0a]">
      <div className="mx-auto w-full max-w-7xl px-6 pb-10 pt-16 md:pt-20">
        <div className="mb-14 grid grid-cols-1 gap-10 md:grid-cols-[2fr_1fr_1fr_1fr] md:gap-12">
          <div>
            <div className="mb-3 flex items-center gap-2.5">
              <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-gradient-to-br from-[#D6588A] to-[#7A2B52] text-sm font-extrabold text-white">
                B
              </span>
              <span className="text-[1.15rem] font-bold text-white">
                Brand<span className="bg-gradient-to-r from-[#D6588A] to-[#E8558C] bg-clip-text text-transparent" style={{ filter: 'drop-shadow(0 0 18px rgba(214,88,138,0.45))' }}>Aura</span>
              </span>
            </div>
              <p className="mb-5 mt-1 text-[0.82rem] uppercase tracking-[0.3em] text-slate-300">{t('footer.tagline')}</p>
          </div>
          <div className="flex flex-col gap-3">
            <h4 className="mb-2 text-[0.82rem] font-bold uppercase tracking-[0.08em] text-white">{t('footer.product')}</h4>
            <a
              href="#features"
              onClick={(e) => {
                e.preventDefault();
                document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' });
              }}
              className="text-[0.88rem] leading-relaxed text-slate-300 no-underline transition-colors hover:text-[#D6588A]"
            >
              {t('footer.features')}
            </a>
            <Link to="/about" className="text-[0.88rem] leading-relaxed text-slate-300 no-underline transition-colors hover:text-[#D6588A]">
              {t('footer.about')}
            </Link>
            <Link to="/register" className="text-[0.88rem] leading-relaxed text-slate-300 no-underline transition-colors hover:text-[#D6588A]">
              {t('footer.getStarted')}
            </Link>
          </div>
          <div className="flex flex-col gap-3">
            <h4 className="mb-2 text-[0.82rem] font-bold uppercase tracking-[0.08em] text-white">{t('footer.company')}</h4>
            <Link to="/about" className="text-[0.88rem] leading-relaxed text-slate-300 no-underline transition-colors hover:text-[#D6588A]">
              {t('footer.about')}
            </Link>
            <a href="mailto:hello@meveryx.com" className="text-[0.88rem] leading-relaxed text-slate-300 no-underline transition-colors hover:text-[#D6588A]">
              {t('footer.contact')}
            </a>
            <a href="mailto:careers@meveryx.com" className="text-[0.88rem] leading-relaxed text-slate-300 no-underline transition-colors hover:text-[#D6588A]">
              {t('footer.careers')}
            </a>
          </div>
          <div className="flex flex-col gap-3">
            <h4 className="mb-2 text-[0.82rem] font-bold uppercase tracking-[0.08em] text-white">{t('footer.legal')}</h4>
            <Link to="/privacy" className="text-[0.88rem] leading-relaxed text-slate-300 no-underline transition-colors hover:text-[#D6588A]">
              {t('footer.privacy')}
            </Link>
            <Link to="/terms" className="text-[0.88rem] leading-relaxed text-slate-300 no-underline transition-colors hover:text-[#D6588A]">
              {t('footer.terms')}
            </Link>
          </div>
        </div>
        <div className="border-t border-[#2A2A2A] pt-8 text-center text-[0.8rem] text-slate-400">
          {t('footer.copyright')}
        </div>
      </div>
    </footer>
  );
}

export default Footer;
