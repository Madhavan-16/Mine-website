(function () {
  var LS_KEY = "mine_recent_searches";
  var MAX_RECENT = 6;

  var root = document.querySelector("[data-search-xp-root]");
  if (!root) return;

  var form = root.querySelector("[data-search-xp-form]");
  var qInput = root.querySelector("[data-search-q-input]");
  var modInput = root.querySelector("[data-search-module-input]");
  var ghost = root.querySelector("[data-search-ghost]");
  var ghostText = root.querySelector("[data-search-ghost-text]");
  var recentList = root.querySelector("[data-recent-search-list]");
  var recentEmpty = root.querySelector("[data-recent-empty]");

  if (!form || !qInput || !modInput) return;

  var phrases = [];
  try {
    phrases = JSON.parse(root.getAttribute("data-placeholders") || "[]");
  } catch (e) {
    phrases = [];
  }
  if (!phrases.length) {
    phrases = ["Search the MiNe corpus…"];
  }

  function updateGhostVisibility() {
    if (!ghost) return;
    var show = !(qInput.value && qInput.value.trim()) && document.activeElement !== qInput;
    ghost.classList.toggle("is-hidden", !show);
  }

  function setGhostPhrase(i) {
    if (!ghostText) return;
    ghostText.style.opacity = "0";
    window.setTimeout(function () {
      ghostText.textContent = phrases[i % phrases.length];
      ghostText.style.opacity = "";
    }, 220);
  }

  var rot = 0;
  var prefersReduce = false;
  try {
    prefersReduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (e0) {}
  if (!prefersReduce) {
    window.setInterval(function () {
      if (document.hidden) return;
      if (document.activeElement === qInput) return;
      if (qInput.value && qInput.value.trim()) return;
      rot = (rot + 1) % phrases.length;
      setGhostPhrase(rot);
    }, 3800);
  }

  setGhostPhrase(0);
  updateGhostVisibility();
  qInput.addEventListener("focus", updateGhostVisibility);
  qInput.addEventListener("blur", updateGhostVisibility);
  qInput.addEventListener("input", updateGhostVisibility);

  var pills = root.querySelectorAll("[data-search-module]");
  pills.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var val = btn.getAttribute("data-search-module") || "";
      modInput.value = val;
      pills.forEach(function (b) {
        b.classList.toggle("is-active", b === btn);
      });
    });
  });

  root.querySelectorAll("[data-search-tag]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var term = btn.getAttribute("data-search-tag") || "";
      if (!term) return;
      btn.classList.add("was-used");
      window.setTimeout(function () {
        btn.classList.remove("was-used");
      }, 620);
      var cur = qInput.value || "";
      if (cur.indexOf(term) >= 0) return;
      qInput.value = (cur + " " + term).replace(/^\s+/, "").trim();
      qInput.dispatchEvent(new Event("input", { bubbles: true }));
      qInput.focus();
    });
  });

  function loadRecent() {
    try {
      return JSON.parse(localStorage.getItem(LS_KEY) || "[]") || [];
    } catch (e) {
      return [];
    }
  }

  function saveRecent(q) {
    var trimmed = q.replace(/\s+/g, " ").trim();
    if (!trimmed) return;
    var r = loadRecent().filter(function (x) {
      return x !== trimmed;
    });
    r.unshift(trimmed);
    r = r.slice(0, MAX_RECENT);
    localStorage.setItem(LS_KEY, JSON.stringify(r));
  }

  function renderRecent() {
    if (!recentList) return;
    recentList.innerHTML = "";
    var items = loadRecent();
    items.forEach(function (text) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.className = "enterprise-search-xp__recent-chip";
      b.textContent = text;
      b.addEventListener("click", function () {
        qInput.value = text;
        qInput.dispatchEvent(new Event("input", { bubbles: true }));
        qInput.focus();
      });
      li.appendChild(b);
      recentList.appendChild(li);
    });
    if (recentEmpty) {
      recentEmpty.classList.toggle("is-hidden", items.length > 0);
    }
  }

  renderRecent();

  form.addEventListener("submit", function () {
    saveRecent(qInput.value || "");
    renderRecent();
  });
})();
