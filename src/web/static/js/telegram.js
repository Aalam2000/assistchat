document.addEventListener("DOMContentLoaded", () => {
    const id = TG_RID;
    if (!id) return;

    const $ = (s) => document.querySelector(s);

    const label        = $("#tgLabel");
    const appId        = $("#tgAppId");
    const appHash      = $("#tgAppHash");
    const phone        = $("#tgPhone");
    const stringSession = $("#tgStringSession");

    const btnSave        = $("#btnSave");
    const btnActivate    = $("#btnActivate");
    const btnToggleRes   = $("#btnToggleStatus");
    const tgResStatus    = $("#tgResStatus");
    const tgMsg          = $("#tgMsg");

    const tgCodeModal   = $("#tgCodeModal");
    const codeInput     = $("#tgCodeInput");
    const btnConfirmCode = $("#btnConfirmCode");
    const btnCancelCode  = $("#btnCancelCode");

    /** Служебные поля активации — не показываем в UI, не затираем при сохранении. */
    let _activationCreds = {};

    function showMsg(text, ok = true) {
        if (!tgMsg) return;
        tgMsg.textContent = text;
        tgMsg.style.display = "block";
        tgMsg.style.background = ok ? "#d4edda" : "#f8d7da";
        tgMsg.style.color = ok ? "#155724" : "#721c24";
    }

    function openCodeModal() {
        tgCodeModal?.classList.remove("hidden");
        codeInput?.focus();
    }

    function closeCodeModal() {
        tgCodeModal?.classList.add("hidden");
        if (codeInput) codeInput.value = "";
    }

    function buildMeta() {
        const sess = (stringSession.value || "").trim();
        const creds = {
            app_id:        (appId.value || "").trim(),
            app_hash:      (appHash.value || "").trim(),
            phone:         (phone.value || "").trim(),
            string_session: sess,
        };
        // Не теряем служебные поля активации
        if (!sess && _activationCreds.phone_code_hash) {
            creds.phone_code_hash = _activationCreds.phone_code_hash;
            creds.pending_session = _activationCreds.pending_session;
        }
        if (_activationCreds.flood_until_ts) {
            creds.flood_until_ts = _activationCreds.flood_until_ts;
        }
        return { creds };
    }

    async function loadData() {
        const r = await fetch(`/api/providers/resources/list`, { credentials: "same-origin" });
        const data = await r.json();
        if (!r.ok || !data.ok) throw new Error(data.error || "load failed");

        const item = (data.items || []).find((x) => x.id === id);
        if (!item) throw new Error("resource not found");

        const rawMeta  = item.meta || item.meta_json || {};
        const rawCreds = rawMeta.creds || {};

        _activationCreds = {
            phone_code_hash: rawCreds.phone_code_hash || null,
            pending_session: rawCreds.pending_session || null,
            flood_until_ts:  rawCreds.flood_until_ts  || null,
        };
        if (rawCreds.string_session) _activationCreds = {};

        label.value        = item.label || "";
        appId.value        = rawCreds.app_id    || "";
        appHash.value      = rawCreds.app_hash  || "";
        phone.value        = rawCreds.phone     || "";
        stringSession.value = rawCreds.string_session || "";
    }

    async function saveData() {
        const payload = {
            label:     (label.value || "").trim() || "Telegram сессия",
            meta_json: buildMeta(),
        };
        const r = await fetch(`/api/telegram/${id}`, {
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
            const r = await fetch(`/api/telegram/${id}/status?probe=1`, { credentials: "same-origin" });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error();

            const status   = data.resource_status ?? "—";
            const authorized = !!(data.authorized ?? false);
            const phase    = data.phase ? ` (${data.phase})` : "";

            tgResStatus.textContent = `РЕСУРС: ${status}${phase} ${authorized ? "🟢" : "🔴"}`;
            btnToggleRes.textContent = status === "active" ? "💡 Остановить" : "💡 Включить";
            btnToggleRes.dataset.enabled = status === "active" ? "1" : "0";

            if (btnActivate) {
                btnActivate.classList.toggle("hidden", authorized);
                btnActivate.disabled = authorized;
            }
        } catch {
            tgResStatus.textContent = "РЕСУРС: ошибка статуса";
        }
    }

    async function activate() {
        try { await saveData(); } catch (e) {
            showMsg("Сохраните данные перед активацией", false);
            return;
        }
        const r = await fetch(`/api/telegram/${id}/activate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({}),
        });
        const data = await r.json();

        if (!data.ok && !data.need_code) {
            showMsg(data.message || "Ошибка активации", false);
            await loadResStatus();
            return;
        }
        if (data.need_code) {
            await loadData();
            openCodeModal();
            return;
        }
        showMsg(data.message || "Активировано", data.ok);
        if (data.ok) await loadData();
        await loadResStatus();
    }

    async function toggleResStatus() {
        btnToggleRes.disabled = true;
        try {
            const enabled = btnToggleRes.dataset.enabled === "1";
            const action  = enabled ? "stop" : "enable";
            const r = await fetch(`/api/telegram/${id}/${action}`, {
                method: "POST",
                credentials: "same-origin",
            });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "toggle failed");
            await loadResStatus();
        } catch (e) {
            showMsg(String(e), false);
        } finally {
            btnToggleRes.disabled = false;
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
    btnToggleRes?.addEventListener("click", toggleResStatus);

    btnConfirmCode?.addEventListener("click", async () => {
        const code = (codeInput?.value || "").trim();
        if (!code) { showMsg("Введи код", false); return; }

        const r = await fetch(`/api/telegram/${id}/activate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ code }),
        });
        const data = await r.json();
        closeCodeModal();
        showMsg(data.message || (data.ok ? "Активировано" : "Ошибка"), data.ok);
        if (data.ok) await loadData();
        await loadResStatus();
    });

    btnCancelCode?.addEventListener("click", closeCodeModal);

    // ── инициализация ────────────────────────────────────────────────────

    (async () => {
        try {
            await loadData();
            await loadResStatus();
        } catch (e) {
            console.error("[telegram] init error:", e);
            showMsg("Ошибка загрузки ресурса", false);
        }
    })();
});
