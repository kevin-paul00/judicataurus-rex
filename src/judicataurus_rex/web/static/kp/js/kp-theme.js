// Colour mode switch: auto → light → dark.
// "auto" follows the device setting. A fixed choice is stored only in the visitor's own
// browser (localStorage "kp-theme"); nothing is sent to the server.
// Without JavaScript the button stays hidden and the page follows the device.
// Labels come per language from the button's data attributes (config/content/*.toml).
(function () {
  var MODES = ["auto", "light", "dark"];
  var root = document.documentElement;
  var button = document.getElementById("kp-theme");
  if (!button) return;
  var LABELS = { auto: button.dataset.auto, light: button.dataset.light, dark: button.dataset.dark };

  function load() {
    try { return localStorage.getItem("kp-theme") || "auto"; } catch (e) { return "auto"; }
  }
  function store(mode) {
    try {
      if (mode === "auto") localStorage.removeItem("kp-theme");
      else localStorage.setItem("kp-theme", mode);
    } catch (e) { /* private window or similar: the choice lasts until the page is reloaded */ }
  }
  function apply(mode) {
    if (mode === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", mode);
    button.querySelector("[data-name]").textContent = LABELS[mode];
    button.setAttribute("aria-label", button.dataset.aria.replace("{mode}", LABELS[mode]));
  }

  var current = load();
  if (MODES.indexOf(current) < 0) current = "auto";
  apply(current);
  button.hidden = false;
  button.addEventListener("click", function () {
    current = MODES[(MODES.indexOf(current) + 1) % MODES.length];
    apply(current);
    store(current);
  });
})();
