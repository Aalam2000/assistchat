document.addEventListener("DOMContentLoaded", () => {
    const id = BOT_RID;
    if (!id) return;

    const $ = (s) => document.querySelector(s);

    const label       = $("#botLabel");
    const botToken    = $("#botToken");
    const btnSave     = $("#btnSave");
    const btnActivate = $("#btnActivate");
    const btnToggle   = $("#btnToggleStatus");
    const resStatus   = $("#botResStatus");
    const msgBox      = $("#botMsg");

    function showMsg(text, ok = true) {
        if (!msgBox) return;
        msgBox.textContent = text;
        msgBox.style.display = "block";
        msgBox.style.background = ok ? "#d4edda" : "#f8d7da";
        msgBox.style.color = ok ? "#155724" : "#721c24";
    }

    function buildMeta() {
        return {
            creds: {
                bot_token: (botToken.value || "").trim(),
            },
        };
    }

    async function loadData() {
        const r = await fetch(`/api/providers/resources/list`, { credentials: "same-origin" });
        const data = await r.json();
        if (!r.ok || !data.ok) throw new Error(data.error || "load failed");

        const item = (data.items || []).find((x) => x.id === id);
        if (!item) throw new Error("resource not found");

        const rawCreds = (item.meta || item.meta_json || {}).creds || {};
        label.value    = item.label || "";
        // Токен не показываем в открытом виде — только placeholder если есть
        if (rawCreds.bot_token) {
            botToken.placeholder = "••••••••••• (сохранён)";
        }
    }

    async function saveData() {
        const payload = {
            label:     (label.value || "").trim() || "Telegram Bot",
            meta_json: buildMeta(),
        };
        const r = await fetch(`/api/telegram_bot/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify(payload),
        });
        const data = await r.json();
        if (!r.ok || !data.ok) throw new Error(data.error || "save failed");
    }

    async function loadResStatus() {
        try {
            const r = await fetch(`/api/telegram_bot/${id}/status`, { credentials: "same-origin" });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error();

            const status  = data.resource_status ?? "—";
            const running = data.running ? " (работает)" : "";
            const phase   = data.phase ? ` (${data.phase})` : "";
            const icon    = data.running ? "🟢" : (data.active ? "🟡" : "🔴");

            resStatus.textContent = `РЕСУРС: ${status}${phase} ${icon}`;
            btnToggle.textContent = status === "active" ? "💡 Остановить" : "💡 Включить";
            btnToggle.dataset.enabled = status === "active" ? "1" : "0";

            if (data.error_message) {
                showMsg(data.error_message, false);
            }
        } catch {
            resStatus.textContent = "РЕСУРС: ошибка статуса";
        }
    }

    async function activate() {
        try { await saveData(); } catch (e) {
            showMsg("Сохрани Bot Token перед проверкой", false);
            return;
        }
        btnActivate.disabled = true;
        btnActivate.textContent = "Проверяю…";
        try {
            const r = await fetch(`/api/telegram_bot/${id}/activate`, {
                method: "POST",
                credentials: "same-origin",
            });
            const data = await r.json();
            showMsg(data.message || (data.ok ? "Подключено" : "Ошибка"), data.ok);
            if (data.ok) await loadData();
            await loadResStatus();
        } finally {
            btnActivate.disabled = false;
            btnActivate.textContent = "Проверить и подключить";
        }
    }

    async function toggleStatus() {
        btnToggle.disabled = true;
        try {
            const enabled = btnToggle.dataset.enabled === "1";
            const action  = enabled ? "stop" : "enable";
            const r = await fetch(`/api/telegram_bot/${id}/${action}`, {
                method: "POST",
                credentials: "same-origin",
            });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.message || "toggle failed");
            await loadResStatus();
        } catch (e) {
            showMsg(String(e), false);
        } finally {
            btnToggle.disabled = false;
        }
    }

    // ── события ──────────────────────────────────────────────────────────

    btnSave?.addEventListener("click", async () => {
        try {
            await saveData();
            showMsg("Сохранено");
            await loadData();
        } catch (e) {
            showMsg("Ошибка сохранения: " + e, false);
        }
    });

    btnActivate?.addEventListener("click", activate);
    btnToggle?.addEventListener("click", toggleStatus);

    // ── инициализация ────────────────────────────────────────────────────

    (async () => {
        try {
            await loadData();
            await loadResStatus();
        } catch (e) {
            console.error("[telegram_bot] init error:", e);
            showMsg("Ошибка загрузки ресурса", false);
        }
    })();
});
