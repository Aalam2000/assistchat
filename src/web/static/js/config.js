// src/web/static/js/config.js
window.APP_CONFIG = {
    endpoints: {
        login: "/api/auth/login",
        register: "/api/auth/register",
        logout: "/api/auth/logout",
        me: "/api/auth/me",
    }
};

document.addEventListener("DOMContentLoaded", () => {
    const switcher = document.getElementById("i18n-switcher");
    const btn = document.getElementById("i18n-switcher-btn");
    const menu = document.getElementById("i18n-switcher-menu");
    const waitModal = document.getElementById("lang-wait");

    if (!switcher || !btn || !menu) return;

    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const open = menu.classList.toggle("hidden");
        btn.setAttribute("aria-expanded", open ? "false" : "true");
    });

    document.addEventListener("click", () => {
        menu.classList.add("hidden");
        btn.setAttribute("aria-expanded", "false");
    });

    menu.querySelectorAll("a[data-lang]").forEach((link) => {
        link.addEventListener("click", () => {
            if (waitModal) {
                waitModal.classList.remove("hidden");
            }
        });
    });
});
