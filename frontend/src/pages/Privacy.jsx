import PublicLayout from '../components/PublicLayout';
import SEO from '../components/SEO';
import { useLanguage } from '../i18n/LanguageContext';

export default function Privacy() {
  const { t } = useLanguage();
  return (
    <PublicLayout active="privacy">
      <SEO
        title="Privacy Policy | BrandAura — AI Social Media Manager"
        description="Read the BrandAura privacy policy to understand how Meveryx collects, uses and protects your data across our AI social media management platform."
        path="/privacy"
      />
      <article className="prose prose-invert max-w-4xl px-6 py-32 mx-auto">
        <h1>{t('privacy.h1')}</h1>
        <p className="lead">
          {t('privacy.lead')}
        </p>
        <p>
          <em>{t('privacy.updated')}</em>
        </p>

        <h2>{t('privacy.s1Title')}</h2>
        <h3>{t('privacy.s1h1Title')}</h3>
        <p>{t('privacy.s1h1Body')}</p>
        <h3>{t('privacy.s1h2Title')}</h3>
        <p>{t('privacy.s1h2Body')}</p>

        <h2>{t('privacy.s2Title')}</h2>
        <ul>
          <li>{t('privacy.s2Item1')}</li>
          <li>{t('privacy.s2Item2')}</li>
          <li>{t('privacy.s2Item3')}</li>
          <li>{t('privacy.s2Item4')}</li>
          <li>{t('privacy.s2Item5')}</li>
        </ul>

        <h2>{t('privacy.s3Title')}</h2>
        <p>{t('privacy.s3Body')}</p>

        <h2>{t('privacy.s4Title')}</h2>
        <p>{t('privacy.s4Body')}</p>

        <h2>{t('privacy.s5Title')}</h2>
        <p>{t('privacy.s5Body')}</p>

        <h2>{t('privacy.s6Title')}</h2>
        <p>{t('privacy.s6Body')}</p>

        <h2>{t('privacy.s7Title')}</h2>
        <p>{t('privacy.s7Body')}</p>
        <ul>
          <li>{t('privacy.s7Item1')}</li>
          <li>{t('privacy.s7Item2')}</li>
          <li>{t('privacy.s7Item3')}</li>
          <li>{t('privacy.s7Item4')}</li>
          <li>{t('privacy.s7Item5')}</li>
          <li>{t('privacy.s7Item6')}</li>
          <li>{t('privacy.s7Item7')}</li>
        </ul>
        <p>{t('privacy.s7Contact')}</p>

        <h2>{t('privacy.s8Title')}</h2>
        <p>{t('privacy.s8Body')}</p>

        <h2>{t('privacy.s9Title')}</h2>
        <p>{t('privacy.s9Body')}</p>

        <h2>{t('privacy.s10Title')}</h2>
        <p>{t('privacy.s10Body')}</p>

        <h2>{t('privacy.s11Title')}</h2>
        <p>{t('privacy.s11Body')}</p>
      </article>
    </PublicLayout>
  );
}
