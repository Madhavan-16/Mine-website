(function () {

  "use strict";



  var header = document.getElementById("site-header");

  var burger = document.querySelector("[data-nav-burger]");

  var sidebar = document.getElementById("portal-sidebar");

  var backdrop = document.getElementById("nav-drawer-backdrop");



  function setScrolled() {

    if (!header) return;

    var y = window.scrollY || document.documentElement.scrollTop;

    header.classList.toggle("is-scrolled", y > 10);

  }



  /** Match .main / sidebar / drawer top to the real fixed enterprise header height (often two rows). */
  /** Prefer the collapsed height so hover/pin expand never leaves a gap when the bar closes. */
  var collapsedPortalOffsetPx = null;

  function isDomainKnowledgePage() {
    return !!document.querySelector(".domain-knowledge-page");
  }

  function portalNavIsExpanded(reveal) {
    /* Outside Domain Knowledge the bar stays visible — always treat as expanded. */
    if (!isDomainKnowledgePage()) return true;
    if (!reveal) return false;
    return (
      reveal.classList.contains("is-pinned") ||
      reveal.matches(":hover") ||
      reveal.matches(":focus-within")
    );
  }

  function syncPortalHeaderOffset() {
    if (!header || !header.classList.contains("header-shell--enterprise")) return;

    var reveal = header.querySelector(".portal-nav-reveal");
    var domainPage = isDomainKnowledgePage();
    var expanded = portalNavIsExpanded(reveal);

    /* Static portal nav: always use full measured header height. */
    if (!domainPage) {
      var fullH = header.getBoundingClientRect().height;
      if (!fullH) return;
      document.documentElement.style.setProperty(
        "--portal-header-offset",
        Math.ceil(fullH + 4) + "px"
      );
      return;
    }

    /* Domain Knowledge hover-reveal: keep collapsed offset while expanded so content does not jump. */
    if (expanded && collapsedPortalOffsetPx != null) {
      document.documentElement.style.setProperty(
        "--portal-header-offset",
        collapsedPortalOffsetPx + "px"
      );
      return;
    }

    var h = header.getBoundingClientRect().height;
    if (!h) return;

    /* Keep a small buffer so flashes / page titles never sit under the bar. */
    var px = Math.ceil(h + 4);
    if (!expanded) {
      collapsedPortalOffsetPx = px;
    }
    document.documentElement.style.setProperty("--portal-header-offset", px + "px");
  }

  function schedulePortalHeaderOffsetSync() {
    window.requestAnimationFrame(function () {
      syncPortalHeaderOffset();
      window.setTimeout(syncPortalHeaderOffset, 320);
    });
  }

  var scrollTick = false;

  window.addEventListener(

    "scroll",

    function () {

      if (!scrollTick) {

        window.requestAnimationFrame(function () {

          setScrolled();

          scrollTick = false;

        });

        scrollTick = true;

      }

    },

    { passive: true }

  );

  setScrolled();



  if (header && header.classList.contains("header-shell--enterprise")) {

    syncPortalHeaderOffset();

    if (typeof ResizeObserver !== "undefined") {

      new ResizeObserver(syncPortalHeaderOffset).observe(header);

    } else {

      window.addEventListener("resize", syncPortalHeaderOffset);

    }

    window.addEventListener("load", syncPortalHeaderOffset);

    var revealEl = header.querySelector(".portal-nav-reveal");
    var barEl = document.getElementById("portal-nav-bar");
    if (revealEl) {
      revealEl.addEventListener("mouseleave", schedulePortalHeaderOffsetSync);
      revealEl.addEventListener("focusout", function () {
        window.setTimeout(schedulePortalHeaderOffsetSync, 0);
      });
    }
    if (barEl) {
      barEl.addEventListener("transitionend", function (e) {
        if (e.target !== barEl) return;
        if (e.propertyName !== "max-height" && e.propertyName !== "opacity") return;
        syncPortalHeaderOffset();
      });
    }

  }



  initPortalNavDropdowns();
  initTopbarDropdowns();



  function initTopbarDropdowns() {

    var dropdowns = Array.prototype.slice.call(document.querySelectorAll("[data-dropdown]"));

    if (!dropdowns.length) return;



    function closeAll(except) {

      dropdowns.forEach(function (dd) {

        if (dd !== except) {

          dd.classList.remove("is-open");

          var trigger = dd.querySelector("[data-dropdown-trigger]");

          if (trigger) trigger.setAttribute("aria-expanded", "false");

        }

      });

    }



    dropdowns.forEach(function (dd) {

      var trigger = dd.querySelector("[data-dropdown-trigger]");

      if (!trigger) return;



      trigger.addEventListener("click", function (e) {

        e.preventDefault();

        e.stopPropagation();

        var open = dd.classList.contains("is-open");

        closeAll(null);

        if (!open) {

          dd.classList.add("is-open");

          trigger.setAttribute("aria-expanded", "true");

        }

      });



      dd.addEventListener("click", function (e) {

        var link = e.target && e.target.closest && e.target.closest("a.dropdown-menu__item");

        if (link) closeAll(null);

      });

    });



    document.addEventListener("click", function (e) {

      var t = e.target;

      if (!t || !t.closest) return;

      if (t.closest("[data-dropdown]")) return;

      closeAll(null);

    });



    document.addEventListener("keydown", function (e) {

      if (e.key === "Escape") closeAll(null);

    });

  }



  function initPortalNavDropdowns() {

    var reveal = document.getElementById("portal-nav-reveal");

    var bar = document.getElementById("portal-nav-bar");

    if (!bar) return;



    var detailsList = Array.prototype.slice.call(bar.querySelectorAll("[data-portal-dropdown]"));



    function syncRevealPinned() {

      if (!reveal) return;

      var pinned = detailsList.some(function (d) { return d.open; });

      reveal.classList.toggle("is-pinned", pinned);
      schedulePortalHeaderOffsetSync();

    }

    /* Honor dropdowns that render already open (e.g. Settings on its own pages). */
    syncRevealPinned();



    function isDesktopNav() {

      return window.matchMedia("(min-width: 1025px)").matches;

    }



    function closeAll(except) {

      detailsList.forEach(function (details) {

        if (details !== except && details.open) {

          details.open = false;

        }

      });

    }



    detailsList.forEach(function (details) {

      details.addEventListener("toggle", function () {

        if (!isDesktopNav()) return;

        if (details.open) {

          closeAll(details);

        }

        syncRevealPinned();

      });

    });



    document.addEventListener("click", function (e) {

      if (!isDesktopNav()) return;

      var t = e.target;

      if (!t || !t.closest) return;

      if (t.closest("[data-portal-dropdown]") || t.closest(".portal-nav-bar__anchor--split > .portal-nav-bar__link")) {

        return;

      }

      closeAll(null);

      syncRevealPinned();

    });



    document.addEventListener("keydown", function (e) {

      if (e.key === "Escape") {

        closeAll(null);

        syncRevealPinned();

      }

    });

  }



  if (!burger || !sidebar) return;



  function isMobileNav() {

    return window.matchMedia("(max-width: 1024px)").matches;

  }



  function focusableIn(el) {

    if (!el) return [];

    return Array.prototype.slice

      .call(

        el.querySelectorAll(

          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

        )

      )

      .filter(function (node) {

        return node.offsetParent !== null || node === document.activeElement;

      });

  }



  function openDrawer() {

    document.body.classList.add("nav-mobile-open");

    burger.setAttribute("aria-expanded", "true");

    burger.setAttribute("aria-label", "Close navigation menu");

    if (backdrop) backdrop.setAttribute("aria-hidden", "false");

    var links = focusableIn(sidebar);

    if (links.length) window.setTimeout(function () { links[0].focus(); }, 50);

  }



  function closeDrawer() {

    document.body.classList.remove("nav-mobile-open");

    burger.setAttribute("aria-expanded", "false");

    burger.setAttribute("aria-label", "Open navigation menu");

    if (backdrop) backdrop.setAttribute("aria-hidden", "true");

    burger.focus();

  }



  function toggleDrawer() {

    if (document.body.classList.contains("nav-mobile-open")) closeDrawer();

    else openDrawer();

  }



  burger.addEventListener("click", function () {

    if (!isMobileNav()) return;

    toggleDrawer();

  });



  if (backdrop) {

    backdrop.addEventListener("click", function () {

      closeDrawer();

    });

  }



  document.addEventListener("keydown", function (e) {

    if (e.key === "Escape" && document.body.classList.contains("nav-mobile-open")) {

      e.preventDefault();

      closeDrawer();

    }

  });



  window.addEventListener("resize", function () {

    if (!isMobileNav() && document.body.classList.contains("nav-mobile-open")) {

      closeDrawer();

    }

  });



  sidebar.addEventListener(

    "click",

    function (e) {

      var t = e.target;

      if (!isMobileNav() || !document.body.classList.contains("nav-mobile-open")) return;

      if (t && t.closest && t.closest("a.nav-link") && !t.closest("summary")) {

        closeDrawer();

      }

    },

    true

  );

})();


