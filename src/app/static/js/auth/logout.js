document.addEventListener("DOMContentLoaded", () => {
  const logout = document.getElementById("logout-btn");
  logout?.addEventListener("click", async () => {
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
