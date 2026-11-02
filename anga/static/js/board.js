// Refreshes the departures/arrivals board every minute from the JSON API. Rows are
// built with DOM nodes rather than HTML strings, so nothing is ever parsed as markup.

const REFRESH_MS = 60_000;
const STATUS_BADGES = {
  Delayed: "badge-warning",
  Cancelled: "badge-danger",
  "On time": "badge-success",
  Landed: "badge-success",
};

function cell(label, text, className = "") {
  const td = document.createElement("td");
  td.dataset.label = label;
  td.textContent = text;
  td.className = className;
  return td;
}

function statusCell(label, flight) {
  const td = document.createElement("td");
  td.dataset.label = label;
  const badge = document.createElement("span");
  badge.className = `badge ${STATUS_BADGES[flight.status] || "badge-info"}`;
  badge.textContent = flight.status;
  td.append(badge);
  if (flight.delay_minutes) {
    const delay = document.createElement("span");
    delay.className = "xs muted";
    delay.textContent = ` +${flight.delay_minutes}m`;
    td.append(delay);
  }
  return td;
}

export function initBoard() {
  const board = document.querySelector("[data-board]");
  const body = board.querySelector("[data-board-body]");
  const updated = document.querySelector("[data-board-updated]");
  const labels = [...board.querySelectorAll("thead th")].map((th) => th.textContent);
  const departures = board.dataset.kind === "departures";

  const refresh = async () => {
    try {
      const response = await fetch(board.dataset.url);
      if (!response.ok) return;
      const { data, meta } = await response.json();
      const today = meta.date;
      if (!data.length) return;
      body.replaceChildren(
        ...data.map((flight) => {
          const row = document.createElement("tr");
          row.append(
            cell(
              labels[0],
              departures ? flight.estimated_departure : flight.estimated_arrival,
              "mono",
            ),
            cell(
              labels[1],
              flight.date === today ? flight.flight_number : `${flight.flight_number} (${flight.date.slice(5)})`,
              "mono strong",
            ),
            cell(labels[2], departures ? flight.destination_city : flight.origin_city),
            cell(labels[3], flight.gate || "—", "mono"),
            statusCell(labels[4], flight),
          );
          return row;
        }),
      );
      updated.textContent = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      // Keep showing the last good data; the next tick tries again.
    }
  };
  setInterval(refresh, REFRESH_MS);
}
