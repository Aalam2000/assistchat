// src/web/static/js/api_keys.js

document.addEventListener("DOMContentLoaded", () => {
  const id = API_KEYS_RID;
  if (!id) {
    console.error("[api_keys] missing resource id");
    return;
  }

  const $ = (s) => document.querySelector(s);

  const label = $("#akLabel");
  const showSecrets = $("#akShowSecrets");

  const openaiApiKey = $("#akOpenaiApiKey");
  const openaiAdminKey = $("#akOpenaiAdminKey");

  const geminiApiKey = $("#akGeminiApiKey");
  const anthropicApiKey = $("#akAnthropicApiKey");
  const groqApiKey = $("#akGroqApiKey");
  const deepseekApiKey = $("#akDeepseekApiKey");
  const mistralApiKey = $("#akMistralApiKey");
  const xaiApiKey = $("#akXaiApiKey");

  const deepgramApiKey = $("#akDeepgramApiKey");
  const notes = $("#akNotes");

  const btnSave = $("#btnSave");

  function setSecretsVisible(isVisible) {
    const inputs = document.querySelectorAll(".ak-secret");
    inputs.forEach((inp) => {
      inp.type = isVisible ? "text" : "password";
    });
  }

  async function loadData() {
    try {
      const r = await fetch(`/api/providers/resources/list`, { credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "load failed");

      const item = (data.items || []).find((x) => x.id === id);
      if (!item) throw new Error("resource not found");

      const meta = item.meta || {};
      const creds = meta.creds || {};
      const extra = meta.extra || {};

      label.value = item.label || "";

      openaiApiKey.value = creds.openai_api_key || "";
      openaiAdminKey.value = creds.openai_admin_key || "";

      geminiApiKey.value = creds.gemini_api_key || "";
      anthropicApiKey.value = creds.anthropic_api_key || "";
      groqApiKey.value = creds.groq_api_key || "";
      deepseekApiKey.value = creds.deepseek_api_key || "";
      mistralApiKey.value = creds.mistral_api_key || "";
      xaiApiKey.value = creds.xai_api_key || "";

      deepgramApiKey.value = creds.deepgram_api_key || "";
      notes.value = extra.notes || "";
    } catch (err) {
      console.error("[api_keys] load error:", err);
      alert("Ошибка загрузки данных ресурса");
    }
  }

  async function saveData() {
    const newMeta = {
      creds: {
        openai_api_key: (openaiApiKey.value || "").trim(),
        openai_admin_key: (openaiAdminKey.value || "").trim(),

        gemini_api_key: (geminiApiKey.value || "").trim(),
        anthropic_api_key: (anthropicApiKey.value || "").trim(),
        groq_api_key: (groqApiKey.value || "").trim(),
        deepseek_api_key: (deepseekApiKey.value || "").trim(),
        mistral_api_key: (mistralApiKey.value || "").trim(),
        xai_api_key: (xaiApiKey.value || "").trim(),

        deepgram_api_key: (deepgramApiKey.value || "").trim(),
      },
      extra: {
        notes: (notes.value || "").trim(),
      },
    };

    const payload = {
      label: (label.value || "").trim() || "API keys",
      meta_json: newMeta,
    };

    try {
      const r = await fetch(`/api/api_keys/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "save failed");

      alert("Настройки сохранены");
      await loadData();
    } catch (err) {
      console.error("[api_keys] save error:", err);
      alert("Ошибка сохранения настроек");
    }
  }

  showSecrets?.addEventListener("change", () => setSecretsVisible(!!showSecrets.checked));
  btnSave?.addEventListener("click", saveData);

  setSecretsVisible(false);
  loadData();
});
