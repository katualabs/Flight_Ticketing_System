// Entry point. Every feature is progressive enhancement and only loads when the
// page actually contains its markup.

import { initTheme } from "./theme.js";
import { initNav } from "./nav.js";
import { initToasts } from "./toast.js";
import { initConfirm } from "./modal.js";

const LAZY_MODULES = [
  ["[data-stepper]", "./stepper.js", "initSteppers"],
  ["[data-airport-combo]", "./autocomplete.js", "initAutocomplete"],
  ["[data-swap]", "./swap.js", "initSwap"],
  ["[data-trip-toggle]", "./swap.js", "initTripToggle"],
  ["[data-route-map]", "./routemap.js", "initRouteMap"],
  ["[data-seatmap]", "./seatmap.js", "initSeatMaps"],
  ["[data-live-quote]", "./quote.js", "initLiveQuote"],
  ["[data-fare-options]", "./fares.js", "initFareOptions"],
  ["[data-payment-poll]", "./payment.js", "initPaymentPoll"],
  ["[data-card-number]", "./payment.js", "initCardFormat"],
  ["[data-payment-tabs]", "./payment.js", "initPaymentTabs"],
  ["[data-board]", "./board.js", "initBoard"],
  ["[data-print]", "./actions.js", "initPrint"],
  ["[data-traveller-picker]", "./actions.js", "initTravellerPicker"],
  ["[data-auto-submit]", "./actions.js", "initAutoSubmit"],
];

function init() {
  initTheme();
  initNav();
  initToasts();
  initConfirm();
  for (const [selector, path, name] of LAZY_MODULES) {
    if (document.querySelector(selector)) {
      import(path).then((module) => module[name]());
    }
  }
}

init();
