// src/app/static/js/profile.js
document.addEventListener("DOMContentLoaded", () => {
  const logout = document.getElementById("logout-btn");
  logout?.addEventListener("click", async () => {
    try {
      const { ok, redirect } = await apiPost(window.APP_CONFIG.endpoints.logout, {});
      if (ok && redirect) window.location.href = redirect;
    } catch { /* ignore */ }
  });
});
