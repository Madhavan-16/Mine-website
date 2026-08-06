(function () {
  var root = document.getElementById("mine-chatbot");
  if (!root) return;

  var endpoint = root.getAttribute("data-endpoint");
  var csrf = root.getAttribute("data-csrf") || "";
  var autoOpen = root.getAttribute("data-auto-open") === "1";
  var pageEndpoint = root.getAttribute("data-page-endpoint") || "";
  var openBtn = document.getElementById("mine-chat-open");
  var closeBtn = document.getElementById("mine-chat-close");
  var clearBtn = document.getElementById("mine-chat-clear");
  var expandBtn = document.getElementById("mine-chat-expand");
  var explainBtn = document.getElementById("mine-chat-explain");
  var panel = document.getElementById("mine-chat-panel");
  var form = document.getElementById("mine-chat-form");
  var input = document.getElementById("mine-chat-input");
  var sendBtn = document.getElementById("mine-chat-send");
  var messages = document.getElementById("mine-chat-messages");
  var busy = false;
  var greeted = false;
  var userClosed = false;
  var activeRequest = 0;
  /** @type {{role: string, content: string}[]} */
  var conversation = [];
  var HISTORY_LIMIT = 8;
  var userKey = (root.getAttribute("data-user-key") || "anon").trim() || "anon";
  var STORAGE_PREFIX = "mine-chat-ephemeral:";
  var storageKey = STORAGE_PREFIX + userKey;

  /** Remove any chat keys from disk-like browser storage (never keep cross-user data). */
  function purgeChatStorage(allUsers) {
    function scrub(store) {
      if (!store) return;
      try {
        Object.keys(store).forEach(function (k) {
          if (
            k.indexOf("mine-chat") === 0 ||
            k.indexOf(STORAGE_PREFIX) === 0
          ) {
            if (allUsers || k !== storageKey) {
              store.removeItem(k);
            }
          }
        });
      } catch (e) {
        /* ignore quota / private mode */
      }
    }
    scrub(window.sessionStorage);
    scrub(window.localStorage);
  }

  function isPageReload() {
    try {
      var nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
      if (nav && nav.type === "reload") return true;
    } catch (e) {
      /* ignore */
    }
    try {
      if (performance.navigation && performance.navigation.type === 1) return true;
    } catch (e2) {
      /* ignore */
    }
    return false;
  }

  function wipeConversationMemory() {
    conversation = [];
    try {
      sessionStorage.removeItem(storageKey);
    } catch (e) {
      /* ignore */
    }
  }

  function persistEphemeralHistory() {
    // Tab-scoped only; keyed by logged-in user. Cleared on refresh / logout / tab close.
    try {
      // Drop other accounts' keys in this tab.
      purgeChatStorage(false);
      if (!conversation.length) {
        sessionStorage.removeItem(storageKey);
        return;
      }
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({
          userKey: userKey,
          turns: conversation.slice(-HISTORY_LIMIT),
        })
      );
    } catch (e) {
      /* ignore */
    }
  }

  function loadEphemeralHistory() {
    // Refresh must start clean (no leftover history taking space).
    if (isPageReload()) {
      purgeChatStorage(true);
      conversation = [];
      return false;
    }
    try {
      // Never reuse another account's transcript in this tab.
      purgeChatStorage(false);
      var raw = sessionStorage.getItem(storageKey);
      if (!raw) {
        conversation = [];
        return false;
      }
      var parsed = JSON.parse(raw);
      if (!parsed || parsed.userKey !== userKey || !Array.isArray(parsed.turns)) {
        sessionStorage.removeItem(storageKey);
        conversation = [];
        return false;
      }
      conversation = parsed.turns
        .filter(function (t) {
          return t && (t.role === "user" || t.role === "assistant") && t.content;
        })
        .slice(-HISTORY_LIMIT)
        .map(function (t) {
          return { role: t.role, content: String(t.content).slice(0, 1200) };
        });
      return conversation.length > 0;
    } catch (e) {
      conversation = [];
      return false;
    }
  }

  function resetChatUi() {
    if (messages) messages.innerHTML = "";
    greeted = false;
    wipeConversationMemory();
    purgeChatStorage(true);
    syncClearVisible();
  }

  function syncClearVisible() {
    if (!clearBtn) return;
    clearBtn.hidden = conversation.length === 0;
  }

  function clearChat() {
    if (busy) return;
    resetChatUi();
    appendWelcome();
    greeted = true;
    if (input) input.focus();
    scrollToBottom();
  }

  function removeStaleFollowups() {
    if (!messages) return;
    messages.querySelectorAll(".mine-chat__followups").forEach(function (el) {
      el.remove();
    });
  }

  function isImageSource(s) {
    if (!s || !s.url) return false;
    if (String(s.kind || "").toLowerCase() === "image") return true;
    return /\/(value-chain|lifecycle|digital-enablement|service-map|pa-process|measurement-hierarchy)-image/i.test(
      String(s.url)
    );
  }

  function scoreSource(s) {
    var kind = String(s.kind || "").toLowerCase();
    var mod = String(s.module || "").toLowerCase();
    var title = String(s.title || "").toLowerCase();
    var n = 100;
    if (isImageSource(s)) n = 40;
    else if (kind === "project" || mod === "projects") n = 300;
    else if (mod === "domain_knowledge" && kind === "page") n = 220;
    else if (kind === "page") n = 50;
    if (
      title === "programs & projects" ||
      title === "programs and projects" ||
      title === "projects"
    ) {
      n -= 100;
    }
    return n;
  }

  function dedupeSources(sources) {
    var best = {};
    (sources || []).forEach(function (s) {
      if (!s || !s.url) return;
      var key = String(s.url).toLowerCase();
      var score = scoreSource(s);
      if (!best[key] || score > best[key].score) {
        best[key] = { score: score, item: s };
      }
    });
    return Object.keys(best)
      .map(function (k) {
        return best[k].item;
      })
      .sort(function (a, b) {
        return scoreSource(b) - scoreSource(a);
      });
  }

  function pickPrimarySource(sources) {
    if (!sources || !sources.length) return null;
    var linkOnly = sources.filter(function (s) {
      return !isImageSource(s);
    });
    var ranked = (linkOnly.length ? linkOnly : sources).slice().sort(function (a, b) {
      return scoreSource(b) - scoreSource(a);
    });
    return ranked[0];
  }

  function restoreTranscriptUi() {
    if (!conversation.length || !messages) return;
    messages.innerHTML = "";
    greeted = true;
    conversation.forEach(function (turn) {
      if (turn.role === "user") {
        appendUser(turn.content);
      } else {
        appendBot(turn.content, [], null, { compact: true });
      }
    });
    syncClearVisible();
  }

  var botIcon = root.getAttribute("data-bot-icon") || "";
  var isGuest = root.getAttribute("data-guest") === "1";
  var AVATAR_SVG =
    botIcon
      ? '<img src="' +
        botIcon.replace(/"/g, "&quot;") +
        '" width="22" height="22" alt="" decoding="async" draggable="false" />'
      : "";

  var QUICK_ACTIONS = isGuest
    ? [
        { label: "📚 Knowledge Base", query: "knowledge" },
        { label: "⛏ Domain Knowledge", query: "domain knowledge" },
        { label: "🗺 Journey", query: "journey" },
        { label: "👤 Know your Customer", query: "know your customer" },
        { label: "⛏ Mining Process", query: "what are the major mining operations" },
      ]
    : [
        { label: "📁 Programs & Projects", query: "projects" },
        { label: "📄 Search SOW", query: "SOW documents" },
        { label: "💻 Technologies", query: "technologies used in Freeport engagement" },
        { label: "⛏ Mining Process", query: "what are the major mining operations" },
        { label: "📚 New Employee Guide", query: "onboarding" },
        { label: "🔍 Search Knowledge Base", query: "knowledge" },
      ];

  function formatTime(date) {
    try {
      return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    } catch (e) {
      var h = date.getHours();
      var m = date.getMinutes();
      var ampm = h >= 12 ? "PM" : "AM";
      h = h % 12 || 12;
      return h + ":" + (m < 10 ? "0" : "") + m + " " + ampm;
    }
  }

  function currentPage() {
    return {
      path: window.location.pathname || "",
      title: document.title || "",
      endpoint: pageEndpoint || "",
    };
  }

  function pushHistory(role, content) {
    conversation.push({ role: role, content: String(content || "").slice(0, 1200) });
    if (conversation.length > HISTORY_LIMIT) {
      conversation = conversation.slice(-HISTORY_LIMIT);
    }
    persistEphemeralHistory();
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /**
   * Rich Mermaid subset → SVG flowchart (boxes, diamonds, LR/TD, edge labels).
   * Supports: flowchart LR|TD, A["Label"], A{Decision?}, A -->|Yes| B
   */
  function buildFlowchartHtml(src) {
    var direction = "TD";
    var nodes = {};
    var edges = [];
    var order = [];
    var seen = {};

    function remember(id) {
      if (!seen[id]) {
        seen[id] = true;
        order.push(id);
      }
    }

    String(src || "")
      .split("\n")
      .forEach(function (raw) {
        var line = String(raw || "").trim();
        if (!line) return;
        var dir = /^(?:flowchart|graph)\s+(LR|RL|TD|BT)\b/i.exec(line);
        if (dir) {
          direction = dir[1].toUpperCase();
          if (direction === "BT") direction = "TD";
          if (direction === "RL") direction = "LR";
          return;
        }
        if (/^(?:flowchart|graph)\b/i.test(line)) return;

        var nodeRe = /([A-Za-z][\w]*)\s*(?:\[\s*"?([^\]"]+)"?\s*\]|\{\s*"?([^}"]+)"?\s*\})/g;
        var m;
        while ((m = nodeRe.exec(line))) {
          var id = m[1];
          var box = (m[2] || "").trim();
          var dia = (m[3] || "").trim();
          if (box) {
            nodes[id] = { label: box, shape: "box" };
            remember(id);
          } else if (dia) {
            nodes[id] = { label: dia, shape: "diamond" };
            remember(id);
          }
        }

        var edge =
          /^\s*([A-Za-z][\w]*)\s*-->\s*(?:\|([^|]+)\|\s*)?([A-Za-z][\w]*)/.exec(line) ||
          /^\s*([A-Za-z][\w]*)\s*--\s*([^-\n]+?)\s*-->\s*([A-Za-z][\w]*)/.exec(line);
        if (edge) {
          var a = edge[1];
          var label = (edge[2] || "").trim();
          var b = edge[3];
          remember(a);
          remember(b);
          if (!nodes[a]) nodes[a] = { label: a, shape: "box" };
          if (!nodes[b]) nodes[b] = { label: b, shape: "box" };
          edges.push({ from: a, to: b, label: label });
        }
      });

    if (!order.length) {
      return (
        '<pre class="mine-chat__md-pre"><code>' +
        escapeHtml(src) +
        "</code></pre>"
      );
    }

    // Layered layout from edges (Kahn-ish levels).
    var indeg = {};
    order.forEach(function (id) {
      indeg[id] = 0;
    });
    edges.forEach(function (e) {
      if (indeg[e.to] != null) indeg[e.to] += 1;
    });
    var levelOf = {};
    var queue = order.filter(function (id) {
      return indeg[id] === 0;
    });
    if (!queue.length) queue = order.slice(0, 1);
    queue.forEach(function (id) {
      levelOf[id] = 0;
    });
    var qi = 0;
    while (qi < queue.length) {
      var cur = queue[qi++];
      edges.forEach(function (e) {
        if (e.from !== cur) return;
        var nextLvl = (levelOf[cur] || 0) + 1;
        if (levelOf[e.to] == null || levelOf[e.to] < nextLvl) {
          levelOf[e.to] = nextLvl;
        }
        if (queue.indexOf(e.to) === -1) queue.push(e.to);
      });
    }
    order.forEach(function (id) {
      if (levelOf[id] == null) levelOf[id] = 0;
    });

    var levels = {};
    order.forEach(function (id) {
      var lv = levelOf[id];
      if (!levels[lv]) levels[lv] = [];
      levels[lv].push(id);
    });
    var levelKeys = Object.keys(levels)
      .map(Number)
      .sort(function (a, b) {
        return a - b;
      });

    var isLR = direction === "LR";
    var nodeW = 128;
    var nodeH = 44;
    var gapMain = 72;
    var gapCross = 28;
    var pad = 24;
    var positions = {};
    var maxCross = 1;
    levelKeys.forEach(function (lv) {
      maxCross = Math.max(maxCross, levels[lv].length);
    });

    levelKeys.forEach(function (lv) {
      var row = levels[lv];
      row.forEach(function (id, idx) {
        var cross = idx * (nodeH + gapCross);
        var main = lv * (nodeW + gapMain);
        if (isLR) {
          positions[id] = { x: pad + main, y: pad + cross };
        } else {
          positions[id] = { x: pad + idx * (nodeW + gapCross), y: pad + lv * (nodeH + gapMain) };
        }
      });
    });

    var maxX = 0;
    var maxY = 0;
    order.forEach(function (id) {
      var p = positions[id];
      maxX = Math.max(maxX, p.x + nodeW);
      maxY = Math.max(maxY, p.y + nodeH);
    });
    var width = Math.max(280, maxX + pad);
    var height = Math.max(160, maxY + pad);

    function esc(s) {
      return escapeHtml(String(s || ""));
    }

    var svgParts = [];
    svgParts.push(
      '<svg class="mine-chat__flow-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' +
        width +
        " " +
        height +
        '" width="' +
        width +
        '" height="' +
        height +
        '" role="img" aria-label="AI flowchart">'
    );
    svgParts.push(
      '<defs><marker id="mineFlowArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#0277a8"/></marker></defs>'
    );

    edges.forEach(function (e) {
      var a = positions[e.from];
      var b = positions[e.to];
      if (!a || !b) return;
      var x1 = a.x + nodeW / 2;
      var y1 = a.y + nodeH / 2;
      var x2 = b.x + nodeW / 2;
      var y2 = b.y + nodeH / 2;
      if (isLR) {
        x1 = a.x + nodeW;
        x2 = b.x;
      } else {
        y1 = a.y + nodeH;
        y2 = b.y;
      }
      svgParts.push(
        '<line x1="' +
          x1 +
          '" y1="' +
          y1 +
          '" x2="' +
          x2 +
          '" y2="' +
          y2 +
          '" stroke="#0277a8" stroke-width="2" marker-end="url(#mineFlowArrow)"/>'
      );
      if (e.label) {
        var mx = (x1 + x2) / 2;
        var my = (y1 + y2) / 2 - 6;
        svgParts.push(
          '<rect x="' +
            (mx - 18) +
            '" y="' +
            (my - 10) +
            '" width="36" height="16" rx="4" fill="#eef9fe" stroke="#9ad8ef"/>'
        );
        svgParts.push(
          '<text x="' +
            mx +
            '" y="' +
            (my + 2) +
            '" text-anchor="middle" font-size="10" fill="#0369a1" font-weight="700">' +
            esc(e.label) +
            "</text>"
        );
      }
    });

    order.forEach(function (id, idx) {
      var n = nodes[id];
      var p = positions[id];
      var label = n.label || id;
      if (n.shape === "diamond") {
        var cx = p.x + nodeW / 2;
        var cy = p.y + nodeH / 2;
        var pts =
          cx +
          "," +
          (p.y + 2) +
          " " +
          (p.x + nodeW - 2) +
          "," +
          cy +
          " " +
          cx +
          "," +
          (p.y + nodeH - 2) +
          " " +
          (p.x + 2) +
          "," +
          cy;
        svgParts.push(
          '<polygon points="' +
            pts +
            '" fill="#fff7ed" stroke="#f59e0b" stroke-width="2"/>'
        );
        svgParts.push(
          '<text x="' +
            cx +
            '" y="' +
            (cy + 4) +
            '" text-anchor="middle" font-size="11" font-weight="700" fill="#9a3412">' +
            esc(label.length > 18 ? label.slice(0, 17) + "…" : label) +
            "</text>"
        );
      } else {
        svgParts.push(
          '<rect x="' +
            p.x +
            '" y="' +
            p.y +
            '" width="' +
            nodeW +
            '" height="' +
            nodeH +
            '" rx="10" fill="#ffffff" stroke="#00aef0" stroke-width="2"/>'
        );
        svgParts.push(
          '<circle cx="' +
            (p.x + 16) +
            '" cy="' +
            (p.y + nodeH / 2) +
            '" r="9" fill="url(#none)" style="fill:#00aef0"/>'
        );
        svgParts.push(
          '<text x="' +
            (p.x + 16) +
            '" y="' +
            (p.y + nodeH / 2 + 4) +
            '" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">' +
            (idx + 1) +
            "</text>"
        );
        svgParts.push(
          '<text x="' +
            (p.x + 30) +
            '" y="' +
            (p.y + nodeH / 2 + 4) +
            '" font-size="11" font-weight="650" fill="#0f2740">' +
            esc(label.length > 16 ? label.slice(0, 15) + "…" : label) +
            "</text>"
        );
      }
    });

    svgParts.push("</svg>");

    return (
      '<div class="mine-chat__flow" data-flow-direction="' +
      direction +
      '">' +
      '<div class="mine-chat__flow-toolbar">' +
      '<p class="mine-chat__flow-label">AI flowchart</p>' +
      '<div class="mine-chat__flow-exports">' +
      '<button type="button" class="mine-chat__flow-export" data-flow-export="svg" title="Download SVG">SVG</button>' +
      '<button type="button" class="mine-chat__flow-export" data-flow-export="png" title="Download PNG">PNG</button>' +
      "</div></div>" +
      '<div class="mine-chat__flow-canvas">' +
      svgParts.join("") +
      "</div></div>"
    );
  }

  function wireFlowExports(rootEl) {
    if (!rootEl) return;
    rootEl.querySelectorAll(".mine-chat__flow").forEach(function (flow) {
      if (flow.getAttribute("data-wired") === "1") return;
      flow.setAttribute("data-wired", "1");
      var svg = flow.querySelector("svg");
      if (!svg) return;
      flow.querySelectorAll("[data-flow-export]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var kind = btn.getAttribute("data-flow-export");
          var clone = svg.cloneNode(true);
          if (!clone.getAttribute("xmlns")) {
            clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
          }
          var xml =
            '<?xml version="1.0" encoding="UTF-8"?>\n' +
            new XMLSerializer().serializeToString(clone);
          if (kind === "svg") {
            downloadBlob(new Blob([xml], { type: "image/svg+xml;charset=utf-8" }), "mine-flowchart.svg");
            return;
          }
          var img = new Image();
          var url = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml;charset=utf-8" }));
          img.onload = function () {
            var canvas = document.createElement("canvas");
            var scale = 2;
            canvas.width = Math.max(1, img.width * scale);
            canvas.height = Math.max(1, img.height * scale);
            var ctx = canvas.getContext("2d");
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            URL.revokeObjectURL(url);
            canvas.toBlob(function (blob) {
              if (blob) downloadBlob(blob, "mine-flowchart.png");
            }, "image/png");
          };
          img.onerror = function () {
            URL.revokeObjectURL(url);
          };
          img.src = url;
        });
      });
    });
  }

  function downloadBlob(blob, filename) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename || "download";
    document.body.appendChild(a);
    a.click();
    window.setTimeout(function () {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 500);
  }

  /** Lightweight Markdown → safe HTML for chat bubbles. */
  function renderMarkdown(src) {
    var text = String(src || "").replace(/\r\n/g, "\n");
    var lines = text.split("\n");
    var html = [];
    var inUl = false;
    var inOl = false;
    var olLiOpen = false;
    var inNestedUl = false;
    var inCode = false;
    var codeBuf = [];
    var codeLang = "";
    var inTable = false;
    var tableRows = [];

    function closeNestedUl() {
      if (inNestedUl) {
        html.push("</ul>");
        inNestedUl = false;
      }
    }

    function closeOlItem() {
      closeNestedUl();
      if (olLiOpen) {
        html.push("</li>");
        olLiOpen = false;
      }
    }

    function closeLists() {
      closeOlItem();
      if (inUl) {
        html.push("</ul>");
        inUl = false;
      }
      if (inOl) {
        html.push("</ol>");
        inOl = false;
      }
    }

    function nextContentLine(from) {
      for (var j = from + 1; j < lines.length; j++) {
        if (String(lines[j] || "").trim()) return lines[j];
      }
      return "";
    }

    function isListLine(s) {
      return /^[-*•]\s+/.test(s) || /^\d+[.)]\s+/.test(s);
    }

    function flushCodeBlock() {
      var body = codeBuf.join("\n");
      codeBuf = [];
      var lang = String(codeLang || "").toLowerCase();
      codeLang = "";
      if (lang === "mermaid") {
        html.push(buildFlowchartHtml(body));
        return;
      }
      html.push(
        '<pre class="mine-chat__md-pre"><code>' +
          escapeHtml(body) +
          "</code></pre>"
      );
    }

    function closeTable() {
      if (!inTable) return;
      var out = ['<table class="mine-chat__md-table"><tbody>'];
      tableRows.forEach(function (row, idx) {
        var cells = row.split("|").map(function (c) {
          return c.trim();
        }).filter(function (c, i, arr) {
          return !(i === 0 && c === "") && !(i === arr.length - 1 && c === "");
        });
        if (cells.every(function (c) {
          return /^:?-+:?$/.test(c);
        })) {
          return;
        }
        var tag = idx === 0 ? "th" : "td";
        out.push(
          "<tr>" +
            cells
              .map(function (c) {
                return "<" + tag + ">" + inlineMd(c) + "</" + tag + ">";
              })
              .join("") +
            "</tr>"
        );
      });
      out.push("</tbody></table>");
      html.push(out.join(""));
      inTable = false;
      tableRows = [];
    }

    function inlineMd(s) {
      var t = escapeHtml(s);
      t = t.replace(/`([^`]+)`/g, '<code class="mine-chat__md-code">$1</code>');
      t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      t = t.replace(/(^|[^\*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
      return t;
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];

      var fence = /^```\s*(\w+)?\s*$/.exec(line);
      if (fence) {
        if (inCode) {
          flushCodeBlock();
          inCode = false;
        } else {
          closeLists();
          closeTable();
          inCode = true;
          codeLang = fence[1] || "";
          codeBuf = [];
        }
        continue;
      }
      if (inCode) {
        codeBuf.push(line);
        continue;
      }

      if (/^\|/.test(line) && line.indexOf("|", 1) !== -1) {
        closeLists();
        if (!inTable) inTable = true;
        tableRows.push(line);
        continue;
      } else if (inTable) {
        closeTable();
      }

      var hm = /^(#{1,3})\s+(.+)$/.exec(line);
      if (hm) {
        closeLists();
        var level = hm[1].length;
        html.push("<h" + (level + 1) + ' class="mine-chat__md-h">' + inlineMd(hm[2]) + "</h" + (level + 1) + ">");
        continue;
      }

      // Keep one continuous <ol> across blank lines / bullet details so stages number 1,2,3…
      if (!String(line || "").trim()) {
        if ((inOl || inUl) && isListLine(nextContentLine(i))) {
          continue;
        }
        closeLists();
        html.push('<div class="mine-chat__md-gap"></div>');
        continue;
      }

      var ul = /^[-*•]\s+(.+)$/.exec(line);
      if (ul) {
        if (inOl && olLiOpen) {
          // Nest detail bullets INSIDE the stage <li> so they don't steal 2,3,5…
          if (!inNestedUl) {
            html.push('<ul class="mine-chat__md-list mine-chat__md-list--nested">');
            inNestedUl = true;
          }
          html.push("<li>" + inlineMd(ul[1]) + "</li>");
          continue;
        }
        closeOlItem();
        if (inOl) {
          html.push("</ol>");
          inOl = false;
        }
        if (!inUl) {
          html.push('<ul class="mine-chat__md-list">');
          inUl = true;
        }
        html.push("<li>" + inlineMd(ul[1]) + "</li>");
        continue;
      }

      var ol = /^(\d+)[.)]\s+(.+)$/.exec(line);
      if (ol) {
        if (inUl) {
          html.push("</ul>");
          inUl = false;
        }
        if (!inOl) {
          html.push('<ol class="mine-chat__md-list mine-chat__md-list--ordered">');
          inOl = true;
        } else {
          closeOlItem();
        }
        // Leave <li> open so following `-` bullets nest under this stage.
        html.push("<li>" + inlineMd(ol[2]));
        olLiOpen = true;
        continue;
      }

      closeLists();
      html.push('<p class="mine-chat__md-p">' + inlineMd(line) + "</p>");
    }

    closeLists();
    closeTable();
    if (inCode) {
      flushCodeBlock();
      inCode = false;
    }
    return html.join("");
  }

  function syncSendEnabled() {
    if (!sendBtn || !input) return;
    var empty = !(input.value || "").trim();
    sendBtn.disabled = empty || busy;
  }

  function setExpanded(expanded) {
    if (!root) return;
    var on = !!expanded;
    if (on) {
      root.classList.add("is-expanded");
      document.documentElement.classList.add("mine-chat-expanded");
    } else {
      root.classList.remove("is-expanded");
      document.documentElement.classList.remove("mine-chat-expanded");
    }
    if (expandBtn) {
      expandBtn.setAttribute("aria-pressed", on ? "true" : "false");
      expandBtn.setAttribute(
        "aria-label",
        on ? "Exit full page" : "Expand chat"
      );
      expandBtn.title = on ? "Exit full page" : "Expand to full page";
      var grow = expandBtn.querySelector(".mine-chat__expand-icon--grow");
      var shrink = expandBtn.querySelector(".mine-chat__expand-icon--shrink");
      if (grow) grow.hidden = on;
      if (shrink) shrink.hidden = !on;
    }
    if (on) {
      window.setTimeout(scrollToBottom, 60);
    }
  }

  function setOpen(open) {
    if (!panel) return;
    if (!open) {
      userClosed = true;
      setExpanded(false);
    }
    if (open) {
      panel.hidden = false;
      panel.classList.remove("is-closed");
      root.classList.add("is-open");
      if (openBtn) openBtn.classList.remove("is-idle-pulse");
    } else {
      panel.hidden = true;
      panel.classList.add("is-closed");
      root.classList.remove("is-open");
    }
    if (openBtn) {
      openBtn.setAttribute("aria-expanded", open ? "true" : "false");
    }
    if (open) {
      if (!greeted) {
        greeted = true;
        if (conversation.length) {
          restoreTranscriptUi();
        } else {
          appendWelcome();
        }
      }
      syncClearVisible();
      if (input) input.focus();
      syncSendEnabled();
    }
  }

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function makeBotAvatar() {
    var avatar = document.createElement("div");
    avatar.className = "mine-chat__avatar";
    avatar.innerHTML = AVATAR_SVG;
    return avatar;
  }

  function makeUserAvatar() {
    var avatar = document.createElement("div");
    avatar.className = "mine-chat__avatar mine-chat__avatar--user";
    avatar.textContent = "You";
    avatar.setAttribute("aria-hidden", "true");
    return avatar;
  }

  function makeStack(bubble, when) {
    var stack = document.createElement("div");
    stack.className = "mine-chat__stack";
    stack.appendChild(bubble);
    var time = document.createElement("p");
    time.className = "mine-chat__time";
    time.textContent = formatTime(when || new Date());
    stack.appendChild(time);
    return stack;
  }

  function appendUser(text) {
    var row = document.createElement("div");
    row.className = "mine-chat__row mine-chat__row--user";
    var bubble = document.createElement("div");
    bubble.className = "mine-chat__bubble mine-chat__bubble--user";
    bubble.textContent = text;
    row.appendChild(makeStack(bubble, new Date()));
    row.appendChild(makeUserAvatar());
    messages.appendChild(row);
    scrollToBottom();
  }

  function appendFollowUps(items) {
    if (items === null) return;
    var list = items && items.length ? items : null;
    if (!list || !list.length) return;
    removeStaleFollowups();
    var wrap = document.createElement("div");
    wrap.className = "mine-chat__followups";
    var label = document.createElement("p");
    label.className = "mine-chat__followups-label";
    label.textContent = "You may also ask:";
    wrap.appendChild(label);
    var chips = document.createElement("div");
    chips.className = "mine-chat__chips mine-chat__chips--followups";
    chips.setAttribute("aria-label", "Follow-up suggestions");
    list.forEach(function (action) {
      if (!action || !action.query) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "mine-chat__chip mine-chat__chip--follow";
      btn.textContent = action.label || action.query;
      btn.addEventListener("click", function () {
        if (busy) return;
        sendMessage(action.query);
      });
      chips.appendChild(btn);
    });
    wrap.appendChild(chips);
    messages.appendChild(wrap);
    scrollToBottom();
  }

  var COPY_ICON =
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<rect x="8" y="8" width="12" height="12" rx="2" stroke="currentColor" stroke-width="1.8"/>' +
    '<path d="M6 16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>' +
    "</svg>";
  var COPIED_ICON =
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
    "</svg>";

  function copyPlainText(text, btn) {
    var value = String(text || "");
    function markCopied() {
      if (!btn) return;
      btn.innerHTML = COPIED_ICON;
      btn.classList.add("is-copied");
      btn.setAttribute("aria-label", "Copied");
      window.setTimeout(function () {
        btn.innerHTML = COPY_ICON;
        btn.classList.remove("is-copied");
        btn.setAttribute("aria-label", "Copy reply");
      }, 1400);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(markCopied).catch(function () {
        fallbackCopy(value, markCopied);
      });
      return;
    }
    fallbackCopy(value, markCopied);
  }

  function fallbackCopy(text, onOk) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      if (onOk) onOk();
    } catch (e) {
      /* ignore */
    }
  }

  function shortOpenLabel(title) {
    var t = String(title || "page").trim();
    if (t.length > 42) t = t.slice(0, 41) + "…";
    return "Open " + t;
  }

  function appendBot(text, sources, followUps, opts) {
    opts = opts || {};
    var row = document.createElement("div");
    row.className = "mine-chat__row mine-chat__row--bot";
    row.appendChild(makeBotAvatar());

    var wrap = document.createElement("div");
    wrap.className = "mine-chat__bubble mine-chat__bubble--bot";
    var body = document.createElement("div");
    body.className = "mine-chat__md";
    body.innerHTML = renderMarkdown(text || "");
    wrap.appendChild(body);
    wireFlowExports(wrap);

    var usableSources = dedupeSources(sources);
    var imageSources = usableSources.filter(isImageSource);
    var linkSources = usableSources.filter(function (s) {
      return !isImageSource(s);
    });
    var hasAiFlow = !!(wrap.querySelector && wrap.querySelector(".mine-chat__flow"));
    var shouldExpand = !opts.compact && (imageSources.length > 0 || hasAiFlow);

    if (imageSources.length && !opts.compact) {
      var media = document.createElement("div");
      media.className = "mine-chat__diagrams";
      imageSources.slice(0, 2).forEach(function (s) {
        var fig = document.createElement("figure");
        fig.className = "mine-chat__diagram";
        var img = document.createElement("img");
        img.className = "mine-chat__diagram-img";
        img.src = s.url;
        img.alt = s.title || "Domain Knowledge diagram";
        img.loading = "lazy";
        img.addEventListener("click", function () {
          window.open(s.url, "_blank", "noopener");
        });
        fig.appendChild(img);
        if (s.title) {
          var cap = document.createElement("figcaption");
          cap.className = "mine-chat__diagram-cap";
          cap.textContent = s.title;
          fig.appendChild(cap);
        }
        media.appendChild(fig);
      });
      wrap.appendChild(media);
    }

    if (linkSources.length && !opts.compact) {
      var top = pickPrimarySource(linkSources) || linkSources[0];
      var cta = document.createElement("a");
      cta.className = "mine-chat__open-cta";
      cta.href = top.url;
      cta.textContent = shortOpenLabel(top.title || top.url);
      cta.title = top.title || top.url;
      wrap.appendChild(cta);

      var rest = linkSources.filter(function (s) {
        return String(s.url).toLowerCase() !== String(top.url).toLowerCase();
      });
      if (rest.length) {
        var srcLabel = document.createElement("p");
        srcLabel.className = "mine-chat__sources-label";
        srcLabel.textContent = "More sources";
        wrap.appendChild(srcLabel);
        var ul = document.createElement("ul");
        ul.className = "mine-chat__sources";
        rest.slice(0, 6).forEach(function (s) {
          var li = document.createElement("li");
          var a = document.createElement("a");
          a.className = "mine-chat__source";
          a.href = s.url;
          a.textContent = s.title || s.url;
          if (s.module_label) {
            var meta = document.createElement("span");
            meta.className = "mine-chat__source-meta";
            meta.textContent = s.module_label;
            a.appendChild(meta);
          }
          li.appendChild(a);
          ul.appendChild(li);
        });
        wrap.appendChild(ul);
      }
    }

    if (!opts.compact) {
      var actions = document.createElement("div");
      actions.className = "mine-chat__actions";
      var copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "mine-chat__action";
      copyBtn.innerHTML = COPY_ICON;
      copyBtn.setAttribute("aria-label", "Copy reply");
      copyBtn.title = "Copy";
      copyBtn.addEventListener("click", function () {
        copyPlainText(text || "", copyBtn);
      });
      actions.appendChild(copyBtn);
      wrap.appendChild(actions);
    }

    row.appendChild(makeStack(wrap, new Date()));
    messages.appendChild(row);
    if (!opts.compact) {
      appendFollowUps(followUps);
    }
    syncClearVisible();
    scrollToBottom();
    if (shouldExpand && !root.classList.contains("is-expanded")) {
      setExpanded(true);
    }
  }

  function appendError(text) {
    var row = document.createElement("div");
    row.className = "mine-chat__row mine-chat__row--bot";
    row.appendChild(makeBotAvatar());
    var bubble = document.createElement("div");
    bubble.className = "mine-chat__bubble mine-chat__bubble--error";
    bubble.textContent =
      text ||
      "I couldn't find that information in the MiNe knowledge repository.\n\nWould you like a general explanation instead?";
    row.appendChild(makeStack(bubble, new Date()));
    messages.appendChild(row);
    scrollToBottom();
  }

  function appendWelcome() {
    var wrap = document.createElement("div");
    wrap.className = "mine-chat__welcome";

    var row = document.createElement("div");
    row.className = "mine-chat__row mine-chat__row--bot";
    row.appendChild(makeBotAvatar());

    var card = document.createElement("div");
    card.className = "mine-chat__welcome-card";
    if (isGuest) {
      card.innerHTML =
        '<p class="mine-chat__welcome-title">👋 Welcome to MiNe AI!</p>' +
        '<p class="mine-chat__welcome-lead">As Guest you can explore:</p>' +
        '<ul class="mine-chat__welcome-list">' +
        "<li>📚 Knowledge Articles</li>" +
        "<li>⛏ Domain Knowledge (mining)</li>" +
        "<li>🗺 Freeport–Hexaware Journey</li>" +
        "<li>👤 Know your Customer</li>" +
        "</ul>" +
        '<p class="mine-chat__welcome-foot">Programs &amp; projects, SOW, Onboarding, and other staff sections need a full MiNe account.</p>';
    } else {
      card.innerHTML =
        '<p class="mine-chat__welcome-title">👋 Welcome to MiNe AI!</p>' +
        '<p class="mine-chat__welcome-lead">I can help you explore:</p>' +
        '<ul class="mine-chat__welcome-list">' +
        "<li>📁 Programs &amp; Projects</li>" +
        "<li>📄 SOW Documents</li>" +
        "<li>⛏ Mining Processes</li>" +
        "<li>💻 Technologies</li>" +
        "<li>📚 Knowledge Articles</li>" +
        "</ul>" +
        '<p class="mine-chat__welcome-foot">Ask anything related to Freeport McMoRan, SAP, Projects, Mining Operations, Technologies or Business Processes.</p>';
    }

    row.appendChild(makeStack(card, new Date()));
    wrap.appendChild(row);

    var chips = document.createElement("div");
    chips.className = "mine-chat__chips";
    chips.setAttribute("aria-label", "Quick actions");
    QUICK_ACTIONS.forEach(function (action) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "mine-chat__chip";
      btn.textContent = action.label;
      btn.addEventListener("click", function () {
        if (busy) return;
        sendMessage(action.query);
      });
      chips.appendChild(btn);
    });
    wrap.appendChild(chips);

    messages.appendChild(wrap);
    scrollToBottom();
  }

  function setChipsDisabled(disabled) {
    messages.querySelectorAll(".mine-chat__chip").forEach(function (chip) {
      chip.disabled = !!disabled;
    });
  }

  function beginBotStream() {
    var row = document.createElement("div");
    row.className = "mine-chat__row mine-chat__row--bot";
    row.appendChild(makeBotAvatar());
    var wrap = document.createElement("div");
    wrap.className = "mine-chat__bubble mine-chat__bubble--bot mine-chat__bubble--streaming";
    var body = document.createElement("div");
    body.className = "mine-chat__md";
    body.innerHTML = '<p class="mine-chat__md-p mine-chat__stream-pending">…</p>';
    wrap.appendChild(body);
    row.appendChild(makeStack(wrap, new Date()));
    messages.appendChild(row);
    scrollToBottom();
    return { row: row, wrap: wrap, body: body, text: "" };
  }

  function updateBotStream(streamState, chunk) {
    if (!streamState) return;
    streamState.text += chunk || "";
    // Progressive plain text until done (markdown finalize on complete).
    streamState.body.textContent = streamState.text;
    scrollToBottom();
  }

  function finalizeBotStream(streamState, fullText, sources, followUps) {
    if (!streamState) {
      appendBot(fullText, sources, followUps);
      return;
    }
    var text = fullText || streamState.text || "";
    streamState.wrap.classList.remove("mine-chat__bubble--streaming");
    streamState.body.className = "mine-chat__md";
    streamState.body.innerHTML = renderMarkdown(text);
    wireFlowExports(streamState.wrap);

    var usableSources = dedupeSources(sources);
    var imageSources = usableSources.filter(isImageSource);
    var linkSources = usableSources.filter(function (s) {
      return !isImageSource(s);
    });

    if (imageSources.length) {
      var media = document.createElement("div");
      media.className = "mine-chat__diagrams";
      imageSources.slice(0, 2).forEach(function (s) {
        var fig = document.createElement("figure");
        fig.className = "mine-chat__diagram";
        var img = document.createElement("img");
        img.className = "mine-chat__diagram-img";
        img.src = s.url;
        img.alt = s.title || "Domain Knowledge diagram";
        img.loading = "lazy";
        img.addEventListener("click", function () {
          window.open(s.url, "_blank", "noopener");
        });
        fig.appendChild(img);
        if (s.title) {
          var cap = document.createElement("figcaption");
          cap.className = "mine-chat__diagram-cap";
          cap.textContent = s.title;
          fig.appendChild(cap);
        }
        media.appendChild(fig);
      });
      streamState.wrap.appendChild(media);
    }

    if (linkSources.length) {
      var top = pickPrimarySource(linkSources) || linkSources[0];
      var cta = document.createElement("a");
      cta.className = "mine-chat__open-cta";
      cta.href = top.url;
      cta.textContent = shortOpenLabel(top.title || top.url);
      cta.title = top.title || top.url;
      streamState.wrap.appendChild(cta);
    }

    var actions = document.createElement("div");
    actions.className = "mine-chat__actions";
    var copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "mine-chat__action";
    copyBtn.innerHTML = COPY_ICON;
    copyBtn.setAttribute("aria-label", "Copy reply");
    copyBtn.title = "Copy";
    copyBtn.addEventListener("click", function () {
      copyPlainText(text || "", copyBtn);
    });
    actions.appendChild(copyBtn);
    streamState.wrap.appendChild(actions);

    appendFollowUps(followUps);
    syncClearVisible();
    scrollToBottom();
    var hasAiFlow = !!streamState.wrap.querySelector(".mine-chat__flow");
    if ((imageSources.length || hasAiFlow) && !root.classList.contains("is-expanded")) {
      setExpanded(true);
    }
  }

  function postChatJson(q, historyPayload) {
    return fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
      },
      credentials: "same-origin",
      body: JSON.stringify({
        message: q,
        history: historyPayload,
        page: currentPage(),
      }),
    }).then(function (res2) {
      return res2.text().then(function (raw) {
        var data = {};
        try {
          data = raw ? JSON.parse(raw) : {};
        } catch (e) {
          data = { error: "Unexpected server response. Please try again." };
        }
        return { mode: "json", ok: res2.ok, data: data };
      });
    });
  }

  function sendMessage(q) {
    q = (q || "").trim();
    if (!q || busy || !input) return;

    input.value = "";
    syncSendEnabled();
    removeStaleFollowups();
    appendUser(q);
    busy = true;
    syncSendEnabled();
    setChipsDisabled(true);
    syncClearVisible();

    var historyPayload = conversation.slice(-HISTORY_LIMIT);
    pushHistory("user", q);
    syncClearVisible();

    var requestId = ++activeRequest;
    var streamState = beginBotStream();

    var streamUrl = String(endpoint || "").replace(/\/?$/, "") + "/stream";
    fetch(streamUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
        Accept: "text/event-stream",
      },
      credentials: "same-origin",
      body: JSON.stringify({
        message: q,
        history: historyPayload,
        page: currentPage(),
      }),
    })
      .then(function (res) {
        if (!res.ok || !res.body || !res.body.getReader) {
          return postChatJson(q, historyPayload);
        }
        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
        var finalPayload = null;
        var streamFailed = null;

        function handleEvent(block) {
          var lines = block.split("\n");
          var dataLine = "";
          lines.forEach(function (ln) {
            if (ln.indexOf("data:") === 0) {
              dataLine += ln.slice(5).trim();
            }
          });
          if (!dataLine) return;
          var evt;
          try {
            evt = JSON.parse(dataLine);
          } catch (e) {
            return;
          }
          if (evt.type === "token") {
            updateBotStream(streamState, evt.text || "");
          } else if (evt.type === "done") {
            finalPayload = evt;
          } else if (evt.type === "error") {
            streamFailed = evt.error || "Stream failed";
          }
        }

        function pump() {
          return reader.read().then(function (result) {
            if (result.done) {
              if (streamFailed || !finalPayload) {
                // Fall back to classic JSON chat if SSE failed mid-flight.
                return postChatJson(q, historyPayload);
              }
              return { mode: "stream", ok: true, data: finalPayload };
            }
            buffer += decoder.decode(result.value, { stream: true });
            var parts = buffer.split("\n\n");
            buffer = parts.pop() || "";
            parts.forEach(handleEvent);
            if (streamFailed) {
              try {
                reader.cancel();
              } catch (e) {
                /* ignore */
              }
              return postChatJson(q, historyPayload);
            }
            return pump();
          });
        }
        return pump();
      })
      .catch(function () {
        // Network / stream transport failure → retry non-stream endpoint.
        return postChatJson(q, historyPayload);
      })
      .then(function (result) {
        if (requestId !== activeRequest) return;
        if (!result || !result.ok) {
          if (streamState && streamState.row) streamState.row.remove();
          appendError(
            (result && result.data && result.data.error) ||
              "I couldn't complete that request. Please try again in a moment."
          );
          return;
        }
        var data = result.data || {};
        var reply = data.reply || (streamState && streamState.text) || "";
        var followUps = data.follow_ups || [];
        pushHistory("assistant", reply);
        if (result.mode === "json") {
          if (streamState && streamState.row) streamState.row.remove();
          appendBot(reply, data.sources || [], followUps);
        } else {
          finalizeBotStream(streamState, reply, data.sources || [], followUps);
        }
      })
      .catch(function () {
        if (requestId !== activeRequest) return;
        if (streamState && streamState.row) streamState.row.remove();
        appendError("Network error. Check your connection and try again.");
      })
      .finally(function () {
        if (requestId !== activeRequest) return;
        busy = false;
        setChipsDisabled(false);
        syncSendEnabled();
        syncClearVisible();
        if (input) input.focus();
      });
  }

  // Per-login ephemeral history: never written to the server/DB.
  // Survives in-tab navigation only; cleared on refresh, logout, or tab close.
  loadEphemeralHistory();
  syncClearVisible();

  document.querySelectorAll('form[action*="logout"]').forEach(function (logoutForm) {
    logoutForm.addEventListener("submit", function () {
      resetChatUi();
    });
  });

  window.addEventListener("pagehide", function () {
    conversation = conversation.slice(-HISTORY_LIMIT);
    persistEphemeralHistory();
  });

  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    var stillSameUser = true;
    try {
      var raw = sessionStorage.getItem(storageKey);
      if (raw) {
        var parsed = JSON.parse(raw);
        stillSameUser = !!(parsed && parsed.userKey === userKey);
      }
    } catch (e) {
      stillSameUser = false;
    }
    if (!stillSameUser) {
      resetChatUi();
    }
  });

  if (openBtn) {
    openBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var isHidden = panel.hidden || panel.classList.contains("is-closed");
      setOpen(isHidden);
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
    });
  }

  function explainThisPage() {
    if (busy) return;
    userClosed = false;
    setOpen(true);
    var page = currentPage();
    var title = (page.title || "").trim();
    var path = (page.path || "").trim();
    var q = "Explain this page";
    if (title) {
      q = 'Explain this page: "' + title.replace(/"/g, "") + '"';
    } else if (path) {
      q = "Explain this page (" + path + ")";
    }
    window.setTimeout(function () {
      sendMessage(q);
    }, 120);
  }

  if (explainBtn) {
    explainBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      explainThisPage();
    });
  }

  document.querySelectorAll("[data-explain-mine-page]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      explainThisPage();
    });
  });

  if (clearBtn) {
    clearBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      clearChat();
    });
  }

  if (expandBtn) {
    expandBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      setExpanded(!root.classList.contains("is-expanded"));
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (!panel || panel.hidden || panel.classList.contains("is-closed")) return;
    if (root.classList.contains("is-expanded")) {
      setExpanded(false);
      return;
    }
    setOpen(false);
  });

  document.querySelectorAll("[data-open-mine-chat]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      userClosed = false;
      setOpen(true);
    });
  });

  if (autoOpen && !userClosed) {
    window.setTimeout(function () {
      if (!userClosed) setOpen(true);
    }, 350);
  }

  if (input) {
    input.addEventListener("input", syncSendEnabled);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn || sendBtn.disabled) return;
        sendMessage(input.value);
      }
    });
  }

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!sendBtn || sendBtn.disabled) return;
      sendMessage(input.value);
    });
  }

  syncSendEnabled();

  window.setInterval(function () {
    if (!openBtn) return;
    var closed = !panel || panel.hidden || panel.classList.contains("is-closed");
    if (!closed) return;
    openBtn.classList.remove("is-idle-pulse");
    void openBtn.offsetWidth;
    openBtn.classList.add("is-idle-pulse");
  }, 30000);
})();
