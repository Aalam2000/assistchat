// src/app/static/js/resources.js

async function loadResources() {
    const tbody = document.getElementById("resources-tbody");
    try {
        const r = await fetch("/api/resources/list", {credentials: "same-origin"});
        if (!r.ok) {
            throw new Error("HTTP " + r.status);
        }
        const data = await r.json();
        const items = data.items || [];
        tbody.innerHTML = "";

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="6">Пока нет ни одного ресурса</td></tr>`;
            return;
        }

        for (const it of items) {
            const tr = document.createElement("tr");
            const btnText = it.status === "active" ? "Пауза" : "Активировать";

            tr.innerHTML = `
              <td>${it.provider ?? ""}</td>
              <td>${it.label ?? ""}</td>
              <td class="status">${it.status ?? ""}</td>
              <td>${it.phase ?? ""}</td>
              <td>${it.last_error_code ?? "—"}</td>
              <td>
                <button class="btn res-toggle" data-id="${it.id}">${btnText}</button>
                <a class="btn" href="/resources/${it.id}">Настроить</a>
              </td>
            `;
            tbody.appendChild(tr);
        }
    } catch (e) {
        console.error("[resources] loadResources error:", e);
        tbody.innerHTML = `<tr><td colspan="6">Ошибка загрузки</td></tr>`;
    }
}

window.reloadResources = loadResources;

function bindResourceActions() {
    const tbody = document.getElementById("resources-tbody");
    tbody.addEventListener("click", async (e) => {
        const btn = e.target.closest(".res-toggle");
        if (!btn) return;

        const id = btn.dataset.id;
        const row = btn.closest("tr");
        const statusCell = row.querySelector(".status");
        const current = statusCell.textContent.trim();
        const want = current === "active" ? "pause" : "activate";

        btn.disabled = true;
        try {
            const r = await fetch("/api/resources/toggle", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify({id, action: want})
            });
            const data = await r.json().catch(() => ({}));

            if (!r.ok) {
                alert("Ошибка: " + (data.error || "toggle failed"));
                return;
            }

            const next = data.status || (want === "activate" ? "active" : "paused");
            statusCell.textContent = next;
            btn.textContent = (next === "active") ? "Пауза" : "Активировать";
        } catch (err) {
            alert("Ошибка переключения");
            console.error("[resources] toggle error:", err);
        } finally {
            btn.disabled = false;
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    loadResources();
    bindResourceActions();
});


document.addEventListener("DOMContentLoaded", () => {
    const $ = (sel) => document.querySelector(sel);

    const modal = $("#addResourceModal");
    const btnOpen = $("#btnAddResource");
    const btnCancel = $("#addResCancel");
    const btnSubmit = $("#addResSubmit");
    const selProv = $("#provSelect");
    const inpLabel = $("#resLabel");
    const txtMeta = $("#metaEditor");
    const elHelp = $("#provHelp");

    const state = {providers: [], byKey: {}};

    const open = () => modal.classList.remove("hidden");
    const close = () => modal.classList.add("hidden");

    async function fetchProviders() {
        const r = await fetch("/api/providers", {credentials: "same-origin"});
        const data = await r.json();
        if (!data.ok) throw new Error("Failed to load providers");
        state.providers = data.providers || [];
        state.byKey = Object.fromEntries(state.providers.map(p => [p.key, p]));
    }

    function fillProviderSelect() {
        selProv.innerHTML = "";
        state.providers.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p.key;
            opt.textContent = p.name || p.key;
            selProv.appendChild(opt);
        });
    }

    function renderTemplateFor(provKey) {
        const p = state.byKey[provKey];
        if (!p) return;
        if (!inpLabel.value) inpLabel.value = p.name || provKey;
        elHelp.textContent = p.help && Object.keys(p.help).length ? JSON.stringify(p.help, null, 2) : "—";
        txtMeta.value = JSON.stringify(p.template || {}, null, 2);
    }

    async function onOpenClick() {
        try {
            await fetchProviders();
            fillProviderSelect();
            inpLabel.value = "";
            renderTemplateFor(selProv.value);
            open();
        } catch (e) {
            alert("Не удалось загрузить список провайдеров");
            console.error(e);
        }
    }

    function onProviderChange() {
        renderTemplateFor(selProv.value);
    }

    async function onSubmit() {
        let meta;
        try {
            meta = JSON.parse(txtMeta.value);
        } catch (e) {
            alert("Ошибка в meta_json: " + e.message);
            return;
        }

        const payload = {
            provider: selProv.value,
            label: inpLabel.value.trim() || selProv.value,
            meta_json: meta,
        };
        const r = await fetch("/api/resources/add", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            credentials: "same-origin",
            body: JSON.stringify(payload),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok || !data.ok) {
            alert("Не удалось создать ресурс: " + (data.error || "unknown"));
            return;
        }
        close();
        // обновим таблицу без перезагрузки страницы, если функция есть
        if (typeof window.reloadResources === "function") window.reloadResources();
        else location.reload();
    }

    if (btnOpen) btnOpen.addEventListener("click", onOpenClick);
    if (btnCancel) btnCancel.addEventListener("click", close);
    if (btnSubmit) btnSubmit.addEventListener("click", onSubmit);
    if (selProv) selProv.addEventListener("change", onProviderChange);
});


