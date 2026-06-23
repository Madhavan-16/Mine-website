/**
 * Homepage (layout-landing only): Motion is the vanilla JS build that shares Framer Motion’s engine.
 * Bundled output: `static/js/landing-motion.bundle.js` — rebuild with `npm run build:landing-motion`.
 */
import { animate, inView, stagger, cubicBezier } from "motion";

const easePro = cubicBezier(0.33, 1, 0.68, 1);
const easeOut = cubicBezier(0.25, 0.46, 0.45, 0.94);
const supportsHover =
  typeof window !== "undefined" &&
  window.matchMedia("(hover: hover) and (pointer: fine)").matches;
const MOTION = {
  sectionDuration: 0.64,
  sectionY: 22,
  cardDuration: 0.5,
  cardY: 20,
  cardStagger: 0.055,
};

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function isLanding() {
  return document.body && document.body.classList.contains("layout-landing");
}

function failSafeReveal() {
  document.documentElement.classList.remove("landing-motion-prep");
}

function bindHoverLift(selector, opts = {}) {
  if (!supportsHover) return;
  const scale = opts.scale ?? 1.012;
  const y = opts.y ?? -3;
  const durationIn = opts.durationIn ?? 0.22;
  const durationOut = opts.durationOut ?? 0.28;

  document.querySelectorAll(selector).forEach((el) => {
    el.addEventListener("pointerenter", () => {
      animate(el, { scale, y }, { duration: durationIn, ease: easePro });
    });
    el.addEventListener("pointerleave", () => {
      animate(el, { scale: 1, y: 0 }, { duration: durationOut, ease: easeOut });
    });
  });
}

function initScrollReveals() {
  inView(
    ".landing-hero[data-landing-motion]",
    ({ target }) => {
      animate(target, { y: [12, 0], opacity: [0.98, 1] }, { duration: 0.58, ease: easePro });
    },
    { amount: 0.01, margin: "0px" }
  );

  inView(
    "section[data-landing-motion]:not(.landing-hero)",
    ({ target }) => {
      /* Stagger groups animate their own children — skip section-level move to avoid double shift / overlap. */
      if (target.querySelector("[data-landing-stagger]")) return;
      animate(
        target,
        { opacity: [0, 1], y: [MOTION.sectionY, 0] },
        { duration: MOTION.sectionDuration, ease: easePro }
      );
    },
    { amount: 0.12, margin: "0px 0px -8% 0px" }
  );
}

function initStaggerGroups() {
  document.querySelectorAll("[data-landing-stagger]").forEach((group) => {
    const items = group.querySelectorAll("[data-landing-item]");
    if (!items.length) return;
    inView(
      group,
      () => {
        animate(
          items,
          { opacity: [0, 1], y: [MOTION.cardY, 0] },
          { duration: MOTION.cardDuration, delay: stagger(MOTION.cardStagger), ease: easePro }
        );
      },
      { amount: 0.16, margin: "0px 0px -8% 0px" }
    );
  });
}

function init() {
  if (!isLanding() || reducedMotion()) {
    failSafeReveal();
    return;
  }

  window.setTimeout(failSafeReveal, 3400);
  initScrollReveals();
  initStaggerGroups();

  /* Hover lift for controls only — tiles/cards/KPIs use landing.css (avoids transform fights / overlap). */
  bindHoverLift(".landing-featured .btn", { scale: 1.01, y: -1.5, durationIn: 0.18, durationOut: 0.24 });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
