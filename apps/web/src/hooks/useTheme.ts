import { useCallback, useEffect, useState } from "react";

// Light/dark theme with a remembered preference. Source of truth is the `.dark`
// class on <html> (set pre-paint by the inline script in index.html); this hook
// keeps React state, localStorage, and that class in sync. If the user has never
// chosen, we follow the OS setting and keep following it until they pick.
export type Theme = "light" | "dark";

const STORAGE_KEY = "lexorama-theme";

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function stored(): Theme | null {
  const v = localStorage.getItem(STORAGE_KEY);
  return v === "light" || v === "dark" ? v : null;
}

function apply(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(() => stored() ?? systemTheme());

  // Reflect the active theme onto <html> whenever it changes.
  useEffect(() => {
    apply(theme);
  }, [theme]);

  // Follow OS changes only while the user hasn't expressed a preference.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (!stored()) setTheme(mq.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return { theme, toggle };
}

// Read-only subscription to the active theme via the `.dark` class on <html>.
// For consumers (e.g. the cytoscape graph) that need to react to theme changes
// but must NOT own theme state — avoids a second useTheme instance desyncing
// from the header toggle. Works no matter who flips the class.
export function useIsDark(): boolean {
  const [isDark, setIsDark] = useState<boolean>(() =>
    document.documentElement.classList.contains("dark"),
  );
  useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => setIsDark(el.classList.contains("dark")));
    obs.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return isDark;
}
