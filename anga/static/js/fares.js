// Keeps the results page's sticky bar in step with the chosen fares.

export function initFareOptions() {
  const form = document.querySelector("[data-fare-options]");
  const bar = form.querySelector("[data-selection]");
  const total = form.querySelector("[data-selection-total]");
  const money = new Intl.NumberFormat("en-KE");

  const update = () => {
    const chosen = [...form.querySelectorAll('input[type="radio"]:checked')];
    bar.textContent = chosen.map((input) => input.dataset.label).join(" + ") || bar.dataset.empty;
    const sum = chosen.reduce((running, input) => running + Number(input.dataset.price), 0);
    total.textContent = sum ? `KSh ${money.format(sum)}` : "";
  };
  form.addEventListener("change", update);
  update();
}
