/**
 * Panel/tab crossfade helper for onboarding, training, projects views.
 */
(function () {
  var reduce =
    typeof window.matchMedia !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function flash(el) {
    if (!el || reduce) return;
    el.classList.remove("is-panel-crossfade");
    void el.offsetWidth;
    el.classList.add("is-panel-crossfade");
  }

  /* Onboarding radio tabs */
  var ob = document.querySelector(".ob-tabs");
  if (ob) {
    ob.querySelectorAll('input[name="ob-tab"]').forEach(function (input) {
      input.addEventListener("change", function () {
        var panel =
          (document.getElementById("ob-tab-dos") && document.getElementById("ob-tab-dos").checked && ob.querySelector(".tab-panel--dos")) ||
          (document.getElementById("ob-tab-tools") && document.getElementById("ob-tab-tools").checked && ob.querySelector(".tab-panel--tools")) ||
          (document.getElementById("ob-tab-master") && document.getElementById("ob-tab-master").checked && ob.querySelector(".tab-panel--master"));
        flash(panel);
      });
    });
  }

  /* Training topic tabs */
  var training = document.querySelector("[data-teams-training]");
  if (training) {
    training.querySelectorAll("[data-teams-topic]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        flash(training.querySelector(".teams-training-groups"));
      });
    });
  }

  /* Projects view switch — flash panel after projects-portal.js toggles visibility */
  var projects = document.querySelector("[data-projects-portal]");
  if (projects) {
    projects.querySelectorAll("[data-projects-view]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = btn.getAttribute("data-projects-view") || "cards";
        window.requestAnimationFrame(function () {
          var panel =
            projects.querySelector('[data-projects-view-panel="' + key + '"]') ||
            projects.querySelector('[data-projects-viz="' + key + '"]');
          flash(panel);
        });
      });
    });
  }
})();
