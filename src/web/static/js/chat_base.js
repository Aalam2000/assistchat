// src/web/static/js/chat_base.js

document.addEventListener("DOMContentLoaded", () => {
    const rid = typeof CHAT_BASE_RID !== "undefined" ? CHAT_BASE_RID : "";
    if (!rid) return;

    const $ = (s) => document.querySelector(s);
    const msgBox = $("#cbMsg");
    const statusEl = $("#cbStatus");

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
        return {
            label: ($("#cbLabel").value || "").trim(),
            meta_json: {
                platform: "telegram",
                topic: ($("#cbTopic").value || "").trim(),
                queries: queriesFromTextarea(),
                filters: {
                    min_members: parseInt($("#cbMinMembers").value || "0", 10) || 0,
                    last_post_max_hours: parseInt($("#cbLastPostHours").value || "24", 10) || 24,
                },
                creds: {
                    app_id: ($("#cbAppId").value || "").trim() || null,
                    app_hash: ($("#cbAppHash").value || "").trim(),
                    string_session: ($("#cbStringSession").value || "").trim(),
                    bot_token: ($("#cbBotToken").value || "").trim(),
                },
                owner: {
                    telegram_user_id: ($("#cbOwnerId").value || "").trim() || null,
                },
                telegram_session_rid: ($("#cbSessionRid").value || "").trim() || null,
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
            const link = it.link ? `<a href="${it.link}" target="_blank">${it.link}</a>` : "—";
            return `<div style="margin-bottom:8px;padding:8px;border:1px solid rgba(255,255,255,.1);border-radius:6px">
                <b>${it.title || it.external_id}</b><br>
                ${link}<br>
                участников: ${it.members ?? "—"} | за неделю: ${it.week_message_count ?? "—"}
            </div>`;
        }).join("");
    }

    function fillForm(data) {
        const meta = data.meta_json || {};
        $("#cbLabel").value = data.label || "";
        $("#cbTopic").value = meta.topic || "";
        $("#cbQueries").value = (meta.queries || []).join("\n");
        $("#cbMinMembers").value = meta.filters?.min_members ?? 3000;
        $("#cbLastPostHours").value = meta.filters?.last_post_max_hours ?? 24;
        $("#cbSessionRid").value = meta.telegram_session_rid || "";
        const creds = meta.creds || {};
        $("#cbAppId").value = creds.app_id || "";
        $("#cbAppHash").value = creds.app_hash || "";
        $("#cbStringSession").value = creds.string_session || "";
        $("#cbBotToken").value = creds.bot_token || "";
        $("#cbOwnerId").value = meta.owner?.telegram_user_id || "";
        const run = meta.run || {};
        statusEl.textContent = `СТАТУС: ${run.status || data.phase || "—"} | ${run.message || ""}`;
        renderAccepted(meta);
    }

    async function loadSessions() {
        const sel = $("#cbSessionRid");
        if (!sel) return;
        try {
            const r = await fetch("/api/providers/resources/list", { credentials: "same-origin" });
            const data = await r.json();
            for (const it of data.items || []) {
                if ((it.provider || "").toLowerCase() !== "telegram") continue;
                const o = document.createElement("option");
                o.value = it.id;
                o.textContent = `${it.label || it.id} (${it.id})`;
                sel.appendChild(o);
            }
        } catch (e) {
            console.warn("[chat_base] sessions load", e);
        }
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
            const topic = ($("#cbTopic").value || "").trim();
            const r = await fetch(`/api/chat_base/${rid}/assist`, {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic }),
            });
            const data = await r.json();
            if (!r.ok) throw new Error("assist error");
            $("#cbQueries").value = (data.queries || []).join("\n");
            showMsg("Ключи добавлены", true);
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

    loadSessions().then(loadResource).catch((e) => showMsg(String(e), false));
});
