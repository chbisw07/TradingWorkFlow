export const themeStorageKey = "twf-theme";

// Trusted static source, executed before body paint. Storage failure keeps dark.
export const themeInitializationScript = `(() => {
  let theme = "dark";
  try {
    if (localStorage.getItem("${themeStorageKey}") === "light") theme = "light";
  } catch {}
  document.documentElement.dataset.theme = theme;
})();`;
