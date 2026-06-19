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

  function syncPortalHeaderOffset() {

    if (!header || !header.classList.contains("header-shell--enterprise")) return;

    var h = header.getBoundingClientRect().height;

    if (!h) return;

    document.documentElement.style.setProperty("--portal-header-offset", Math.ceil(h) + "px");

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

  }



  initPortalNavDropdowns();



  function initPortalNavDropdowns() {

    var reveal = document.getElementById("portal-nav-reveal");

    var bar = document.getElementById("portal-nav-bar");

    if (!bar) return;



    var detailsList = Array.prototype.slice.call(bar.querySelectorAll("[data-portal-dropdown]"));



    function syncRevealPinned() {

      if (!reveal) return;

      var pinned = detailsList.some(function (d) { return d.open; });

      reveal.classList.toggle("is-pinned", pinned);

    }



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


