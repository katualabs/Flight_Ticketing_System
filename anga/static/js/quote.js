// Live price summary. The server does all the arithmetic and returns the rendered
// summary; if a request fails, the form still submits and the next page is right.

export function initLiveQuote() {
  const summary = document.querySelector("[data-summary]");
  document.querySelectorAll("form[data-live-quote]").forEach((form) => {
    let latest = 0;
    form.addEventListener("change", async () => {
      latest += 1;
      const request = latest;
      const token = document.querySelector('meta[name="csrf-token"]').content;
      try {
        const response = await fetch(form.dataset.quoteUrl, {
          method: "POST",
          headers: { "X-CSRF-Token": token },
          body: new FormData(form),
        });
        if (!response.ok || request !== latest) return;
        const html = new DOMParser().parseFromString(await response.text(), "text/html");
        summary.replaceChildren(...html.body.childNodes);
      } catch {
        // A dropped request only delays the update until the next page.
      }
    });
  });
}
