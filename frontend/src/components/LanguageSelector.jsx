import { useState, useRef, useEffect } from 'react';
import { useLanguage } from '../i18n/LanguageContext';
import { SUPPORTED_LANGUAGES } from '../i18n/translations';

export default function LanguageSelector() {
  const { language, setLanguage, dir } = useLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const current = SUPPORTED_LANGUAGES.find((l) => l.code === language) || SUPPORTED_LANGUAGES[0];

  return (
    <div className={`lang-selector ${open ? 'open' : ''}`} ref={ref}>
      <button
        type="button"
        className="lang-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="lang-flag">{current.flag}</span>
        <span className="lang-label">{current.label}</span>
        <svg className="lang-caret" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && (
        <ul className="lang-menu" role="listbox">
          {SUPPORTED_LANGUAGES.map((l) => (
            <li key={l.code}>
              <button
                type="button"
                role="option"
                aria-selected={l.code === language}
                className={`lang-item ${l.code === language ? 'active' : ''}`}
                onClick={() => {
                  setLanguage(l.code);
                  setOpen(false);
                }}
              >
                <span className="lang-flag">{l.flag}</span>
                <span className="lang-label">{l.label}</span>
                {l.code === language && (
                  <svg className="lang-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
