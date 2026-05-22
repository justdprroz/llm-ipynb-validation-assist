import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ThemeType } from '@gravity-ui/uikit';

const STORAGE_KEY = 'gradelab-theme';

type ThemePreference = ThemeType | 'system';

function getSystemTheme(): ThemeType {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function loadPreference(): ThemePreference {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark' || stored === 'system') return stored;
  return 'system';
}

interface ThemeState {
  preference: ThemePreference;
  resolved: ThemeType;
  toggle: () => void;
}

export const ThemeContext = createContext<ThemeState>({
  preference: 'system',
  resolved: 'light',
  toggle: () => {},
});

export function useThemeState(): ThemeState {
  const [preference, setPreference] = useState<ThemePreference>(loadPreference);
  const [systemTheme, setSystemTheme] = useState<ThemeType>(getSystemTheme);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setSystemTheme(e.matches ? 'dark' : 'light');
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const resolved = preference === 'system' ? systemTheme : preference;

  const toggle = useCallback(() => {
    const next: ThemePreference = resolved === 'light' ? 'dark' : 'light';
    localStorage.setItem(STORAGE_KEY, next);
    setPreference(next);
  }, [resolved]);

  return { preference, resolved, toggle };
}

export function useTheme(): ThemeState {
  return useContext(ThemeContext);
}
