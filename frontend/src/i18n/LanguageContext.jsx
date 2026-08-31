import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { translations, SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE, RTL_LANGUAGES } from './translations';

const LanguageContext = createContext(null);

const KNOWN_LANGS = new Set(SUPPORTED_LANGUAGES.map((l) => l.code));

function getInitialLanguage() {
  // Strict persistence rule: a previously selected language ALWAYS wins.
  // We never infer or auto-switch from the browser locale — if nothing has
  // ever been selected, we default to English and stay there until the user
  // makes an explicit choice via the LanguageSelector.
  if (typeof window === 'undefined') return DEFAULT_LANGUAGE;
  const stored = window.localStorage.getItem('brandora_lang');
  if (typeof stored === 'string' && KNOWN_LANGS.has(stored)) return stored;
  return DEFAULT_LANGUAGE;
}

function lookup(dict, path) {
  return path.split('.').reduce((acc, k) => (acc && acc[k] !== undefined ? acc[k] : undefined), dict);
}

function interpolate(str, vars) {
  if (!vars) return str;
  return str.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, k) => (vars[k] !== undefined ? vars[k] : `{{${k}}}`));
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(getInitialLanguage);

  const dir = RTL_LANGUAGES.includes(language) ? 'rtl' : 'ltr';

  const applyDocDirection = useCallback((lang) => {
    const d = RTL_LANGUAGES.includes(lang) ? 'rtl' : 'ltr';
    document.documentElement.lang = lang;
    document.documentElement.dir = d;
  }, []);

  useEffect(() => {
    applyDocDirection(language);
  }, [language, applyDocDirection]);

  const setLanguage = useCallback((lang) => {
    if (!KNOWN_LANGS.has(lang)) return;
    window.localStorage.setItem('brandora_lang', lang);
    setLanguageState(lang);
  }, []);

  const t = useCallback((key, vars) => {
    const val = lookup(translations[language] || {}, key);
    if (val === undefined) {
      // Fallback to English so the UI never shows a raw key.
      const en = lookup(translations[DEFAULT_LANGUAGE], key);
      if (en === undefined) return key;
      return typeof en === 'string' ? interpolate(en, vars) : en;
    }
    return typeof val === 'string' ? interpolate(val, vars) : val;
  }, [language]);

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t, dir, languages: SUPPORTED_LANGUAGES.map((l) => l.code) }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within a LanguageProvider');
  return ctx;
}
