import { createContext, useContext, useEffect, useMemo, useRef, useState, useCallback } from 'react';

// Workflow persistence layer for BrandAura.
//
// All generator state (topic, tone, platforms, generated content, image prompt,
// media metadata, publish results, brand profile, market brief) lives here at
// the App level — ABOVE the router — so navigating between Dashboard,
// Scheduler, Calendar etc. never wipes user work. The draft is mirrored to
// sessionStorage so even a full page navigation (e.g. the OAuth callback
// redirect) restores the exact same state. It is cleared ONLY via the explicit
// 'Clear' action or logging out.
const STORAGE_KEY = 'brandora_draft_v1';

export const DEFAULT_DRAFT = {
  topic: '',
  tone: 'professional',
  selectedPlatforms: ['facebook', 'linkedin', 'instagram'],
  content: null,
  imagePrompt: '',
  imageMode: 'free',
  media: null, // { dataUrl, name, size, type } — dataUrl may be null if too large to store
  publishResults: {},
  strategyData: null,
  competitorError: null,
  brandProfile: {
    niche: '',
    audience: '',
    businessType: '',
    offerings: '',
    location: '',
  },
  marketQuery: '',
  marketData: null,
  marketError: null,
  marketLoading: false,
};

function safeParse(raw) {
  try {
    return JSON.parse(raw) || {};
  } catch {
    return {};
  }
}

const DraftContext = createContext(null);

export function DraftProvider({ children }) {
  const [draft, setDraftState] = useState(() => {
    try {
      const saved = safeParse(window.sessionStorage.getItem(STORAGE_KEY));
      return { ...DEFAULT_DRAFT, ...saved };
    } catch {
      return { ...DEFAULT_DRAFT };
    }
  });
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
    } catch {
      // Quota exceeded (usually a large media dataUrl): persist the metadata
      // only, so the session keeps going without hard-failing.
      try {
        const slim = {
          ...draft,
          media: draft.media
            ? { name: draft.media.name, size: draft.media.size, type: draft.media.type, dataUrl: null }
            : null,
        };
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(slim));
      } catch {
        /* give up silently — in-memory draft still works */
      }
    }
  }, [draft]);

  const setDraft = useCallback((patch) => {
    setDraftState((prev) => {
      const next = typeof patch === 'function' ? patch(prev) : { ...prev, ...patch };
      return next;
    });
  }, []);

  const clearDraft = useCallback(() => {
    setDraftState({ ...DEFAULT_DRAFT });
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(() => ({ draft, setDraft, clearDraft }), [draft, setDraft, clearDraft]);

  return <DraftContext.Provider value={value}>{children}</DraftContext.Provider>;
}

export function useDraft() {
  const ctx = useContext(DraftContext);
  if (!ctx) throw new Error('useDraft must be used within a DraftProvider');
  return ctx;
}