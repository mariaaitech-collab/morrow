import { useState } from 'react';

// WebGL / canvas code cannot read CSS variables, so it gets the resolved token
// values here. Only base tokens are read: they are plain colour values that
// three.js and canvas understand (derived color-mix() tokens are not).
const TOKENS = {
  accent: '--accent',
  accentHover: '--accent-hover',
  text: '--text',
  textMuted: '--text-muted',
  border: '--border',
  bg: '--bg',
  surface: '--surface',
};

export function readTokenColors() {
  const styles = getComputedStyle(document.documentElement);
  return Object.fromEntries(
    Object.entries(TOKENS).map(([key, name]) => [key, styles.getPropertyValue(name).trim() || undefined]),
  );
}

/** Token colours as plain values, read once per mount. */
export default function useTokenColors() {
  const [colors] = useState(readTokenColors);
  return colors;
}
