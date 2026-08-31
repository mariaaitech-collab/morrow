import React from 'react';
import { translations } from '../i18n/translations';

// Class components can't use the i18n hook, so resolve the fallback copy from
// the persisted language in localStorage (falls back to English).
function tFallback(key) {
  try {
    const lang = (typeof localStorage !== 'undefined' && localStorage.getItem('brandora_lang')) || 'en';
    const lookup = (obj, k) => k.split('.').reduce((o, p) => (o && o[p] != null ? o[p] : undefined), obj);
    return lookup(translations[lang], key) || lookup(translations.en, key) || key;
  } catch {
    return key;
  }
}

// Generic React error boundary. Catches render/runtime errors anywhere in
// the subtree so a single failing component can never blank out the whole
// app (black screen). Renders a clean fallback with a reload action.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Surface in console for diagnostics, but never crash the app.
    console.error('[ErrorBoundary]', this.props.label || 'app', error, info);
  }

  handleReload = () => {
    if (this.props.reloadTo) {
      window.location.href = this.props.reloadTo;
    } else {
      window.location.reload();
    }
  };

  render() {
    if (this.state.hasError) {
      const { title, message, reloadLabel, showDetail } = this.props;
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            background: 'radial-gradient(1200px 800px at 50% -10%, rgba(214,88,138,0.18), #0A0A0A 60%)',
            color: '#fff',
            fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif',
          }}
        >
          <div
            style={{
              maxWidth: '460px',
              width: '100%',
              textAlign: 'center',
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: '20px',
              padding: '2.5rem 2rem',
              boxShadow: '0 30px 80px -20px rgba(214,88,138,0.35)',
            }}
          >
            <div
              style={{
                width: '54px',
                height: '54px',
                margin: '0 auto 1.25rem',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'rgba(214,88,138,0.15)',
                fontSize: '26px',
              }}
            >
              ⚠️
            </div>
            <h2 style={{ margin: '0 0 0.5rem', fontSize: '1.4rem', fontWeight: 700 }}>
              {title || tFallback('errorBoundary.title')}
            </h2>
            <p style={{ margin: '0 0 1.5rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
              {message || tFallback('errorBoundary.message')}
            </p>
            {showDetail && this.state.error && (
              <pre
                style={{
                  textAlign: 'left',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontSize: '0.78rem',
                  background: 'rgba(0,0,0,0.35)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '10px',
                  padding: '0.75rem',
                  margin: '0 0 1.5rem',
                  color: 'rgba(255,255,255,0.8)',
                }}
              >
                {String(this.state.error.message || this.state.error)}
              </pre>
            )}
            <button
              type="button"
              onClick={this.handleReload}
              style={{
                cursor: 'pointer',
                border: '0',
                borderRadius: '12px',
                padding: '0.8rem 1.6rem',
                fontSize: '0.95rem',
                fontWeight: 600,
                color: '#fff',
                background: 'linear-gradient(90deg, #D6588A, #7A2B52)',
                boxShadow: '0 0 22px rgba(214,88,138,0.45)',
              }}
            >
              {reloadLabel || tFallback('errorBoundary.reload')}
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
