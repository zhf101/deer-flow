const themeScript = `
(() => {
  try {
    const root = document.documentElement;
    const stored = localStorage.getItem("theme");
    let theme = stored === "light" || stored === "dark" || stored === "system" ? stored : "system";

    if (window.location.pathname === "/") {
      theme = "dark";
    }

    if (theme === "system") {
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }

    root.classList.remove("light", "dark");
    root.classList.add(theme);
    root.style.colorScheme = theme;
  } catch {}
})();
`;

export function ThemeScript() {
  return (
    <script
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: themeScript }}
    />
  );
}
