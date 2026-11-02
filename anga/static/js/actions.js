// Small one-off behaviours.

export function initPrint() {
  document.querySelectorAll("[data-print]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", () => window.print());
  });
}

export function initAutoSubmit() {
  document.querySelectorAll("form[data-auto-submit]").forEach((form) => {
    form.addEventListener("change", () => form.requestSubmit());
  });
}

// Copies a saved traveller's details into a passenger form.
export function initTravellerPicker() {
  document.querySelectorAll("[data-traveller-picker]").forEach((select) => {
    select.addEventListener("change", () => {
      const option = select.selectedOptions[0];
      if (!option.value) return;
      const group = select.closest("[data-passenger]");
      group.querySelector('[data-field="full_name"]').value = option.dataset.name;
      group.querySelector('[data-field="id_number"]').value = option.dataset.idNumber;
      const birth = group.querySelector('[data-field="date_of_birth"]');
      if (birth) birth.value = option.dataset.dob || "";
    });
  });
}
