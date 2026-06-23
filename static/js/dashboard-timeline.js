/**
 * Strategic timeline — live readout, era navigator, scroll-synced runner & wave.
 */
(function () {
  "use strict";

  function init() {
    var root = document.getElementById("dash-timeline-motion");
    if (!root) return;

    var viewport = root.querySelector("[data-timeline-viewport]");
    var stage = root.querySelector("[data-timeline-stage]");
    var eras = root.querySelectorAll("[data-timeline-era]");
    var navBtns = root.querySelectorAll("[data-timeline-jump]");
    var liveYear = root.querySelector("[data-timeline-live-year]");
    var liveTitle = root.querySelector("[data-timeline-live-title]");
    var liveDesc = root.querySelector("[data-timeline-live-desc]");
    var runner = root.querySelector("[data-timeline-runner]");
    var waveFill = root.querySelector("[data-timeline-wave-fill]");

    if (!viewport || !eras.length) return;

    var reduceMotion = false;
    try {
      reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {}

    var waveLength = 0;
    if (waveFill && typeof waveFill.getTotalLength === "function") {
      waveLength = waveFill.getTotalLength();
      waveFill.style.strokeDasharray = String(waveLength);
      waveFill.style.strokeDashoffset = String(waveLength);
    }

    function setActive(index, scrollIntoView) {
      var i = Math.max(0, Math.min(eras.length - 1, index));
      var era = eras[i];
      if (!era) return;

      root.classList.add("dash-strategic-timeline--focused");
      eras.forEach(function (el, n) {
        el.classList.toggle("is-active", n === i);
      });
      navBtns.forEach(function (btn) {
        btn.classList.toggle("is-active", Number(btn.getAttribute("data-timeline-jump")) === i);
      });

      if (liveYear) liveYear.textContent = era.getAttribute("data-era-year") || "";
      if (liveTitle) liveTitle.textContent = era.getAttribute("data-era-title") || "";
      if (liveDesc) liveDesc.textContent = era.getAttribute("data-era-body") || "";

      if (scrollIntoView) {
        var card = era.querySelector("[data-timeline-card]");
        if (card) {
          card.scrollIntoView({
            behavior: reduceMotion ? "auto" : "smooth",
            inline: "center",
            block: "nearest",
          });
        }
      }
    }

    function scrollProgress() {
      var max = viewport.scrollWidth - viewport.clientWidth;
      return max > 0 ? viewport.scrollLeft / max : 1;
    }

    function updateRunner() {
      var p = scrollProgress();
      root.style.setProperty("--scroll-p", String(p));
      if (runner && stage) {
        var track = root.querySelector(".dash-strategic-timeline__track");
        if (track) {
          var trackRect = track.getBoundingClientRect();
          var stageRect = stage.getBoundingClientRect();
          var left = trackRect.left - stageRect.left + p * trackRect.width;
          runner.style.left = left + "px";
        }
      }
      if (waveFill && waveLength) {
        waveFill.style.strokeDashoffset = String(waveLength * (1 - p));
      }
    }

    function nearestEraIndex() {
      var vpCenter = viewport.scrollLeft + viewport.clientWidth * 0.5;
      var best = 0;
      var bestDist = Infinity;
      eras.forEach(function (era, i) {
        var center = era.offsetLeft + era.offsetWidth * 0.5;
        var dist = Math.abs(center - vpCenter);
        if (dist < bestDist) {
          bestDist = dist;
          best = i;
        }
      });
      return best;
    }

    var scrollRaf = 0;
    viewport.addEventListener(
      "scroll",
      function () {
        if (scrollRaf) return;
        scrollRaf = window.requestAnimationFrame(function () {
          scrollRaf = 0;
          updateRunner();
          setActive(nearestEraIndex(), false);
        });
      },
      { passive: true }
    );

    viewport.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      var idx = nearestEraIndex();
      if (e.key === "ArrowLeft") idx = Math.max(0, idx - 1);
      else idx = Math.min(eras.length - 1, idx + 1);
      setActive(idx, true);
    });

    navBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var idx = Number(btn.getAttribute("data-timeline-jump"));
        setActive(idx, true);
        viewport.focus({ preventScroll: true });
      });
    });

    eras.forEach(function (era, i) {
      var card = era.querySelector("[data-timeline-card]");
      if (!card) return;
      card.addEventListener("click", function () {
        setActive(i, false);
      });
    });

    updateRunner();
    setActive(0, false);

    window.addEventListener(
      "resize",
      function () {
        updateRunner();
      },
      { passive: true }
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
