import {
  createContext,
  type ReactNode,
  use,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from "react";

/**
 * Tema da interface: "system" segue o sistema operacional; "light" e "dark" fixam.
 * O tema resolvido vai para <html data-theme="…"> (o CSS lê daí). O index.html aplica o tema
 * salvo antes do React carregar, para não piscar escuro → claro.
 */
export type ThemePreference = "system" | "light" | "dark";
export type Theme = "light" | "dark";

export const THEME_KEY = "qc-theme";
const query = () => window.matchMedia("(prefers-color-scheme: light)");

function readPreference(): ThemePreference {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch {
    // modo privado / armazenamento bloqueado: segue o sistema
  }
  return "system";
}

const resolve = (preference: ThemePreference): Theme =>
  preference === "system" ? (query().matches ? "light" : "dark") : preference;

interface ThemeValue {
  preference: ThemePreference;
  theme: Theme;
  setPreference: (preference: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readPreference);
  const [theme, setTheme] = useState<Theme>(() => resolve(readPreference()));

  useEffect(() => {
    const apply = () => setTheme(resolve(preference));
    apply();
    if (preference !== "system") return;
    const media = query();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [preference]);

  // layout effect: o atributo muda antes dos efeitos dos filhos (que leem tokens do CSS)
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", theme === "light" ? "#F4F6F5" : "#050607");
  }, [theme]);

  const setPreference = useCallback((next: ThemePreference) => {
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // sem armazenamento: vale só nesta aba
    }
    setPreferenceState(next);
  }, []);

  const value = useMemo(() => ({ preference, theme, setPreference }), [preference, theme, setPreference]);
  return <ThemeContext value={value}>{children}</ThemeContext>;
}

export function useTheme(): ThemeValue {
  const value = use(ThemeContext);
  if (!value) throw new Error("useTheme fora do ThemeProvider");
  return value;
}

/** Lê um token de cor do CSS (para desenhos em <canvas>, que não enxergam variáveis CSS). */
export function cssToken(name: string, fallback = ""): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}
