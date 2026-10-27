"use strict";

const $ = (id) => document.getElementById(id);
const LIVE_LOOKUP_ENABLED = false;
const LATEST_UPLOAD = /\b(?:latest|most recent|newest|last)\s+(?:upload|uploaded file|file|document|note)\b/i;

const el = {
  sidebar: $("sidebar"),
  backdrop: $("backdrop"),
  menuBtn: $("menuBtn"),
  chatList: $("chatList"),
  search: $("searchInput"),
  messages: $("messages"),
  composer: $("composer"),
  input: $("input"),
  sendBtn: $("sendBtn"),
  stopBtn: $("stopBtn"),
  mode: $("mode"),
  language: $("language"),
  model: $("model"),
  notesToggle: $("notesToggle"),
  webToggle: $("webToggle"),
  chatTitle: $("chatTitle"),
  chatSub: $("chatSub"),
  status: $("status"),
  notesCount: $("notesCount"),
  memoryNote: $("memoryNote"),
  banner: $("banner"),
  bannerText: $("bannerText"),
  bannerClose: $("bannerClose"),
  drawer: $("notesDrawer"),
  drawerClose: $("drawerClose"),
  dropzone: $("dropzone"),
  fileInput: $("fileInput"),
  fileList: $("fileList"),
  drawerNotesCount: $("drawerNotesCount"),
  notesStatus: $("notesStatus"),
  urlForm: $("urlForm"),
  urlInput: $("urlInput"),
  rescanBtn: $("rescanBtn"),
  clearBtn: $("clearBtn"),
  toast: $("toast"),
  themeBtn: $("themeBtn"),
  exportBtn: $("exportBtn"),
  inputHint: $("inputHint"),
  clearChatsBtn: $("clearChatsBtn"),
};

const memory = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* private mode */
    }
  },
};

const state = {
  status: null,
  conversations: [],
  activeId: null,
  streaming: false,
  controller: null,
  messages: [],
  notes: { files: [] },
  prefs: {
    theme: memory.get("os.theme", null),
    mode: memory.get("os.mode", "Just chat"),
    language: memory.get("os.language", "English"),
    model: memory.get("os.model2", ""),
    useNotes: memory.get("os.useNotes3", true),
    useWeb: memory.get("os.useWeb", false),
  },
};

let drawerTimer = null;
let drawerReturnFocus = null;
let toastTimer = null;

/* ---------- Small helpers ---------- */

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderMarkdown(source) {
  const blocks = [];
  let text = String(source || "").replace(/\r\n/g, "\n");

  text = text.replace(/```[^\n]*\n?([\s\S]*?)```/g, (_match, code) => {
    const index = blocks.push("<pre><code>" + escapeHtml(code.replace(/\n+$/, "")) + "</code></pre>") - 1;
    return "\u0000" + index + "\u0000";
  });

  text = escapeHtml(text);
  text = text.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  text = text.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,!?]|$)/g, "$1<em>$2</em>");
  text = text.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );

  const lines = text.split("\n");
  let html = "";
  let list = "";
  let paragraph = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      html += "<p>" + paragraph.join("<br>") + "</p>";
      paragraph = [];
    }
  };
  const closeList = () => {
    if (list) {
      html += "</" + list + ">";
      list = "";
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushParagraph();
      closeList();
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      flushParagraph();
      closeList();
      const level = Math.min(heading[1].length + 2, 5);
      html += "<h" + level + ">" + heading[2] + "</h" + level + ">";
      continue;
    }

    if (/^\u0000\d+\u0000$/.test(line)) {
      flushParagraph();
      closeList();
      html += line;
      continue;
    }

    const bullet = /^[-*\u2022]\s+(.*)$/.exec(line);
    if (bullet) {
      flushParagraph();
      if (list !== "ul") {
        closeList();
        html += "<ul>";
        list = "ul";
      }
      html += "<li>" + bullet[1] + "</li>";
      continue;
    }

    const numbered = /^\d+[.)]\s+(.*)$/.exec(line);
    if (numbered) {
      flushParagraph();
      if (list !== "ol") {
        closeList();
        html += "<ol>";
        list = "ol";
      }
      html += "<li>" + numbered[1] + "</li>";
      continue;
    }

    closeList();
    paragraph.push(line);
  }

  flushParagraph();
  closeList();
  return html.replace(/\u0000(\d+)\u0000/g, (_match, index) => blocks[Number(index)] || "");
}

function timeAgo(epochSeconds) {
  if (!epochSeconds) return "";
  const seconds = Date.now() / 1000 - Number(epochSeconds);
  if (seconds < 60) return "now";
  if (seconds < 3600) return Math.floor(seconds / 60) + "m";
  if (seconds < 86400) return Math.floor(seconds / 3600) + "h";
  if (seconds < 604800) return Math.floor(seconds / 86400) + "d";
  return new Date(epochSeconds * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function prettySize(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return size + " B";
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
  return (size / (1024 * 1024)).toFixed(1) + " MB";
}

function initials(title) {
  const words = String(title || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "OS";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function firstLine(text) {
  return String(text || "").split("\n").find((line) => line.trim()) || "";
}

function friendlyError(message) {
  const text = String(message || "");
  if (/failed to fetch|networkerror|load failed/i.test(text)) {
    return "Can't reach the OfflineScholar server. Is it still running?";
  }
  return text || "Something went wrong.";
}

/* ---------- API ---------- */

async function api(path, options = {}) {
  const opts = { ...options };
  const headers = new Headers(opts.headers || {});
  if (typeof opts.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  opts.headers = headers;
  const response = await fetch(path, opts);
  let data = {};
  try {
    data = await response.json();
  } catch {
    /* empty body */
  }
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.message;
    throw new Error(detail || "Request failed (" + response.status + ")");
  }
  return data;
}

/* ---------- Theme and layout ---------- */

function systemTheme() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme() {
  document.documentElement.dataset.theme = state.prefs.theme || systemTheme();
}

function toggleTheme() {
  const next = (document.documentElement.dataset.theme || "light") === "dark" ? "light" : "dark";
  state.prefs.theme = next;
  memory.set("os.theme", next);
  applyTheme();
}

function openSidebar() {
  el.sidebar.classList.add("open");
  el.backdrop.hidden = false;
  el.menuBtn.setAttribute("aria-expanded", "true");
  el.menuBtn.setAttribute("aria-label", "Close chat history");
}

function closeSidebar() {
  el.sidebar.classList.remove("open");
  if (el.drawer.hidden) el.backdrop.hidden = true;
  el.menuBtn.setAttribute("aria-expanded", "false");
  el.menuBtn.setAttribute("aria-label", "Open chat history");
}

function openDrawer() {
  clearTimeout(drawerTimer);
  if (el.drawer.hidden) drawerReturnFocus = document.activeElement;
  el.drawer.hidden = false;
  el.backdrop.hidden = false;
  el.drawer.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => el.drawer.classList.add("open"));
  loadNotes();
  drawerTimer = setTimeout(() => el.drawerClose.focus(), 270);
}

function closeDrawer() {
  if (el.drawer.hidden) return;
  el.drawer.classList.remove("open");
  el.drawer.setAttribute("aria-hidden", "true");
  clearTimeout(drawerTimer);
  drawerTimer = setTimeout(() => {
    el.drawer.hidden = true;
    if (!el.sidebar.classList.contains("open")) el.backdrop.hidden = true;
    if (drawerReturnFocus && drawerReturnFocus.isConnected) drawerReturnFocus.focus();
    drawerReturnFocus = null;
  }, 260);
}

function closeAllOverlays() {
  closeDrawer();
  closeSidebar();
}

/* ---------- Notices ---------- */

function toast(message) {
  clearTimeout(toastTimer);
  el.toast.textContent = message;
  el.toast.hidden = false;
  requestAnimationFrame(() => el.toast.classList.add("show"));
  toastTimer = setTimeout(() => {
    el.toast.classList.remove("show");
    setTimeout(() => {
      el.toast.hidden = true;
    }, 220);
  }, 3600);
}

function applyNotesPreference(enabled, announce = false) {
  state.prefs.useNotes = Boolean(enabled);
  memory.set("os.useNotes3", state.prefs.useNotes);
  el.notesToggle.setAttribute("aria-pressed", state.prefs.useNotes ? "true" : "false");
  el.notesToggle.title = state.prefs.useNotes
    ? "Notes are on: replies can search your library"
    : "Notes are off: click to search your library";
  if (announce) {
    toast(state.prefs.useNotes ? "Replies will search your notes" : "Notes search is off");
  }
}

function showBanner(message) {
  el.bannerText.textContent = message;
  el.banner.hidden = false;
}

function hideBanner() {
  el.banner.hidden = true;
}

/* ---------- Status and options ---------- */

function setStatus(kind, label) {
  el.status.classList.remove("online", "offline");
  if (kind) el.status.classList.add(kind);
  el.status.querySelector(".status-text").textContent = label;
}

function fillSelect(select, values, desired) {
  select.replaceChildren();
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
  select.value = values.includes(desired) ? desired : values[0] || "";
  return select.value;
}

function updateSubtitle() {
  const model = el.model.value || (state.status && state.status.model) || "";
  const low = state.status && state.status.low_memory;
  el.chatSub.textContent = model
    ? model + " \u00b7 " + (low ? "low-RAM mode" : "running on this laptop")
    : "Your private, offline study tutor";
}

async function loadStatus() {
  try {
    const status = await api("/api/status");
    state.status = status;

    setStatus(status.ollama ? "online" : "offline", status.ollama ? "Ollama ready" : "Ollama offline \u2014 run ollama serve");
    if (!status.ollama) showBanner("Ollama isn't running, so replies will fail. Start it with:  ollama serve");

    state.prefs.mode = fillSelect(el.mode, status.modes, state.prefs.mode);
    state.prefs.language = fillSelect(el.language, status.languages, state.prefs.language);

    const models = Array.from(new Set([...(status.models || []), status.model].filter(Boolean)));
    state.prefs.model = fillSelect(el.model, models, state.prefs.model || status.model);
    memory.set("os.model2", state.prefs.model);

    el.memoryNote.hidden = !status.low_memory;
    if (status.low_memory) {
      const gb = Number(status.available_memory_gb || 0).toFixed(1);
      el.memoryNote.textContent = "Low-RAM mode: " + gb + " GB free. The lighter model keeps replies fast.";
    }

    updateSubtitle();
    if (status.max_message_chars) el.input.maxLength = Number(status.max_message_chars);
    updateInputHint();
  } catch (error) {
    setStatus("offline", "Server not reachable");
    showBanner(friendlyError(error.message));
  }
}

/* ---------- Conversation list ---------- */

function renderChatList() {
  const query = el.search.value.trim().toLowerCase();
  const items = state.conversations.filter((conversation) => {
    if (!query) return true;
    return (conversation.title + " " + (conversation.preview || "")).toLowerCase().includes(query);
  });

  el.chatList.replaceChildren();

  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "chat-list-empty";
    empty.textContent = state.conversations.length
      ? "No chats match your search."
      : "No chats yet. Ask your first question to start one.";
    el.chatList.append(empty);
    return;
  }

  for (const conversation of items) {
    const item = document.createElement("div");
    item.className = "chat-item" + (conversation.id === state.activeId ? " active" : "");
    item.setAttribute("role", "listitem");

    const button = document.createElement("button");
    button.type = "button";
    button.className = "chat-item-btn";
    if (conversation.id === state.activeId) button.setAttribute("aria-current", "true");

    const badge = document.createElement("span");
    badge.className = "chat-badge";
    badge.textContent = initials(conversation.title);

    const text = document.createElement("span");
    text.className = "chat-item-text";
    const title = document.createElement("span");
    title.className = "chat-title";
    title.textContent = conversation.title || "New chat";
    const preview = document.createElement("span");
    preview.className = "chat-preview";
    preview.textContent = firstLine(conversation.preview) || "No messages yet";
    text.append(title, preview);

    const meta = document.createElement("span");
    meta.className = "chat-meta";
    const time = document.createElement("span");
    time.className = "chat-time";
    time.textContent = timeAgo(conversation.updated);
    const count = document.createElement("span");
    count.className = "chat-count";
    const messages = Number(conversation.messages) || 0;
    count.textContent = messages + (messages === 1 ? " msg" : " msgs");
    meta.append(time, count);

    button.append(badge, text, meta);
    button.addEventListener("click", () => openConversation(conversation.id, { focus: true }));

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chat-delete";
    remove.setAttribute("aria-label", "Delete chat");
    remove.innerHTML = "&times;";
    remove.addEventListener("click", async (event) => {
      event.stopPropagation();
      if (!window.confirm('Delete "' + (conversation.title || "this chat") + '"?')) return;
      try {
        await api("/api/conversations/" + conversation.id, { method: "DELETE" });
        if (conversation.id === state.activeId) newChat();
        await loadConversations();
        toast("Chat deleted");
      } catch (error) {
        toast(friendlyError(error.message));
      }
    });

    item.append(button, remove);
    el.chatList.append(item);
  }
}

async function loadConversations() {
  try {
    const data = await api("/api/conversations");
    state.conversations = data.conversations || [];
    renderChatList();
    return state.conversations;
  } catch (error) {
    showBanner(friendlyError(error.message));
    return [];
  }
}

function syncTitleFromList() {
  if (!state.activeId) return;
  const conversation = state.conversations.find((item) => item.id === state.activeId);
  if (conversation) {
    el.chatTitle.textContent = conversation.title || "New chat";
    el.chatTitle.title = "Click to rename";
  }
}

/* ---------- Messages ---------- */

function isNearBottom() {
  const node = el.messages;
  return node.scrollHeight - node.scrollTop - node.clientHeight < 140;
}

function scrollToBottom(force = false) {
  if (force || isNearBottom()) {
    el.messages.scrollTop = el.messages.scrollHeight;
  }
}

function messageAvatar(role) {
  const avatar = document.createElement("span");
  avatar.className = "msg-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "You" : "OS";
  return avatar;
}

function appendMessage(role, content) {
  const row = document.createElement("div");
  row.className = "msg " + role;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant") {
    bubble.innerHTML = renderMarkdown(content);
  } else {
    bubble.textContent = content;
  }
  row.append(messageAvatar(role), bubble);
  el.messages.append(row);
  scrollToBottom(true);
  return bubble;
}

function attachSources(bubble, sources) {
  if (!sources || !sources.length) return;
  const wrap = document.createElement("div");
  wrap.className = "sources";
  const label = document.createElement("span");
  label.className = "sources-label";
  label.textContent = "Sources";
  wrap.append(label);
  sources.forEach((source, index) => {
    const chip = document.createElement(source.url ? "a" : "span");
    chip.className = "source-chip";
    if (source.url) {
      chip.href = source.url;
      chip.target = "_blank";
      chip.rel = "noopener noreferrer";
    }
    const label = source.label ? " \u00b7 " + source.label : "";
    chip.textContent = "[" + (index + 1) + "] " + source.name + label;
    if (typeof source.score === "number") {
      chip.title = "Relevance " + Math.round(source.score * 100) + "%";
    }
    wrap.append(chip);
  });
  bubble.append(wrap);
}

function appendTyping() {
  const row = document.createElement("div");
  row.className = "msg assistant";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
  row.append(messageAvatar("assistant"), bubble);
  el.messages.append(row);
  scrollToBottom(true);
  return bubble;
}

function renderWelcome() {
  el.messages.replaceChildren();

  const wrap = document.createElement("div");
  wrap.className = "welcome";

  const logo = document.createElement("div");
  logo.className = "welcome-logo";
  logo.innerHTML =
    '<svg viewBox="0 0 48 48" width="34" height="34" aria-hidden="true">' +
    '<path d="M8 11h12a5 5 0 0 1 5 5v20a4 4 0 0 0-4-4H8z" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/>' +
    '<path d="M40 11H28a5 5 0 0 0-5 5v20a4 4 0 0 1 4-4h13z" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/>' +
    '<circle cx="34" cy="33" r="3.4" fill="currentColor"/>' +
    "</svg>";

  const heading = document.createElement("h2");
  heading.textContent = "What are we studying today?";

  const noteCount = state.notes && state.notes.files ? state.notes.files.length : 0;
  const copy = document.createElement("p");
  copy.textContent = noteCount
    ? "Ask a question, practise a quiz, or turn your " + noteCount + " saved note" + (noteCount === 1 ? "" : "s") + " into a study guide."
    : "Ask a question, paste homework, or upload your class notes. Everything stays on this laptop.";

  const suggestions = document.createElement("div");
  suggestions.className = "suggestions";
  const prompts = noteCount
    ? [
        ["Quiz me on my notes", "Quiz me on my notes, 5 questions."],
        ["Explain a hard idea simply", "Explain the hardest idea in my notes as if I'm a beginner."],
        ["Summarise my latest upload", "Summarise my latest upload in 5 bullet points."],
      ]
    : [
        ["Explain a concept simply", "Explain photosynthesis simply, with an everyday example."],
        ["Walk me through homework", "Help me solve a maths problem step by step."],
        ["Make a revision quiz", "Make a 5-question quiz on the water cycle."],
      ];

  for (const [label, prompt] of prompts) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggestion";
    const icon = document.createElement("span");
    icon.className = "emoji";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = label.startsWith("Quiz") ? "?" : label.startsWith("Summarise") ? "\u2261" : "\u2192";
    const text = document.createElement("span");
    text.textContent = label;
    button.append(icon, text);
    button.addEventListener("click", () => sendMessage(prompt));
    suggestions.append(button);
  }

  wrap.append(logo, heading, copy, suggestions);
  el.messages.append(wrap);
}

function renderMessages(messages) {
  el.messages.replaceChildren();
  const visible = (messages || []).filter((message) => message.role === "user" || message.role === "assistant");
  if (!visible.length) {
    renderWelcome();
    return;
  }
  for (const message of visible) appendMessage(message.role, message.content);
  scrollToBottom(true);
}

/* ---------- Streaming chat ---------- */

function setStreaming(streaming) {
  state.streaming = streaming;
  el.sendBtn.hidden = streaming;
  el.stopBtn.hidden = !streaming;
  el.messages.setAttribute("aria-busy", streaming ? "true" : "false");
}

function stopStreaming(notify = true) {
  if (state.controller) {
    state.controller.abort();
    if (notify) toast("Stopped");
  }
}

async function sendMessage(preset) {
  if (state.streaming) return;
  const text = String(preset !== undefined ? preset : el.input.value).trim();
  if (!text) return;
  if (LATEST_UPLOAD.test(text)) applyNotesPreference(true);

  hideBanner();
  if (preset === undefined) {
    el.input.value = "";
    autoGrow();
    updateInputHint();
  }

  appendMessage("user", text);
  state.messages.push({ role: "user", content: text });

  const bubble = appendTyping();
  let answer = "";
  let sources = [];
  let sawToken = false;
  let failed = false;

  setStreaming(true);
  const controller = new AbortController();
  state.controller = controller;

  const handleEvent = (event) => {
    if (!event || typeof event !== "object") return;
    if (event.type === "start" && event.conversation_id) {
      state.activeId = event.conversation_id;
      memory.set("os.active", state.activeId);
      loadConversations().then(syncTitleFromList);
      return;
    }
    if (event.type === "sources") {
      sources = event.sources || [];
      return;
    }
    if (event.type === "token") {
      sawToken = true;
      answer += event.text || "";
      bubble.textContent = answer;
      scrollToBottom();
      return;
    }
    if (event.type === "error") {
      failed = true;
      if (!answer) answer = event.message || "Something went wrong.";
      bubble.textContent = answer;
      showBanner(event.message || "Something went wrong.");
    }
  };

  try {
    const payload = {
      message: text,
      conversation_id: state.activeId,
      mode: el.mode.value || "Just chat",
      language: el.language.value || "English",
      use_notes: el.notesToggle.getAttribute("aria-pressed") === "true",
      use_web: LIVE_LOOKUP_ENABLED && el.webToggle.getAttribute("aria-pressed") === "true",
      model: el.model.value || null,
    };

    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Request failed (" + response.status + ")");
    }
    if (!response.body) throw new Error("This browser can't stream replies.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let split;
      while ((split = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const raw = line.slice(5).trim();
          if (!raw) continue;
          try {
            handleEvent(JSON.parse(raw));
          } catch {
            /* ignore malformed frame */
          }
        }
      }
    }
  } catch (error) {
    if (error.name !== "AbortError") {
      failed = true;
      const message = friendlyError(error.message);
      answer = answer ? answer + "\n\n" + message : message;
      bubble.textContent = answer;
      showBanner(message);
    }
  } finally {
    setStreaming(false);
    state.controller = null;

    if (answer.trim()) {
      bubble.innerHTML = renderMarkdown(answer);
      if (!sawToken && failed) bubble.innerHTML = renderMarkdown(answer);
      attachSources(bubble, sources);
      state.messages.push({ role: "assistant", content: answer });
    } else {
      const row = bubble.parentElement;
      if (row) row.remove();
    }

    if (state.activeId) {
      await loadConversations();
      syncTitleFromList();
    }
    el.input.focus();
  }
}

function autoGrow() {
  el.input.style.height = "auto";
  el.input.style.height = Math.min(el.input.scrollHeight, 180) + "px";
}

function updateInputHint() {
  const max = Number((state.status && state.status.max_message_chars) || 20000);
  const length = el.input.value.length;
  if (length >= max * 0.8) {
    el.inputHint.textContent = length.toLocaleString() + " / " + max.toLocaleString() + " characters";
    el.inputHint.classList.toggle("limit", length >= max);
  } else {
    el.inputHint.textContent = "Enter to send · Shift+Enter for a new line";
    el.inputHint.classList.remove("limit");
  }
}

/* ---------- Opening and creating chats ---------- */

async function openConversation(id, options = {}) {
  if (state.streaming) stopStreaming(false);
  closeSidebar();
  try {
    const conversation = await api("/api/conversations/" + id);
    state.activeId = conversation.id;
    state.messages = conversation.messages || [];
    memory.set("os.active", conversation.id);
    el.chatTitle.textContent = conversation.title || "New chat";
    renderMessages(state.messages);
    renderChatList();
    updateSubtitle();
    if (options.focus) el.input.focus();
  } catch (error) {
    if (/not found/i.test(error.message)) {
      memory.set("os.active", null);
      await loadConversations();
      newChat();
      toast("That chat no longer exists");
    } else {
      showBanner(friendlyError(error.message));
    }
  }
}

function newChat() {
  if (state.streaming) stopStreaming(false);
  state.activeId = null;
  state.messages = [];
  memory.set("os.active", null);
  el.chatTitle.textContent = "New chat";
  renderWelcome();
  renderChatList();
  updateSubtitle();
  closeSidebar();
  el.input.focus();
}

async function clearAllChats() {
  if (!state.conversations.length) {
    toast("There are no saved chats.");
    return;
  }
  if (!window.confirm("Delete all saved chats? This cannot be undone.")) return;
  try {
    const data = await api("/api/conversations", { method: "DELETE" });
    newChat();
    await loadConversations();
    toast(data.deleted ? "Deleted " + data.deleted + " chat(s)" : "No chats to delete");
  } catch (error) {
    toast(friendlyError(error.message));
  }
}

function exportChat() {
  if (!state.activeId) {
    toast("Send a message first, then you can download this chat.");
    return;
  }
  window.location.href = "/api/conversations/" + state.activeId + "/export";
}

async function renameActive() {
  if (!state.activeId) {
    toast("Send a message first, then you can rename this chat.");
    return;
  }
  const current = el.chatTitle.textContent || "New chat";
  const title = window.prompt("Rename this chat", current);
  if (title === null) return;
  const clean = title.trim().slice(0, 80);
  if (!clean || clean === current) return;
  try {
    const data = await api("/api/conversations/" + state.activeId, {
      method: "PATCH",
      body: JSON.stringify({ title: clean }),
    });
    el.chatTitle.textContent = data.title;
    await loadConversations();
    toast("Chat renamed");
  } catch (error) {
    toast(friendlyError(error.message));
  }
}

/* ---------- Notes library ---------- */

function stateBadge(stateName) {
  if (stateName === "indexed") return { text: "Indexed", kind: "ok" };
  if (stateName === "keyword only") return { text: "Keyword only", kind: "warn" };
  return { text: "Not indexed", kind: "warn" };
}

function renderNotes(data) {
  state.notes = data;
  const files = data.files || [];
  el.notesCount.textContent = files.length;
  el.drawerNotesCount.textContent = files.length;
  el.fileList.replaceChildren();

  if (!files.length) {
    const empty = document.createElement("li");
    empty.className = "file-empty";
    empty.textContent = "No notes yet. Upload a PDF, DOCX, TXT or MD file, or save a web page.";
    el.fileList.append(empty);
    return;
  }

  for (const file of files) {
    const item = document.createElement("li");
    item.className = "file-item";

    const icon = document.createElement("span");
    icon.className = "file-icon";
    icon.textContent = (file.name.split(".").pop() || "file").slice(0, 4);

    const meta = document.createElement("span");
    meta.className = "file-meta";
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = file.name;
    name.title = file.name;
    const sub = document.createElement("span");
    sub.className = "file-sub";
    sub.textContent = prettySize(file.size) + " \u00b7 " + file.state;
    meta.append(name, sub);

    const info = stateBadge(file.state);
    const badge = document.createElement("span");
    badge.className = "badge " + info.kind;
    badge.textContent = info.text;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "file-delete";
    remove.title = "Remove from library";
    remove.setAttribute("aria-label", "Remove " + file.name);
    remove.innerHTML = "&times;";
    remove.addEventListener("click", () => removeNote(file.name));

    item.append(icon, meta, badge, remove);
    el.fileList.append(item);
  }
}

async function loadNotes() {
  try {
    const data = await api("/api/notes");
    renderNotes(data);
  } catch (error) {
    el.notesStatus.hidden = false;
    el.notesStatus.textContent = friendlyError(error.message);
  }
}

function showNotesStatus(message) {
  el.notesStatus.hidden = false;
  el.notesStatus.textContent = message;
}

async function uploadFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  const oversized = files.filter((file) => file.size > 25 * 1024 * 1024);
  const allowed = files.filter((file) => file.size <= 25 * 1024 * 1024);
  if (oversized.length) {
    const names = oversized.map((file) => file.name).join(", ");
    toast(names + (oversized.length === 1 ? " is larger than 25 MB" : " are larger than 25 MB"));
  }
  if (!allowed.length) return;

  const form = new FormData();
  for (const file of allowed) form.append("files", file, file.name);

  showNotesStatus("Reading " + allowed.length + " file" + (allowed.length === 1 ? "" : "s") + "\u2026");
  try {
    const data = await api("/api/notes/upload", { method: "POST", body: form });
    renderNotes(data);
    if (data.saved) applyNotesPreference(true);
    showNotesStatus(firstLine(data.message));
    toast(firstLine(data.message));
    await loadStatus();
  } catch (error) {
    showNotesStatus(friendlyError(error.message));
  } finally {
    el.fileInput.value = "";
  }
}

async function addUrl(event) {
  event.preventDefault();
  const url = el.urlInput.value.trim();
  if (!url) return;
  showNotesStatus("Saving the page\u2026");
  try {
    const data = await api("/api/notes/url", { method: "POST", body: JSON.stringify({ url }) });
    renderNotes(data);
    showNotesStatus(firstLine(data.message));
    toast(firstLine(data.message));
    el.urlInput.value = "";
    await loadStatus();
  } catch (error) {
    showNotesStatus(friendlyError(error.message));
  }
}

async function rescanNotes() {
  showNotesStatus("Re-scanning the library\u2026");
  try {
    const data = await api("/api/notes/rescan", { method: "POST" });
    renderNotes(data);
    showNotesStatus(firstLine(data.message));
  } catch (error) {
    showNotesStatus(friendlyError(error.message));
  }
}

async function clearNotes() {
  if (!window.confirm("Clear the search index? Your files stay in the library.")) return;
  showNotesStatus("Clearing the index\u2026");
  try {
    const data = await api("/api/notes/clear", { method: "POST" });
    renderNotes(data);
    showNotesStatus(firstLine(data.message));
    toast("Index cleared");
  } catch (error) {
    showNotesStatus(friendlyError(error.message));
  }
}

async function removeNote(name) {
  if (!window.confirm('Remove "' + name + '" from the library?')) return;
  showNotesStatus("Removing " + name + "\u2026");
  try {
    const data = await api("/api/notes?name=" + encodeURIComponent(name), { method: "DELETE" });
    renderNotes(data);
    showNotesStatus(firstLine(data.message));
    toast(firstLine(data.message));
    await loadStatus();
  } catch (error) {
    showNotesStatus(friendlyError(error.message));
  }
}

/* ---------- Event wiring ---------- */

function wireEvents() {
  el.themeBtn.addEventListener("click", toggleTheme);
  el.menuBtn.addEventListener("click", openSidebar);
  el.backdrop.addEventListener("click", closeAllOverlays);

  $("newChatBtn").addEventListener("click", newChat);
  $("newChatBtnTop").addEventListener("click", newChat);
  $("notesBtn").addEventListener("click", openDrawer);
  $("notesBtnSide").addEventListener("click", openDrawer);
  el.drawerClose.addEventListener("click", closeDrawer);
  el.bannerClose.addEventListener("click", hideBanner);
  el.chatTitle.addEventListener("click", renameActive);
  el.chatTitle.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      renameActive();
    }
  });
  el.exportBtn.addEventListener("click", exportChat);
  el.clearChatsBtn.addEventListener("click", clearAllChats);

  el.search.addEventListener("input", renderChatList);

  el.composer.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage();
  });

  el.input.addEventListener("input", () => {
    autoGrow();
    updateInputHint();
  });
  el.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage();
    }
  });

  el.stopBtn.addEventListener("click", () => stopStreaming(true));

  el.mode.addEventListener("change", () => {
    state.prefs.mode = el.mode.value;
    memory.set("os.mode", el.mode.value);
  });
  el.language.addEventListener("change", () => {
    state.prefs.language = el.language.value;
    memory.set("os.language", el.language.value);
  });
  el.model.addEventListener("change", () => {
    state.prefs.model = el.model.value;
    memory.set("os.model2", el.model.value);
    updateSubtitle();
  });

  applyNotesPreference(state.prefs.useNotes);
  el.notesToggle.addEventListener("click", () => {
    applyNotesPreference(!state.prefs.useNotes, true);
  });

  const syncWebToggle = () => {
    el.webToggle.setAttribute("aria-pressed", state.prefs.useWeb ? "true" : "false");
  };
  syncWebToggle();
  el.webToggle.addEventListener("click", () => {
    state.prefs.useWeb = !state.prefs.useWeb;
    memory.set("os.useWeb", state.prefs.useWeb);
    syncWebToggle();
    toast(state.prefs.useWeb
      ? "Live lookup is on for current questions. Your question is sent to a search engine."
      : "Live lookup is off");
  });

  el.fileInput.addEventListener("change", () => uploadFiles(el.fileInput.files));
  ["dragenter", "dragover"].forEach((type) => {
    el.dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      el.dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((type) => {
    el.dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      el.dropzone.classList.remove("dragover");
    });
  });
  el.dropzone.addEventListener("drop", (event) => uploadFiles(event.dataTransfer.files));

  el.urlForm.addEventListener("submit", addUrl);
  el.rescanBtn.addEventListener("click", rescanNotes);
  el.clearBtn.addEventListener("click", clearNotes);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAllOverlays();
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      el.search.focus();
      el.search.select();
    }
    if (event.altKey && event.key.toLowerCase() === "n") {
      event.preventDefault();
      newChat();
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 960) closeSidebar();
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!state.prefs.theme) applyTheme();
  });
}

/* ---------- Start ---------- */

async function init() {
  const params = new URLSearchParams(window.location.search);
  const requestedTheme = params.get("theme");
  if (requestedTheme === "dark" || requestedTheme === "light") state.prefs.theme = requestedTheme;

  applyTheme();
  wireEvents();
  autoGrow();

  await loadStatus();
  await loadConversations();
  await loadNotes();

  const requested = Number(params.get("c"));
  const lastActive = memory.get("os.active", null);
  const target = [requested, lastActive].find((id) =>
    Number.isInteger(id) && state.conversations.some((conversation) => conversation.id === id)
  );
  if (target) {
    await openConversation(target);
  } else {
    renderWelcome();
  }

  el.input.focus();
  if (params.get("notes") === "1") openDrawer();
}

document.addEventListener("DOMContentLoaded", init);
