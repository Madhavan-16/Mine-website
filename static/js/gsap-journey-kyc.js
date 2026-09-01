/**
 * Journey + KYC scroll signature — GSAP ScrollTrigger.
 * Loaded only on journey / KYC pages. Respects prefers-reduced-motion.
 */
(function () {
  var reduce =
    typeof window.matchMedia !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;

  function run() {
    var g = window.gsap;
    var ST = window.ScrollTrigger;
    if (!g || !ST) return;
    g.registerPlugin(ST);

    var journeySections = document.querySelectorAll(".journey-page .journey-digital");
    if (journeySections.length) {
      g.fromTo(
        journeySections,
        { opacity: 0, y: 36 },
        {
          opacity: 1,
          y: 0,
          duration: 0.7,
          ease: "power2.out",
          stagger: 0.12,
          scrollTrigger: {
            trigger: ".journey-page",
            start: "top 78%",
            once: true,
          },
        }
      );
    }

    var spine = document.getElementById("kyc-evolution-timeline");
    if (spine) {
      var fill = spine.querySelector(".kyc-evo-spine__line-fill");
      var glow = spine.querySelector(".kyc-evo-spine__glow");
      var milestones = spine.querySelectorAll(".kyc-evo-spine__milestone");

      if (fill) {
        g.set(fill, { scaleY: 0, transformOrigin: "top center" });
        g.to(fill, {
          scaleY: 1,
          ease: "none",
          scrollTrigger: {
            trigger: spine,
            start: "top 70%",
            end: "bottom 35%",
            scrub: 0.6,
          },
        });
      }

      if (glow) {
        g.fromTo(
          glow,
          { opacity: 0.2 },
          {
            opacity: 0.85,
            ease: "none",
            scrollTrigger: {
              trigger: spine,
              start: "top 70%",
              end: "bottom 35%",
              scrub: true,
            },
          }
        );
      }

      if (milestones.length) {
        g.fromTo(
          milestones,
          { opacity: 0, y: 28 },
          {
            opacity: 1,
            y: 0,
            duration: 0.55,
            ease: "power2.out",
            stagger: 0.1,
            scrollTrigger: {
              trigger: spine,
              start: "top 72%",
              once: true,
            },
          }
        );
      }
    }

    ST.refresh(true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run, { once: true });
  } else {
    run();
  }
})();
