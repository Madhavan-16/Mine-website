/**
 * Team roster — search + discipline filter for squad mosaic.
 */
(function () {
  var root = document.querySelector("[data-team-roster]");
  if (!root) return;

  var search = root.querySelector("[data-team-roster-search]");
  var filters = Array.prototype.slice.call(root.querySelectorAll("[data-team-roster-filter]"));
  var squads = Array.prototype.slice.call(root.querySelectorAll("[data-team-roster-squad]"));
  var emptyMsg = root.querySelector("[data-team-roster-empty]");
  var activeFilter = "all";

  function normalize(s) {
    return (s || "").toLowerCase().trim();
  }

  function apply() {
    var q = search ? normalize(search.value) : "";
    var visibleTotal = 0;

    squads.forEach(function (squad) {
      var slug = squad.getAttribute("data-team-roster-squad") || "";
      var squadMatch = activeFilter === "all" || activeFilter === slug;
      var squadVisible = 0;

      Array.prototype.forEach.call(squad.querySelectorAll("[data-team-roster-card]"), function (card) {
        var hay = normalize(card.getAttribute("data-search"));
        var match = squadMatch && (!q || hay.indexOf(q) !== -1);
        card.classList.toggle("is-hidden", !match);
        if (match) squadVisible += 1;
      });

      squad.classList.toggle("is-hidden", squadVisible === 0);
      visibleTotal += squadVisible;
    });

    if (emptyMsg) {
      emptyMsg.classList.toggle("is-visible", visibleTotal === 0);
    }
  }

  if (search) {
    search.addEventListener("input", apply);
  }

  filters.forEach(function (btn) {
    btn.addEventListener("click", function () {
      activeFilter = btn.getAttribute("data-team-roster-filter") || "all";
      filters.forEach(function (b) {
        b.classList.toggle("is-active", b === btn);
      });
      apply();
    });
  });
})();
