// Interactive seat maps. The per-passenger <select> stays the source of truth,
// so the form submits exactly the same data with or without this script.

function initSeatMap(section) {
  const grid = section.querySelector("[data-seat-grid]");
  const panels = [...section.querySelectorAll("[data-seat-pax]")];
  const seats = [...grid.querySelectorAll("[data-seat]")];
  const enabled = seats.filter((seat) => !seat.disabled);

  const activePanel = () => panels.find((panel) => panel.querySelector("input").checked);

  const paint = () => {
    const owners = new Map(
      panels.map((panel, i) => [panel.querySelector("select").value, i + 1]),
    );
    for (const seat of seats) {
      const owner = owners.get(seat.dataset.seat);
      seat.classList.toggle("is-selected", Boolean(owner));
      seat.setAttribute("aria-pressed", String(Boolean(owner)));
      seat.textContent = owner ? String(owner) : seat.dataset.seat.slice(-1);
    }
  };

  const assign = (code) => {
    const panel = activePanel();
    const select = panel.querySelector("select");
    const holder = panels.find((p) => p.querySelector("select").value === code);
    if (holder === panel) {
      select.value = "";
    } else {
      if (holder) holder.querySelector("select").value = "";
      select.value = code;
      const next = panels[panels.indexOf(panel) + 1];
      if (next) next.querySelector("input").checked = true;
    }
    paint();
    select.dispatchEvent(new Event("change", { bubbles: true }));
  };

  // Roving tabindex: one tab stop for the whole map, arrow keys inside it.
  enabled.forEach((seat, i) => {
    seat.tabIndex = i === 0 ? 0 : -1;
  });

  const rows = [...grid.querySelectorAll(".seat-row:not(.seat-columns)")].map((row) => [
    ...row.querySelectorAll("[data-seat]"),
  ]);

  const moveFrom = (seat, rowStep, columnStep) => {
    let rowIndex = rows.findIndex((row) => row.includes(seat));
    let columnIndex = rows[rowIndex].indexOf(seat);
    for (let guard = 0; guard < 200; guard += 1) {
      rowIndex += rowStep;
      columnIndex += columnStep;
      const row = rows[rowIndex];
      const candidate = row?.[columnIndex];
      if (!candidate) return null;
      if (!candidate.disabled) return candidate;
    }
    return null;
  };

  grid.addEventListener("keydown", (event) => {
    const seat = event.target.closest("[data-seat]");
    if (!seat) return;
    const steps = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    }[event.key];
    if (!steps) return;
    event.preventDefault();
    const target = moveFrom(seat, steps[0], steps[1]);
    if (target) {
      seat.tabIndex = -1;
      target.tabIndex = 0;
      target.focus();
    }
  });

  grid.addEventListener("click", (event) => {
    const seat = event.target.closest("[data-seat]");
    if (seat && !seat.disabled) assign(seat.dataset.seat);
  });

  panels.forEach((panel) => {
    panel.querySelector("select").addEventListener("change", paint);
  });
  paint();
}

export function initSeatMaps() {
  document.querySelectorAll("[data-seatmap]").forEach(initSeatMap);
}
