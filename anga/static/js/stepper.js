// Plus/minus buttons for number inputs; the input itself works without JS.

export function initSteppers() {
  document.querySelectorAll("[data-stepper]").forEach((stepper) => {
    const input = stepper.querySelector("input");
    stepper.querySelectorAll("[data-step]").forEach((button) => {
      button.addEventListener("click", () => {
        const next = Number(input.value || 0) + Number(button.dataset.step);
        const min = Number(input.min || 0);
        const max = Number(input.max || 99);
        input.value = String(Math.min(max, Math.max(min, next)));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
  });
}
