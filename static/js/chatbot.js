(function () {
  var root = document.getElementById("mine-chatbot");
  if (!root) return;

  var endpoint = root.getAttribute("data-endpoint");
  var csrf = root.getAttribute("data-csrf") || "";
  var autoOpen = root.getAttribute("data-auto-open") === "1";
  var openBtn = document.getElementById("mine-chat-open");
  var closeBtn = document.getElementById("mine-chat-close");
  var panel = document.getElementById("mine-chat-panel");
  var form = document.getElementById("mine-chat-form");
  var input = document.getElementById("mine-chat-input");
  var messages = document.getElementById("mine-chat-messages");
  var busy = false;
  var greeted = false;
  var userClosed = false;

  function setOpen(open) {
    if (!panel) return;
    if (!open) {
      userClosed = true;
    }
    if (open) {
      panel.hidden = false;
      panel.classList.remove("is-closed");
    } else {
      panel.hidden = true;
      panel.classList.add("is-closed");
    }
    if (openBtn) {
      openBtn.setAttribute("aria-expanded", open ? "true" : "false");
    }
      if (open) {
      if (!greeted) {
        greeted = true;
        appendBot(
          "Hey — I'm Ask MiNe. How can I assist you today? Ask me anything, or about Freeport Knowledge, Domain, Journey, or Projects.",
          []
        );
      }
      if (input) input.focus();
    }
  }

  function appendBubble(text, cls) {
    var div = document.createElement("div");
    div.className = "mine-chat__bubble " + cls;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  function appendBot(text, sources) {
    var wrap = document.createElement("div");
    wrap.className = "mine-chat__bubble mine-chat__bubble--bot";
    wrap.textContent = text || "";
    if (sources && sources.length) {
      var ul = document.createElement("ul");
      ul.className = "mine-chat__sources";
      sources.slice(0, 8).forEach(function (s) {
        if (!s || !s.url) return;
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
      if (ul.childNodes.length) wrap.appendChild(ul);
    }
    messages.appendChild(wrap);
    messages.scrollTop = messages.scrollHeight;
  }

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

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (busy || !input) return;
      var q = (input.value || "").trim();
      if (!q) return;
      input.value = "";
      appendBubble(q, "mine-chat__bubble--user");
      busy = true;
      var typing = document.createElement("div");
      typing.className = "mine-chat__typing";
      typing.textContent = "Thinking…";
      messages.appendChild(typing);
      messages.scrollTop = messages.scrollHeight;

      fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        credentials: "same-origin",
        body: JSON.stringify({ message: q }),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { ok: res.ok, status: res.status, data: data };
          });
        })
        .then(function (result) {
          typing.remove();
          if (!result.ok) {
            appendBubble(
              (result.data && result.data.error) || "Something went wrong. Try again.",
              "mine-chat__bubble--error"
            );
            return;
          }
          appendBot(result.data.reply, result.data.sources || []);
        })
        .catch(function () {
          typing.remove();
          appendBubble("Network error. Check your connection and try again.", "mine-chat__bubble--error");
        })
        .finally(function () {
          busy = false;
          if (input) input.focus();
        });
    });
  }
})();
