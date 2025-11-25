// src/web/static/js/resources.js

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
                <td>${it.provider.toLowerCase()}</td>
                <td>${it.label || "—"}</td>
                <td>${creds.app_id || "—"}</td>
                <td>${creds.app_hash || "—"}</td>
                <td>${creds.phone || "—"}</td>
                <td>${it.status || "—"}</td>
                <td>${it.meta?.phase || "—"}</td>
                <td>${it.meta?.error || "—"}</td>
                <td>
                    <button class="btn res-delete" data-id="${it.id}" data-provider="${it.provider}">Удалить</button>
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

        // === DELETE ===
        const btnDelete = e.target.closest(".res-delete");
        if (btnDelete) {
            const id = btnDelete.dataset.id;

            if (!confirm("Удалить ресурс?")) return;

            btnDelete.disabled = true;
            try {
                const r = await fetch(`/api/providers/resource/${id}`, {
                    method: "DELETE",
                    credentials: "same-origin"
                });
                const data = await r.json().catch(() => ({}));

                if (!data.ok) {
                    alert(data.error || "Ошибка удаления");
                } else {
                    reloadResources();
                }
            } finally {
                btnDelete.disabled = false;
            }
            return;
        }

        // === ОТКРЫТИЕ СТРАНИЦЫ РЕСУРСА ПО КЛИКУ ПО СТРОКЕ ===
        const tr = e.target.closest("tr");
        if (!e.target.closest(".res-delete") && tr) {
            const provider = tr.children[1].textContent.trim().toLowerCase();
            const rid = tr.children[0].textContent.trim();

            if (provider && rid) {
                window.location.href = `/resources/${provider}/${rid}`;
            }
        }

    });
}


document.getElementById("btnAddResource").onclick = openAddResourceModal;
document.getElementById("addResClose").onclick = closeAddResourceModal;
document.getElementById("addResCancel").onclick = closeAddResourceModal;
document.getElementById("addResSubmit").onclick = submitAddResource;

// === ADD RESOURCE MODAL ===

function openAddResourceModal() {
    document.getElementById("addResourceModal").classList.remove("hidden");
    loadProvidersForSelect();
}

function closeAddResourceModal() {
    document.getElementById("addResourceModal").classList.add("hidden");
}

async function loadProvidersForSelect() {
    const sel = document.getElementById("provSelect");
    sel.innerHTML = "";
    const r = await fetch("/api/providers/list", { credentials: "same-origin" });
    const data = await r.json();
    const items = data.providers || [];
    for (const it of items) {
        const o = document.createElement("option");
        o.value = it.key;
        o.textContent = it.name;
        sel.appendChild(o);
    }
}

async function submitAddResource() {
    const provider = document.getElementById("provSelect").value;
    const label = document.getElementById("resLabel").value.trim();

    const fd = new FormData();
    fd.append("label", label);
    console.log(`/api/${provider.toLowerCase()}/create`);
    const r = await fetch(`/api/${provider.toLowerCase()}/create`, {
        method: "POST",
        credentials: "same-origin",
        body: fd
    });


    const data = await r.json();
    if (!r.ok) {
        alert(data.error || "Ошибка создания");
        return;
    }

    closeAddResourceModal();
    reloadResources();
}

window.addEventListener("DOMContentLoaded", () => {
    loadResources();
    bindResourceActions();
});
