/**
 * Dashboard motion stack:
 * — AOS (global): section-level scroll reveals via data-aos.*
 * — GSAP + ScrollTrigger (this file): horizontal era runway, staged nodes, analytic cards & project tiles.
 *
 * Framer Motion is React-only; GSAP fills the same choreography role here.
 */
(function () {
  var reduceMq = window.matchMedia("(prefers-reduced-motion: reduce)");

  function run() {
    if (reduceMq.matches) return;

    var g = typeof window.gsap !== "undefined" ? window.gsap : null;
    var ST = typeof window.ScrollTrigger !== "undefined" ? window.ScrollTrigger : null;
    if (!g || !ST) return;

    g.registerPlugin(ST);

    var root = document.getElementById("dash-timeline-motion");
    if (root) {
      var glow = root.querySelector(".dash-strategic-timeline__glow");
      var track = root.querySelector(".dash-strategic-timeline__rail-fill");
      var nodes = root.querySelectorAll("[data-timeline-node]");

      if (glow && track && nodes.length) {
        g.set([glow, track], {
          scaleX: 0,
          transformOrigin: "left center",
        });
        g.set(nodes, {
          x: 36,
          willChange: "transform",
        });

        var tl = g.timeline({
          scrollTrigger: {
            trigger: root,
            start: "top 76%",
            end: "bottom 30%",
            once: true,
            toggleActions: "play none none none",
          },
        });

        tl.to(glow, {
          scaleX: 1,
          duration: 1.15,
          ease: "power2.out",
          force3D: true,
        }).to(
          track,
          {
            scaleX: 1,
            duration: 1.05,
            ease: "power2.inOut",
            force3D: true,
          },
          "-=1.02"
        );

        tl.fromTo(
          nodes,
          { x: 40 },
          {
            x: 0,
            duration: 0.7,
            ease: "power2.out",
            stagger: 0.08,
            force3D: true,
          },
          "-=0.78"
        );
      }
    }

    var splitPanels = document.querySelectorAll(".dashboard-split-reveal-wrap .dashboard-panel.card");
    if (splitPanels.length) {
      g.fromTo(
        splitPanels,
        {
          opacity: 0,
          y: 48,
        },
        {
          opacity: 1,
          y: 0,
          duration: 0.82,
          ease: "power2.out",
          stagger: 0.12,
          force3D: true,
          scrollTrigger: {
            trigger: ".dashboard-split-reveal-wrap",
            start: "top 82%",
            once: true,
            toggleActions: "play none none none",
          },
        }
      );
    }

    var projectGrid = document.querySelector(".dashboard-project-grid");
    if (projectGrid && projectGrid.querySelectorAll(".dashboard-project-card").length) {
      g.from(".dashboard-project-grid .dashboard-project-card", {
        opacity: 0,
        y: 52,
        duration: 0.72,
        stagger: 0.06,
        ease: "power2.out",
        force3D: true,
        scrollTrigger: {
          trigger: projectGrid,
          start: "top 88%",
          once: true,
          toggleActions: "play none none none",
        },
      });
    }

    var feedSection = document.querySelector(".dashboard-feed-section");
    if (feedSection) {
      g.fromTo(
        feedSection,
        { opacity: 0, y: 36 },
        {
          opacity: 1,
          y: 0,
          duration: 0.75,
          ease: "power2.out",
          scrollTrigger: {
            trigger: feedSection,
            start: "top 82%",
            once: true,
            toggleActions: "play none none none",
          },
        }
      );
    }

    ST.refresh(true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
