// src/web/static/js/chat_base.js

document.addEventListener("DOMContentLoaded", () => {
    const rid = typeof CHAT_BASE_RID !== "undefined" ? CHAT_BASE_RID : "";
    if (!rid) return;

    const $ = (s) => document.querySelector(s);
    const msgBox = $("#cbMsg");
    const statusEl = $("#cbStatus");
    const selSession = $("#cbSession");
    const selBot = $("#cbBot");
    const selApiKeysRes = $("#cbApiKeysRes");
    const selApiKeyField = $("#cbApiKeyField");
    const selModel = $("#cbModel");

    const DEFAULT_MODELS = {
        "creds.openai_api_key": "gpt-4o-mini",
        "creds.openai_admin_key": "gpt-4o-mini",
        "creds.gemini_api_key": "gemini-2.0-flash",
        "creds.anthropic_api_key": "claude-3-5-haiku-latest",
        "creds.groq_api_key": "llama-3.1-8b-instant",
        "creds.deepseek_api_key": "deepseek-chat",
        "creds.mistral_api_key": "mistral-small-latest",
        "creds.xai_api_key": "grok-2-1212",
    };

    const KEY_LABELS = {
        "creds.openai_api_key": "OpenAI",
        "creds.openai_admin_key": "OpenAI Admin",
        "creds.gemini_api_key": "Google Gemini",
        "creds.anthropic_api_key": "Anthropic Claude",
        "creds.groq_api_key": "Groq",
        "creds.deepseek_api_key": "DeepSeek",
        "creds.mistral_api_key": "Mistral",
        "creds.xai_api_key": "xAI Grok",
    };

    function showMsg(text, ok) {
        if (!msgBox) return;
        msgBox.style.display = "block";
        msgBox.textContent = text;
        msgBox.style.background = ok ? "rgba(0,128,0,.15)" : "rgba(200,0,0,.15)";
    }

    function queriesFromTextarea() {
        return ($("#cbQueries").value || "")
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean);
    }

    function buildPayload() {
        const ownerRaw = ($("#cbOwnerId").value || "").trim();
        return {
            label: ($("#cbLabel").value || "").trim(),
            meta_json: {
                platform: "telegram",
                topic: ($("#cbTopic").value || "").trim(),
                queries: queriesFromTextarea(),
                filters: {
                    min_members: parseInt($("#cbMinMembers").value || "0", 10) || 0,
                    last_post_max_hours: parseInt(
                        $("#cbLastPostHours").value || "24", 10
                    ) || 24,
                },
                sources: {
                    telegram_session_rid: selSession?.value || null,
                    telegram_bot_rid: selBot?.value || null,
                },
                owner: {
                    telegram_user_id: ownerRaw ? parseInt(ownerRaw, 10) : null,
                },
                ai: {
                    api_keys_resource_id: selApiKeysRes?.value || null,
                    api_key_field: selApiKeyField?.value || null,
                    model: selModel?.value || null,
                },
            },
        };
    }

    function renderAccepted(meta) {
        const el = $("#cbAccepted");
        if (!el) return;
        const items = (meta.accepted && meta.accepted.telegram) || [];
        if (!items.length) {
            el.textContent = "Пока пусто";
            return;
        }
        el.innerHTML = items.map((it) => {
            const link = it.link
                ? `<a href="${it.link}" target="_blank">${it.link}</a>`
                : "—";
            return `<div style="margin-bottom:8px;padding:8px;border:1px solid rgba(255,255,255,.1);border-radius:6px">
                <b>${it.title || it.external_id}</b><br>
                ${link}<br>
                участников: ${it.members ?? "—"} | за неделю: ${it.week_message_count ?? "—"}
            </div>`;
        }).join("");
    }

    function fillForm(data) {
        const meta = data.meta_json || {};
        const sources = meta.sources || {};
        const ai = meta.ai || {};
        $("#cbLabel").value = data.label || "";
        $("#cbTopic").value = meta.topic || "";
        $("#cbQueries").value = (meta.queries || []).join("\n");
        $("#cbMinMembers").value = meta.filters?.min_members ?? 3000;
        $("#cbLastPostHours").value = meta.filters?.last_post_max_hours ?? 24;
        if (selSession) selSession.value = sources.telegram_session_rid || "";
        if (selBot) selBot.value = sources.telegram_bot_rid || "";
        $("#cbOwnerId").value = meta.owner?.telegram_user_id || "";
        if (selApiKeysRes && ai.api_keys_resource_id) {
            selApiKeysRes.value = ai.api_keys_resource_id;
            selApiKeysRes.dispatchEvent(new Event("change"));
        }
        if (selApiKeyField && ai.api_key_field) {
            setTimeout(() => {
                selApiKeyField.value = ai.api_key_field;
                selApiKeyField.dispatchEvent(new Event("change"));
                setTimeout(() => {
                    if (selModel && ai.model) selModel.value = ai.model;
                }, 300);
            }, 50);
        }
        const run = meta.run || {};
        statusEl.textContent = `СТАТУС: ${run.status || data.phase || "—"} | ${run.message || ""}`;
        renderAccepted(meta);
    }

    async function loadUserResources() {
        const r = await fetch("/api/providers/resources/list", {
            credentials: "same-origin",
        });
        const data = await r.json();
        if (!r.ok || !data.ok) return;

        const items = data.items || [];
        const sessions = items.filter((x) => x.provider === "telegram");
        const bots = items.filter((x) => x.provider === "telegram_bot");
        const apiKeys = items.filter((x) => x.provider === "api_keys");

        if (selSession) {
            selSession.innerHTML = '<option value="">— не выбрано —</option>';
            sessions.forEach((s) => {
                const o = document.createElement("option");
                o.value = s.id;
                o.textContent = s.label || s.id;
                selSession.appendChild(o);
            });
        }

        if (selBot) {
            selBot.innerHTML = '<option value="">— не выбрано —</option>';
            bots.forEach((b) => {
                const o = document.createElement("option");
                o.value = b.id;
                o.textContent = b.label || b.id;
                selBot.appendChild(o);
            });
        }

        if (selApiKeysRes) {
            selApiKeysRes.innerHTML = '<option value="">— выберите ресурс —</option>';
            apiKeys.forEach((k) => {
                const o = document.createElement("option");
                o.value = k.id;
                o.textContent = k.label || k.id;
                o.dataset.verified = JSON.stringify((k.meta || {}).verified || {});
                selApiKeysRes.appendChild(o);
            });
        }
    }

    if (selApiKeysRes) {
        selApiKeysRes.addEventListener("change", () => {
            const opt = selApiKeysRes.selectedOptions[0];
            selApiKeyField.innerHTML = '<option value="">— выберите ключ —</option>';
            selApiKeyField.disabled = true;
            selModel.innerHTML = '<option value="">— сначала ключ —</option>';
            selModel.disabled = true;
            if (!opt || !opt.value) return;

            let verified = {};
            try { verified = JSON.parse(opt.dataset.verified || "{}"); } catch (_) {}

            let hasKeys = false;
            Object.entries(KEY_LABELS).forEach(([field, label]) => {
                const v = verified[field];
                if (v && v.ok) {
                    const o = document.createElement("option");
                    o.value = field;
                    o.textContent = label;
                    selApiKeyField.appendChild(o);
                    hasKeys = true;
                }
            });
            if (hasKeys) selApiKeyField.disabled = false;
        });
    }

    if (selApiKeyField) {
        selApiKeyField.addEventListener("change", async () => {
            const keyField = selApiKeyField.value;
            const resId = selApiKeysRes?.value;
            selModel.innerHTML = '<option value="">Загрузка...</option>';
            selModel.disabled = true;
            if (!keyField || !resId) return;

            const defModel = DEFAULT_MODELS[keyField] || "";
            selModel.innerHTML = `<option value="${defModel}">${defModel} (рекомендуется)</option>`;
            selModel.disabled = false;

            try {
                const r = await fetch(
                    `/api/api_keys/${resId}/models?key_field=${encodeURIComponent(keyField)}`,
                    { credentials: "same-origin" }
                );
                const data = await r.json();
                if (data.ok && data.models?.length) {
                    selModel.innerHTML = "";
                    data.models.forEach((m) => {
                        const o = document.createElement("option");
                        o.value = m;
                        o.textContent = m;
                        selModel.appendChild(o);
                    });
                    if (defModel) selModel.value = defModel;
                }
            } catch (_) {}
        });
    }

    async function loadResource() {
        const r = await fetch(`/api/chat_base/${rid}`, { credentials: "same-origin" });
        if (!r.ok) throw new Error("load failed");
        const data = await r.json();
        fillForm(data);
    }

    async function saveResource() {
        const r = await fetch(`/api/chat_base/${rid}`, {
            method: "PUT",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(buildPayload()),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || "save error");
        return data;
    }

    $("#btnSave").onclick = async () => {
        try {
            await saveResource();
            showMsg("Сохранено", true);
            await loadResource();
        } catch (e) {
            showMsg(String(e.message || e), false);
        }
    };

    $("#btnAssist").onclick = async () => {
        try {
            const label = ($("#cbLabel").value || "").trim();
            const topic = ($("#cbTopic").value || "").trim();
            if (!label && !topic) {
                showMsg("Укажите название базы или описание темы", false);
                return;
            }
            if (!selApiKeysRes?.value || !selApiKeyField?.value || !selModel?.value) {
                showMsg("Настройте AI: API Keys, ключ и модель", false);
                return;
            }
            await saveResource();
            showMsg("AI генерирует запросы…", true);
            const r = await fetch(`/api/chat_base/${rid}/assist`, {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ label, topic }),
            });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "assist error");
            $("#cbQueries").value = (data.queries || []).join("\n");
            showMsg(`Готово: ${(data.queries || []).length} запросов`, true);
            await loadResource();
        } catch (e) {
            showMsg(String(e.message || e), false);
        }
    };

    $("#btnRun").onclick = async () => {
        try {
            await saveResource();
            const r = await fetch(`/api/chat_base/${rid}/run`, {
                method: "POST",
                credentials: "same-origin",
            });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "run error");
            showMsg("Поиск запущен — смотри бота", true);
            setTimeout(loadResource, 2000);
        } catch (e) {
            showMsg(String(e.message || e), false);
        }
    };

    $("#btnResetQueries").onclick = async () => {
        try {
            const r = await fetch(`/api/chat_base/${rid}/reset-queries`, {
                method: "POST",
                credentials: "same-origin",
            });
            if (!r.ok) throw new Error("reset error");
            showMsg("Список выполненных запросов сброшен", true);
            await loadResource();
        } catch (e) {
            showMsg(String(e.message || e), false);
        }
    };

    loadUserResources()
        .then(loadResource)
        .catch((e) => showMsg(String(e), false));
});
