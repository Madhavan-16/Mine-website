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

  function dedupeSources(sources) {
    var best = {};
    (sources || []).forEach(function (s) {
      if (!s || !s.url) return;
      var key = String(s.url).toLowerCase();
      var score = 100;
      var kind = String(s.kind || "").toLowerCase();
      var mod = String(s.module || "").toLowerCase();
      var title = String(s.title || "").toLowerCase();
      if (kind === "project" || mod === "projects") score = 300;
      else if (kind === "page") score = 50;
      if (
        title === "programs & projects" ||
        title === "programs and projects" ||
        title === "projects"
      ) {
        score -= 100;
      }
      if (!best[key] || score > best[key].score) {
        best[key] = { score: score, item: s };
      }
    });
    return Object.keys(best)
      .map(function (k) {
        return best[k].item;
      })
      .sort(function (a, b) {
        function score(s) {
          var kind = String(s.kind || "").toLowerCase();
          var mod = String(s.module || "").toLowerCase();
          if (kind === "project" || mod === "projects") return 300;
          if (kind === "page") return 50;
          return 100;
        }
        return score(b) - score(a);
      });
  }

  function pickPrimarySource(sources) {
    if (!sources || !sources.length) return null;
    var ranked = sources.slice().sort(function (a, b) {
      function score(s) {
        var kind = String(s.kind || "").toLowerCase();
        var mod = String(s.module || "").toLowerCase();
        var title = String(s.title || "").toLowerCase();
        var n = 100;
        if (kind === "project" || mod === "projects") n = 300;
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
      return score(b) - score(a);
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

  /** Lightweight Markdown → safe HTML for chat bubbles. */
  function renderMarkdown(src) {
    var text = String(src || "").replace(/\r\n/g, "\n");
    var lines = text.split("\n");
    var html = [];
    var inUl = false;
    var inOl = false;
    var inCode = false;
    var codeBuf = [];
    var inTable = false;
    var tableRows = [];

    function closeLists() {
      if (inUl) {
        html.push("</ul>");
        inUl = false;
      }
      if (inOl) {
        html.push("</ol>");
        inOl = false;
      }
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

      if (/^```/.test(line)) {
        if (inCode) {
          html.push(
            '<pre class="mine-chat__md-pre"><code>' +
              escapeHtml(codeBuf.join("\n")) +
              "</code></pre>"
          );
          codeBuf = [];
          inCode = false;
        } else {
          closeLists();
          closeTable();
          inCode = true;
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

      var ul = /^[-*•]\s+(.+)$/.exec(line);
      if (ul) {
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
          html.push('<ol class="mine-chat__md-list">');
          inOl = true;
        }
        html.push("<li>" + inlineMd(ol[2]) + "</li>");
        continue;
      }

      closeLists();
      if (!line.trim()) {
        html.push('<div class="mine-chat__md-gap"></div>');
      } else {
        html.push('<p class="mine-chat__md-p">' + inlineMd(line) + "</p>");
      }
    }

    closeLists();
    closeTable();
    if (inCode) {
      html.push(
        '<pre class="mine-chat__md-pre"><code>' + escapeHtml(codeBuf.join("\n")) + "</code></pre>"
      );
    }
    return html.join("");
  }

  function syncSendEnabled() {
    if (!sendBtn || !input) return;
    var empty = !(input.value || "").trim();
    sendBtn.disabled = empty || busy;
  }

  function setOpen(open) {
    if (!panel) return;
    if (!open) {
      userClosed = true;
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

  function copyPlainText(text, btn) {
    var value = String(text || "");
    function markCopied() {
      if (!btn) return;
      var prev = btn.textContent;
      btn.textContent = "Copied";
      btn.classList.add("is-copied");
      window.setTimeout(function () {
        btn.textContent = prev;
        btn.classList.remove("is-copied");
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

    var usableSources = dedupeSources(sources);
    if (usableSources.length && !opts.compact) {
      var top = pickPrimarySource(usableSources) || usableSources[0];
      var cta = document.createElement("a");
      cta.className = "mine-chat__open-cta";
      cta.href = top.url;
      cta.textContent = shortOpenLabel(top.title || top.url);
      cta.title = top.title || top.url;
      wrap.appendChild(cta);

      var rest = usableSources.filter(function (s) {
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
      copyBtn.textContent = "Copy";
      copyBtn.setAttribute("aria-label", "Copy reply");
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
    var typing = document.createElement("div");
    typing.className = "mine-chat__typing";
    typing.setAttribute("aria-live", "polite");
    typing.innerHTML =
      '<span class="mine-chat__typing-emoji" aria-hidden="true">🤖</span>' +
      '<span class="mine-chat__typing-copy">MiNe AI is thinking' +
      '<span class="mine-chat__typing-dots" aria-hidden="true"><span></span><span></span><span></span></span>' +
      "</span>" +
      '<span class="mine-chat__typing-pulse" aria-hidden="true"></span>';
    messages.appendChild(typing);
    scrollToBottom();

    fetch(endpoint, {
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
    })
      .then(function (res) {
        return res.text().then(function (raw) {
          var data = {};
          try {
            data = raw ? JSON.parse(raw) : {};
          } catch (e) {
            data = { error: "Unexpected server response. Please try again." };
          }
          return { ok: res.ok, status: res.status, data: data };
        });
      })
      .then(function (result) {
        if (requestId !== activeRequest) return;
        typing.remove();
        if (!result.ok) {
          appendError(
            (result.data && result.data.error) ||
              "I couldn't complete that request. Please try again in a moment."
          );
          return;
        }
        var reply = (result.data && result.data.reply) || "";
        var followUps = (result.data && result.data.follow_ups) || [];
        pushHistory("assistant", reply);
        appendBot(reply, (result.data && result.data.sources) || [], followUps);
      })
      .catch(function () {
        if (requestId !== activeRequest) return;
        typing.remove();
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

  if (clearBtn) {
    clearBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      clearChat();
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (!panel || panel.hidden || panel.classList.contains("is-closed")) return;
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
