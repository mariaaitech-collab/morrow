import PublicLayout from '../components/PublicLayout';
import SEO from '../components/SEO';
import { useLanguage } from '../i18n/LanguageContext';

export default function Terms() {
  const { t } = useLanguage();
  return (
    <PublicLayout active="terms">
      <SEO
        title="Terms of Service | BrandAura — AI Social Media Manager"
        description="Review the BrandAura terms of service that govern your use of our AI social media management, content generation and scheduling platform."
        path="/terms"
      />
      <article className="prose prose-invert max-w-4xl px-6 py-32 mx-auto">
        <h1>{t('terms.h1')}</h1>
        <p className="lead">
          {t('terms.lead')}
        </p>
        <p>
          <em>{t('terms.updated')}</em>
        </p>

        <h2>{t('terms.s1Title')}</h2>
        <p>{t('terms.s1Body')}</p>

        <h2>{t('terms.s2Title')}</h2>
        <p>{t('terms.s2Intro')}</p>
        <ul>
          <li>{t('terms.s2Item1')}</li>
          <li>{t('terms.s2Item2')}</li>
          <li>{t('terms.s2Item3')}</li>
          <li>{t('terms.s2Item4')}</li>
          <li>{t('terms.s2Item5')}</li>
        </ul>
        <p>{t('terms.s2Body')}</p>

        <h2>{t('terms.s3Title')}</h2>
        <p>{t('terms.s3Body')}</p>

        <h2>{t('terms.s4Title')}</h2>
        <p>{t('terms.s4Body')}</p>

        <h2>{t('terms.s5Title')}</h2>
        <p>{t('terms.s5Body')}</p>

        <h2>{t('terms.s6Title')}</h2>
        <p>{t('terms.s6Body')}</p>

        <h2>{t('terms.s7Title')}</h2>
        <p>{t('terms.s7Body')}</p>

        <h2>{t('terms.s8Title')}</h2>
        <p>{t('terms.s8Body')}</p>

        <h2>{t('terms.s9Title')}</h2>
        <p>{t('terms.s9Body')}</p>

        <h2>{t('terms.s10Title')}</h2>
        <p>{t('terms.s10Body')}</p>

        <h2>{t('terms.s11Title')}</h2>
        <p>{t('terms.s11Body')}</p>
      </article>
    </PublicLayout>
  );
}
