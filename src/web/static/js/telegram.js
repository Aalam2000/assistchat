// src/web/static/js/telegram.js

document.addEventListener("DOMContentLoaded", () => {
    const id = TG_RID;
    if (!id) {
        console.error("[telegram] missing resource id");
        return;
    }

    const $ = (s) => document.querySelector(s);

    const appId = $("#tgAppId");
    const appHash = $("#tgAppHash");
    const phone = $("#tgPhone");
    const label = $("#tgLabel");
    const prompt = $("#tgPrompt");
    const rules = $("#tgRules");
    const auto = $("#tgAuto");
    const whitelist = $("#tgWhitelist");
    const blacklist = $("#tgBlacklist");
    const historyLen = $("#tgHistory");
    const btnActivate = $("#btnActivate");
    const btnSave = $("#btnSave");

    let lastPayload = null;
    let botEnabled = false;

    // ───────────────────────────────
    // Загрузка данных ресурса
    // ───────────────────────────────
    async function loadData() {
        try {
            const r = await fetch(`/api/resources/${id}`, {credentials: "same-origin"});
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "load failed");

            const meta = data.meta_json || {};
            const creds = meta.creds || {};
            const extra = meta.extra || {};
            const prompts = meta.prompts || {};
            const lists = meta.lists || {};
            const limits = meta.limits || {};

            appId.value = creds.app_id || "";
            appHash.value = creds.app_hash || "";
            phone.value = extra.phone_e164 || creds.phone || "";
            label.value = data.label || "";
            prompt.value = prompts.settings || "";
            rules.value = prompts.rules_common || "";
            auto.value = prompts.rules_dialog || "";
            whitelist.value = (lists.whitelist || []).join(", ");
            blacklist.value = (lists.blacklist || []).join(", ");
            historyLen.value = limits.history_length ?? 20;
        } catch (err) {
            console.error("[telegram] load error:", err);
            alert("Ошибка загрузки данных ресурса");
        }
    }

    // ───────────────────────────────
    // Сохранение изменений
    // ───────────────────────────────
    async function saveData() {
        function parseList(s) {
            return (s || "")
                .split(/[\n,;]+|,\s*/g)
                .map((x) => x.trim())
                .filter(Boolean);
        }

        const meta = {
            creds: {
                app_id: appId.value.trim(),
                app_hash: appHash.value.trim(),
            },
            extra: {
                phone_e164: phone.value.trim(),
                allow_groups: true,
            },
            lists: {
                whitelist: parseList(whitelist.value),
                blacklist: parseList(blacklist.value),
            },
            limits: {
                history_length: Number(historyLen.value || 20),
            },
            prompts: {
                settings: prompt.value.trim(),
                rules_common: rules.value.trim(),
                rules_dialog: auto.value.trim(),
            },
        };

        const payload = {
            label: label.value.trim() || "Telegram ассистент",
            meta_json: meta,
        };

        try {
            const r = await fetch(`/api/resources/${id}`, {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify(payload),
            });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "save failed");
            alert("Настройки сохранены");
        } catch (err) {
            console.error("[telegram] save error:", err);
            alert("Ошибка сохранения настроек");
        }
    }

    // ───────────────────────────────
    // Активация Telegram
    // ───────────────────────────────
    async function activate() {
        const payload = {
            phone: phone.value.trim(),
            app_id: appId.value.trim(),
            app_hash: appHash.value.trim(),
            code: null,
        };

        if (!payload.phone || !payload.app_id || !payload.app_hash) {
            alert("Заполните App ID, App Hash и телефон");
            return;
        }

        try {
            const r = await fetch(`/api/resource/${id}/activate`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify(payload),
            });

            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "Ошибка активации");

            // сервер сообщил, что код отправлен
            if (data.need_code) {
                lastPayload = payload; // сохраняем данные для подтверждения
                openCodeModal();       // открываем модалку
                // обновляем данные из БД — чтобы meta_json включил phone_code_hash
                await loadData();
            } else if (data.activated) {
                alert("Telegram активирован!");
                await loadData();
            }
        } catch (err) {
            console.error("[telegram] activate error:", err);
            alert("Ошибка при активации Telegram");
        }
    }


    // ───────────────────────────────
    // Модальное окно подтверждения Telegram
    // ───────────────────────────────
    const tgCodeModal = document.getElementById("tgCodeModal");
    const codeInput = document.getElementById("tgCodeInput");
    const btnConfirmCode = document.getElementById("btnConfirmCode");
    const btnCancelCode = document.getElementById("btnCancelCode");

    function openCodeModal() {
        tgCodeModal.classList.remove("hidden");
        codeInput.focus();
    }

    function closeCodeModal() {
        tgCodeModal.classList.add("hidden");
        codeInput.value = "";
    }


    async function confirmCode() {
        const code = codeInput.value.trim();
        if (!code) {
            alert("Введите код подтверждения");
            return;
        }

        try {
            const r = await fetch(`/api/resource/${id}/activate`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify({
                    phone: phone.value.trim(),
                    app_id: appId.value.trim(),
                    app_hash: appHash.value.trim(),
                    code,
                }),
            });

            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "Ошибка подтверждения");

            if (data.activated) {
                alert("Telegram успешно активирован!");
                closeCodeModal();
                await loadData();
            }
        } catch (err) {
            console.error("[telegram] confirm error:", err);
            alert("Ошибка при подтверждении кода");
        }
    }


    // ───────────────────────────────
    // Привязка событий
    // ───────────────────────────────
    btnActivate?.addEventListener("click", activate);
    btnConfirmCode?.addEventListener("click", confirmCode);
    btnCancelCode?.addEventListener("click", closeCodeModal);
    btnSave?.addEventListener("click", saveData);
    // ───────────────────────────────
    // Управление БОТом
    // ───────────────────────────────
    async function loadBotStatus() {
        const out = document.getElementById("tgBotStatus");
        const btn = document.getElementById("btnToggleBot");
        try {
            const r = await fetch("/api/bot/status", {credentials: "same-origin"});
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "load failed");
            const enabled = !!data.bot_enabled;
            out.textContent = `БОТ: ${enabled ? "🟢 активен" : "🔴 выключен"}`;
            btn.textContent = enabled ? "💡 Выключить БОТ" : "💡 Включить БОТ";
            btn.dataset.state = enabled ? "on" : "off";
        } catch (err) {
            console.error("[telegram] loadBotStatus error:", err);
            out.textContent = "БОТ: ошибка статуса";
        }
    }

    async function toggleBot() {
        const btn = document.getElementById("btnToggleBot");
        const out = document.getElementById("tgBotStatus");
        btn.disabled = true;
        try {
            const r = await fetch("/api/bot/toggle", {
                method: "POST",
                credentials: "same-origin",
            });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "toggle failed");
            const enabled = !!data.bot_enabled;
            out.textContent = `БОТ: ${enabled ? "🟢 активен" : "🔴 выключен"}`;
            btn.textContent = enabled ? "💡 Выключить БОТ" : "💡 Включить БОТ";
        } catch (err) {
            console.error("[telegram] toggleBot error:", err);
            out.textContent = "Ошибка переключения БОТа";
        } finally {
            btn.disabled = false;
        }
    }

    // ───────────────────────────────
    // Управление ресурсом
    // ───────────────────────────────
    async function loadResStatus() {
        const out = document.getElementById("tgResStatus");
        const btn = document.getElementById("btnToggleStatus");
        try {
            const r = await fetch(`/api/resources/${id}`, {credentials: "same-origin"});
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "load failed");
            const st = data.status || "—";
            out.textContent = `РЕСУРС: ${st}`;
            btn.textContent = st === "active" ? "💡 Остановить ресурс" : "💡 Включить ресурс";
        } catch (err) {
            console.error("[telegram] loadResStatus error:", err);
            out.textContent = "РЕСУРС: ошибка статуса";
        }
    }

    async function toggleResStatus() {
        const btn = document.getElementById("btnToggleStatus");
        const out = document.getElementById("tgResStatus");
        btn.disabled = true;
        try {
            const action = btn.textContent.includes("Остановить") ? "pause" : "activate";
            const r = await fetch("/api/resources/toggle", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify({id, action}),
            });
            const data = await r.json();
            if (!r.ok || !data.ok) {
                const issues = Array.isArray(data.issues) && data.issues.length ? " (" + data.issues.join(", ") + ")" : "";
                const msg = data.message || data.error || "Ошибка переключения ресурса";
                // выводим строго в готовую строку статуса
                out.textContent = `РЕСУРС: 🔴 ${msg}${issues}`;
                btn.textContent = "💡 Включить ресурс";
                return;
            }


            const st = data.status || (action === "activate" ? "active" : "paused");
            out.textContent = `РЕСУРС: ${st}`;
            btn.textContent = st === "active" ? "💡 Остановить ресурс" : "💡 Включить ресурс";
        } catch (err) {
            console.error("[telegram] toggleResStatus error:", err);
            out.textContent = "Ошибка переключения ресурса";
        } finally {
            btn.disabled = false;
        }
    }

    // ───────────────────────────────
    // Подключаем кнопки
    // ───────────────────────────────
    document.getElementById("btnToggleBot")?.addEventListener("click", toggleBot);
    document.getElementById("btnToggleStatus")?.addEventListener("click", toggleResStatus);

    // загружаем состояния при открытии страницы
    loadBotStatus();
    loadResStatus();


    loadData();
});
