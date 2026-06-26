// src/web/static/js/config.js
window.APP_CONFIG = {
    endpoints: {
        login: "/api/auth/login",
        register: "/api/auth/register",
        logout: "/api/auth/logout",
        me: "/api/auth/me",
    }
};

(function () {
    const COOKIE_NAME = "ui_lang";

    function getCookie(name) {
        const prefix = name + "=";
        const cookies = document.cookie.split(";").map((v) => v.trim());
        for (const c of cookies) {
            if (c.startsWith(prefix)) {
                return decodeURIComponent(c.slice(prefix.length));
            }
        }
        return "";
    }

    function setCookie(name, value, days = 365) {
        const expires = new Date(Date.now() + days * 86400000).toUTCString();
        document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
    }

    function getSupportedLanguages() {
        const dataEl = document.getElementById("app-languages-data");
        if (!dataEl) return ["ru"];

        try {
            const parsed = JSON.parse(dataEl.textContent || "[]");
            return Array.isArray(parsed)
                ? parsed.map((v) => String(v).trim().toLowerCase()).filter(Boolean)
                : ["ru"];
        } catch (e) {
            console.error("Failed to parse app languages", e);
            return ["ru"];
        }
    }

    function getCurrentLang(supported) {
        const fromCookie = getCookie(COOKIE_NAME) || getCookie("lang");
        if (supported.includes(fromCookie)) return fromCookie;

        const browserLang = String(navigator.language || "").trim().toLowerCase();
        if (supported.includes(browserLang)) return browserLang;

        const browserBaseLang = browserLang.split("-")[0];
        if (supported.includes(browserBaseLang)) return browserBaseLang;

        const htmlLang = (document.documentElement.getAttribute("lang") || "").toLowerCase();
        if (supported.includes(htmlLang)) return htmlLang;

        return supported[0] || "ru";
    }

    document.addEventListener("DOMContentLoaded", () => {
        const select = document.getElementById("langSwitch");
        if (!select) return;

        const supported = getSupportedLanguages();
        const currentLang = getCurrentLang(supported);

        select.value = currentLang;
        document.documentElement.setAttribute("lang", currentLang);

        select.addEventListener("change", () => {
            const newLang = String(select.value || "").trim().toLowerCase();
            if (!supported.includes(newLang)) return;

            setCookie(COOKIE_NAME, newLang);
            setCookie("lang", newLang);
            document.documentElement.setAttribute("lang", newLang);
            window.location.reload();
        });
    });
})();
