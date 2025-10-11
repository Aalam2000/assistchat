// src/app/static/js/auth.js
document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");
  const logoutBtn = document.getElementById("logout-btn");

  // переключение форм
  const loginPanel = document.getElementById("tab-login");
  const registerPanel = document.getElementById("tab-register");
  document.getElementById("switch-to-register")?.addEventListener("click", (e) => {
    e.preventDefault();
    loginPanel.classList.remove("active");
    registerPanel.classList.add("active");
  });
  document.getElementById("switch-to-login")?.addEventListener("click", (e) => {
    e.preventDefault();
    registerPanel.classList.remove("active");
    loginPanel.classList.add("active");
  });

  // вход
  loginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("login-error");
    err.textContent = "";
    const fd = new FormData(loginForm);
    const payload = {
      username: fd.get("username")?.trim(),
      password: fd.get("password")
    };
    try {
      const { ok, error } = await apiPost(window.APP_CONFIG.endpoints.login, payload);
      if (ok) window.location.reload();
      else err.textContent = error || "Ошибка входа";
    } catch (ex) {
      err.textContent = "Ошибка входа";
    }
  });

  // регистрация
  registerForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("register-error");
    err.textContent = "";
    const fd = new FormData(registerForm);
    const payload = {
      username: fd.get("username")?.trim(),
      password: fd.get("password"),
    };
    const email = fd.get("email")?.trim();
    if (email) payload.email = email;

    try {
      const { ok, error } = await apiPost(window.APP_CONFIG.endpoints.register, payload);
      if (ok) window.location.reload();
      else err.textContent = error || "Ошибка регистрации";
    } catch (ex) {
      err.textContent = "Ошибка регистрации";
    }
  });

  // выход
  logoutBtn?.addEventListener("click", async () => {
    try {
      const r = await fetch(window.APP_CONFIG.endpoints.logout, {
        method: "POST",
        credentials: "same-origin"
      });
      await r.json().catch(() => ({}));
    } finally {
      window.location.reload();
    }
  });
});
