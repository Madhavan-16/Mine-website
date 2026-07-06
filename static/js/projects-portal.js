/**
 * Programs & Projects — expandable cards + exclusive section tab explorer.
 */
(function () {
  var root = document.querySelector("[data-projects-portal]");
  if (!root) return;

  var reduce =
    typeof window.matchMedia !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function activateTab(card, tabKey) {
    var tabs = card.querySelectorAll("[data-project-tab]");
    var panels = card.querySelectorAll("[data-project-panel]");

    tabs.forEach(function (tab) {
      var active = tab.getAttribute("data-project-tab") === tabKey;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });

    panels.forEach(function (panel) {
      var active = panel.getAttribute("data-project-panel") === tabKey;
      panel.classList.toggle("is-active", active);
      if (active) {
        panel.removeAttribute("hidden");
        if (!reduce) {
          panel.style.animation = "none";
          void panel.offsetHeight;
          panel.style.animation = "";
        }
      } else {
        panel.setAttribute("hidden", "");
      }
    });
  }

  function initExplorer(card) {
    var explorer = card.querySelector("[data-project-explorer]");
    if (!explorer) return;

    var tabs = explorer.querySelectorAll("[data-project-tab]");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function (e) {
        e.stopPropagation();
        activateTab(card, tab.getAttribute("data-project-tab"));
      });
    });
  }

  var cards = Array.prototype.slice.call(root.querySelectorAll("[data-project-card]"));

  cards.forEach(function (card) {
    var toggle = card.querySelector("[data-project-card-toggle]");
    if (!toggle) return;

    initExplorer(card);

    toggle.addEventListener("click", function () {
      var expanded = card.classList.toggle("is-expanded");
      toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
      var panel = card.querySelector("[data-project-card-panel]");
      if (panel) {
        panel.setAttribute("aria-hidden", expanded ? "false" : "true");
      }
    });
  });
})();
