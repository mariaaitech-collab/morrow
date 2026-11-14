// WCAG AA contrast check for every text/background pair the Morrow UI uses.
// Reads src/styles/tokens.css, so it stays in sync with the real values.
//
//   node scripts/check-contrast.mjs        (exit code 1 if any pair fails)

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const css = readFileSync(fileURLToPath(new URL('../src/styles/tokens.css', import.meta.url)), 'utf8');
const t = Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const hex = (c) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`;
const mix = (a, b, pctA) => hex(rgb(a).map((v, i) => v * pctA + rgb(b)[i] * (1 - pctA)));
const lum = (h) => {
  const [r, g, b] = rgb(h).map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

// Derived tokens, computed the same way as the color-mix() rules in tokens.css.
for (const k of ['accent', 'accent-2', 'success', 'warning', 'danger']) {
  t[`${k}-soft`] = mix(t[k], t.surface, 0.12);
  if (k !== 'accent') t[`${k}-text`] = mix(t[k], t.text, 0.5);
}
t['sidebar-active'] = mix(t['sidebar-accent'], t.sidebar, 0.14);
for (const p of ['instagram', 'facebook', 'linkedin', 'tiktok']) t[`tile-${p}`] = mix(t[`platform-${p}`], t.surface, 0.14);

const GROUPS = {
  'Page and cards': [
    ['text', 'bg'], ['text', 'surface'], ['text', 'surface-2'],
    ['text-muted', 'bg'], ['text-muted', 'surface'], ['text-muted', 'surface-2'],
    ['accent-text', 'bg'], ['accent-text', 'surface'], ['accent-text', 'surface-2'], ['accent-text', 'accent-soft'],
    ['on-accent', 'accent'], ['on-accent', 'accent-hover'], ['on-danger', 'danger'],
    ['accent-2-text', 'accent-2-soft'], ['success-text', 'success-soft'],
    ['warning-text', 'warning-soft'], ['danger-text', 'danger-soft'],
    ['accent-2-text', 'surface'], ['success-text', 'surface'], ['warning-text', 'surface'], ['danger-text', 'surface'],
    ['text', 'tile-instagram'], ['text', 'tile-facebook'], ['text', 'tile-linkedin'], ['text', 'tile-tiktok'],
  ],
  Sidebar: [
    ['sidebar-text', 'sidebar'], ['sidebar-muted', 'sidebar'], ['sidebar-accent', 'sidebar'],
    ['sidebar-text', 'sidebar-hover'], ['sidebar-text', 'sidebar-active'], ['sidebar-muted', 'sidebar-hover'],
  ],
};

let failures = 0;
for (const [name, pairs] of Object.entries(GROUPS)) {
  console.log(`\n${name}`);
  for (const [fg, bg] of pairs) {
    const r = ratio(t[fg], t[bg]);
    const ok = r >= 4.5;
    if (!ok) failures += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${r.toFixed(2).padStart(5)}:1  ${fg.padEnd(14)} on ${bg.padEnd(15)} ${t[fg]} / ${t[bg]}`);
  }
}
console.log(failures ? `\n${failures} pair(s) below WCAG AA 4.5:1` : '\nAll pairs meet WCAG AA (4.5:1).');
process.exit(failures ? 1 : 0);
