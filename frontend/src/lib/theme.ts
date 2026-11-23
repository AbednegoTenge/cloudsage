export type Theme = "dark" | "light";
const KEY = "cloudsage.theme";

export function getStoredTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* storage unavailable: theme still applies for this session */
  }
}

export function applyStoredTheme(): void {
  document.documentElement.dataset.theme = getStoredTheme();
}
