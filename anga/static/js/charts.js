// Hover and keyboard tooltips for the dashboard's SVG charts. The figures are all
// also in each mark's <title> and in the table view, so this is purely a nicety.

export function initCharts() {
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;
  document.body.append(tooltip);

  const show = (mark, x, y) => {
    tooltip.textContent = mark.dataset.tip;
    tooltip.hidden = false;
    const width = tooltip.offsetWidth;
    tooltip.style.left = `${Math.min(x + 12, window.innerWidth - width - 8)}px`;
    tooltip.style.top = `${y - 34}px`;
  };

  document.querySelectorAll("[data-chart] [data-tip]").forEach((mark) => {
    mark.addEventListener("mousemove", (event) => show(mark, event.clientX, event.clientY));
    mark.addEventListener("mouseleave", () => {
      tooltip.hidden = true;
    });
    mark.addEventListener("focus", () => {
      const box = mark.getBoundingClientRect();
      show(mark, box.left, box.top);
    });
    mark.addEventListener("blur", () => {
      tooltip.hidden = true;
    });
  });
}
