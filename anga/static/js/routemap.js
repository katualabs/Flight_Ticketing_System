// Route map: hovering or focusing a route shows its price beside the map.

export function initRouteMap() {
  const map = document.querySelector("[data-route-map]");
  const readout = document.querySelector("[data-map-readout]");
  if (!map || !readout) return;
  const hint = readout.querySelector("[data-map-hint]");
  const route = readout.querySelector("[data-map-route]");
  const price = readout.querySelector("[data-map-price]");

  const show = (link) => {
    hint.textContent = map.dataset.fromLabel;
    route.textContent = link.dataset.route;
    price.textContent = link.dataset.price;
    map.querySelectorAll(".is-active").forEach((el) => el.classList.remove("is-active"));
    link.classList.add("is-active");
  };
  map.querySelectorAll("[data-route]").forEach((link) => {
    link.addEventListener("mouseenter", () => show(link));
    link.addEventListener("focus", () => show(link));
  });
}
