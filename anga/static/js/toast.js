// Toasts: flash messages are server-rendered into an aria-live region, and this
// just lets them dismiss themselves.

const AUTO_DISMISS_MS = 7000;

function dismissOnTimer(toast) {
  const close = () => toast.remove();
  toast.querySelector("button")?.addEventListener("click", close);
  if (!toast.classList.contains("toast-error")) {
    setTimeout(close, AUTO_DISMISS_MS);
  }
}

export function initToasts() {
  document.querySelectorAll(".toast").forEach(dismissOnTimer);
}

export function showToast(message, kind = "info") {
  const region = document.querySelector(".toast-region");
  if (!region) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${kind}`;
  const text = document.createElement("span");
  text.textContent = message;
  const close = document.createElement("button");
  close.type = "button";
  close.setAttribute("aria-label", "Dismiss");
  close.textContent = "×";
  toast.append(text, close);
  region.append(toast);
  dismissOnTimer(toast);
}
