// Search card behaviour: swapping airports and hiding the return date on one-ways.

export function initSwap() {
  document.querySelectorAll("[data-swap]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", () => {
      const form = button.closest("form");
      const from = form.elements.from;
      const to = form.elements.to;
      [from.value, to.value] = [to.value, from.value];
      from.dispatchEvent(new Event("change", { bubbles: true }));
      to.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
}

export function initTripToggle() {
  document.querySelectorAll("[data-trip-toggle]").forEach((toggle) => {
    const form = toggle.closest("form");
    const field = form.querySelector("[data-return-field]");
    const depart = form.elements.depart;
    const returning = form.elements.return;
    const sync = () => {
      field.hidden = form.elements.trip.value !== "round_trip";
      returning.disabled = field.hidden;
    };
    toggle.addEventListener("change", sync);
    depart.addEventListener("change", () => {
      returning.min = depart.value || returning.min;
    });
    sync();
  });
}
