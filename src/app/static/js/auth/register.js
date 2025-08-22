// src/app/static/js/auth/register.js
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("register-form");
  const err = document.getElementById("register-error");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.textContent = "";
    const fd = new FormData(form);
    const payload = {
      username: fd.get("username")?.trim(),
      email: fd.get("email")?.trim(),
      password: fd.get("password")
    };
    try {
      const { ok, redirect, error } = await apiPost(window.APP_CONFIG.endpoints.register, payload);
      if (ok && redirect) window.location.href = redirect;
      else err.textContent = error || "Ошибка регистрации";
    } catch (ex) {
      err.textContent = ex.error || "Ошибка регистрации";
    }
  });
});
