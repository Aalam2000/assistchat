// src/web/static/js/resources.js (адаптирован под новую архитектуру)

async function loadResources() {
    const tbody = document.getElementById("resources-tbody");
    try {
        const r = await fetch("/api/providers/resources/list", { credentials: "same-origin" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        const items = data.items || [];

        tbody.innerHTML = "";

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="10">Нет доступных провайдеров</td></tr>`;
            return;
        }

        for (const it of items) {
            const creds = it.meta?.creds || {};
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${it.id}</td>
                <td>${it.provider}</td>
                <td>${it.label || "—"}</td>
                <td>${creds.app_id || "—"}</td>
                <td>${creds.app_hash || "—"}</td>
                <td>${creds.phone || "—"}</td>
                <td>${it.status || "—"}</td>
                <td>${it.meta?.phase || "—"}</td>
                <td>${it.meta?.error || "—"}</td>
                <td>
                    <button class="btn res-toggle" data-id="${it.id}" data-provider="${it.provider}" data-status="${it.status}">
                        ${it.status === "active" ? "Пауза" : "Активировать"}
                    </button>
                    <button class="btn res-settings" data-id="${it.id}" data-provider="${it.provider}">Открыть</button>
                </td>
            `;
            tbody.appendChild(tr);
        }

    } catch (e) {
        console.error("[resources] loadResources error:", e);
        tbody.innerHTML = `<tr><td colspan="10">Ошибка загрузки</td></tr>`;
    }
}

window.reloadResources = loadResources;

function bindResourceActions() {
    const tbody = document.getElementById("resources-tbody");
    tbody.addEventListener("click", async (e) => {
        // переключение статуса
        const btnToggle = e.target.closest(".res-toggle");
        if (btnToggle) {
            const provider = btnToggle.dataset.provider;
            const current = btnToggle.dataset.status;
            const want = current === "active" ? "pause" : "activate";

            btnToggle.disabled = true;
            try {
                const r = await fetch(`/api/${provider}/${want}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    credentials: "same-origin",
                });
                const data = await r.json().catch(() => ({}));

                if (!r.ok) {
                    alert("Ошибка: " + (data.error || "toggle failed"));
                    return;
                }

                const next = data.status || (want === "activate" ? "active" : "paused");
                btnToggle.textContent = next === "active" ? "Пауза" : "Активировать";
                btnToggle.dataset.status = next;
            } catch (err) {
                alert("Ошибка переключения");
                console.error("[resources] toggle error:", err);
            } finally {
                btnToggle.disabled = false;
            }
            return;
        }

        // открыть страницу провайдера
        const btnSettings = e.target.closest(".res-settings");
        if (btnSettings) {
            const provider = btnSettings.dataset.provider;
            window.location.href = `/resources/${provider}`;
        }
    });
}

window.addEventListener("DOMContentLoaded", () => {
    loadResources();
    bindResourceActions();
});
