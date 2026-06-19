/**
 * Particle mesh: copper links when nodes are near; subtle drift.
 * prefers-reduced-motion: still draw once, no animation loop.
 */
(function () {
  var canvas = document.getElementById("ambient-canvas");
  if (!canvas) return;

  var reduce =
    typeof window.matchMedia !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var ctx = canvas.getContext("2d");
  if (!ctx) return;

  var w = 0;
  var h = 0;
  var pts = [];
  var linkDist = 128;
  var nDots = reduce ? 36 : 52;
  var rafId = null;

  function seedDots() {
    pts = [];
    var i;
    for (i = 0; i < nDots; i++) {
      pts.push({
        x: Math.random() * Math.max(w, 1),
        y: Math.random() * Math.max(h, 1),
        vx: reduce ? 0 : (Math.random() - 0.5) * 0.15,
        vy: reduce ? 0 : (Math.random() - 0.5) * 0.15,
        r: Math.random() * 1.1 + 0.42,
        g: 0.45 + Math.random() * 0.2,
      });
    }
  }

  function drawConnections() {
    var i;
    var j;
    var dx;
    var dy;
    var d;
    var a;
    for (i = 0; i < pts.length; i++) {
      for (j = i + 1; j < pts.length; j++) {
        dx = pts[i].x - pts[j].x;
        dy = pts[i].y - pts[j].y;
        d = Math.sqrt(dx * dx + dy * dy);
        if (d < linkDist) {
          a = 1 - d / linkDist;
          ctx.beginPath();
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.strokeStyle = "rgba(179, 119, 67, " + (0.07 + a * 0.34) + ")";
          ctx.lineWidth = 0.85;
          ctx.stroke();

          ctx.beginPath();
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.strokeStyle = "rgba(0, 174, 240, " + (a * 0.09) + ")";
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }
  }

  function drawDots() {
    var i;
    for (i = 0; i < pts.length; i++) {
      ctx.beginPath();
      ctx.arc(pts[i].x, pts[i].y, pts[i].r, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(179, 119, 67, " + pts[i].g + ")";
      ctx.fill();
      ctx.beginPath();
      ctx.arc(pts[i].x, pts[i].y, pts[i].r * 0.48, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(0, 174, 240, 0.22)";
      ctx.fill();
    }
  }

  function drawFrame() {
    ctx.clearRect(0, 0, w, h);
    drawConnections();
    drawDots();
  }

  function step() {
    var i;
    for (i = 0; i < pts.length; i++) {
      pts[i].x += pts[i].vx;
      pts[i].y += pts[i].vy;

      if (pts[i].x < 6 || pts[i].x > w - 6) pts[i].vx *= -1;
      if (pts[i].y < 6 || pts[i].y > h - 6) pts[i].vy *= -1;

      pts[i].x = Math.max(6, Math.min(w - 6, pts[i].x));
      pts[i].y = Math.max(6, Math.min(h - 6, pts[i].y));

      pts[i].vx += (Math.random() - 0.5) * 0.0016;
      pts[i].vy += (Math.random() - 0.5) * 0.0016;
      pts[i].vx *= 0.999;
      pts[i].vy *= 0.999;
    }
  }

  function loop() {
    step();
    drawFrame();
    rafId = window.requestAnimationFrame(loop);
  }

  function mount() {
    if (rafId !== null) {
      window.cancelAnimationFrame(rafId);
      rafId = null;
    }

    w = canvas.clientWidth | 0;
    h = canvas.clientHeight | 0;
    if (w < 12 || h < 12) return;

    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = (w * dpr) | 0;
    canvas.height = (h * dpr) | 0;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    seedDots();
    drawFrame();

    if (!reduce) rafId = window.requestAnimationFrame(loop);
  }

  window.addEventListener("resize", mount, { passive: true });
  mount();
})();
