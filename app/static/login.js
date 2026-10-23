(() => {
  "use strict";

  const ERROR_MESSAGES = {
    google: "Google sign-in didn't complete. Please try again.",
    unverified: "Your Google account's email address isn't verified, so we can't sign you in.",
    not_configured: "Google sign-in isn't configured on this server.",
  };

  const el = {
    error: document.getElementById("login-error"),
    google: document.getElementById("google-signin"),
    googleUnavailable: document.getElementById("google-unavailable"),
    devSection: document.getElementById("dev-login"),
    devForm: document.getElementById("dev-login-form"),
    devName: document.getElementById("dev-name"),
    devStatus: document.getElementById("dev-status"),
  };

  let csrfToken = "";

  function showError(message) {
    el.error.textContent = message;
    el.error.hidden = false;
  }

  async function devLogin(event) {
    event.preventDefault();
    const name = el.devName.value.replace(/\s+/g, " ").trim();
    if (!name) {
      el.devName.setAttribute("aria-invalid", "true");
      el.devStatus.textContent = "Enter a display name.";
      el.devStatus.className = "status is-error";
      el.devName.focus();
      return;
    }

    const button = el.devForm.querySelector("button");
    button.disabled = true;
    el.devStatus.textContent = "";
    try {
      const response = await fetch("/auth/dev-login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: JSON.stringify({ name }),
      });
      if (response.ok) {
        window.location.assign("/");
        return;
      }
      const data = await response.json().catch(() => null);
      el.devStatus.textContent = data && typeof data.detail === "string" ? data.detail : "Sign-in failed.";
    } catch {
      el.devStatus.textContent = "Couldn't reach the server. Try again.";
    }
    el.devStatus.className = "status is-error";
    el.devName.setAttribute("aria-invalid", "true");
    button.disabled = false;
  }

  async function init() {
    const code = new URLSearchParams(window.location.search).get("error");
    if (code) showError(ERROR_MESSAGES[code] || "Sign-in failed. Please try again.");

    let options;
    try {
      const response = await fetch("/auth/options", { credentials: "same-origin" });
      options = await response.json();
    } catch {
      showError("Couldn't reach the server. Refresh to try again.");
      return;
    }

    csrfToken = options.csrf_token;
    el.google.hidden = !options.google_enabled;
    el.googleUnavailable.hidden = options.google_enabled;
    el.devSection.hidden = !options.dev_login_enabled;

    el.devForm.addEventListener("submit", devLogin);
    el.devName.addEventListener("input", () => el.devName.removeAttribute("aria-invalid"));
  }

  init();
})();
