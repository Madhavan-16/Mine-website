(function () {
  function updateCounts(tableId) {
    var table = document.querySelector('[data-table-id="' + tableId + '"]');
    var shell = document.querySelector('[data-table-shell="' + tableId + '"]');
    if (!table) return;

    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));
    var visibleCount = rows.filter(function (row) {
      return !row.hidden;
    }).length;
    var selectedCount = rows.filter(function (row) {
      return row.classList.contains("is-selected") && !row.hidden;
    }).length;

    var countNode = document.querySelector('[data-table-count="' + tableId + '"]');
    var selectionNode = document.querySelector('[data-table-selection="' + tableId + '"]');

    if (countNode) {
      countNode.textContent = visibleCount + (visibleCount === 1 ? " result" : " results");
    }
    if (selectionNode) {
      selectionNode.textContent = selectedCount + " selected";
    }
    if (shell) {
      shell.classList.toggle("is-empty", visibleCount === 0);
    }
  }

  function applyFilters(tableId) {
    var table = document.querySelector('[data-table-id="' + tableId + '"]');
    var input = document.querySelector('[data-table-search="' + tableId + '"]');
    var filter = document.querySelector('[data-table-filter="' + tableId + '"]');
    if (!table) return;

    var query = input ? input.value.trim().toLowerCase() : "";
    var status = filter ? filter.value : "";
    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));

    rows.forEach(function (row) {
      var hay = row.textContent.toLowerCase();
      var rowStatus = row.getAttribute("data-status") || "";
      var matchQuery = !query || hay.indexOf(query) !== -1;
      var matchStatus = !status || rowStatus === status;
      row.hidden = !(matchQuery && matchStatus);
    });

    updateCounts(tableId);
  }

  function sortTable(tableId, key, th) {
    var table = document.querySelector('[data-table-id="' + tableId + '"]');
    if (!table || !key) return;
    var tbody = table.tBodies[0];
    if (!tbody) return;

    var current = th.getAttribute("aria-sort");
    var next = current === "ascending" ? "descending" : "ascending";
    table.querySelectorAll("th[data-sortable]").forEach(function (node) {
      node.removeAttribute("aria-sort");
    });
    th.setAttribute("aria-sort", next);

    var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
    rows.sort(function (a, b) {
      var av = (a.getAttribute("data-" + key) || a.textContent || "").toLowerCase();
      var bv = (b.getAttribute("data-" + key) || b.textContent || "").toLowerCase();
      if (av < bv) return next === "ascending" ? -1 : 1;
      if (av > bv) return next === "ascending" ? 1 : -1;
      return 0;
    });
    rows.forEach(function (row) {
      tbody.appendChild(row);
    });
  }

  function bindTable(tableId) {
    var table = document.querySelector('[data-table-id="' + tableId + '"]');
    var input = document.querySelector('[data-table-search="' + tableId + '"]');
    var filter = document.querySelector('[data-table-filter="' + tableId + '"]');
    if (!table) return;

    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));

    rows.forEach(function (row) {
      row.addEventListener("click", function (event) {
        if (event.target.closest("a, button, input, select, textarea, label")) return;
        row.classList.toggle("is-selected");
        updateCounts(tableId);
      });

      row.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          row.click();
        }
      });
    });

    if (input) {
      input.addEventListener("input", function () {
        applyFilters(tableId);
      });
    }
    if (filter) {
      filter.addEventListener("change", function () {
        applyFilters(tableId);
      });
    }

    table.querySelectorAll("th[data-sortable]").forEach(function (th) {
      th.addEventListener("click", function () {
        sortTable(tableId, th.getAttribute("data-sort-key"), th);
      });
    });

    updateCounts(tableId);
  }

  function bindAll() {
    document.querySelectorAll("[data-table-id]").forEach(function (table) {
      var id = table.getAttribute("data-table-id");
      if (id) bindTable(id);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindAll, { once: true });
  } else {
    bindAll();
  }

  window.MineTable = { bindTable: bindTable, bindAll: bindAll, updateCounts: updateCounts };
})();
