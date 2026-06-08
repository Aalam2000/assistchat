// src/web/static/js/prompt.js

document.addEventListener("DOMContentLoaded", () => {
  const id = PROMPT_RID;
  const $ = (s) => document.querySelector(s);

  const label       = $("#prLabel");
  const description = $("#prDescription");
  const systemPrompt = $("#prSystemPrompt");
  const styleRules  = $("#prStyleRules");
  const googleSource = $("#prGoogleSource");
  const examples    = $("#prExamples");
  const btnSave     = $("#btnSave");
  const msgEl       = $("#prMsg");

  // ── Inline-сообщения ────────────────────────────────────────────────────────
  function showMsg(text, type = "info") {
    if (!msgEl) return;
    const colors = {
      ok:    { bg: "#d4edda", color: "#155724", border: "#c3e6cb" },
      error: { bg: "#f8d7da", color: "#721c24", border: "#f5c6cb" },
      info:  { bg: "#d1ecf1", color: "#0c5460", border: "#bee5eb" },
      warn:  { bg: "#fff3cd", color: "#856404", border: "#ffeeba" },
    };
    const s = colors[type] || colors.info;
    msgEl.style.cssText = `display:block;padding:8px 12px;border-radius:6px;margin:10px 0;
        font-size:14px;background:${s.bg};color:${s.color};border:1px solid ${s.border}`;
    msgEl.textContent = text;
  }

  // ── JSON примеры ────────────────────────────────────────────────────────────
  function safeJsonStringify(v) {
    try { return JSON.stringify(v, null, 2); } catch (e) { return ""; }
  }

  function parseExamples() {
    const raw = (examples.value || "").trim();
    if (!raw || raw === "[]") return [];
    try {
      const v = JSON.parse(raw);
      if (!Array.isArray(v)) {
        showMsg("Examples: JSON должен быть массивом [{\"q\":\"...\",\"a\":\"...\"}]", "error");
        return null;
      }
      return v;
    } catch (e) {
      showMsg("Examples: неверный JSON. Нужен массив, напр: [{\"q\":\"...\",\"a\":\"...\"}]", "error");
      return null;
    }
  }

  // ── Сборка мета ────────────────────────────────────────────────────────────
  function buildMeta() {
    const ex = parseExamples();
    if (ex === null) return null;
    return {
      prompt: {
        description:   (description.value   || "").trim(),
        system_prompt: (systemPrompt.value  || "").trim(),
        style_rules:   (styleRules.value    || "").trim(),
        google_source: (googleSource.value  || "").trim(),
        examples: ex,
      }
    };
  }

  // ── Сохранение ────────────────────────────────────────────────────────────
  async function save() {
    const meta = buildMeta();
    if (meta === null) return;

    btnSave.disabled = true;
    try {
      const r = await fetch(`/api/prompt/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          label: (label.value || "").trim() || "Prompt",
          meta_json: meta,
        }),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) {
        showMsg("Ошибка сохранения: " + (data.detail || data.error || r.status), "error");
      } else {
        showMsg("Сохранено", "ok");
        await load();
      }
    } catch (e) {
      showMsg("Сетевая ошибка: " + e.message, "error");
    } finally {
      setTimeout(() => { btnSave.disabled = false; }, 1500);
    }
  }

  // ── Загрузка ────────────────────────────────────────────────────────────────
  async function load() {
    try {
      const r = await fetch(`/api/providers/resources/list`, { credentials: "same-origin" });
      const data = await r.json();
      const item = (data.items || []).find(x => String(x.id) === String(id));
      if (!item) {
        showMsg("Ресурс не найден", "error");
        return;
      }

      label.value = item.label || "";

      const p = (item.meta || {}).prompt || {};
      description.value  = p.description   || "";
      systemPrompt.value = p.system_prompt  || "";
      styleRules.value   = p.style_rules    || "";
      googleSource.value = p.google_source  || "";
      examples.value     = safeJsonStringify(p.examples || []);
    } catch (e) {
      showMsg("Ошибка загрузки: " + e.message, "error");
    }
  }

  btnSave.addEventListener("click", save);
  load();
});
