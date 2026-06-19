/**
 * Site-wide motion (portal, public, reference) — Flaire-style scroll reveals, hovers, parallax.
 * Skips layout-landing (landing-motion.bundle.js) and journey timeline pages.
 * Output: static/js/site-motion.bundle.js — `npm run build:site-motion`
 */
import { animate, inView, stagger, cubicBezier } from "motion";

const easePro = cubicBezier(0.33, 1, 0.68, 1);
const easeOut = cubicBezier(0.25, 0.46, 0.45, 0.94);
const supportsHover =
  typeof window !== "undefined" &&
  window.matchMedia("(hover: hover) and (pointer: fine)").matches;
const PROFILE_MAP = {
  "admin-ultra": {
    scale: 0.72,
    parallax: 0.035,
    cardHoverScale: 1.002,
    cardHoverY: -1,
    buttonHoverScale: 1.008,
    buttonHoverY: -0.5,
    navHoverScale: 1.003,
  },
  "dashboard-balanced": {
    scale: 0.86,
    parallax: 0.05,
    cardHoverScale: 1.003,
    cardHoverY: -1.4,
    buttonHoverScale: 1.01,
    buttonHoverY: -0.8,
    navHoverScale: 1.004,
  },
  "portal-soft": {
    scale: 0.8,
    parallax: 0.045,
    cardHoverScale: 1.003,
    cardHoverY: -1.2,
    buttonHoverScale: 1.009,
    buttonHoverY: -0.75,
    navHoverScale: 1.004,
  },
  "journey-soft": {
    scale: 0.78,
    parallax: 0.04,
    cardHoverScale: 1.002,
    cardHoverY: -1.1,
    buttonHoverScale: 1.009,
    buttonHoverY: -0.7,
    navHoverScale: 1.004,
  },
  "reference-medium": {
    scale: 0.92,
    parallax: 0.062,
    cardHoverScale: 1.004,
    cardHoverY: -1.8,
    buttonHoverScale: 1.011,
    buttonHoverY: -1,
    navHoverScale: 1.005,
  },
  "public-cinematic": {
    scale: 1,
    parallax: 0.08,
    cardHoverScale: 1.005,
    cardHoverY: -2,
    buttonHoverScale: 1.014,
    buttonHoverY: -1.2,
    navHoverScale: 1.006,
  },
};

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function isLanding() {
  return document.body && document.body.classList.contains("layout-landing");
}

function isJourneyPage() {
  return (
    document.documentElement.classList.contains("has-journey-motion") ||
    !!document.querySelector("[data-journey-milestone]")
  );
}

function failSafeReveal() {
  document.documentElement.classList.remove("site-motion-prep");
}

function getMotionProfile() {
  const body = document.body;
  if (body && body.dataset.motionProfile && PROFILE_MAP[body.dataset.motionProfile]) {
    return { ...PROFILE_MAP[body.dataset.motionProfile] };
  }

  if (!body) {
    return { ...PROFILE_MAP["public-cinematic"] };
  }

  if (body.classList.contains("layout-portal")) {
    return { ...PROFILE_MAP["portal-soft"] };
  }

  if (body.classList.contains("layout-reference")) {
    return { ...PROFILE_MAP["reference-medium"] };
  }

  return { ...PROFILE_MAP["public-cinematic"] };
}

function isDomainPage() {
  return !!document.querySelector(".domain-knowledge-page");
}

function shouldSkip(el) {
  if (!el || !el.closest) return true;
  if (el.closest(".domain-knowledge-page, [data-aos], [data-motion-skip], .flash")) return true;
  if (el.closest("#dash-timeline-motion, .dashboard-split-reveal-wrap, .dashboard-project-grid, .dashboard-feed-section")) {
    return true;
  }
  if (el.closest("[data-journey-milestone], [data-journey-connector], .landing-hero, [data-landing-motion]")) {
    return true;
  }
  return false;
}

function bindHoverLift(selector, opts = {}) {
  if (!supportsHover) return;
  const scale = opts.scale ?? 1.02;
  const y = opts.y ?? -2;
  const durationIn = opts.durationIn ?? 0.2;
  const durationOut = opts.durationOut ?? 0.26;

  document.querySelectorAll(selector).forEach((el) => {
    if (shouldSkip(el)) return;
    el.addEventListener("pointerenter", () => {
      animate(el, { scale, y }, { duration: durationIn, ease: easePro });
    });
    el.addEventListener("pointerleave", () => {
      animate(el, { scale: 1, y: 0 }, { duration: durationOut, ease: easeOut });
    });
  });
}

function splitHeadingWords(el) {
  if (el.dataset.motionSplit === "1") return el.querySelectorAll(".motion-word");
  const text = (el.textContent || "").trim();
  if (!text) return [];
  const words = text.split(/\s+/).filter(Boolean);
  el.setAttribute("aria-label", text);
  el.innerHTML = words
    .map((w) => `<span class="motion-word" aria-hidden="true">${w}</span>`)
    .join('<span class="motion-word-gap" aria-hidden="true"> </span>');
  el.dataset.motionSplit = "1";
  return el.querySelectorAll(".motion-word");
}

function initTextReveals(profile) {
  const headings = document.querySelectorAll(
    "#main h1.page-title, #main .page-head h1, #main > h1:first-of-type, #main [data-text-reveal]"
  );

  headings.forEach((el) => {
    if (shouldSkip(el)) return;
    const words = splitHeadingWords(el);
    if (!words.length) return;

    inView(
      el,
      () => {
        animate(
          words,
          { opacity: [0, 1], y: [18 * profile.scale, 0] },
          { duration: 0.48 + 0.06 * profile.scale, delay: stagger(0.04), ease: easePro }
        );
      },
      { amount: 0.35, margin: "0px 0px -10% 0px" }
    );
  });

  document.querySelectorAll("#main h2, #main .page-lede").forEach((el) => {
    if (shouldSkip(el) || el.closest(".page-head h1")) return;
    inView(
      el,
      () => {
        animate(el, { opacity: [0, 1], y: [14 * profile.scale, 0] }, { duration: 0.46, ease: easePro });
      },
      { amount: 0.2, margin: "0px 0px -8% 0px" }
    );
  });
}

function initScrollReveals(profile) {
  const main = document.getElementById("main");
  if (!main) return;

  const pageHead = main.querySelector(".page-head");
  if (pageHead && !shouldSkip(pageHead)) {
    inView(
      pageHead,
      ({ target }) => {
        animate(target, { opacity: [0, 1], y: [12 * profile.scale, 0] }, { duration: 0.48, ease: easePro });
      },
      { amount: 0.12 }
    );
  }

  main.querySelectorAll(".card-grid").forEach((grid) => {
    if (shouldSkip(grid)) return;
    const cards = [...grid.querySelectorAll(":scope > .card, :scope > article.card")].filter((c) => !shouldSkip(c));
    if (!cards.length) return;

    inView(
      grid,
      () => {
        animate(
          cards,
          { opacity: [0, 1], y: [18 * profile.scale, 0] },
          { duration: 0.44 + 0.05 * profile.scale, delay: stagger(0.05), ease: easePro }
        );
      },
      { amount: 0.12, margin: "0px 0px -6% 0px" }
    );
  });

  const standaloneCards = main.querySelectorAll(
    ".card:not(.auth-card), section.card, .knowledge-repo-browse-card, .attach-previews-card"
  );

  standaloneCards.forEach((card) => {
    if (shouldSkip(card) || card.closest(".card-grid")) return;
    inView(
      card,
      () => {
        animate(card, { opacity: [0, 1], y: [16 * profile.scale, 0] }, { duration: 0.46, ease: easePro });
      },
      { amount: 0.14, margin: "0px 0px -8% 0px" }
    );
  });

  main.querySelectorAll("section:not(.card)").forEach((section) => {
    if (shouldSkip(section) || section.querySelector(".card")) return;
    inView(
      section,
      () => {
        animate(section, { opacity: [0, 1], y: [14 * profile.scale, 0] }, { duration: 0.5, ease: easePro });
      },
      { amount: 0.1, margin: "0px 0px -6% 0px" }
    );
  });
}

function initParallax(profile) {
  const gradient = document.querySelector(".ambient-backdrop__gradient");
  const grid = document.querySelector(".ambient-backdrop__grid");
  if (!gradient && !grid) return;

  let ticking = false;
  function update() {
    const y = window.scrollY * profile.parallax;
    if (gradient) gradient.style.transform = `translate3d(0, ${y}px, 0)`;
    if (grid) grid.style.transform = `translate3d(0, ${y * 0.55}px, 0)`;
    ticking = false;
  }

  window.addEventListener(
    "scroll",
    () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(update);
      }
    },
    { passive: true }
  );
  update();
}

function initPageEnter(profile) {
  const main = document.getElementById("main");
  if (!main) {
    failSafeReveal();
    return;
  }

  animate(main, { opacity: [0, 1], y: [8 * profile.scale, 0] }, { duration: 0.36 + 0.05 * profile.scale, ease: easePro });
  window.setTimeout(failSafeReveal, 480);
  window.setTimeout(failSafeReveal, 3200);
}

function init() {
  if (reducedMotion() || isLanding() || isJourneyPage() || isDomainPage()) {
    failSafeReveal();
    return;
  }

  const profile = getMotionProfile();
  initPageEnter(profile);
  initScrollReveals(profile);
  initTextReveals(profile);
  initParallax(profile);

  bindHoverLift(".btn", {
    scale: profile.buttonHoverScale,
    y: profile.buttonHoverY,
    durationIn: 0.18,
    durationOut: 0.24,
  });
  bindHoverLift(".card:not(.landing-role-card):not(.dashboard-timeline-card)", {
    scale: profile.cardHoverScale,
    y: profile.cardHoverY,
    durationIn: 0.22,
    durationOut: 0.28,
  });
  bindHoverLift(".nav-link, .enterprise-nav-primary__link", {
    scale: profile.navHoverScale,
    y: 0,
    durationIn: 0.16,
    durationOut: 0.22,
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
