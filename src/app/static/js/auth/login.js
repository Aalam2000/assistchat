// src/app/static/js/auth/login.js
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("login-form");
  const err = document.getElementById("login-error");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.textContent = "";
    const fd = new FormData(form);
    const payload = {
      username: fd.get("username")?.trim(),
      password: fd.get("password")
    };
    try {
      const { ok, redirect, error } = await apiPost(window.APP_CONFIG.endpoints.login, payload);
      if (ok && redirect) window.location.href = redirect;
      else err.textContent = error || "Ошибка входа";
    } catch (ex) {
      err.textContent = ex.error || "Ошибка входа";
    }
  });
});
