// Light/dark toggle, remembered in localStorage.

export function initTheme() {
  const button = document.querySelector("[data-theme-toggle]");
  if (!button) return;
  button.hidden = false;
  const label = () => {
    const dark = document.documentElement.dataset.theme === "dark";
    button.setAttribute("aria-pressed", String(dark));
    button.textContent = dark ? "☀" : "☾";
  };
  label();
  button.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("anga-theme", next);
    } catch {
      // Private browsing may refuse storage; the toggle still works for this page.
    }
    label();
  });
}
