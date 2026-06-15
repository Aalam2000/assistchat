document.addEventListener("DOMContentLoaded", () => {
    const id = PROMPT_RID;
    if (!id) return;

    const $ = (s) => document.querySelector(s);

    // ── элементы ──────────────────────────────────────────────────────────
    const label          = $("#promptLabel");
    const selSession     = $("#selSession");
    const selBot         = $("#selBot");
    const ownerTgId      = $("#ownerTgId");
    const chkPrivate     = $("#chkPrivate");
    const chkGroups      = $("#chkGroups");
    const chkChannels    = $("#chkChannels");
    const txtWhitelist   = $("#txtWhitelist");
    const txtBlacklist   = $("#txtBlacklist");
    const selApiKeysRes  = $("#selApiKeysResource");
    const selApiKeyField = $("#selApiKeyField");
    const selModel       = $("#selModel");
    const promptSystem   = $("#promptSystem");
    const promptContext  = $("#promptContext");
    const contextFileName = $("#contextFileName");
    const btnDeleteFile  = $("#btnDeleteContextFile");
    const contextFileInput = $("#contextFileInput");
    const stepsContainer = $("#stepsContainer");
    const examplesContainer = $("#examplesContainer");
    const btnSave        = $("#btnSave");
    const btnToggle      = $("#btnToggleStatus");
    const msgBox         = $("#promptMsg");
    const resStatus      = $("#promptResStatus");

    // ── состояние ─────────────────────────────────────────────────────────
    let _steps    = [];  // [{name, type, ...type-specific fields}]
    let _examples = [];  // [{user, assistant}]
    let _contextFile = null;  // rel path

    // Карта ключей → дефолтные модели
    const DEFAULT_MODELS = {
        "creds.openai_api_key":    "gpt-4o-mini",
        "creds.openai_admin_key":  "gpt-4o-mini",
        "creds.gemini_api_key":    "gemini-2.0-flash",
        "creds.anthropic_api_key": "claude-3-5-haiku-latest",
        "creds.groq_api_key":      "llama-3.1-8b-instant",
        "creds.deepseek_api_key":  "deepseek-chat",
        "creds.mistral_api_key":   "mistral-small-latest",
        "creds.xai_api_key":       "grok-2-1212",
    };

    const KEY_LABELS = {
        "creds.openai_api_key":    "OpenAI",
        "creds.openai_admin_key":  "OpenAI Admin",
        "creds.gemini_api_key":    "Google Gemini",
        "creds.anthropic_api_key": "Anthropic Claude",
        "creds.groq_api_key":      "Groq",
        "creds.deepseek_api_key":  "DeepSeek",
        "creds.mistral_api_key":   "Mistral",
        "creds.xai_api_key":       "xAI Grok",
    };

    // ── утилиты ──────────────────────────────────────────────────────────
    function showMsg(text, ok = true) {
        if (!msgBox) return;
        msgBox.textContent = text;
        msgBox.style.display = "block";
        msgBox.style.background = ok ? "#d4edda" : "#f8d7da";
        msgBox.style.color = ok ? "#155724" : "#721c24";
    }

    function listToText(arr) {
        return (arr || []).join("\n");
    }

    function textToList(str) {
        return (str || "").split("\n").map(s => s.trim()).filter(Boolean);
    }

    // ── шаги ─────────────────────────────────────────────────────────────

    function stepTypeFields(step, i) {
        const type = step.type || "condition";

        if (type === "condition") {
            const mode     = step.condition_mode || "keywords";
            const kwVal    = (step.keywords || []).join(", ");
            const sndrVal  = (step.senders  || []).join(", ");
            const onMatch  = step.on_match    || "continue";
            const onNoMatch = step.on_no_match || "stop";
            return `
              <div style="font-size:13px;margin-bottom:8px;display:flex;gap:16px">
                <label><input type="radio" name="cmode_${i}" value="keywords" ${mode==="keywords"?"checked":""}> По ключевым словам</label>
                <label><input type="radio" name="cmode_${i}" value="sender"   ${mode==="sender"  ?"checked":""}> По отправителю</label>
              </div>
              <div data-cond-kw="${i}" style="${mode!=="keywords"?"display:none":""}">
                <input type="text" placeholder="слово1, фраза два, слово3"
                  value="${escHtml(kwVal)}" style="width:100%;margin-bottom:8px;font-size:13px"
                  data-step-keywords="${i}">
              </div>
              <div data-cond-sndr="${i}" style="${mode!=="sender"?"display:none":""}">
                <input type="text" placeholder="@username, 123456789"
                  value="${escHtml(sndrVal)}" style="width:100%;margin-bottom:8px;font-size:13px"
                  data-step-senders="${i}">
              </div>
              <div style="font-size:13px;display:flex;flex-wrap:wrap;gap:12px">
                <span>Совпало →</span>
                <label><input type="radio" name="on_match_${i}"    value="continue" ${onMatch   ==="continue"?"checked":""}> Продолжить</label>
                <label><input type="radio" name="on_match_${i}"    value="stop"     ${onMatch   ==="stop"    ?"checked":""}> Стоп</label>
                <span style="margin-left:12px">Не совпало →</span>
                <label><input type="radio" name="on_no_match_${i}" value="stop"     ${onNoMatch ==="stop"    ?"checked":""}> Стоп</label>
                <label><input type="radio" name="on_no_match_${i}" value="continue" ${onNoMatch ==="continue"?"checked":""}> Продолжить</label>
              </div>`;
        }

        if (type === "ai") {
            const inst   = step.ai_instruction || "";
            const action = step.ai_action      || "continue";
            return `
              <textarea placeholder="Инструкция для AI — что проверить/проанализировать" rows="2"
                style="width:100%;margin-bottom:8px;font-size:13px"
                data-step-ai-inst="${i}">${escHtml(inst)}</textarea>
              <div style="font-size:13px;display:flex;gap:12px;flex-wrap:wrap">
                <span>Действие:</span>
                <label><input type="radio" name="ai_act_${i}" value="continue"     ${action==="continue"    ?"checked":""}> Продолжить</label>
                <label><input type="radio" name="ai_act_${i}" value="notify_owner" ${action==="notify_owner"?"checked":""}> Уведомить хозяина</label>
                <label><input type="radio" name="ai_act_${i}" value="stop"         ${action==="stop"        ?"checked":""}> Стоп</label>
              </div>`;
        }

        if (type === "notify") {
            const mode = step.notify_mode        || "direct";
            const inst = step.notify_instruction || "";
            return `
              <div style="font-size:13px;margin-bottom:8px;display:flex;gap:16px">
                <label><input type="radio" name="notify_mode_${i}" value="direct"       ${mode==="direct"      ?"checked":""}> Прямая пересылка (без AI)</label>
                <label><input type="radio" name="notify_mode_${i}" value="ai_formatted" ${mode==="ai_formatted"?"checked":""}> AI форматирует перед отправкой</label>
              </div>
              <div data-notify-inst-wrap="${i}" style="${mode!=="ai_formatted"?"display:none":""}">
                <textarea placeholder="Как AI должен сформировать уведомление" rows="2"
                  style="width:100%;font-size:13px"
                  data-step-notify-inst="${i}">${escHtml(inst)}</textarea>
              </div>`;
        }
        return "";
    }

    function renderSteps() {
        stepsContainer.innerHTML = "";
        _steps.forEach((step, i) => {
            const type = step.type || "condition";
            const div = document.createElement("div");
            div.style.cssText = "border:1px solid #ddd;border-radius:8px;padding:12px;margin-bottom:10px;background:#fafafa";
            div.innerHTML = `
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
                <span style="font-weight:600;font-size:13px">Шаг ${i+1}</span>
                <input type="text" value="${escHtml(step.name||"")}" placeholder="Название"
                  style="flex:1;font-size:13px" data-step-name="${i}">
                <select data-step-type="${i}" style="font-size:13px">
                  <option value="condition" ${type==="condition"?"selected":""}>🔍 Условие</option>
                  <option value="ai"        ${type==="ai"       ?"selected":""}>🤖 AI анализ</option>
                  <option value="notify"    ${type==="notify"   ?"selected":""}>📬 Уведомить хозяина</option>
                </select>
                <button class="btn" style="padding:2px 8px;font-size:12px" data-step-up="${i}"   ${i===0             ?"disabled":""}>↑</button>
                <button class="btn" style="padding:2px 8px;font-size:12px" data-step-down="${i}" ${i===_steps.length-1?"disabled":""}>↓</button>
                <button class="btn" style="padding:2px 8px;font-size:12px;color:#c00" data-step-del="${i}">✕</button>
              </div>
              <div data-step-fields="${i}">${stepTypeFields(step, i)}</div>`;
            stepsContainer.appendChild(div);
        });

        // тип шага
        stepsContainer.querySelectorAll("[data-step-type]").forEach(el => {
            el.addEventListener("change", e => {
                const idx = +e.target.dataset.stepType;
                _steps[idx] = { name: _steps[idx].name, type: e.target.value };
                renderSteps();
            });
        });

        // название
        stepsContainer.querySelectorAll("[data-step-name]").forEach(el => {
            el.addEventListener("input", e => { _steps[+e.target.dataset.stepName].name = e.target.value; });
        });

        // condition: режим
        stepsContainer.querySelectorAll("[name^='cmode_']").forEach(el => {
            el.addEventListener("change", e => {
                const idx  = +e.target.name.replace("cmode_", "");
                _steps[idx].condition_mode = e.target.value;
                stepsContainer.querySelector(`[data-cond-kw="${idx}"]`).style.display  = e.target.value === "keywords" ? "" : "none";
                stepsContainer.querySelector(`[data-cond-sndr="${idx}"]`).style.display = e.target.value === "sender"   ? "" : "none";
            });
        });
        stepsContainer.querySelectorAll("[data-step-keywords]").forEach(el => {
            el.addEventListener("input", e => {
                const idx = +e.target.dataset.stepKeywords;
                _steps[idx].keywords = e.target.value.split(",").map(s => s.trim()).filter(Boolean);
            });
        });
        stepsContainer.querySelectorAll("[data-step-senders]").forEach(el => {
            el.addEventListener("input", e => {
                const idx = +e.target.dataset.stepSenders;
                _steps[idx].senders = e.target.value.split(",").map(s => s.trim()).filter(Boolean);
            });
        });
        stepsContainer.querySelectorAll("[name^='on_match_']").forEach(el => {
            el.addEventListener("change", e => {
                _steps[+e.target.name.replace("on_match_", "")].on_match = e.target.value;
            });
        });
        stepsContainer.querySelectorAll("[name^='on_no_match_']").forEach(el => {
            el.addEventListener("change", e => {
                _steps[+e.target.name.replace("on_no_match_", "")].on_no_match = e.target.value;
            });
        });

        // ai
        stepsContainer.querySelectorAll("[data-step-ai-inst]").forEach(el => {
            el.addEventListener("input", e => { _steps[+e.target.dataset.stepAiInst].ai_instruction = e.target.value; });
        });
        stepsContainer.querySelectorAll("[name^='ai_act_']").forEach(el => {
            el.addEventListener("change", e => {
                _steps[+e.target.name.replace("ai_act_", "")].ai_action = e.target.value;
            });
        });

        // notify
        stepsContainer.querySelectorAll("[name^='notify_mode_']").forEach(el => {
            el.addEventListener("change", e => {
                const idx = +e.target.name.replace("notify_mode_", "");
                _steps[idx].notify_mode = e.target.value;
                const wrap = stepsContainer.querySelector(`[data-notify-inst-wrap="${idx}"]`);
                if (wrap) wrap.style.display = e.target.value === "ai_formatted" ? "" : "none";
            });
        });
        stepsContainer.querySelectorAll("[data-step-notify-inst]").forEach(el => {
            el.addEventListener("input", e => { _steps[+e.target.dataset.stepNotifyInst].notify_instruction = e.target.value; });
        });

        // перемещение / удаление
        stepsContainer.querySelectorAll("[data-step-del]").forEach(el => {
            el.addEventListener("click", e => { _steps.splice(+e.target.dataset.stepDel, 1); renderSteps(); });
        });
        stepsContainer.querySelectorAll("[data-step-up]").forEach(el => {
            el.addEventListener("click", e => {
                const i = +e.target.dataset.stepUp;
                [_steps[i-1], _steps[i]] = [_steps[i], _steps[i-1]]; renderSteps();
            });
        });
        stepsContainer.querySelectorAll("[data-step-down]").forEach(el => {
            el.addEventListener("click", e => {
                const i = +e.target.dataset.stepDown;
                [_steps[i], _steps[i+1]] = [_steps[i+1], _steps[i]]; renderSteps();
            });
        });
    }

    $("#btnAddStep")?.addEventListener("click", () => {
        _steps.push({ name: `Шаг ${_steps.length + 1}`, type: "condition",
            condition_mode: "keywords", keywords: [], on_match: "continue", on_no_match: "stop" });
        renderSteps();
    });

    // ── примеры ──────────────────────────────────────────────────────────
    function renderExamples() {
        examplesContainer.innerHTML = "";
        _examples.forEach((ex, i) => {
            const div = document.createElement("div");
            div.style.cssText = "border:1px solid #ddd;border-radius:8px;padding:12px;margin-bottom:10px;background:#fafafa";
            div.innerHTML = `
                <div style="display:flex;justify-content:space-between;margin-bottom:6px">
                    <span style="font-weight:600;font-size:13px">Пример ${i + 1}</span>
                    <button class="btn" style="padding:2px 8px;font-size:12px;color:#c00" data-ex-del="${i}">✕</button>
                </div>
                <label style="font-size:12px;opacity:.7">Входящее сообщение</label>
                <textarea rows="2" style="width:100%;margin-bottom:6px;font-size:13px" data-ex-user="${i}">${escHtml(ex.user)}</textarea>
                <label style="font-size:12px;opacity:.7">Ожидаемый ответ AI</label>
                <textarea rows="2" style="width:100%;font-size:13px" data-ex-asst="${i}">${escHtml(ex.assistant)}</textarea>
            `;
            examplesContainer.appendChild(div);
        });
        examplesContainer.querySelectorAll("[data-ex-user]").forEach(el => {
            el.addEventListener("input", e => { _examples[+e.target.dataset.exUser].user = e.target.value; });
        });
        examplesContainer.querySelectorAll("[data-ex-asst]").forEach(el => {
            el.addEventListener("input", e => { _examples[+e.target.dataset.exAsst].assistant = e.target.value; });
        });
        examplesContainer.querySelectorAll("[data-ex-del]").forEach(el => {
            el.addEventListener("click", e => {
                _examples.splice(+e.target.dataset.exDel, 1);
                renderExamples();
            });
        });
    }

    $("#btnAddExample")?.addEventListener("click", () => {
        _examples.push({ user: "", assistant: "" });
        renderExamples();
    });

    // ── загрузка ресурсов пользователя ────────────────────────────────────
    async function loadUserResources() {
        const r = await fetch("/api/providers/resources/list", { credentials: "same-origin" });
        const data = await r.json();
        if (!r.ok || !data.ok) return;

        const items = data.items || [];
        const sessions = items.filter(x => x.provider === "telegram");
        const bots     = items.filter(x => x.provider === "telegram_bot");
        const apiKeys  = items.filter(x => x.provider === "api_keys");

        // Сессии
        selSession.innerHTML = '<option value="">— не выбрано —</option>';
        sessions.forEach(s => {
            const o = document.createElement("option");
            o.value = s.id;
            o.textContent = s.label || s.id;
            selSession.appendChild(o);
        });

        // Боты
        selBot.innerHTML = '<option value="">— не выбрано —</option>';
        bots.forEach(b => {
            const o = document.createElement("option");
            o.value = b.id;
            o.textContent = b.label || b.id;
            selBot.appendChild(o);
        });

        // API Keys ресурсы
        selApiKeysRes.innerHTML = '<option value="">— выберите ресурс —</option>';
        apiKeys.forEach(k => {
            const o = document.createElement("option");
            o.value = k.id;
            o.textContent = k.label || k.id;
            // Храним verified для отображения ключей
            o.dataset.verified = JSON.stringify((k.meta || {}).verified || {});
            o.dataset.creds    = JSON.stringify(Object.keys((k.meta || {}).creds || {}));
            selApiKeysRes.appendChild(o);
        });
    }

    // ── динамика: ресурс ключей → список ключей ───────────────────────────
    selApiKeysRes.addEventListener("change", () => {
        const opt = selApiKeysRes.selectedOptions[0];
        selApiKeyField.innerHTML = '<option value="">— выберите ключ —</option>';
        selApiKeyField.disabled = true;
        selModel.innerHTML = '<option value="">— сначала выберите ключ —</option>';
        selModel.disabled = true;

        if (!opt || !opt.value) return;

        let verified = {};
        try { verified = JSON.parse(opt.dataset.verified || "{}"); } catch {}

        // Показываем только проверенные и рабочие ключи
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

        if (hasKeys) {
            selApiKeyField.disabled = false;
        } else {
            selApiKeyField.innerHTML = '<option value="">Нет рабочих ключей</option>';
        }
    });

    // ── динамика: ключ → список моделей ───────────────────────────────────
    selApiKeyField.addEventListener("change", async () => {
        const keyField = selApiKeyField.value;
        const resId = selApiKeysRes.value;

        selModel.innerHTML = '<option value="">Загрузка...</option>';
        selModel.disabled = true;

        if (!keyField || !resId) return;

        // Подставляем дефолт немедленно
        const defModel = DEFAULT_MODELS[keyField] || "";
        selModel.innerHTML = `<option value="${defModel}">${defModel} (рекомендуется)</option>`;
        selModel.disabled = false;

        // Запрашиваем полный список
        try {
            const r = await fetch(`/api/api_keys/${resId}/models?key_field=${encodeURIComponent(keyField)}`, {
                credentials: "same-origin",
            });
            const data = await r.json();
            if (data.ok && data.models?.length) {
                const current = selModel.value;
                selModel.innerHTML = "";
                data.models.forEach(m => {
                    const o = document.createElement("option");
                    o.value = m;
                    o.textContent = m + (m === defModel ? " ✓" : "");
                    if (m === current || (!current && m === defModel)) o.selected = true;
                    selModel.appendChild(o);
                });
                // Если дефолт не в списке — добавим первым
                if (defModel && !data.models.includes(defModel)) {
                    const o = document.createElement("option");
                    o.value = defModel;
                    o.textContent = defModel + " ✓";
                    selModel.prepend(o);
                    if (!current) selModel.value = defModel;
                }
            }
        } catch (e) {
            console.warn("[prompt] models fetch error:", e);
        }
    });

    // ── загрузка файла контекста ──────────────────────────────────────────
    contextFileInput?.addEventListener("change", async () => {
        const file = contextFileInput.files?.[0];
        if (!file) return;

        const fd = new FormData();
        fd.append("file", file);

        try {
            const r = await fetch(`/api/prompt/${id}/upload-context`, {
                method: "POST",
                credentials: "same-origin",
                body: fd,
            });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.detail || "upload failed");
            _contextFile = data.context_file;
            contextFileName.textContent = data.filename;
            btnDeleteFile.style.display = "inline-block";
            showMsg("Файл загружен: " + data.filename);
        } catch (e) {
            showMsg("Ошибка загрузки файла: " + e, false);
        }
        contextFileInput.value = "";
    });

    btnDeleteFile?.addEventListener("click", async () => {
        try {
            const r = await fetch(`/api/prompt/${id}/upload-context`, {
                method: "DELETE",
                credentials: "same-origin",
            });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error("delete failed");
            _contextFile = null;
            contextFileName.textContent = "";
            btnDeleteFile.style.display = "none";
            showMsg("Файл удалён");
        } catch (e) {
            showMsg("Ошибка удаления: " + e, false);
        }
    });

    // ── загрузка данных ресурса ───────────────────────────────────────────
    async function loadData() {
        const r = await fetch("/api/providers/resources/list", { credentials: "same-origin" });
        const data = await r.json();
        if (!r.ok || !data.ok) throw new Error("load failed");

        const item = (data.items || []).find(x => x.id === id);
        if (!item) throw new Error("resource not found");

        const meta     = item.meta || item.meta_json || {};
        const sources  = meta.sources || {};
        const owner    = meta.owner || {};
        const filters  = meta.filters || {};
        const ai       = meta.ai || {};
        const prompt   = meta.prompt || {};

        label.value = item.label || "";

        // Источники (ждём пока options загружены)
        selSession.value = sources.telegram_session_rid || "";
        selBot.value     = sources.telegram_bot_rid || "";

        // Хозяин
        ownerTgId.value = owner.telegram_user_id || "";

        // Фильтры
        chkPrivate.checked  = filters.reply_private  ?? true;
        chkGroups.checked   = filters.reply_groups   ?? false;
        chkChannels.checked = filters.reply_channels ?? false;
        txtWhitelist.value  = listToText(filters.whitelist);
        txtBlacklist.value  = listToText(filters.blacklist);

        // AI
        if (ai.api_keys_resource_id) {
            selApiKeysRes.value = ai.api_keys_resource_id;
            selApiKeysRes.dispatchEvent(new Event("change"));
            // Ждём немного чтобы options отрисовались
            await new Promise(r => setTimeout(r, 50));
            if (ai.api_key_field) {
                selApiKeyField.value = ai.api_key_field;
                selApiKeyField.dispatchEvent(new Event("change"));
                await new Promise(r => setTimeout(r, 300));
                if (ai.model) selModel.value = ai.model;
            }
        }

        // Промпт (совместимость со старым форматом system_prompt → system)
        promptSystem.value  = prompt.system  || prompt.system_prompt || "";
        promptContext.value = prompt.context || prompt.description   || "";

        // Файл контекста
        _contextFile = prompt.context_file || null;
        if (_contextFile) {
            const parts = _contextFile.split("/");
            contextFileName.textContent = parts[parts.length - 1];
            btnDeleteFile.style.display = "inline-block";
        } else {
            contextFileName.textContent = "";
            btnDeleteFile.style.display = "none";
        }

        // Шаги и примеры — migrate old format {instruction, action} → new typed format
        const rawSteps = prompt.steps || [];
        _steps = rawSteps.map(s => {
            if (s.type) return JSON.parse(JSON.stringify(s)); // already new format
            // old: {name, instruction, action}
            const action = s.action || "continue";
            if (action === "notify_owner") {
                return { name: s.name || "Уведомление", type: "notify",
                    notify_mode: "direct", notify_instruction: "" };
            }
            return { name: s.name || "AI шаг", type: "ai",
                ai_instruction: s.instruction || "", ai_action: action };
        });
        _examples = JSON.parse(JSON.stringify(prompt.examples || []));
        renderSteps();
        renderExamples();
    }

    // ── сборка meta_json ──────────────────────────────────────────────────
    function buildMeta() {
        return {
            sources: {
                telegram_session_rid: selSession.value || null,
                telegram_bot_rid:     selBot.value     || null,
            },
            owner: {
                telegram_user_id: ownerTgId.value ? parseInt(ownerTgId.value) : null,
            },
            filters: {
                reply_private:  chkPrivate.checked,
                reply_groups:   chkGroups.checked,
                reply_channels: chkChannels.checked,
                whitelist: textToList(txtWhitelist.value),
                blacklist: textToList(txtBlacklist.value),
            },
            ai: {
                api_keys_resource_id: selApiKeysRes.value || null,
                api_key_field:        selApiKeyField.value || null,
                model:                selModel.value || null,
            },
            prompt: {
                system:       promptSystem.value,
                context:      promptContext.value,
                context_file: _contextFile,
                steps:        _steps,
                examples:     _examples,
            },
        };
    }

    async function saveData() {
        const payload = {
            label:     (label.value || "").trim() || "Промпт",
            meta_json: buildMeta(),
        };
        const r = await fetch(`/api/prompt/${id}`, {
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
            const r = await fetch(`/api/prompt/${id}/status`, { credentials: "same-origin" });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error();

            const status = data.resource_status ?? "—";
            const phase  = data.phase ? ` (${data.phase})` : "";
            const icon   = data.running ? "🟢" : (data.active ? "🟡" : "🔴");

            resStatus.textContent = `РЕСУРС: ${status}${phase} ${icon}`;
            btnToggle.textContent = status === "active" ? "💡 Остановить" : "💡 Включить";
            btnToggle.dataset.enabled = status === "active" ? "1" : "0";

            if (data.error_message) showMsg(data.error_message, false);
        } catch {
            resStatus.textContent = "РЕСУРС: ошибка статуса";
        }
    }

    async function toggleStatus() {
        btnToggle.disabled = true;
        try {
            const enabled = btnToggle.dataset.enabled === "1";
            const action  = enabled ? "stop" : "enable";
            const r = await fetch(`/api/prompt/${id}/${action}`, {
                method: "POST",
                credentials: "same-origin",
            });
            const data = await r.json();
            if (!r.ok || !data.ok) throw new Error(data.message || "failed");
            showMsg(data.message || "OK");
            await loadResStatus();
        } catch (e) {
            showMsg(String(e), false);
        } finally {
            btnToggle.disabled = false;
        }
    }

    // ── события ──────────────────────────────────────────────────────────
    btnSave?.addEventListener("click", async () => {
        try {
            await saveData();
            showMsg("Сохранено");
        } catch (e) {
            showMsg("Ошибка сохранения: " + e, false);
        }
    });

    btnToggle?.addEventListener("click", toggleStatus);

    // ── пикер диалогов ───────────────────────────────────────────────────
    (function () {
        const overlay      = $("#dialogPickerOverlay");
        const pickerTitle  = $("#pickerTitle");
        const pickerSearch = $("#pickerSearch");
        const pickerList   = $("#pickerList");
        const pickerLoading = $("#pickerLoading");
        const btnClose     = $("#btnPickerClose");
        const chkUser      = $("#pickerFilterUser");
        const chkGroup     = $("#pickerFilterGroup");
        const chkChannel   = $("#pickerFilterChannel");

        let _targetTxt = null;   // txtWhitelist | txtBlacklist
        let _allDialogs = [];    // кэш

        function currentEntries() {
            return textToList(_targetTxt?.value || "");
        }

        function isAdded(d) {
            const entries = currentEntries();
            return entries.includes(d.username) || entries.includes(d.peer_id);
        }

        function kindIcon(k) {
            return k === "user" ? "👤" : k === "channel" ? "📢" : "👥";
        }

        function renderList() {
            const q  = (pickerSearch?.value || "").toLowerCase();
            const showUser    = chkUser?.checked;
            const showGroup   = chkGroup?.checked;
            const showChannel = chkChannel?.checked;

            const filtered = _allDialogs.filter(d => {
                if (d.kind === "user"    && !showUser)    return false;
                if (d.kind === "group"   && !showGroup)   return false;
                if (d.kind === "channel" && !showChannel) return false;
                if (q) {
                    const name = (d.name || "").toLowerCase();
                    const uname = (d.username || "").toLowerCase();
                    if (!name.includes(q) && !uname.includes(q)) return false;
                }
                return true;
            });

            if (!filtered.length) {
                pickerList.innerHTML = `<div style="padding:16px;text-align:center;opacity:.6">Ничего не найдено</div>`;
                return;
            }

            pickerList.innerHTML = filtered.map(d => {
                const added = isAdded(d);
                const sub = d.username ? `<span style="opacity:.5;font-size:12px">${escHtml(d.username)}</span>` : "";
                return `<div data-peer="${escHtml(d.peer_id)}" data-uname="${escHtml(d.username || "")}"
                    style="display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:5px;cursor:pointer;
                           ${added ? "opacity:.5" : ""}transition:background .15s"
                    onmouseover="this.style.background='rgba(0,0,0,.06)'"
                    onmouseout="this.style.background=''"
                >
                  <span style="font-size:16px">${kindIcon(d.kind)}</span>
                  <span style="flex:1;min-width:0">
                    <span style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(d.name)}</span>
                    ${sub}
                  </span>
                  <span style="font-size:14px;min-width:16px">${added ? "✓" : ""}</span>
                </div>`;
            }).join("");

            pickerList.querySelectorAll("[data-peer]").forEach(el => {
                el.addEventListener("click", () => {
                    const peer  = el.dataset.peer;
                    const uname = el.dataset.uname;
                    const value = uname || peer;
                    const entries = currentEntries();
                    if (!entries.includes(value) && !entries.includes(peer)) {
                        const lines = _targetTxt.value.trim();
                        _targetTxt.value = lines ? lines + "\n" + value : value;
                    }
                    renderList();
                });
            });
        }

        async function openPicker(targetTxt, title) {
            _targetTxt = targetTxt;
            if (pickerTitle) pickerTitle.textContent = title;
            if (pickerSearch) pickerSearch.value = "";
            overlay.style.display = "flex";

            if (_allDialogs.length) { renderList(); return; }

            if (pickerList) pickerList.innerHTML = `<div id="pickerLoading" style="padding:16px;text-align:center;opacity:.6">Загрузка…</div>`;

            // Берём resource_id сессии из селектора
            const sessionRid = selSession?.value;
            if (!sessionRid) {
                pickerList.innerHTML = `<div style="padding:16px;text-align:center;opacity:.6">Сначала выберите Telegram-сессию</div>`;
                return;
            }

            try {
                const resp = await fetch(`/api/telegram/${sessionRid}/dialogs`);
                const data = await resp.json();
                if (!data.ok) throw new Error(data.detail || "Ошибка");
                _allDialogs = data.dialogs || [];
                renderList();
            } catch (e) {
                pickerList.innerHTML = `<div style="padding:16px;text-align:center;color:#c00">Ошибка: ${escHtml(String(e))}</div>`;
            }
        }

        // Сбрасываем кэш при смене сессии
        selSession?.addEventListener("change", () => { _allDialogs = []; });

        $("#btnPickWhitelist")?.addEventListener("click", () => openPicker(txtWhitelist, "Белый список — выберите чаты"));
        $("#btnPickBlacklist")?.addEventListener("click", () => openPicker(txtBlacklist, "Чёрный список — выберите чаты"));

        btnClose?.addEventListener("click", () => { overlay.style.display = "none"; });
        overlay?.addEventListener("click", e => { if (e.target === overlay) overlay.style.display = "none"; });
        pickerSearch?.addEventListener("input", renderList);
        chkUser?.addEventListener("change", renderList);
        chkGroup?.addEventListener("change", renderList);
        chkChannel?.addEventListener("change", renderList);
    })();

    // ── вспомогательные ──────────────────────────────────────────────────
    function escHtml(s) {
        return (s || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    // ── инициализация ─────────────────────────────────────────────────────
    (async () => {
        try {
            await loadUserResources();
            await loadData();
            await loadResStatus();
        } catch (e) {
            console.error("[prompt] init error:", e);
            showMsg("Ошибка загрузки ресурса", false);
        }
    })();
});
