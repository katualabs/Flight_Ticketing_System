// Confirmation dialogs. Forms with data-confirm open a native <dialog>, which
// traps focus and closes on Escape by itself, and without JS they simply submit.

function buildDialog() {
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "modal-title");
  const title = document.createElement("h2");
  title.id = "modal-title";
  title.className = "card-title";
  const actions = document.createElement("div");
  actions.className = "modal-actions";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn btn-secondary";
  const accept = document.createElement("button");
  accept.type = "button";
  accept.className = "btn btn-primary";
  actions.append(cancel, accept);
  dialog.append(title, actions);
  document.body.append(dialog);
  return { dialog, title, cancel, accept };
}

export function initConfirm() {
  let parts = null;
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!form.matches("form[data-confirm]") || form.dataset.confirmed) return;
    event.preventDefault();
    parts ??= buildDialog();
    parts.title.textContent = form.dataset.confirm;
    parts.cancel.textContent = form.dataset.confirmCancel || "Go back";
    parts.accept.textContent = form.dataset.confirmAccept || "Confirm";
    parts.cancel.onclick = () => parts.dialog.close();
    parts.accept.onclick = () => {
      form.dataset.confirmed = "true";
      parts.dialog.close();
      form.requestSubmit(event.submitter || undefined);
    };
    parts.dialog.showModal();
    parts.cancel.focus();
  });
}
