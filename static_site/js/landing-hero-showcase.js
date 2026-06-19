/**
 * Landing hero media rotator — thumbnails link to YouTube on click.
 */
(function () {
  const root = document.querySelector("[data-hero-showcase]");
  if (!root) return;

  const slides = Array.from(root.querySelectorAll("[data-hero-slide]"));
  if (!slides.length) return;

  const captionEl = root.querySelector("[data-hero-caption]");
  const dots = Array.from(root.querySelectorAll("[data-hero-dot]"));
  const prevBtn = root.querySelector("[data-hero-prev]");
  const nextBtn = root.querySelector("[data-hero-next]");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const intervalMs = reducedMotion || slides.length <= 1 ? 0 : 12000;

  let index = slides.findIndex((s) => s.classList.contains("is-active"));
  if (index < 0) index = 0;

  let timer = null;
  let paused = false;

  function setSlide(nextIndex) {
    index = (nextIndex + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      slide.classList.toggle("is-active", i === index);
    });
    dots.forEach((dot, i) => dot.classList.toggle("is-active", i === index));
    if (captionEl) {
      captionEl.textContent = slides[index].getAttribute("data-caption") || "";
    }
  }

  function next() {
    setSlide(index + 1);
  }

  function prev() {
    setSlide(index - 1);
  }

  function startTimer() {
    if (!intervalMs || paused) return;
    stopTimer();
    timer = window.setInterval(next, intervalMs);
  }

  function stopTimer() {
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  if (prevBtn) prevBtn.addEventListener("click", function () { prev(); startTimer(); });
  if (nextBtn) nextBtn.addEventListener("click", function () { next(); startTimer(); });

  dots.forEach(function (dot) {
    dot.addEventListener("click", function () {
      const i = parseInt(dot.getAttribute("data-hero-dot"), 10);
      if (!Number.isNaN(i)) {
        setSlide(i);
        startTimer();
      }
    });
  });

  root.addEventListener("mouseenter", function () {
    paused = true;
    stopTimer();
  });

  root.addEventListener("mouseleave", function () {
    paused = false;
    startTimer();
  });

  root.addEventListener("focusin", function () {
    paused = true;
    stopTimer();
  });

  root.addEventListener("focusout", function (e) {
    if (!root.contains(e.relatedTarget)) {
      paused = false;
      startTimer();
    }
  });

  setSlide(index);
  startTimer();
})();
