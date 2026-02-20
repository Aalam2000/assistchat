// src/web/static/js/prompt.js

document.addEventListener("DOMContentLoaded", () => {
  const id = PROMPT_RID;
  const $ = (s) => document.querySelector(s);

  const label = $("#prLabel");
  const description = $("#prDescription");
  const systemPrompt = $("#prSystemPrompt");
  const styleRules = $("#prStyleRules");
  const googleSource = $("#prGoogleSource");
  const examples = $("#prExamples");
  const btnSave = $("#btnSave");

  function safeJsonStringify(v) {
    try { return JSON.stringify(v, null, 2); } catch (e) { return ""; }
  }

  function parseExamples() {
    const raw = (examples.value || "").trim();
    if (!raw) return [];
    let v;
    try {
      v = JSON.parse(raw);
    } catch (e) {
      alert("Examples: неверный JSON. Нужен массив объектов, напр: [{\"q\":\"...\",\"a\":\"...\"}]");
      return null;
    }
    if (!Array.isArray(v)) {
      alert("Examples: JSON должен быть массивом.");
      return null;
    }
    return v;
  }

  function buildMeta() {
    const ex = parseExamples();
    if (ex === null) return null;

    return {
      prompt: {
        description: (description.value || "").trim(),
        system_prompt: (systemPrompt.value || "").trim(),
        style_rules: (styleRules.value || "").trim(),
        google_source: (googleSource.value || "").trim(),
        examples: ex
      }
    };
  }

  async function save() {
    const meta = buildMeta();
    if (meta === null) return;

    const payload = {
      label: (label.value || "").trim() || "Prompt",
      meta_json: meta
    };

    const r = await fetch(`/api/prompt/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    });

    const data = await r.json();
    if (!data.ok) {
      alert("Не удалось сохранить PROMPT");
    }
  }

  async function load() {
    const r = await fetch(`/api/providers/resources/list`, { credentials: "same-origin" });
    const data = await r.json();
    const item = (data.items || []).find(x => x.id === id);
    if (!item) return;

    label.value = item.label || "";

    const m = item.meta || {};
    const p = m.prompt || {};

    description.value = p.description || "";
    systemPrompt.value = p.system_prompt || "";
    styleRules.value = p.style_rules || "";
    googleSource.value = p.google_source || "";
    examples.value = safeJsonStringify(p.examples || []);
  }

  btnSave.addEventListener("click", save);
  load();
});
