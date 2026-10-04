/**
 * Theme Store (Zustand)
 * ======================
 * Manages user theme preferences: accent color, font size, sidebar width,
 * minimap visibility, and other UI customizations.
 * Persists to localStorage and applies CSS variables to :root.
 */

import { create } from 'zustand';

const STORAGE_KEY = 'agk_theme_prefs:v1';
const LEGACY_STORAGE_KEY = 'agk_theme_prefs';

export interface ThemePrefs {
  accentColor: string;
  fontSize: number;
  sidebarWidth: number;
  showMinimap: boolean;
  showLineNumbers: boolean;
  wordWrap: 'on' | 'off';
  tabSize: number;
}

export type ThemeStore = ThemePrefs & {
  /** Load preferences from localStorage */
  load: () => void;
  /** Apply CSS variables to document root */
  apply: () => void;
  /** Update a single preference */
  setPref: <K extends keyof ThemePrefs>(key: K, value: ThemePrefs[K]) => void;
  /** Reset to defaults */
  reset: () => void;
};

const DEFAULTS: ThemePrefs = {
  accentColor: '#a8bfff',
  fontSize: 14,
  sidebarWidth: 248,
  showMinimap: false,
  showLineNumbers: true,
  wordWrap: 'on',
  tabSize: 2,
};

export const useThemeStore = create<ThemeStore>((set, get) => ({
  ...DEFAULTS,

  load: () => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as Partial<ThemePrefs>;
        set({ ...DEFAULTS, ...saved });
      }
    } catch {
      // ignore corrupt data
    }
    // Apply after loading
    setTimeout(() => get().apply(), 0);
  },

  apply: () => {
    const state = get();
    const root = document.documentElement;
    root.style.setProperty('--accent-color', state.accentColor);
    root.style.setProperty('--accent-hover', adjustBrightness(state.accentColor, -10));
    root.style.setProperty('--accent-glow', state.accentColor + '4D');
    root.style.setProperty('--sidebar-width', state.sidebarWidth + 'px');

    // Font size for editor (via CSS variable)
    root.style.setProperty('--editor-font-size', state.fontSize + 'px');

  },

  setPref: (key, value) => {
    set({ [key]: value } as Pick<ThemePrefs, typeof key>);
    // Persist
    const state = get();
    const prefs = {
      accentColor: state.accentColor,
      fontSize: state.fontSize,
      sidebarWidth: state.sidebarWidth,
      showMinimap: state.showMinimap,
      showLineNumbers: state.showLineNumbers,
      wordWrap: state.wordWrap,
      tabSize: state.tabSize,
    } satisfies ThemePrefs;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    // Apply CSS variables
    get().apply();
  },

  reset: () => {
    set(DEFAULTS);
    localStorage.removeItem(STORAGE_KEY);
    get().apply();
  },
}));

/* ─── Utility: adjust color brightness ─────────────────────── */

function adjustBrightness(hex: string, percent: number): string {
  const num = parseInt(hex.replace('#', ''), 16);
  const r = Math.min(255, Math.max(0, ((num >> 16) & 0xff) + percent));
  const g = Math.min(255, Math.max(0, ((num >> 8) & 0xff) + percent));
  const b = Math.min(255, Math.max(0, (num & 0xff) + percent));
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`;
}
