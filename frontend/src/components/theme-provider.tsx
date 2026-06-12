"use client";

import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type ResolvedTheme = "light" | "dark";
type ThemeMode = ResolvedTheme | "system";

type ThemeProviderProps = {
  children: ReactNode;
  attribute?: string | string[];
  defaultTheme?: ThemeMode;
  disableTransitionOnChange?: boolean;
  enableColorScheme?: boolean;
  enableSystem?: boolean;
  forcedTheme?: ThemeMode;
  storageKey?: string;
  themes?: ResolvedTheme[];
  value?: Record<string, string>;
};

type ThemeContextValue = {
  forcedTheme?: ThemeMode;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: ThemeMode) => void;
  systemTheme: ResolvedTheme;
  theme: ThemeMode;
  themes: ThemeMode[];
};

const DEFAULT_STORAGE_KEY = "theme";
const DEFAULT_THEMES: ResolvedTheme[] = ["light", "dark"];

const ThemeContext = createContext<ThemeContextValue>({
  resolvedTheme: "light",
  setTheme: () => undefined,
  systemTheme: "light",
  theme: "system",
  themes: ["light", "dark", "system"],
});

export function useTheme() {
  return useContext(ThemeContext);
}

export function ThemeProvider({
  children,
  attribute = "data-theme",
  defaultTheme = "system",
  disableTransitionOnChange = false,
  enableColorScheme = true,
  enableSystem = true,
  forcedTheme,
  storageKey = DEFAULT_STORAGE_KEY,
  themes = DEFAULT_THEMES,
  value,
}: ThemeProviderProps) {
  const pathname = usePathname();
  const routeForcedTheme = pathname === "/" ? "dark" : forcedTheme;
  const [theme, setThemeState] = useState<ThemeMode>(() =>
    getStoredTheme(storageKey, defaultTheme),
  );
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() =>
    getSystemTheme(),
  );

  const resolvedTheme = useMemo(
    () => resolveTheme(routeForcedTheme ?? theme, systemTheme, enableSystem),
    [enableSystem, routeForcedTheme, systemTheme, theme],
  );

  const setTheme = useCallback(
    (nextTheme: ThemeMode) => {
      setThemeState(nextTheme);
      try {
        localStorage.setItem(storageKey, nextTheme);
      } catch {
        // 浏览器禁用存储时只更新当前页面状态。
      }
    },
    [storageKey],
  );

  useEffect(() => {
    setThemeState(getStoredTheme(storageKey, defaultTheme));
  }, [defaultTheme, storageKey]);

  useEffect(() => {
    applyTheme({
      attribute,
      disableTransitionOnChange,
      enableColorScheme,
      resolvedTheme,
      themes,
      value,
    });
  }, [
    attribute,
    disableTransitionOnChange,
    enableColorScheme,
    resolvedTheme,
    themes,
    value,
  ]);

  useEffect(() => {
    if (!enableSystem) {
      return;
    }

    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => setSystemTheme(query.matches ? "dark" : "light");

    handleChange();
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, [enableSystem]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === storageKey) {
        setThemeState(normalizeTheme(event.newValue, defaultTheme));
      }
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [defaultTheme, storageKey]);

  const contextValue = useMemo<ThemeContextValue>(
    () => ({
      forcedTheme: routeForcedTheme,
      resolvedTheme,
      setTheme,
      systemTheme,
      theme,
      themes: enableSystem ? [...themes, "system"] : themes,
    }),
    [
      enableSystem,
      resolvedTheme,
      routeForcedTheme,
      setTheme,
      systemTheme,
      theme,
      themes,
    ],
  );

  return (
    <ThemeContext.Provider value={contextValue}>
      {children}
    </ThemeContext.Provider>
  );
}

function getStoredTheme(
  storageKey: string,
  defaultTheme: ThemeMode,
): ThemeMode {
  if (typeof window === "undefined") {
    return defaultTheme;
  }

  try {
    return normalizeTheme(localStorage.getItem(storageKey), defaultTheme);
  } catch {
    return defaultTheme;
  }
}

function normalizeTheme(value: string | null, fallback: ThemeMode): ThemeMode {
  return value === "light" || value === "dark" || value === "system"
    ? value
    : fallback;
}

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") {
    return "light";
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function resolveTheme(
  theme: ThemeMode,
  systemTheme: ResolvedTheme,
  enableSystem: boolean,
): ResolvedTheme {
  return theme === "system" && enableSystem
    ? systemTheme
    : theme === "dark"
      ? "dark"
      : "light";
}

function applyTheme({
  attribute,
  disableTransitionOnChange,
  enableColorScheme,
  resolvedTheme,
  themes,
  value,
}: {
  attribute: string | string[];
  disableTransitionOnChange: boolean;
  enableColorScheme: boolean;
  resolvedTheme: ResolvedTheme;
  themes: ResolvedTheme[];
  value?: Record<string, string>;
}) {
  const restoreTransitions = disableTransitionOnChange
    ? disableTransitions()
    : undefined;
  const root = document.documentElement;
  const mappedTheme = value?.[resolvedTheme] ?? resolvedTheme;
  const themeValues = value ? Object.values(value) : themes;

  for (const attr of Array.isArray(attribute) ? attribute : [attribute]) {
    if (attr === "class") {
      root.classList.remove(...themeValues);
      root.classList.add(mappedTheme);
      continue;
    }

    if (attr.startsWith("data-")) {
      root.setAttribute(attr, mappedTheme);
    }
  }

  if (enableColorScheme) {
    root.style.colorScheme = resolvedTheme;
  }

  restoreTransitions?.();
}

function disableTransitions() {
  const style = document.createElement("style");
  style.appendChild(
    document.createTextNode("*,*::before,*::after{transition:none!important}"),
  );
  document.head.appendChild(style);

  return () => {
    window.getComputedStyle(document.body);
    window.setTimeout(() => document.head.removeChild(style), 1);
  };
}
