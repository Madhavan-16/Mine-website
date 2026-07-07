/**
 * Programs & Projects — portfolio Gantt (delivery runway) view.
 */
(function () {
  var root = document.querySelector("[data-projects-portal]");
  if (!root) return;

  function readVizData() {
    var raw = root.getAttribute("data-portfolio-viz");
    if (raw) {
      try {
        return JSON.parse(raw);
      } catch (e) {
        /* fall through */
      }
    }
    var dataEl = document.getElementById("portfolio-viz-data");
    if (!dataEl) return null;
    try {
      return JSON.parse(dataEl.textContent || "{}");
    } catch (err) {
      return null;
    }
  }

  var data = readVizData();
  if (!data || !data.gantt) return;

  var TONE_COLORS = ["#00aef0", "#029fd7", "#b37743"];
  var ganttEl = root.querySelector("[data-projects-gantt]");
  var ganttReady = false;

  function pad2(n) {
    n = String(n);
    return n.length < 2 ? "0" + n : n;
  }

  function shortTitle(title, max) {
    max = max || 28;
    if (!title || title.length <= max) return title;
    return title.slice(0, max - 1).trim() + "\u2026";
  }

  function parseIso(iso) {
    if (!iso) return null;
    var parts = iso.split("-");
    return new Date(+parts[0], +parts[1] - 1, +parts[2]);
  }

  function monthLabel(d) {
    return d.toLocaleString("en-GB", { month: "short", year: "numeric" });
  }

  function yearLabel(d) {
    return String(d.getFullYear());
  }

  function bindOpenProject(el, id) {
    el.addEventListener("click", function () {
      if (window.MiNeProjects && window.MiNeProjects.openProjectCard) {
        window.MiNeProjects.openProjectCard(id);
      }
    });
  }

  function renderGantt(container, gantt) {
    if (!container || !gantt || !gantt.rows || !gantt.rows.length) {
      container.innerHTML = '<p class="projects-gantt__empty">No dated projects to chart yet.</p>';
      return;
    }

    var start = parseIso(gantt.rangeStart);
    var end = parseIso(gantt.rangeEnd);
    if (!start || !end) {
      container.innerHTML = '<p class="projects-gantt__empty">No dated projects to chart yet.</p>';
      return;
    }

    var totalMs = end.getTime() - start.getTime() || 1;
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    var todayIso = today.toISOString().slice(0, 10);
    var todayPct = ((today.getTime() - start.getTime()) / totalMs) * 100;
    var showToday = todayPct >= 0 && todayPct <= 100;

    var ticks = [];
    var tick = new Date(start.getFullYear(), 0, 1);
    while (tick.getTime() <= end.getTime()) {
      ticks.push(new Date(tick.getTime()));
      tick = new Date(tick.getFullYear() + 1, 0, 1);
    }

    var html = '<div class="projects-gantt__chart">';

    html += '<div class="projects-gantt__axis">';
    html += '<div class="projects-gantt__axis-label"><span>Engagement</span></div>';
    html += '<div class="projects-gantt__axis-track">';
    ticks.forEach(function (t) {
      var pct = ((t.getTime() - start.getTime()) / totalMs) * 100;
      html +=
        '<span class="projects-gantt__year" style="left:' +
        pct.toFixed(2) +
        '%">' +
        yearLabel(t) +
        "</span>";
    });
    html += "</div></div>";

    html += '<div class="projects-gantt__quarters">';
    html += '<div class="projects-gantt__axis-label" aria-hidden="true"></div>';
    html += '<div class="projects-gantt__axis-track projects-gantt__axis-track--quarters">';
    var quarter = new Date(start.getFullYear(), Math.floor(start.getMonth() / 3) * 3, 1);
    while (quarter.getTime() <= end.getTime()) {
      var qpct = ((quarter.getTime() - start.getTime()) / totalMs) * 100;
      html +=
        '<span class="projects-gantt__tick" style="left:' +
        qpct.toFixed(2) +
        '%"><span class="projects-gantt__tick-line"></span><span class="projects-gantt__tick-label">' +
        monthLabel(quarter) +
        "</span></span>";
      quarter = new Date(quarter.getFullYear(), quarter.getMonth() + 3, 1);
    }
    html += "</div></div>";

    html += '<div class="projects-gantt__body">';
    if (showToday) {
      html +=
        '<div class="projects-gantt__today-overlay" aria-hidden="true"><div class="projects-gantt__today-overlay-spacer"></div><div class="projects-gantt__today-overlay-track"><span class="projects-gantt__today projects-gantt__today--global" style="left:' +
        todayPct.toFixed(2) +
        '%" title="Today"></span></div></div>';
    }

    gantt.rows.forEach(function (row) {
      var rowStart = parseIso(row.start);
      var rowEnd = parseIso(row.end);
      if (!rowStart || !rowEnd) return;
      var left = ((rowStart.getTime() - start.getTime()) / totalMs) * 100;
      var width = ((rowEnd.getTime() - rowStart.getTime()) / totalMs) * 100;
      width = Math.max(width, 2);
      var color = TONE_COLORS[row.tone % TONE_COLORS.length];
      var isActive = row.start <= todayIso && row.end >= todayIso;
      var barLabel = row.shortRange || row.duration || "";
      var showBarLabel = width >= 14;

      html += '<div class="projects-gantt__row' + (isActive ? " is-active" : "") + '">';
      html +=
        '<button type="button" class="projects-gantt__row-label" data-project-id="' +
        row.id +
        '" title="Open ' +
        row.title.replace(/"/g, "&quot;") +
        '">';
      html += '<span class="projects-gantt__row-index">' + pad2((row.order || 0) + 1) + "</span>";
      html += '<span class="projects-gantt__row-copy">';
      html += '<span class="projects-gantt__row-title">' + shortTitle(row.title, 42) + "</span>";
      html += '<span class="projects-gantt__row-dates">' + (row.shortRange || "") + "</span>";
      html += "</span>";
      if (isActive) {
        html += '<span class="projects-gantt__live">Live</span>';
      }
      html += "</button>";
      html +=
        '<div class="projects-gantt__row-track"><button type="button" class="projects-gantt__bar" data-project-id="' +
        row.id +
        '" style="left:' +
        left.toFixed(2) +
        "%;width:" +
        width.toFixed(2) +
        "%;--bar-color:" +
        color +
        '" title="' +
        (row.duration || row.title).replace(/"/g, "&quot;") +
        '">';
      html += '<span class="projects-gantt__bar-fill"></span>';
      if (showBarLabel && barLabel) {
        html += '<span class="projects-gantt__bar-label">' + barLabel + "</span>";
      }
      html += "</button></div></div>";
    });

    html += "</div></div>";
    container.innerHTML = html;

    container.querySelectorAll("[data-project-id]").forEach(function (btn) {
      bindOpenProject(btn, btn.getAttribute("data-project-id"));
    });
  }

  function refresh() {
    renderGantt(ganttEl, data.gantt);
    ganttReady = true;
  }

  window.MiNeProjectsViz = {
    refresh: refresh,
    ensure: function (viewKey) {
      if (viewKey === "gantt" && !ganttReady) refresh();
    },
  };

  refresh();
})();
