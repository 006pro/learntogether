(() => {
  "use strict";

  const MAX_LENGTH = 100;

  const state = {
    csrfToken: null,
    topics: [],
    highlightId: null,
  };

  const el = {
    userName: document.getElementById("user-name"),
    logout: document.getElementById("logout"),
    form: document.getElementById("topic-form"),
    input: document.getElementById("topic-input"),
    submit: document.querySelector("#topic-form button[type=submit]"),
    formStatus: document.getElementById("topic-status"),
    charCount: document.getElementById("char-count"),
    hint: document.getElementById("topic-hint"),
    list: document.getElementById("topic-list"),
    listStatus: document.getElementById("list-status"),
    total: document.getElementById("topic-total"),
    empty: document.getElementById("empty-state"),
  };

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }

  async function api(path, { method = "GET", body } = {}) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (method !== "GET") headers["X-CSRF-Token"] = state.csrfToken || "";

    let response;
    try {
      response = await fetch(path, {
        method,
        headers,
        credentials: "same-origin",
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError("Couldn't reach the server. Check your connection and try again.", 0);
    }

    if (response.status === 401) {
      window.location.assign("/login");
      throw new ApiError("Your session has ended. Please sign in again.", 401);
    }

    let data = null;
    if (response.status !== 204) {
      try {
        data = await response.json();
      } catch {
        data = null;
      }
    }

    if (!response.ok) {
      const message = data && typeof data.detail === "string"
        ? data.detail
        : "Something went wrong. Please try again.";
      throw new ApiError(message, response.status);
    }
    return data;
  }

  function setStatus(node, message, kind) {
    node.textContent = message || "";
    node.classList.toggle("is-error", kind === "error");
    node.classList.toggle("is-success", kind === "success");
  }

  function cleanText(value) {
    return value.replace(/\s+/g, " ").trim();
  }

  // ---------- Rendering ----------

  function renderTopic(topic) {
    const item = document.createElement("li");
    item.className = "topic";
    item.tabIndex = -1;
    item.dataset.id = String(topic.id);
    if (topic.id === state.highlightId) item.classList.add("is-new");

    const name = document.createElement("span");
    name.className = "topic-name";
    name.textContent = topic.name;

    const count = document.createElement("span");
    count.className = "topic-count";
    const num = document.createElement("span");
    num.className = "count-num";
    num.textContent = String(topic.vote_count);
    count.append(num, " interested");

    const button = document.createElement("button");
    button.type = "button";
    button.className = "vote-button";
    if (topic.has_voted) {
      button.textContent = "Voted";
      button.disabled = true;
      button.classList.add("is-voted");
      button.setAttribute("aria-label", `You're interested in ${topic.name}`);
    } else {
      button.textContent = "+1";
      button.setAttribute("aria-label", `+1 for ${topic.name}`);
      button.addEventListener("click", () => vote(topic, button));
    }

    item.append(name, count, button);
    return item;
  }

  function render() {
    const topics = state.topics;
    el.list.replaceChildren(...topics.map(renderTopic));
    el.list.hidden = topics.length === 0;
    el.empty.hidden = topics.length !== 0;
    el.total.textContent = topics.length === 0
      ? ""
      : `${topics.length} ${topics.length === 1 ? "topic" : "topics"}`;
  }

  async function loadTopics() {
    try {
      state.topics = await api("/api/topics");
      render();
    } catch (error) {
      setStatus(el.listStatus, error.message, "error");
    }
  }

  function focusTopic(id) {
    const item = el.list.querySelector(`li[data-id="${id}"]`);
    if (item) item.focus({ preventScroll: false });
  }

  // ---------- Actions ----------

  async function vote(topic, button) {
    button.disabled = true;
    button.classList.add("is-pending");
    button.textContent = "…";
    setStatus(el.listStatus, "");
    try {
      await api(`/api/topics/${topic.id}/vote`, { method: "POST" });
      setStatus(el.listStatus, `Added your +1 to “${topic.name}”.`, "success");
    } catch (error) {
      setStatus(el.listStatus, error.message, "error");
    }
    // Refresh either way: on a conflict or 404 the list is stale.
    await loadTopics();
    focusTopic(topic.id);
  }

  async function submitTopic(event) {
    event.preventDefault();
    const name = cleanText(el.input.value);

    if (!name) {
      el.input.setAttribute("aria-invalid", "true");
      setStatus(el.formStatus, "Enter a topic first.", "error");
      el.input.focus();
      return;
    }
    if (name.length > MAX_LENGTH) {
      el.input.setAttribute("aria-invalid", "true");
      setStatus(el.formStatus, `Keep it to ${MAX_LENGTH} characters or fewer.`, "error");
      return;
    }

    el.submit.disabled = true;
    setStatus(el.formStatus, "Adding…");
    try {
      const topic = await api("/api/topics", { method: "POST", body: { name } });
      el.input.value = "";
      updateCharCount();
      el.input.removeAttribute("aria-invalid");
      setStatus(el.formStatus, `Added “${topic.name}”.`, "success");
      state.highlightId = topic.id;
      await loadTopics();
      state.highlightId = null;
    } catch (error) {
      el.input.setAttribute("aria-invalid", "true");
      setStatus(el.formStatus, error.message, "error");
    } finally {
      el.submit.disabled = false;
      el.input.focus();
    }
  }

  function updateCharCount() {
    const length = el.input.value.length;
    el.charCount.textContent = String(length);
    el.hint.classList.toggle("is-near-limit", length >= MAX_LENGTH - 10);
  }

  async function logout() {
    el.logout.disabled = true;
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      // Fall through: the login page will show the right state either way.
    }
    window.location.assign("/login");
  }

  // ---------- Start ----------

  async function init() {
    el.form.addEventListener("submit", submitTopic);
    el.input.addEventListener("input", () => {
      updateCharCount();
      if (el.input.getAttribute("aria-invalid") === "true") {
        el.input.removeAttribute("aria-invalid");
        setStatus(el.formStatus, "");
      }
    });
    el.logout.addEventListener("click", logout);

    try {
      const me = await api("/api/me");
      state.csrfToken = me.csrf_token;
      el.userName.textContent = me.user.name;
    } catch (error) {
      if (error.status !== 401) setStatus(el.listStatus, error.message, "error");
      return;
    }
    await loadTopics();
    if (el.listStatus.textContent === "Loading topics…") setStatus(el.listStatus, "");
  }

  init();
})();
