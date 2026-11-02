// Payment page behaviour: method tabs, card spacing and the M-Pesa status poll.

const POLL_INTERVAL_MS = 1500;

export function initPaymentPoll() {
  const panel = document.querySelector("[data-payment-poll]");
  const tick = async () => {
    try {
      const response = await fetch(panel.dataset.paymentPoll, {
        headers: { Accept: "application/json" },
      });
      if (response.ok) {
        const { status, redirect } = await response.json();
        if (status !== "initiated") {
          window.location.assign(redirect);
          return;
        }
      }
    } catch {
      // A dropped poll is harmless; the next tick tries again.
    }
    setTimeout(tick, POLL_INTERVAL_MS);
  };
  setTimeout(tick, POLL_INTERVAL_MS);
}

export function initCardFormat() {
  document.querySelectorAll("[data-card-number]").forEach((input) => {
    input.addEventListener("input", () => {
      const digits = input.value.replace(/\D/g, "").slice(0, 16);
      input.value = digits.replace(/(.{4})(?=.)/g, "$1 ");
    });
  });
}

export function initPaymentTabs() {
  const tabs = document.querySelector("[data-payment-tabs]");
  const buttons = [...tabs.querySelectorAll("[data-tab]")];
  const panels = [...document.querySelectorAll("[data-panel]")];
  const show = (name) => {
    buttons.forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.tab === name));
    });
    panels.forEach((panel) => {
      panel.hidden = panel.dataset.panel !== name;
    });
  };
  tabs.hidden = false;
  buttons.forEach((button) => {
    button.addEventListener("click", () => show(button.dataset.tab));
  });
  const initial = buttons.find((b) => b.getAttribute("aria-selected") === "true") || buttons[0];
  show(initial.dataset.tab);
}
