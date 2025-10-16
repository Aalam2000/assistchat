// src/web/static/js/resources.js

async function loadResources() {
    const tbody = document.getElementById("resources-tbody");
    try {
        const r = await fetch("/api/resources/list", {credentials: "same-origin"});
        if (!r.ok) throw new Error("HTTP " + r.status);

        const data = await r.json();
        const items = data.items || [];
        tbody.innerHTML = "";

        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="10">Пока нет ни одного ресурса</td></tr>`;
            return;
        }

        for (const it of items) {
            const meta = it.meta_json || {};
            const creds = meta.creds || {};
            const extra = meta.extra || {};

            const tr = document.createElement("tr");
            const btnText = it.status === "active" ? "Пауза" : "Активировать";

            tr.innerHTML = `
              <td class="mono small">${it.id ?? ""}</td>
              <td>${it.provider ?? ""}</td>
              <td>${it.label ?? ""}</td>
              <td>${creds.app_id ?? "—"}</td>
              <td class="mono small">${(creds.app_hash || "").slice(0, 8)}...</td>
              <td>${extra.phone_e164 || creds.phone || "—"}</td>
              <td class="status">${it.status ?? ""}</td>
              <td>${it.phase ?? ""}</td>
              <td>${it.last_error_code ?? "—"}</td>
              <td>
                <button class="btn res-toggle" data-id="${it.id}">${btnText}</button>
                <button class="btn res-edit" data-id="${it.id}">Настроить</button>
                <button class="btn res-delete" data-id="${it.id}" title="Удалить ресурс">🗑️</button>
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
            const id = btnToggle.dataset.id;
            const row = btnToggle.closest("tr");
            const statusCell = row.querySelector(".status");
            const current = statusCell.textContent.trim();
            const want = current === "active" ? "pause" : "activate";

            btnToggle.disabled = true;
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
                btnToggle.textContent = (next === "active") ? "Пауза" : "Активировать";
            } catch (err) {
                alert("Ошибка переключения");
                console.error("[resources] toggle error:", err);
            } finally {
                btnToggle.disabled = false;
            }
            return;
        }

        // редактирование
        const btnEdit = e.target.closest(".res-edit");
        if (btnEdit) {
            const id = btnEdit.dataset.id;
            const row = btnEdit.closest("tr");
            const provider = row.querySelector("td:nth-child(2)")?.textContent?.trim();

            if (provider === "zoom_meeting") {
                window.location.href = `/resources/zoom/${id}`;
            } else if (provider === "telegram") {
                window.location.href = `/resources/telegram/${id}`;
            } else {
                openEditModal(id);
            }
        }

        // удаление
        const btnDelete = e.target.closest(".res-delete");
        if (btnDelete) {
            const id = btnDelete.dataset.id;
            const row = btnDelete.closest("tr");
            const name = row.querySelector("td:nth-child(3)")?.textContent?.trim() || "";
            if (!confirm(`Удаляем ресурс "${name}"?`)) return;

            try {
                const r = await fetch(`/api/resources/${id}`, {
                    method: "DELETE",
                    credentials: "same-origin"
                });
                const data = await r.json().catch(() => ({}));
                if (!r.ok || !data.ok) {
                    alert("Ошибка удаления: " + (data.error || "unknown"));
                    return;
                }
                row.remove();
            } catch (err) {
                alert("Ошибка при удалении ресурса");
                console.error(err);
            }
            return;
        }

    });
}

window.addEventListener("DOMContentLoaded", () => {
    // гарантируем, что весь DOM загружен перед инициализацией
    loadResources();
    bindResourceActions();

    const $ = (sel) => document.querySelector(sel);
    const codeModal = $("#codeModal");
    const codeInput = $("#tgCodeInput");
    const codeOkBtn = $("#codeOkBtn");
    const codeCancelBtn = $("#codeCancelBtn");

    const openCodeModal = () => codeModal.classList.remove("hidden");
    const closeCodeModal = () => {
        codeModal.classList.add("hidden");
        codeInput.value = "";
    };

    const modal = $("#addResourceModal");
    const btnOpen = $("#btnAddResource");
    const btnCancel = $("#addResCancel");
    const btnClose = $("#addResClose");
    const btnSubmit = $("#addResSubmit");
    const selProv = $("#provSelect");
    const inpLabel = $("#resLabel");
    const elHelp = $("#provHelp");
    const dynForm = $("#dynForm");
    const formErrors = $("#formErrors");

    if (!modal || !btnOpen || !selProv || !inpLabel) return;

    const state = {
        providers: [],
        byKey: {},
        uiSchema: null,
        template: {},
        lastAutoLabel: "",
        labelTouched: false,
        editingId: null,   // null → создание, id → редактирование
    };

    inpLabel.addEventListener("input", () => {
        state.labelTouched = true;
    });

    const open = () => modal.classList.remove("hidden");
    const close = () => {
        modal.classList.add("hidden");
        state.editingId = null;
        btnSubmit.textContent = "Создать";
    };

    const getByPath = (obj, path) => {
        if (!obj) return undefined;
        return path.split(".").reduce((cur, k) => (cur && typeof cur === "object" ? cur[k] : undefined), obj);
    };
    const setByPath = (obj, path, value) => {
        const keys = path.split(".");
        let cur = obj;
        for (let i = 0; i < keys.length - 1; i++) {
            const k = keys[i];
            if (typeof cur[k] !== "object" || cur[k] === null) cur[k] = {};
            cur = cur[k];
        }
        cur[keys[keys.length - 1]] = value;
    };

    async function fetchProviders() {
        const r = await fetch("/api/resources/providers", { credentials: "same-origin" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        state.providers = data.providers || [];
        state.byKey = Object.fromEntries(state.providers.map(p => [p.key, p]));
        console.log("[DEBUG providers]", state.providers);
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

    async function fetchProviderSchema(provKey) {
        const r = await fetch(`/api/resources/providers/${provKey}/schema`, {credentials: "same-origin"});
        const data = await r.json();
        if (!data.ok) throw new Error(`Schema not found for ${provKey}`);
        state.uiSchema = data.schema || {version: 1, groups: []};
        state.template = data.template || {};
        if (elHelp) elHelp.textContent = data.help && Object.keys(data.help).length ? JSON.stringify(data.help, null, 2) : "—";
    }

    function renderDynForm(schema, template) {
        dynForm.innerHTML = "";
        if (formErrors) formErrors.textContent = "";

        const groups = (schema && Array.isArray(schema.groups)) ? schema.groups : [];
        groups.forEach((g, gi) => {
            const wrap = document.createElement("div");
            wrap.className = "card";
            wrap.style.marginTop = gi ? "10px" : "0";

            if (g.title) {
                const h = document.createElement("h3");
                h.textContent = g.title;
                h.style.marginTop = "0";
                wrap.appendChild(h);
            }

            (g.fields || []).forEach(f => {
                if (f.key === "creds.code") return;
                const fieldWrap = document.createElement("div");
                fieldWrap.style.margin = "10px 0";
                const lbl = document.createElement("label");
                lbl.textContent = f.label || f.key;
                lbl.htmlFor = `f_${f.key.replace(/\./g, "_")}`;
                fieldWrap.appendChild(lbl);

                const type = (f.type || "string").toLowerCase();
                const id = lbl.htmlFor;
                const val = getByPath(template, f.key);

                let el;
                if (type === "textarea" || type === "json" || type === "list") {
                    el = document.createElement("textarea");
                    el.rows = type === "list" ? 4 : 3;
                } else if (type === "boolean") {
                    el = document.createElement("input");
                    el.type = "checkbox";
                } else {
                    el = document.createElement("input");
                    el.type = (type === "password") ? "password" : (type === "number" ? "number" : "text");
                }
                el.id = id;
                el.dataset.path = f.key;
                el.placeholder = f.placeholder || "";
                el.required = !!f.required;

                if (type === "boolean") {
                    el.checked = !!val;
                } else if (type === "list") {
                    const arr = Array.isArray(val) ? val : [];
                    el.value = arr.join("\n");
                } else if (type === "json") {
                    el.value = (val && typeof val === "object") ? JSON.stringify(val, null, 2) : "{}";
                    el.style.fontFamily = "monospace";
                } else {
                    el.value = (val ?? "");
                }

                el.style.width = "100%";
                if (type !== "boolean") el.style.fontFamily = "inherit";
                fieldWrap.appendChild(el);

                if (f.help) {
                    const note = document.createElement("div");
                    note.className = "note";
                    note.textContent = f.help;
                    fieldWrap.appendChild(note);
                }

                wrap.appendChild(fieldWrap);

                // 🔵 если это поле телефона → сразу под ним кнопка Активировать
                if (f.key === "creds.phone" || f.key === "extra.phone_e164") {
                    const actBtn = document.createElement("button");
                    actBtn.id = "addResActivate";
                    actBtn.className = "btn accent";
                    actBtn.textContent = "Активировать";
                    actBtn.style.marginTop = "8px";
                    fieldWrap.appendChild(actBtn);

                    actBtn.addEventListener("click", onActivate);
                }
            });

            dynForm.appendChild(wrap);
        });

        if (!groups.length) {
            dynForm.innerHTML = `<div class="note">Нет полей для этого провайдера</div>`;
        }
    }


    function collectMeta(schema) {
        const meta = {};
        const groups = (schema && Array.isArray(schema.groups)) ? schema.groups : [];
        let errors = [];

        groups.forEach(g => {
            (g.fields || []).forEach(f => {
                const path = f.key;
                const id = `f_${path.replace(/\./g, "_")}`;
                const type = (f.type || "string").toLowerCase();
                const el = document.getElementById(id);
                if (!el) return;

                let value;
                if (type === "boolean") {
                    value = !!el.checked;
                } else if (type === "number") {
                    const v = el.value.trim();
                    if (!v) {
                        value = v;
                    } else if (/^-?\d+(\.\d+)?$/.test(v)) {
                        value = v.includes(".") ? parseFloat(v) : parseInt(v, 10);
                    } else {
                        errors.push(`${f.label || path}: число некорректно`);
                        return;
                    }
                } else if (type === "list") {
                    const lines = el.value.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
                    value = lines;
                } else if (type === "json") {
                    try {
                        value = el.value.trim() ? JSON.parse(el.value) : {};
                    } catch (e) {
                        errors.push(`${f.label || path}: JSON ошибка — ${e.message}`);
                        return;
                    }
                } else {
                    value = el.value;
                }

                if (f.required) {
                    const empty = (
                        value === null || value === undefined ||
                        (typeof value === "string" && !value.trim()) ||
                        (Array.isArray(value) && value.length === 0) ||
                        (type === "json" && value && typeof value === "object" && Object.keys(value).length === 0)
                    );
                    if (empty) errors.push(`${f.label || path}: обязательно`);
                }

                setByPath(meta, path, value);
            });
        });

        return {meta, errors};
    }

    function autoSetLabel(key) {
        const p = state.byKey[key];
        const auto = (p && (p.name || p.key)) || key;
        const current = (inpLabel.value || "").trim();
        if (!state.labelTouched || current === state.lastAutoLabel || current === "") {
            inpLabel.value = auto;
            state.lastAutoLabel = auto;
        }
    }

    async function onOpenClick() {
        try {
            await fetchProviders();
            fillProviderSelect();
            inpLabel.value = "";
            const key = selProv.value;
            autoSetLabel(key);
            state.editingId = null;
            btnSubmit.textContent = "Создать";
            open();
        } catch (e) {
            alert("Не удалось загрузить список провайдеров");
            console.error(e);
        }
    }


    async function onProviderChange() {
        const key = selProv.value;
        autoSetLabel(key);
    }


    const btnActivate = $("#addResActivate");

    async function onActivate() {
        if (!state.editingId) {
            alert("Сначала сохраните ресурс, потом активируйте.");
            return;
        }

        const {meta, errors} = collectMeta(state.uiSchema);
        if (errors.length) {
            if (formErrors) formErrors.textContent = errors.join("; ");
            return;
        }

        // собрали данные
        const payload = {
            ...meta,
            phone: meta?.extra?.phone_e164 || meta?.creds?.phone_e164 || null,
            app_id: meta?.creds?.app_id || meta?.creds?.api_id || null,
            app_hash: meta?.creds?.app_hash || meta?.creds?.api_hash || null,
        };


        try {
            state.lastActivation = {
                phone: payload.phone,
                app_id: payload.app_id,
                app_hash: payload.app_hash,
            };
            const r = await fetch(`/api/resource/${state.editingId}/activate`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify(payload),
            });
            const data = await r.json();

            if (!r.ok || !data.ok) {
                alert("Ошибка активации: " + (data.error || "unknown"));
                return;
            }

            if (data.need_code) {
                // сервер код отправил — просто открываем модалку для ввода
                openCodeModal();
            } else if (data.activated) {
                // alert("Telegram-ресурс успешно активирован!");
                close();
                if (typeof window.reloadResources === "function") window.reloadResources();
            }

        } catch (err) {
            console.error("[resources] activate error:", err);
            alert("Ошибка при активации");
        }
    }


    if (btnActivate) btnActivate.addEventListener("click", onActivate);

    async function onSubmit() {
        const provider = selProv.value;
        const label = inpLabel.value.trim() || provider;

        try {
            const r = await fetch("/api/resources/add", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify({provider, label})
            });
            const data = await r.json();
            if (!r.ok || !data.ok) {
                alert("Ошибка создания ресурса: " + (data.error || "unknown"));
                return;
            }
            // alert("Ресурс создан");
            close();
            if (typeof window.reloadResources === "function") window.reloadResources();
        } catch (err) {
            console.error(err);
            alert("Ошибка при создании ресурса");
        }
    }


    async function openEditModal(id) {
        try {
            const r = await fetch(`/api/resource/${id}`, { credentials: "same-origin" });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "failed to load resource");

            await fetchProviders();
            fillProviderSelect();

            selProv.value = data.provider;
            inpLabel.value = data.label || "";
            state.labelTouched = true;
            state.editingId = id;
            btnSubmit.textContent = "Сохранить";
            open();
        } catch (e) {
            alert("Не удалось загрузить ресурс для редактирования");
            console.error(e);
        }
    }


    btnOpen.addEventListener("click", onOpenClick);
    if (btnCancel) btnCancel.addEventListener("click", close);
    if (btnClose) btnClose.addEventListener("click", close);
    if (btnSubmit) btnSubmit.addEventListener("click", onSubmit);
    selProv.addEventListener("change", onProviderChange);


    if (codeOkBtn) codeOkBtn.addEventListener("click", async () => {
        const code = codeInput.value.trim();
        if (!code) {
            alert("Введите код подтверждения");
            return;
        }
        try {
            const r = await fetch(`/api/resource/${state.editingId}/activate`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify({
                    phone: state.lastActivation?.phone,
                    app_id: state.lastActivation?.app_id,
                    app_hash: state.lastActivation?.app_hash,
                    code: code,
                }),
            });
            const data = await r.json();
            if (!r.ok || !data.ok) {
                alert("Ошибка подтверждения: " + (data.error || "unknown"));
                return;
            }
            if (data.activated) {
                // alert("Telegram-ресурс успешно активирован!");
                closeCodeModal();
                close(); // закрыть большую модалку
                if (typeof window.reloadResources === "function") window.reloadResources();
            }
        } catch (err) {
            console.error("[resources] code confirm error:", err);
            alert("Ошибка при подтверждении кода");
        }
    });

    if (codeCancelBtn) codeCancelBtn.addEventListener("click", closeCodeModal);

    // делаем доступным для внешнего вызова
    window.openEditModal = openEditModal;
});
