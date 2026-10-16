export const themeStorageKey = "twf-theme";

// Trusted static source, executed before body paint. Light is the workstation baseline.
export const themeInitializationScript = `(() => {
  let theme = "light";
  try {
    if (localStorage.getItem("${themeStorageKey}") === "dark") theme = "dark";
  } catch {}
  document.documentElement.dataset.theme = theme;
})();`;
