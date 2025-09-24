// src/app/static/js/config.js
window.APP_CONFIG = {
  endpoints: {
    login: "/api/auth/login",
    register: "/api/auth/register",
    logout: "/api/auth/logout",
    me: "/api/auth/me",
  }
};
document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("i18n-toggle");
  const waitModal = document.getElementById("lang-wait");
  if (btn && waitModal) {
    btn.addEventListener("click", () => {
      waitModal.classList.remove("hidden");
    });
  }
});
