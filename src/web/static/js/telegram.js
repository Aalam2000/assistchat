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

  // details toggle
  const btnToggleDetails = $("#btnToggleDetails");
  const tgConnectionBlock = $("#tgConnectionBlock");

  // code modal (пока просто UI)
  const tgCodeModal = $("#tgCodeModal");
  const codeInput = $("#tgCodeInput");
  const btnConfirmCode = $("#btnConfirmCode");
  const btnCancelCode = $("#btnCancelCode");

  const parseList = (s) =>
    (s || "")
      .split(/[\n,;]+|,\s*/g)
      .map((x) => x.trim())
      .filter(Boolean);

  const KEY_SPECS = [
    { field: "creds.openai_api_key", label: "ChatGPT" },
    { field: "creds.openai_admin_key", label: "ChatGPT ADMIN" },
    { field: "creds.gemini_api_key", label: "Gemini" },
    { field: "creds.anthropic_api_key", label: "Anthropic" },
    { field: "creds.groq_api_key", label: "Groq" },
    { field: "creds.deepseek_api_key", label: "DeepSeek" },
    { field: "creds.mistral_api_key", label: "Mistral" },
    { field: "creds.xai_api_key", label: "xAI" },
    { field: "creds.deepgram_api_key", label: "Deepgram" },
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
      // ВАЖНО: в UI показываем только название (без id)
      o.textContent = it.label || it.id;
      if (it.id === selected) o.selected = true;
      select.appendChild(o);
    });
  }

  let _allItems = [];

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

    if (!keysRid) {
      setModelDisabled("— выбери API_KEYS ресурс —");
      return;
    }
    if (!kf || keyField.disabled) {
      setModelDisabled("— выбери ключ —");
      return;
    }

    // пока грузим
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
    } catch (e) {
      data = null;
    }

    const list = Array.isArray(data?.models)
      ? data.models.filter((x) => typeof x === "string" && x.trim())
      : [];

    // 0/1 модель => readonly
    if (list.length <= 1) {
      const one = (list[0] || wanted || fallbackName).trim();
      setModelDisabled(one, one);
      return;
    }

    // много моделей => select активен
    if (model.tagName !== "SELECT") {
      // если кто-то не заменил HTML — просто не ломаем страницу
      model.disabled = false;
      model.value = wanted || list[0];
      return;
    }

    model.disabled = false;
    model.innerHTML = "";

    // если сохранённая модель не в списке — добавим сверху (не теряем)
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
    return {
      creds: {
        app_id: (appId.value || "").trim(),
        app_hash: (appHash.value || "").trim(),
        phone: (phone.value || "").trim(),
        string_session: (stringSession.value || "").trim(),
      },
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

    const meta = readMetaCompat(item.meta || item.meta_json || {});

    label.value = item.label || "";

    appId.value = meta.creds.app_id || "";
    appHash.value = meta.creds.app_hash || "";
    phone.value = meta.creds.phone || "";
    stringSession.value = meta.creds.string_session || "";

    // dropdowns
    const prompts = items.filter((x) => x.provider === "prompt");
    const keys = items.filter((x) => x.provider === "api_keys");

    setOptions(promptId, prompts, meta.prompt_id || "");
    setOptions(apiKeysId, keys, meta.ai_keys_resource_id || "");

    refreshKeyFieldOptions(meta.ai_key_field || "creds.openai_api_key");
    preferVoice.checked = !!meta.prefer_voice_reply;

    // модели — зависят от ключа
    await refreshModelOptions(meta.model || "");

    whitelist.value = (meta.lists.whitelist || []).join(", ");
    blacklist.value = (meta.lists.blacklist || []).join(", ");

    replyPrivate.checked = !!meta.rules.reply_private;
    replyGroups.checked = !!meta.rules.reply_groups;
    replyChannels.checked = !!meta.rules.reply_channels;
  }

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

  async function activate() {
    // для проверки живости нужна именно string_session
    if (!appId.value.trim() || !appHash.value.trim() || !stringSession.value.trim()) {
      alert("Заполни App ID, App Hash и String Session");
      return;
    }

    await saveData();

    const r = await fetch(`/api/telegram/${id}/activate`, { method: "POST", credentials: "same-origin" });
    const data = await r.json();

    if (!r.ok || !data.ok) {
      alert(data.error || "Ошибка активации");
      return;
    }

    if (data.authorized === false) {
      alert(data.message || "Сессия не активна");
      await loadResStatus();
      return;
    }

    if (data.need_code) openCodeModal();
    alert(data.message || "Telegram активирован");
    await loadResStatus();
  }

  async function loadResStatus() {
    try {
      const r = await fetch(`/api/telegram/${id}/status?probe=1`, { credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "load failed");

      const status = data.resource_status ?? data.status ?? "—";
      const enabled = String(status).toLowerCase() === "active";
      const authorized = !!(data.authorized ?? false);
      const phase = data.phase ? ` (${data.phase})` : "";

      tgResStatus.textContent = `РЕСУРС: ${status}${phase} ${authorized ? "🟢" : "🔴"}`;
      btnToggleRes.textContent = enabled ? "💡 Остановить ресурс" : "💡 Включить ресурс";
      btnToggleRes.dataset.enabled = enabled ? "1" : "0";

      if (btnActivate) {
        // показываем кнопку только если сессия НЕ живая
        btnActivate.classList.toggle("hidden", authorized);
        btnActivate.disabled = authorized;
      }
    } catch {
      tgResStatus.textContent = "РЕСУРС: ошибка статуса";
    }
  }

  async function toggleResStatus() {
    btnToggleRes.disabled = true;
    try {
      const enabled = btnToggleRes.dataset.enabled === "1";
      const action = enabled ? "stop" : "activate";
      const r = await fetch(`/api/telegram/${id}/${action}`, { method: "POST", credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "toggle failed");

      if (action === "activate" && data.authorized === false) {
        alert(data.message || "Сессия не активна");
      }

      await loadResStatus();
    } finally {
      btnToggleRes.disabled = false;
    }
  }

  // events
  btnSave?.addEventListener("click", async () => {
    try {
      await saveData();
      // alert("Сохранено");
      await loadData();
    } catch (e) {
      console.error(e);
      alert("Ошибка сохранения");
    }
  });

  apiKeysId?.addEventListener("change", () => {
    refreshKeyFieldOptions("");
    refreshModelOptions("");
  });

  keyField?.addEventListener("change", () => {
    refreshModelOptions("");
  });

  btnActivate?.addEventListener("click", activate);
  btnToggleRes?.addEventListener("click", toggleResStatus);

  btnConfirmCode?.addEventListener("click", closeCodeModal);
  btnCancelCode?.addEventListener("click", closeCodeModal);

  btnToggleDetails?.addEventListener("click", () => {
    if (!tgConnectionBlock) return;
    const hidden = tgConnectionBlock.classList.toggle("hidden");
    btnToggleDetails.textContent = hidden
      ? "⚙️ Показать настройки подключения"
      : "🔽 Скрыть настройки подключения";
  });

  // init
  (async () => {
    try {
      await loadData();
      await loadResStatus();
    } catch (e) {
      console.error("[telegram] init error:", e);
      alert("Ошибка загрузки Telegram-ресурса");
    }
  })();
});
