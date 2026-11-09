"use strict";
(function () {
  const searchForm = document.getElementById("search-form");
  if (searchForm) {
    searchForm.addEventListener("submit", () => {
      const busy = document.getElementById("search-busy");
      if (busy) busy.hidden = false;
    });
  }

  const zipForm = document.getElementById("zip-form");
  if (!zipForm) return;
  const max = Number(zipForm.dataset.max || "100");
  const interval = Number(zipForm.dataset.interval || "2");
  const picks = Array.from(zipForm.querySelectorAll("input.pick:not(:disabled)"));
  const all = document.getElementById("select-all");
  const count = document.getElementById("selected-count");
  const button = document.getElementById("zip-button");
  const busy = document.getElementById("zip-busy");

  function update() {
    const n = picks.filter((p) => p.checked).length;
    const seconds = Math.ceil(n * interval);
    count.textContent = n + " ausgewählt" + (n ? " (ca. " + seconds + " s Download)" : "");
    button.disabled = n === 0 || n > max;
    if (n > max) count.textContent += " – höchstens " + max + " pro ZIP";
    all.checked = n > 0 && n === picks.length;
    all.indeterminate = n > 0 && n < picks.length;
  }

  all.addEventListener("change", () => {
    picks.forEach((p) => { p.checked = all.checked; });
    update();
  });
  picks.forEach((p) => p.addEventListener("change", update));

  zipForm.addEventListener("submit", () => {
    const n = picks.filter((p) => p.checked).length;
    busy.textContent = "ZIP wird erstellt … " + n + " PDFs, ca. " + Math.ceil(n * interval) + " s. Der Download startet automatisch.";
    busy.hidden = false;
  });
  update();
})();
