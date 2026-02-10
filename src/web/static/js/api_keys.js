// src/web/static/js/api_keys.js

document.addEventListener("DOMContentLoaded", () => {
  const id = API_KEYS_RID;
  const $ = (s) => document.querySelector(s);

  const label = $("#akLabel");
  const showSecrets = $("#akShowSecrets");
  const notes = $("#akNotes");
  const btnSave = $("#btnSave");

  const MAP = [
    ["creds.openai_api_key", $("#akOpenaiApiKey")],
    ["creds.openai_admin_key", $("#akOpenaiAdminKey")],
    ["creds.gemini_api_key", $("#akGeminiApiKey")],
    ["creds.anthropic_api_key", $("#akAnthropicApiKey")],
    ["creds.groq_api_key", $("#akGroqApiKey")],
    ["creds.deepseek_api_key", $("#akDeepseekApiKey")],
    ["creds.mistral_api_key", $("#akMistralApiKey")],
    ["creds.xai_api_key", $("#akXaiApiKey")],
    ["creds.deepgram_api_key", $("#akDeepgramApiKey")],
  ];

  let lastVerified = {};

  function setSecretsVisible(v) {
    document.querySelectorAll(".ak-secret")
      .forEach(i => i.type = v ? "text" : "password");
  }

  function setStatus(inp, ok) {
    inp.classList.remove("ak-status-ok", "ak-status-bad");
    if (ok === true) inp.classList.add("ak-status-ok");
    if (ok === false) inp.classList.add("ak-status-bad");
  }

  function buildMeta() {
    const creds = {};
    MAP.forEach(([k, inp]) => {
      const f = k.split(".")[1];
      // ВАЖНО: отправляем и пустые, чтобы сервер мог удалить ключ из БД
      creds[f] = (inp.value || "").trim();
    });
    return {
      creds,
      extra: { notes: (notes.value || "").trim() }
    };
  }


  async function verifyAndSave() {
    const payload = {
      label: label.value.trim() || "API keys",
      meta_json: buildMeta()
    };

    const r = await fetch(`/api/api_keys/${id}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    });

    const data = await r.json();
    if (!data.ok) return;

    lastVerified = data.verified || {};

    MAP.forEach(([k, inp]) => {
      if (!inp.value.trim()) return;
      setStatus(inp, lastVerified[k]?.ok);
    });
  }

  async function load() {
    const r = await fetch(`/api/providers/resources/list`, { credentials: "same-origin" });
    const data = await r.json();
    const item = data.items.find(x => x.id === id);
    if (!item) return;

    const m = item.meta || {};
    const c = m.creds || {};
    const v = m.verified || {};

    label.value = item.label || "";
    notes.value = m.extra?.notes || "";
    lastVerified = v;

    MAP.forEach(([k, inp]) => {
      const f = k.split(".")[1];
      inp.value = c[f] || "";
      if (v[k]) setStatus(inp, v[k].ok);
    });
  }

  // autosave on blur
  MAP.forEach(([_, inp]) => {
    inp.addEventListener("blur", () => {
      if (inp.value.trim()) verifyAndSave();
    });
  });

  btnSave.addEventListener("click", verifyAndSave);
  showSecrets.addEventListener("change", e => setSecretsVisible(e.target.checked));

  load();
});
