document.addEventListener("DOMContentLoaded", () => {
    const id = TG_RID;
    if (!id) return;

    const $ = (s) => document.querySelector(s);

    // fields
    const label = $("#tgLabel");
    const appId = $("#tgAppId");
    const appHash = $("#tgAppHash");
    const phone = $("#tgPhone");
    const stringSession = $("#tgStringSession");

    const promptId = $("#tgPromptId");
    const apiKeysId = $("#tgApiKeysId");
    const keyField = $("#tgKeyField");
    const model = $("#tgModel");
    const preferVoice = $("#tgPreferVoice");

    const whitelist = $("#tgWhitelist");
    const blacklist = $("#tgBlacklist");

    const replyPrivate = $("#tgReplyPrivate");
    const replyGroups = $("#tgReplyGroups");
    const replyChannels = $("#tgReplyChannels");

    // buttons
    const btnSave = $("#btnSave");
    const btnActivate = $("#btnActivate");
    const btnToggleRes = $("#btnToggleStatus");

    const tgResStatus = $("#tgResStatus");
    const tgMsg = $("#tgMsg");

    // details toggle
    const btnToggleDetails = $("#btnToggleDetails");
    const tgConnectionBlock = $("#tgConnectionBlock");

    // code modal
    const tgCodeModal = $("#tgCodeModal");
    const codeInput = $("#tgCodeInput");
    const btnConfirmCode = $("#btnConfirmCode");
    const btnCancelCode = $("#btnCancelCode");

    // ── Состояние ──────────────────────────────────────────────────────────────
    let _allItems = [];
    let _activationCreds = {};
    let _hasStringSession = false;
    let _resourceActive = false;

    // ── Inline-сообщения (вместо alert) ────────────────────────────────────────
    function showMsg(text, type = "info") {
        if (!tgMsg) return;
        const colors = {
            ok:    { bg: "#d4edda", color: "#155724", border: "#c3e6cb" },
            error: { bg: "#f8d7da", color: "#721c24", border: "#f5c6cb" },
            info:  { bg: "#d1ecf1", color: "#0c5460", border: "#bee5eb" },
            warn:  { bg: "#fff3cd", color: "#856404", border: "#ffeeba" },
        };
        const s = colors[type] || colors.info;
        tgMsg.style.cssText = `display:block;padding:8px 12px;border-radius:6px;margin:10px 0;
            font-size:14px;background:${s.bg};color:${s.color};border:1px solid ${s.border}`;
        tgMsg.textContent = text;
    }

    function clearMsg() {
        if (tgMsg) tgMsg.style.display = "none";
    }

    // ── Debounce кнопок ────────────────────────────────────────────────────────
    // Блокирует кнопку на ms мс после клика, независимо от результата
    function btnLock(btn, ms = 3000) {
        btn.disabled = true;
        setTimeout(() => { btn.disabled = false; }, ms);
    }

    // ── Парсинг/построение мета ────────────────────────────────────────────────
    const parseList = (s) =>
        (s || "")
            .split(/[\n,;]+|,\s*/g)
            .map((x) => x.trim())
            .filter(Boolean);

    const KEY_SPECS = [
        { field: "creds.openai_api_key",   label: "ChatGPT" },
        { field: "creds.openai_admin_key",  label: "ChatGPT ADMIN" },
        { field: "creds.gemini_api_key",    label: "Gemini" },
        { field: "creds.anthropic_api_key", label: "Anthropic" },
        { field: "creds.groq_api_key",      label: "Groq" },
        { field: "creds.deepseek_api_key",  label: "DeepSeek" },
        { field: "creds.mistral_api_key",   label: "Mistral" },
        { field: "creds.xai_api_key",       label: "xAI" },
        { field: "creds.deepgram_api_key",  label: "Deepgram" },
    ];

    function getByPath(obj, path) {
        let cur = obj || {};
        for (const k of (path || "").split(".")) {
            if (!cur || typeof cur !== "object" || !(k in cur)) return undefined;
            cur = cur[k];
        }
        return cur;
    }

    function getKeySpec(field) {
        return KEY_SPECS.find((s) => s.field === field) || null;
    }

    function openCodeModal() {
        tgCodeModal?.classList.remove("hidden");
        codeInput?.focus();
    }

    function closeCodeModal() {
        tgCodeModal?.classList.add("hidden");
        if (codeInput) codeInput.value = "";
    }

    function setOptions(select, items, selected) {
        select.innerHTML = "";
        const opt0 = document.createElement("option");
        opt0.value = "";
        opt0.textContent = "— выбери —";
        select.appendChild(opt0);
        items.forEach((it) => {
            const o = document.createElement("option");
            o.value = it.id;
            o.textContent = it.label || it.id;
            if (it.id === selected) o.selected = true;
            select.appendChild(o);
        });
    }

    function setKeyFieldDisabled(msg) {
        keyField.innerHTML = "";
        const o = document.createElement("option");
        o.value = "";
        o.textContent = msg;
        keyField.appendChild(o);
        keyField.disabled = true;
        keyField.value = "";
    }

    function refreshKeyFieldOptions(selectedField) {
        const keysRid = (apiKeysId.value || "").trim();
        if (!keysRid) {
            setKeyFieldDisabled("— выбери API_KEYS ресурс —");
            return;
        }
        const keysRes = _allItems.find((x) => x.id === keysRid);
        const keysMeta = keysRes?.meta || keysRes?.meta_json || {};
        const available = KEY_SPECS.filter((s) => {
            const v = getByPath(keysMeta, s.field);
            return typeof v === "string" && v.trim().length > 0;
        });
        if (!available.length) {
            setKeyFieldDisabled("— в API_KEYS нет заполненных ключей —");
            return;
        }
        keyField.disabled = false;
        keyField.innerHTML = "";
        const opt0 = document.createElement("option");
        opt0.value = "";
        opt0.textContent = "— выбери —";
        keyField.appendChild(opt0);
        let foundSelected = false;
        for (const s of available) {
            const o = document.createElement("option");
            o.value = s.field;
            o.textContent = s.label;
            if (s.field === selectedField) {
                o.selected = true;
                foundSelected = true;
            }
            keyField.appendChild(o);
        }
        if (!foundSelected) keyField.value = available[0].field;
    }

    function setModelDisabled(msg, value = "") {
        if (!model) return;
        if (model.tagName !== "SELECT") {
            model.value = value || "";
            model.disabled = true;
            return;
        }
        model.innerHTML = "";
        const o = document.createElement("option");
        o.value = value || "";
        o.textContent = msg;
        model.appendChild(o);
        model.value = o.value;
        model.disabled = true;
    }

    async function refreshModelOptions(selectedModel) {
        const keysRid = (apiKeysId.value || "").trim();
        const kf = (keyField.value || "").trim();
        if (!keysRid) { setModelDisabled("— выбери API_KEYS ресурс —"); return; }
        if (!kf || keyField.disabled) { setModelDisabled("— выбери ключ —"); return; }
        setModelDisabled("— загрузка моделей… —");
        const spec = getKeySpec(kf);
        const fallbackName = (spec?.label || "").trim() || "AI";
        const wanted = (selectedModel || "").trim();
        let data = null;
        try {
            const r = await fetch(
                `/api/api_keys/${keysRid}/models?key_field=${encodeURIComponent(kf)}`,
                { credentials: "same-origin" }
            );
            data = await r.json();
        } catch (e) { data = null; }
        const list = Array.isArray(data?.models)
            ? data.models.filter((x) => typeof x === "string" && x.trim())
            : [];
        if (list.length <= 1) {
            const one = (list[0] || wanted || fallbackName).trim();
            setModelDisabled(one, one);
            return;
        }
        if (model.tagName !== "SELECT") {
            model.disabled = false;
            model.value = wanted || list[0];
            return;
        }
        model.disabled = false;
        model.innerHTML = "";
        if (wanted && !list.includes(wanted)) {
            const o = document.createElement("option");
            o.value = wanted;
            o.textContent = wanted;
            model.appendChild(o);
        }
        for (const m of list) {
            const o = document.createElement("option");
            o.value = m;
            o.textContent = m;
            if (m === wanted) o.selected = true;
            model.appendChild(o);
        }
        if (!model.value) model.value = list[0];
    }

    // ── Загрузка данных ────────────────────────────────────────────────────────
    async function loadResourceList() {
        const r = await fetch(`/api/providers/resources/list`, { credentials: "same-origin" });
        const data = await r.json();
        if (!r.ok || !data.ok) throw new Error(data.error || "load failed");
        return data.items || [];
    }

    function readMetaCompat(meta) {
        const creds = meta.creds || {};
        const lists = meta.lists || meta.session || {};
        const rules = meta.rules || meta.routing || {};
        const ai = meta.ai || {};
        return {
            label: meta.label || "",
            creds: {
                app_id: creds.app_id || "",
                app_hash: creds.app_hash || "",
                phone: creds.phone || "",
                string_session: creds.string_session || "",
            },
            prompt_id: meta.prompt_id || meta.promptId || "",
            ai_keys_resource_id: meta.ai_keys_resource_id || ai.api_keys_resource_id || "",
            ai_key_field: meta.ai_key_field || ai.api_key_field || "creds.openai_api_key",
            model: meta.model || ai.model || "",
            prefer_voice_reply: meta.prefer_voice_reply ?? ai.prefer_voice_reply ?? true,
            lists: {
                whitelist: lists.whitelist || [],
                blacklist: lists.blacklist || [],
            },
            rules: {
                reply_private: rules.reply_private ?? true,
                reply_groups: rules.reply_groups ?? false,
                reply_channels: rules.reply_channels ?? false,
            },
        };
    }

    function buildMeta() {
        const string_session = (stringSession.value || "").trim();
        const creds = {
            app_id: (appId.value || "").trim(),
            app_hash: (appHash.value || "").trim(),
            phone: (phone.value || "").trim(),
            string_session,
        };
        // Сервер сам защищает activation-поля при PUT, но дублируем на всякий случай
        if (!string_session && _activationCreds.phone_code_hash) {
            creds.phone_code_hash = _activationCreds.phone_code_hash;
            creds.pending_session = _activationCreds.pending_session;
        }
        if (_activationCreds.flood_until_ts) {
            creds.flood_until_ts = _activationCreds.flood_until_ts;
        }
        return {
            creds,
            prompt_id: (promptId.value || "").trim(),
            ai_keys_resource_id: (apiKeysId.value || "").trim(),
            ai_key_field: (keyField.value || "").trim(),
            model: (model.value || "").trim(),
            prefer_voice_reply: !!preferVoice.checked,
            lists: {
                whitelist: parseList(whitelist.value),
                blacklist: parseList(blacklist.value),
            },
            rules: {
                reply_private: !!replyPrivate.checked,
                reply_groups: !!replyGroups.checked,
                reply_channels: !!replyChannels.checked,
            },
        };
    }

    async function loadData() {
        const items = await loadResourceList();
        _allItems = items;
        const item = items.find((x) => x.id === id);
        if (!item) throw new Error("resource not found");

        const rawMeta = item.meta || item.meta_json || {};
        const meta = readMetaCompat(rawMeta);
        const rawCreds = rawMeta.creds || {};

        _hasStringSession = !!(meta.creds.string_session);
        _activationCreds = {
            phone_code_hash: rawCreds.phone_code_hash || null,
            pending_session: rawCreds.pending_session || null,
            flood_until_ts: rawCreds.flood_until_ts || null,
        };
        if (meta.creds.string_session) {
            _activationCreds = {};
        }

        label.value = item.label || "";
        appId.value = meta.creds.app_id || "";
        appHash.value = meta.creds.app_hash || "";
        phone.value = meta.creds.phone || "";
        stringSession.value = meta.creds.string_session || "";

        const prompts = items.filter((x) => x.provider === "prompt");
        const keys = items.filter((x) => x.provider === "api_keys");
        setOptions(promptId, prompts, meta.prompt_id || "");
        setOptions(apiKeysId, keys, meta.ai_keys_resource_id || "");
        refreshKeyFieldOptions(meta.ai_key_field || "creds.openai_api_key");
        preferVoice.checked = !!meta.prefer_voice_reply;
        await refreshModelOptions(meta.model || "");

        whitelist.value = (meta.lists.whitelist || []).join(", ");
        blacklist.value = (meta.lists.blacklist || []).join(", ");
        replyPrivate.checked = !!meta.rules.reply_private;
        replyGroups.checked = !!meta.rules.reply_groups;
        replyChannels.checked = !!meta.rules.reply_channels;
    }

    // ── Статус ресурса (без probe — только из БД) ──────────────────────────────
    async function loadResStatus() {
        try {
            const r = await fetch(`/api/telegram/${id}/status`, { credentials: "same-origin" });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.error || "load failed");

            const status = data.resource_status ?? "—";
            const phase = data.phase ? ` (${data.phase})` : "";
            const running = !!data.running;
            const active = !!data.active;
            const hasSession = !!(data.has_session ?? _hasStringSession);

            // Обновляем _hasStringSession из ответа сервера
            _hasStringSession = hasSession;
            _resourceActive = active;

            // Иконка состояния
            let icon = "⚪";
            if (running) icon = "🟢";
            else if (active) icon = "🟡";
            else if (data.last_error_code) icon = "🔴";

            tgResStatus.textContent = `РЕСУРС: ${status}${phase} ${icon}`;

            // Кнопка тоггла
            _updateToggleBtn(hasSession, active);

            // Кнопка Активировать — только если нет сессии или есть ошибка авторизации
            if (btnActivate) {
                const needReauth = data.last_error_code === "telegram_not_authorized";
                const showActivate = !hasSession || needReauth;
                btnActivate.classList.toggle("hidden", !showActivate);
                btnActivate.disabled = false;
            }

            // Показываем last_error если есть
            if (data.last_error_code && !running) {
                const errText = data.error_message
                    ? `Ошибка: ${data.error_message}`
                    : `Код ошибки: ${data.last_error_code}`;
                // Не перебиваем пользовательские сообщения — только если нет своего
                if (tgMsg && tgMsg.style.display === "none") {
                    showMsg(errText, "warn");
                }
            }
        } catch {
            tgResStatus.textContent = "РЕСУРС: ошибка статуса";
        }
    }

    function _updateToggleBtn(hasSession, active) {
        if (!btnToggleRes) return;
        if (!hasSession) {
            btnToggleRes.textContent = "▶️ Активировать";
            btnToggleRes.dataset.mode = "activate";
        } else if (active) {
            btnToggleRes.textContent = "⏸ Выключить";
            btnToggleRes.dataset.mode = "disable";
        } else {
            btnToggleRes.textContent = "▶️ Включить";
            btnToggleRes.dataset.mode = "enable";
        }
    }

    // ── Сохранение ────────────────────────────────────────────────────────────
    async function saveData() {
        const payload = {
            label: (label.value || "").trim() || "Telegram ассистент",
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

    // ── Активация (создание сессии через телефон + код) ────────────────────────
    async function activate() {
        // Сначала сохраняем актуальные кредсы
        try {
            await saveData();
        } catch (e) {
            showMsg("Сохрани App ID, App Hash и номер телефона перед активацией", "error");
            return;
        }

        showMsg("Запрашиваем код у Telegram…", "info");
        const r = await fetch(`/api/telegram/${id}/activate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({}),
        });
        const data = await r.json();

        if (data.need_code) {
            showMsg("Код отправлен в Telegram. Введи его в открывшемся окне.", "info");
            await loadData();
            openCodeModal();
            return;
        }

        if (data.ok && data.authorized) {
            showMsg(data.message || "Сессия активирована", "ok");
            await loadData();
        } else {
            showMsg(data.message || "Ошибка активации", data.need_reauth ? "warn" : "error");
        }
        await loadResStatus();
    }

    // ── Кнопка вкл/выкл ───────────────────────────────────────────────────────
    async function toggleResStatus() {
        btnLock(btnToggleRes, 4000);
        clearMsg();

        const mode = btnToggleRes.dataset.mode;

        if (mode === "activate") {
            await activate();
            return;
        }

        const action = mode === "disable" ? "stop" : "enable";
        try {
            const r = await fetch(`/api/telegram/${id}/${action}`, {
                method: "POST",
                credentials: "same-origin",
            });
            const data = await r.json();
            if (!r.ok || !data.ok) {
                showMsg(data.message || "Ошибка переключения", "error");
            } else {
                showMsg(data.message || (action === "enable" ? "Ресурс включён" : "Ресурс остановлен"), "ok");
            }
        } catch (e) {
            showMsg("Сетевая ошибка: " + e.message, "error");
        }
        await loadResStatus();
    }

    // ── События ────────────────────────────────────────────────────────────────
    btnSave?.addEventListener("click", async () => {
        btnLock(btnSave, 2000);
        clearMsg();
        try {
            await saveData();
            showMsg("Сохранено", "ok");
            await loadData();
        } catch (e) {
            showMsg("Ошибка сохранения: " + e.message, "error");
        }
    });

    apiKeysId?.addEventListener("change", () => {
        refreshKeyFieldOptions("");
        refreshModelOptions("");
    });

    keyField?.addEventListener("change", () => {
        refreshModelOptions("");
    });

    btnActivate?.addEventListener("click", async () => {
        btnLock(btnActivate, 5000);
        clearMsg();
        await activate();
    });

    btnToggleRes?.addEventListener("click", toggleResStatus);

    btnConfirmCode?.addEventListener("click", async () => {
        const code = (codeInput?.value || "").trim();
        if (!code) {
            showMsg("Введи код подтверждения", "warn");
            return;
        }
        btnLock(btnConfirmCode, 5000);

        const r = await fetch(`/api/telegram/${id}/activate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ code }),
        });
        const data = await r.json();
        closeCodeModal();

        if (data.ok) {
            showMsg(data.message || "Telegram активирован успешно", "ok");
            await loadData();
        } else {
            showMsg(data.message || "Ошибка подтверждения кода", "error");
        }
        await loadResStatus();
    });

    btnCancelCode?.addEventListener("click", () => {
        closeCodeModal();
        showMsg("Активация отменена", "info");
    });

    btnToggleDetails?.addEventListener("click", () => {
        if (!tgConnectionBlock) return;
        const hidden = tgConnectionBlock.classList.toggle("hidden");
        btnToggleDetails.textContent = hidden
            ? "⚙️ Показать настройки подключения"
            : "🔽 Скрыть настройки подключения";
    });

    // ── Инициализация ──────────────────────────────────────────────────────────
    (async () => {
        try {
            await loadData();
            await loadResStatus();
        } catch (e) {
            console.error("[telegram] init error:", e);
            showMsg("Ошибка загрузки данных ресурса", "error");
        }
    })();
});
