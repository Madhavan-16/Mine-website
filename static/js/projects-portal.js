/**
 * Programs & Projects — view switcher, expandable cards + section tab explorer.
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

  function expandCard(card) {
    var toggle = card.querySelector("[data-project-card-toggle]");
    if (!toggle || card.classList.contains("is-expanded")) return;
    card.classList.add("is-expanded");
    toggle.setAttribute("aria-expanded", "true");
    var panel = card.querySelector("[data-project-card-panel]");
    if (panel) panel.setAttribute("aria-hidden", "false");
  }

  function setView(viewKey) {
    var buttons = root.querySelectorAll("[data-projects-view]");
    var vizPanels = root.querySelectorAll("[data-projects-viz]");
    var cardsPanel = root.querySelector('[data-projects-view-panel="cards"]');

    buttons.forEach(function (btn) {
      var active = btn.getAttribute("data-projects-view") === viewKey;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });

    vizPanels.forEach(function (panel) {
      var show = panel.getAttribute("data-projects-viz") === viewKey;
      if (show) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
    });

    if (cardsPanel) {
      if (viewKey === "cards") cardsPanel.removeAttribute("hidden");
      else cardsPanel.setAttribute("hidden", "");
    }

    root.setAttribute("data-active-view", viewKey);

    if (viewKey === "gantt") {
      if (window.MiNeProjectsViz && window.MiNeProjectsViz.ensure) {
        window.MiNeProjectsViz.ensure(viewKey);
      }
      window.requestAnimationFrame(function () {
        if (window.MiNeProjectsViz && window.MiNeProjectsViz.refresh) {
          window.MiNeProjectsViz.refresh();
        }
      });
    }
  }

  function openProjectCard(projectId) {
    setView("cards");
    var card = root.querySelector('[data-project-card][id="project-' + projectId + '"]');
    if (!card) {
      card = root.querySelector('[data-project-card][id="' + projectId + '"]');
    }
    if (!card) return;
    expandCard(card);
    window.setTimeout(function () {
      card.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      var toggle = card.querySelector("[data-project-card-toggle]");
      if (toggle) toggle.focus({ preventScroll: true });
    }, 60);
  }

  window.MiNeProjects = {
    openProjectCard: openProjectCard,
    setView: setView,
  };

  root.querySelectorAll("[data-projects-view]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setView(btn.getAttribute("data-projects-view") || "cards");
    });
  });

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
