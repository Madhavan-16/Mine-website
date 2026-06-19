(function () {
  const input = document.getElementById("dashboard-feed-q");
  const list = document.getElementById("dashboard-feed-list");
  if (!input || !list) return;

  const items = list.querySelectorAll("[data-feed-search]");
  const empty = document.getElementById("dashboard-feed-empty");

  input.addEventListener("input", function () {
    const q = input.value.trim().toLowerCase();
    let visible = 0;
    items.forEach(function (el) {
      const hay = (el.getAttribute("data-feed-search") || "").toLowerCase();
      const show = !q || hay.includes(q);
      el.hidden = !show;
      if (show) visible++;
    });
    if (empty) empty.hidden = visible > 0;
  });
})();
