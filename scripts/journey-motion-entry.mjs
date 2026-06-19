/**
 * Journey page: Motion (vanilla build; Framer Motion compatible engine) —
 * scroll reveals, active milestone (copper), rail progress, and connector glow.
 * Output: `static/js/journey-motion.bundle.js` via `npm run build:journey-motion`.
 */
import { animate, inView, stagger, cubicBezier } from "motion";

const easePro = cubicBezier(0.33, 1, 0.68, 1);

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function narrowTimeline() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function failSafeReveal() {
  document.documentElement.classList.remove("journey-motion-prep");
}

function setRailProgress(root, milestones, index) {
  const rail = root.querySelector("[data-journey-rail-fill]");
  if (!rail || !milestones.length) return;
  const p = (index + 1) / milestones.length;
  rail.style.setProperty("--journey-progress", String(Math.max(0.08, Math.min(1, p))));
}

function setActive(root, index, milestones, connectors) {
  milestones.forEach((m, i) => {
    const on = i === index;
    m.classList.toggle("is-active", on);
    const btn = m.querySelector(".journey-ht__card");
    if (btn) {
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      if (on) btn.setAttribute("aria-current", "true");
      else btn.removeAttribute("aria-current");
    }
  });
  connectors.forEach((c, i) => {
    const lit = i === index || i + 1 === index;
    c.classList.toggle("is-lit", lit);
  });
  setRailProgress(root, milestones, index);
}

function centerOnMilestone(scrollport, milestone) {
  const m = milestone.querySelector(".journey-ht__card");
  if (!m) return;
  m.scrollIntoView({
    behavior: reducedMotion() ? "auto" : "smooth",
    inline: "center",
    block: "nearest",
  });
}

function spyActiveFromScroll(scrollport, milestones, root, connectors, getIndex, setIndex, stacked) {
  let best = 0;
  let bestDist = Infinity;
  milestones.forEach((m, i) => {
    const r = m.getBoundingClientRect();
    let d;
    if (stacked) {
      const mid = window.innerHeight * 0.42;
      const c = r.top + r.height / 2;
      d = Math.abs(c - mid);
    } else {
      const rootRect = scrollport.getBoundingClientRect();
      const mid = rootRect.left + rootRect.width / 2;
      const c = r.left + r.width / 2;
      d = Math.abs(c - mid);
    }
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  });
  if (best !== getIndex()) {
    setIndex(best);
    setActive(root, best, milestones, connectors);
  }
}

function initTimeline() {
  const root = document.querySelector("[data-journey-timeline]");
  if (!root) return;

  const scrollport = root.querySelector("[data-journey-scroll]");
  const milestones = [...root.querySelectorAll("[data-journey-milestone]")];
  const connectors = [...root.querySelectorAll("[data-journey-connector]")];
  if (!scrollport || !milestones.length) {
    failSafeReveal();
    return;
  }

  let activeIndex = milestones.length - 1;
  let spyLockedUntil = 0;
  const getIndex = () => activeIndex;
  const setIndex = (v) => {
    activeIndex = v;
  };

  setActive(root, activeIndex, milestones, connectors);

  milestones.forEach((m, i) => {
    const btn = m.querySelector(".journey-ht__card");
    if (!btn) return;
    btn.addEventListener("click", () => {
      setIndex(i);
      setActive(root, i, milestones, connectors);
      spyLockedUntil = performance.now() + 720;
      centerOnMilestone(scrollport, m);
    });
  });

  let raf = 0;
  const onScrollOrResize = () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      if (performance.now() < spyLockedUntil) return;
      const stacked = narrowTimeline();
      spyActiveFromScroll(scrollport, milestones, root, connectors, getIndex, setIndex, stacked);
    });
  };
  scrollport.addEventListener("scroll", onScrollOrResize, { passive: true });
  window.addEventListener("scroll", onScrollOrResize, { passive: true });
  window.addEventListener("resize", onScrollOrResize);
  onScrollOrResize();

  root.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const buttons = milestones.map((mm) => mm.querySelector(".journey-ht__card")).filter(Boolean);
    const ix = buttons.indexOf(document.activeElement);
    if (ix < 0) return;
    e.preventDefault();
    const next =
      e.key === "ArrowRight"
        ? Math.min(buttons.length - 1, ix + 1)
        : Math.max(0, ix - 1);
    const target = buttons[next];
    if (target) {
      target.focus();
      spyLockedUntil = performance.now() + 720;
      setIndex(next);
      setActive(root, next, milestones, connectors);
      centerOnMilestone(scrollport, milestones[next]);
    }
  });

  if (reducedMotion()) {
    failSafeReveal();
    return;
  }

  window.setTimeout(failSafeReveal, 3400);

  inView(
    root,
    () => {
      const isNarrow = narrowTimeline();
      Promise.all([
        animate(
          milestones,
          { opacity: [0, 1], y: [22, 0] },
          {
            duration: 0.54,
            delay: stagger(0.065),
            ease: easePro,
          }
        ),
        animate(
          connectors,
          isNarrow ? { opacity: [0, 1] } : { opacity: [0, 1], scaleX: [0.72, 1] },
          {
            duration: 0.5,
            delay: stagger(0.07, { startDelay: 0.1 }),
            ease: easePro,
          }
        ),
      ]).then(failSafeReveal).catch(failSafeReveal);
    },
    { amount: 0.12, margin: "0px 0px -8% 0px" }
  );
}

function init() {
  initTimeline();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
