const TOKEN_KEY = "grievance_access_token";

function showMessage(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("is-error", isError);
  element.classList.toggle("is-success", !isError);
}

async function responseMessage(response) {
  const body = await response.json().catch(() => ({}));
  if (Array.isArray(body.detail)) {
    return body.detail.map((issue) => issue.msg).join(" ");
  }
  return body.detail || "Something went wrong. Please try again.";
}

function setupRegisterForm() {
  const form = document.querySelector("#register-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.querySelector("#form-message");
    const submit = form.querySelector("button[type='submit']");
    const payload = Object.fromEntries(new FormData(form).entries());

    submit.disabled = true;
    showMessage(message, "Creating your account…");
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        showMessage(message, await responseMessage(response), true);
        return;
      }
      showMessage(message, "Account created. You can now sign in.");
      form.reset();
      window.setTimeout(() => {
        window.location.assign("/login");
      }, 700);
    } catch {
      showMessage(message, "Could not connect to the portal. Check that the server is running.", true);
    } finally {
      submit.disabled = false;
    }
  });
}

function setupLoginForm() {
  const form = document.querySelector("#login-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.querySelector("#form-message");
    const submit = form.querySelector("button[type='submit']");
    const payload = Object.fromEntries(new FormData(form).entries());

    submit.disabled = true;
    showMessage(message, "Signing you in…");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        showMessage(message, await responseMessage(response), true);
        return;
      }
      const data = await response.json();
      sessionStorage.setItem(TOKEN_KEY, data.access_token);
      const dashboardByRole = {
        citizen: "/citizen/dashboard",
        admin: "/admin/dashboard",
        officer: "/officer/dashboard",
      };
      window.location.assign(dashboardByRole[data.user.role] || "/login");
    } catch {
      showMessage(message, "Could not connect to the portal. Check that the server is running.", true);
    } finally {
      submit.disabled = false;
    }
  });
}

async function setupDashboard() {
  if (document.body.dataset.authPage !== "dashboard") return;
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (!token) {
    window.location.replace("/login");
    return;
  }

  const dashboardMessage = document.querySelector("#dashboard-message");
  try {
    const response = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.status === 401) {
      sessionStorage.removeItem(TOKEN_KEY);
      window.location.replace("/login");
      return;
    }
    if (!response.ok) {
      showMessage(dashboardMessage, "Could not load your profile. Please try again.", true);
      return;
    }
    const user = await response.json();
    document.querySelector("#citizen-name").textContent = user.name;
  } catch {
    showMessage(dashboardMessage, "Could not connect to the portal. Check that the server is running.", true);
  }

  document.querySelector("#logout-button").addEventListener("click", async () => {
    const logoutToken = sessionStorage.getItem(TOKEN_KEY);
    if (logoutToken) {
      try {
        await fetch("/api/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${logoutToken}` },
        });
      } catch {
        showMessage(dashboardMessage, "Could not contact the server to sign out. Please try again.", true);
        return;
      }
    }
    sessionStorage.removeItem(TOKEN_KEY);
    window.location.assign("/");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupRegisterForm();
  setupLoginForm();
  setupDashboard();
});
