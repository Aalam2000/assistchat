// src/app/static/js/profile.js

// ──────────────────────────────────────────────────────────────────────────────
// ЛОГАУТ
document.addEventListener("DOMContentLoaded", () => {
    const logout = document.getElementById("logout-btn");
    logout?.addEventListener("click", async () => {
        try {
            const r = await fetch("/api/auth/logout", {method: "POST", credentials: "same-origin"});
            const data = await r.json().catch(() => ({}));
            if (data.redirect) window.location.href = data.redirect;
        } catch {
        }
    });
});


// ──────────────────────────────────────────────────────────────────────────────
// ПРОФИЛЬ (имя, язык, часовой пояс)
async function loadProfile() {
    try {
        const r = await fetch("/api/auth/me", {credentials: "same-origin"});
        if (!r.ok) throw new Error(String(r.status));
        const data = await r.json();
        const u = (data && data.user) || {};
        document.getElementById("profile-username").value = u.username ?? "";
        document.getElementById("profile-email").value = u.email ?? "";
    } catch (e) {
        document.getElementById("profile-status").textContent = "Ошибка загрузки профиля";
        console.error("[profile] loadProfile error:", e);
    }
}


async function saveProfile() {
    const btn = document.getElementById("btn-profile-save");
    const out = document.getElementById("profile-status");
    btn.disabled = true;
    out.textContent = "Сохранение...";
    try {
        const payload = {
            name: document.getElementById("profile-name").value.trim(),
            lang: document.getElementById("profile-lang").value.trim(),
            tz: document.getElementById("profile-tz").value.trim(),
        };
        const r = await fetch("/api/profile/update", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            credentials: "same-origin",
            body: JSON.stringify(payload)
        });
        out.textContent = r.ok ? "Сохранено" : "Ошибка сохранения";
    } catch (e) {
        out.textContent = "Ошибка сохранения";
        console.error("[profile] saveProfile error:", e);
    } finally {
        btn.disabled = false;
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// OPENAI доступ (режим, ключ, модель, история, голос)
function syncOpenAIModeVisibility() {
    const byok = document.getElementById("openai-mode-byok").checked;
    const keyInput = document.getElementById("openai-key");
    keyInput.disabled = !byok;
    keyInput.parentElement.style.opacity = byok ? "1" : ".6";
}

async function loadOpenAI() {
    try {
        const r = await fetch("/api/profile/openai", {credentials: "same-origin"});
        if (!r.ok) throw new Error(String(r.status));
        const data = await r.json();

        // режим
        const mode = (data.mode ?? "byok").toLowerCase();
        document.getElementById("openai-mode-byok").checked = (mode === "byok");
        document.getElementById("openai-mode-managed").checked = (mode === "managed");
        syncOpenAIModeVisibility();

        // поля
        document.getElementById("openai-key").value = data.key_masked ?? ""; // реальный ключ не показываем
        document.getElementById("openai-model").value = data.model ?? "gpt-4o-mini";
        document.getElementById("openai-history").value = String(data.history_limit ?? 20);
        document.getElementById("openai-voice").checked = !!data.voice_enabled;
    } catch (e) {
        document.getElementById("openai-status").textContent = "Ошибка загрузки настроек OpenAI";
        console.error("[profile] loadOpenAI error:", e);
    }
}

async function testOpenAI() {
    const btn = document.getElementById("btn-openai-test");
    const out = document.getElementById("openai-status");
    btn.disabled = true;
    out.textContent = "Проверка ключа...";
    try {
        const payload = {
            mode: document.getElementById("openai-mode-byok").checked ? "byok" : "managed",
            key: document.getElementById("openai-key").value.trim() || null,
            model: document.getElementById("openai-model").value.trim() || "gpt-4o-mini",
        };
        const r = await fetch("/api/profile/openai/test", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            credentials: "same-origin",
            body: JSON.stringify(payload)
        });
        const data = await r.json().catch(() => ({}));
        out.textContent = r.ok
            ? (data.message || "Ключ валиден")
            : (data.error || "Ошибка проверки");
    } catch (e) {
        out.textContent = "Ошибка проверки";
        console.error("[profile] testOpenAI error:", e);
    } finally {
        btn.disabled = false;
    }
}

async function saveOpenAI() {
    const btn = document.getElementById("btn-openai-save");
    const out = document.getElementById("openai-status");
    btn.disabled = true;
    out.textContent = "Сохранение...";
    try {
        const payload = {
            mode: document.getElementById("openai-mode-byok").checked ? "byok" : "managed",
            key: document.getElementById("openai-key").value.trim() || null,
            model: document.getElementById("openai-model").value.trim() || "gpt-4o-mini",
            history_limit: parseInt(document.getElementById("openai-history").value || "20", 10),
            voice_enabled: document.getElementById("openai-voice").checked,
        };
        const r = await fetch("/api/profile/openai/save", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            credentials: "same-origin",
            body: JSON.stringify(payload)
        });
        out.textContent = r.ok ? "Сохранено" : "Ошибка сохранения";
    } catch (e) {
        out.textContent = "Ошибка сохранения";
        console.error("[profile] saveOpenAI error:", e);
    } finally {
        btn.disabled = false;
    }
}


// ──────────────────────────────────────────────────────────────────────────────
// БОТ: глобальный статус и переключатель
async function loadBotStatus() {
    const out = document.getElementById("bot-summary");
    const btn = document.getElementById("btn-bot-toggle");
    try {
        const r = await fetch("/api/status", {credentials: "same-origin"});
        if (!r.ok) throw new Error(String(r.status));
        const d = await r.json();
        const on = !!d.on;
        out.textContent = `Статус: ${on ? "активен" : "пауза"} · сервисы ${d.services_active}/${d.services_total} · TG ${d.tg_active}/${d.tg_total}`;
        btn.textContent = on ? "Выключить" : "Включить";
        btn.dataset.state = on ? "on" : "off";
    } catch (e) {
        out.textContent = "Статус: ошибка";
        console.error("[profile] loadBotStatus error:", e);
    }
}

async function toggleBot() {
    const btn = document.getElementById("btn-bot-toggle");
    const out = document.getElementById("bot-status");
    const want = (btn.dataset.state === "on") ? "pause" : "activate";
    btn.disabled = true;
    out.textContent = "Проверяем ресурсы...";

    try {
        // 1) префлайт: показываем статусы, но не блокируем запуск, если есть готовые
        const pre = await fetch("/api/preflight", {credentials: "same-origin"});
        const preData = await pre.json();
        if (!pre.ok || !preData.ok) throw new Error("PREFLIGHT");

        const results = preData.results || {};
        const entries = Object.entries(results);
        const ready = entries.filter(([, r]) => r && r.ok);
        const notReady = entries.filter(([, r]) => !r || !r.ok);

        out.innerHTML = entries.map(([rid, r]) =>
            `${rid}: ${r && r.ok ? "✅ OK" : `❌ ${r && r.reason || "ERR"}`}`
        ).join("<br>");

        if (want === "activate") {
            if (ready.length === 0) {
                out.innerHTML += "<br>Нет готовых ресурсов для запуска.";
                return;
            }
            // 2) запускаем только готовые (бекенд сам подхватит active/ready)
            const resp = await fetch("/api/bot/start", {
                method: "POST",
                credentials: "same-origin"
            });
            const data = await resp.json();
            if (!resp.ok || !data.ok) throw new Error("START");
            out.innerHTML += `<br>Запущено: ${Array.isArray(data.started) ? data.started.length : 0}`;
            btn.dataset.state = "on";
            btn.textContent = "Пауза";
        } else {
            const resp = await fetch("/api/bot/stop", {
                method: "POST",
                credentials: "same-origin"
            });
            const data = await resp.json();
            if (!resp.ok || !data.ok) throw new Error("STOP");
            out.innerHTML += `<br>Остановлено: ${Array.isArray(data.stopped) ? data.stopped.length : 0}`;
            btn.dataset.state = "off";
            btn.textContent = "Включить";
        }
    } catch (e) {
        out.textContent = "Ошибка: " + (e && e.message ? e.message : e);
        console.error("[profile] toggleBot error:", e);
    } finally {
        btn.disabled = false;
    }
}


// ──────────────────────────────────────────────────────────────────────────────
// ИНИЦИАЛИЗАЦИЯ
document.addEventListener("DOMContentLoaded", () => {
    // профиль
    loadProfile();
    // document.getElementById("btn-profile-save")?.addEventListener("click", saveProfile);

    // openai
    loadOpenAI();
    document.getElementById("openai-mode-byok")?.addEventListener("change", syncOpenAIModeVisibility);
    document.getElementById("openai-mode-managed")?.addEventListener("change", syncOpenAIModeVisibility);
    document.getElementById("btn-openai-test")?.addEventListener("click", testOpenAI);
    document.getElementById("btn-openai-save")?.addEventListener("click", saveOpenAI);

});


// бот (глобально)
loadBotStatus();
document.getElementById("btn-bot-toggle")?.addEventListener("click", toggleBot);

