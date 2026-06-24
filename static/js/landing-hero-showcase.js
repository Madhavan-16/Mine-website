/**
 * Landing hero media rotator + in-page YouTube lightbox (same footprint as showcase stage).
 */
(function () {
  var root = document.querySelector("[data-hero-showcase]");
  if (!root) return;

  var slides = Array.from(root.querySelectorAll("[data-hero-slide]"));
  if (!slides.length) return;

  var captionEl = root.querySelector("[data-hero-caption]");
  var dots = Array.from(root.querySelectorAll("[data-hero-dot]"));
  var prevBtn = root.querySelector("[data-hero-prev]");
  var nextBtn = root.querySelector("[data-hero-next]");
  var playBtns = root.querySelectorAll("[data-hero-play]");
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var intervalMs = reducedMotion || slides.length <= 1 ? 0 : 12000;

  var index = slides.findIndex(function (s) {
    return s.classList.contains("is-active");
  });
  if (index < 0) index = 0;

  var timer = null;
  var paused = false;
  var videoModalOpen = false;

  /* ——— Carousel ——— */
  function setSlide(nextIndex) {
    index = (nextIndex + slides.length) % slides.length;
    slides.forEach(function (slide, i) {
      slide.classList.toggle("is-active", i === index);
    });
    dots.forEach(function (dot, i) {
      dot.classList.toggle("is-active", i === index);
    });
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

  if (prevBtn) {
    prevBtn.addEventListener("click", function () {
      prev();
      startTimer();
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", function () {
      next();
      startTimer();
    });
  }

  dots.forEach(function (dot) {
    dot.addEventListener("click", function () {
      var i = parseInt(dot.getAttribute("data-hero-dot"), 10);
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
    if (!videoModalOpen) {
      paused = false;
      startTimer();
    }
  });

  root.addEventListener("focusin", function () {
    paused = true;
    stopTimer();
  });

  root.addEventListener("focusout", function (e) {
    if (!root.contains(e.relatedTarget) && !videoModalOpen) {
      paused = false;
      startTimer();
    }
  });

  setSlide(index);
  startTimer();

  /* ——— Video lightbox ——— */
  var modal = document.getElementById("landing-hero-video-modal");
  if (!modal) return;

  var dialog = modal.querySelector(".landing-hero-video-modal__dialog");
  var iframe = modal.querySelector("[data-hero-video-iframe]");
  var titleEl = document.getElementById("landing-hero-video-title");
  var externalLink = modal.querySelector("[data-hero-video-external]");
  var closers = modal.querySelectorAll("[data-hero-video-close]");
  var lastFocus = null;

  function embedUrl(videoId) {
    return (
      "https://www.youtube-nocookie.com/embed/" +
      encodeURIComponent(videoId) +
      "?autoplay=1&rel=0&modestbranding=1&playsinline=1"
    );
  }

  function openVideo(btn) {
    var slide = btn.closest("[data-hero-slide]");
    if (!slide || !iframe) return;

    var videoId = slide.getAttribute("data-youtube-id") || btn.getAttribute("data-youtube-id");
    var caption = slide.getAttribute("data-caption") || "Freeport mining video";
    var watchUrl = btn.getAttribute("data-watch-url") || "https://www.youtube.com/watch?v=" + videoId;

    if (!videoId) return;

    lastFocus = document.activeElement;
    videoModalOpen = true;
    paused = true;
    stopTimer();

    if (titleEl) titleEl.textContent = caption;
    iframe.setAttribute("title", caption);
    iframe.src = embedUrl(videoId);

    if (externalLink) {
      externalLink.href = watchUrl;
    }

    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("is-open");
    document.body.classList.add("landing-hero-video-open");

    window.requestAnimationFrame(function () {
      if (dialog) dialog.focus();
    });
  }

  function closeVideo() {
    if (!modal.classList.contains("is-open")) return;

    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("landing-hero-video-open");
    videoModalOpen = false;

    if (iframe) {
      iframe.src = "";
      iframe.removeAttribute("title");
    }

    window.setTimeout(function () {
      modal.hidden = true;
      if (lastFocus && typeof lastFocus.focus === "function") {
        lastFocus.focus();
      }
      paused = false;
      startTimer();
    }, 220);
  }

  playBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      openVideo(btn);
    });
  });

  closers.forEach(function (el) {
    el.addEventListener("click", closeVideo);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && modal.classList.contains("is-open")) {
      e.preventDefault();
      closeVideo();
    }
  });
})();
