// Runs before first paint (classic script, not deferred) so a saved dark theme
// never flashes light. Must stay external: the CSP forbids inline scripts.
(function () {
  var saved = null;
  try {
    saved = localStorage.getItem("anga-theme");
  } catch (_) {
    saved = null;
  }
  var prefersDark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = saved || (prefersDark ? "dark" : "light");
  document.documentElement.classList.add("js");
})();
