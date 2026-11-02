// Airport combobox built on the WAI-ARIA combobox pattern. It upgrades the plain
// <select>, which stays in the DOM as the submitted value and as the no-JS fallback.

function filterAirports(airports, query) {
  const needle = query.trim().toLowerCase();
  if (!needle) return airports;
  return airports.filter((airport) =>
    [airport.code, airport.city, airport.country, airport.name].some((value) =>
      value.toLowerCase().includes(needle),
    ),
  );
}

function upgrade(field, airports, index) {
  const select = field.querySelector("select");
  const label = field.querySelector("label");
  const wrapper = document.createElement("div");
  wrapper.className = "combo";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "input";
  input.id = `${select.id}-combo`;
  input.autocomplete = "off";
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.placeholder = select.options[0]?.textContent || "";

  const list = document.createElement("ul");
  const listId = `combo-list-${index}`;
  list.id = listId;
  list.className = "combo-list";
  list.setAttribute("role", "listbox");
  list.hidden = true;
  input.setAttribute("aria-controls", listId);

  let active = -1;
  let matches = [];

  const displayName = () => {
    const option = select.options[select.selectedIndex];
    return option && option.value ? option.textContent : "";
  };
  const close = () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  };
  const choose = (airport) => {
    select.value = airport.code;
    input.value = displayName();
    close();
    select.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const highlight = (position) => {
    const items = [...list.children];
    items.forEach((item, i) => item.setAttribute("aria-selected", String(i === position)));
    active = position;
    if (items[position]) {
      input.setAttribute("aria-activedescendant", items[position].id);
      items[position].scrollIntoView({ block: "nearest" });
    }
  };
  const render = () => {
    matches = filterAirports(airports, input.value === displayName() ? "" : input.value);
    list.replaceChildren(
      ...matches.map((airport, i) => {
        const item = document.createElement("li");
        item.id = `${listId}-${i}`;
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", "false");
        const name = document.createElement("span");
        name.textContent = `${airport.city}, ${airport.country}`;
        const code = document.createElement("span");
        code.className = "code";
        code.textContent = airport.code;
        item.append(name, code);
        item.addEventListener("mousedown", (event) => {
          event.preventDefault();
          choose(airport);
        });
        return item;
      }),
    );
    list.hidden = matches.length === 0;
    input.setAttribute("aria-expanded", String(!list.hidden));
    active = -1;
  };

  input.addEventListener("focus", () => {
    input.select();
    render();
  });
  input.addEventListener("input", render);
  input.addEventListener("blur", () => {
    close();
    input.value = displayName();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (list.hidden) render();
      if (!matches.length) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      highlight((active + step + matches.length) % matches.length);
    } else if (event.key === "Enter" && !list.hidden) {
      const pick = matches[active >= 0 ? active : 0];
      if (pick) {
        event.preventDefault();
        choose(pick);
      }
    } else if (event.key === "Escape") {
      close();
    }
  });
  select.addEventListener("change", () => {
    input.value = displayName();
  });

  label.htmlFor = input.id;
  select.hidden = true;
  select.tabIndex = -1;
  wrapper.append(input, list);
  field.insertBefore(wrapper, select);
  input.value = displayName();
}

export async function initAutocomplete() {
  let airports;
  try {
    const response = await fetch("/api/v1/airports");
    if (!response.ok) return;
    ({ data: airports } = await response.json());
  } catch {
    return; // The plain <select> remains fully usable.
  }
  document
    .querySelectorAll("[data-airport-combo]")
    .forEach((field, index) => upgrade(field, airports, index));
}
