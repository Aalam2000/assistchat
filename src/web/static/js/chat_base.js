// src/web/static/js/chat_base.js

document.addEventListener("DOMContentLoaded", () => {
    const rid = typeof CHAT_BASE_RID !== "undefined" ? CHAT_BASE_RID : "";
    if (!rid) return;

    const $ = (s) => document.querySelector(s);
    const msgBox = $("#cbMsg");
    const statusEl = $("#cbStatus");
    const selSession = $("#cbSession");
    const selBot = $("#cbBot");

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
        $("#cbLabel").value = data.label || "";
        $("#cbTopic").value = meta.topic || "";
        $("#cbQueries").value = (meta.queries || []).join("\n");
        $("#cbMinMembers").value = meta.filters?.min_members ?? 3000;
        $("#cbLastPostHours").value = meta.filters?.last_post_max_hours ?? 24;
        if (selSession) selSession.value = sources.telegram_session_rid || "";
        if (selBot) selBot.value = sources.telegram_bot_rid || "";
        $("#cbOwnerId").value = meta.owner?.telegram_user_id || "";
        const run = meta.run || {};
        statusEl.textContent = `СТАТУС: ${run.status || data.phase || "—"} | ${run.message || ""}`;
        renderAccepted(meta);
    }

    async function loadUserResources() {
        if (!selSession || !selBot) return;
        const r = await fetch("/api/providers/resources/list", {
            credentials: "same-origin",
        });
        const data = await r.json();
        if (!r.ok || !data.ok) return;

        const items = data.items || [];
        const sessions = items.filter((x) => x.provider === "telegram");
        const bots = items.filter((x) => x.provider === "telegram_bot");

        selSession.innerHTML = '<option value="">— не выбрано —</option>';
        sessions.forEach((s) => {
            const o = document.createElement("option");
            o.value = s.id;
            o.textContent = s.label || s.id;
            selSession.appendChild(o);
        });

        selBot.innerHTML = '<option value="">— не выбрано —</option>';
        bots.forEach((b) => {
            const o = document.createElement("option");
            o.value = b.id;
            o.textContent = b.label || b.id;
            selBot.appendChild(o);
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

    loadUserResources()
        .then(loadResource)
        .catch((e) => showMsg(String(e), false));
});
