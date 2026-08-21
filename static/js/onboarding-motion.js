(function () {
  var reduceMotion =
    typeof window.matchMedia !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var root = document.querySelector(".ob-tabs");
  if (!root) return;

  var seenPanels = new WeakSet();

  function animatePanel(panel) {
    if (reduceMotion || !panel || seenPanels.has(panel)) return;
    seenPanels.add(panel);
    panel.querySelectorAll("[data-ob-stagger]").forEach(function (node) {
      node.classList.add("is-staggered");
    });
  }

  function currentPanel() {
    if (document.getElementById("ob-tab-dos") && document.getElementById("ob-tab-dos").checked) {
      return root.querySelector(".tab-panel--dos");
    }
    if (document.getElementById("ob-tab-tools") && document.getElementById("ob-tab-tools").checked) {
      return root.querySelector(".tab-panel--tools");
    }
    if (document.getElementById("ob-tab-master") && document.getElementById("ob-tab-master").checked) {
      return root.querySelector(".tab-panel--master");
    }
    return null;
  }

  function sync() {
    animatePanel(currentPanel());
  }

  root.querySelectorAll('input[name="ob-tab"]').forEach(function (input) {
    input.addEventListener("change", sync);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sync, { once: true });
  } else {
    sync();
  }
})();
