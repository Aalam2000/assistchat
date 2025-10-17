// src/web/static/js/telegram.js — финальная версия под новую схему settings.yaml

document.addEventListener("DOMContentLoaded", () => {
  const id = TG_RID;
  if (!id) {
    console.error("[telegram] missing resource id");
    return;
  }

  const $  = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  // ── Элементы формы
  const appId      = $("#tgAppId");
  const appHash    = $("#tgAppHash");
  const phone      = $("#tgPhone");
  const label      = $("#tgLabel");
  const whitelist  = $("#tgWhitelist");
  const blacklist  = $("#tgBlacklist");
  const historyLen = $("#tgHistory");
  const btnActivate = $("#btnActivate");
  const btnSave     = $("#btnSave");

  // ── Роли
  const rolesContainer = $("#rolesContainer");
  const roleTemplate   = $("#roleTemplate");
  const btnAddRole     = $("#btnAddRole");
  const MAX_ROLES = 5;

  // ── Модалка Telegram
  const tgCodeModal    = document.getElementById("tgCodeModal");
  const codeInput      = document.getElementById("tgCodeInput");
  const btnConfirmCode = document.getElementById("btnConfirmCode");
  const btnCancelCode  = document.getElementById("btnCancelCode");

  // ── Вспомогательные функции
  const parseList = (s) =>
    (s || "")
      .split(/[\n,;]+|,\s*/g)
      .map((x) => x.trim())
      .filter(Boolean);

  function openCodeModal() {
    tgCodeModal.classList.remove("hidden");
    codeInput.focus();
  }

  function closeCodeModal() {
    tgCodeModal.classList.add("hidden");
    codeInput.value = "";
  }

  function makeRoleCard(role, index) {
    const tpl = roleTemplate.content.cloneNode(true);
    const card = tpl.querySelector(".role-card");

    card.querySelector(".role-title").textContent = role.name || `Роль ${index + 1}`;
    card.querySelector(".role-description").value = role.description || "";
    card.querySelector(".role-system").value = role.system_prompt || "";
    card.querySelector(".role-lesson").value = role.modes?.lesson || "";
    card.querySelector(".role-dialogue").value = role.modes?.dialogue || "";
    card.querySelector(".role-quiz").value = role.modes?.quiz || "";
    card.querySelector(".role-translate").value = role.modes?.translate || "";
    card.querySelector(".role-temp").value = role.temperature ?? 0.7;
    card.querySelector(".role-top").value = role.top_p ?? 1.0;
    card.querySelector(".role-tokens").value = role.max_tokens ?? 1024;
    card.querySelector(".role-voice").checked = role.voice_enabled ?? true;

    card.querySelector(".btnDeleteRole").addEventListener("click", () => {
      card.remove();
    });

    return card;
  }

  function collectRoles() {
    const cards = $$(".role-card");
    const roles = [];
    cards.forEach((card, i) => {
      roles.push({
        name: card.querySelector(".role-title").textContent.trim() || `Роль ${i + 1}`,
        description: card.querySelector(".role-description").value.trim(),
        system_prompt: card.querySelector(".role-system").value.trim(),
        modes: {
          lesson: card.querySelector(".role-lesson").value.trim(),
          dialogue: card.querySelector(".role-dialogue").value.trim(),
          quiz: card.querySelector(".role-quiz").value.trim(),
          translate: card.querySelector(".role-translate").value.trim(),
        },
        temperature: parseFloat(card.querySelector(".role-temp").value || 0.7),
        top_p: parseFloat(card.querySelector(".role-top").value || 1.0),
        max_tokens: parseInt(card.querySelector(".role-tokens").value || 1024),
        voice_enabled: card.querySelector(".role-voice").checked,
      });
    });
    return roles.slice(0, MAX_ROLES);
  }

  // ───────────────────────────────
  // ЗАГРУЗКА ДАННЫХ
  // ───────────────────────────────
  async function loadData() {
    try {
      const r = await fetch(`/api/resources/${id}`, { credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "load failed");

      const meta = data.meta_json || {};
      const creds = meta.creds || {};
      const session = meta.session || {};
      const roles = Array.isArray(meta.roles) ? meta.roles : [];

      appId.value = creds.app_id || "";
      appHash.value = creds.app_hash || "";
      phone.value = creds.phone || "";
      label.value = data.label || "";

      whitelist.value = (session.whitelist || []).join(", ");
      blacklist.value = (session.blacklist || []).join(", ");
      historyLen.value = session.history_limit ?? 20;

      // Роли
      rolesContainer.innerHTML = "";
      roles.slice(0, MAX_ROLES).forEach((r, i) => {
        const card = makeRoleCard(r, i);
        rolesContainer.appendChild(card);
      });
    } catch (err) {
      console.error("[telegram] load error:", err);
      alert("Ошибка загрузки данных ресурса");
    }
  }

  // ───────────────────────────────
  // СОХРАНЕНИЕ
  // ───────────────────────────────
  async function saveData() {
    const newMeta = {
      creds: {
        app_id: appId.value.trim(),
        app_hash: appHash.value.trim(),
      },
      session: {
        whitelist: parseList(whitelist.value),
        blacklist: parseList(blacklist.value),
        history_limit: Number(historyLen.value || 20),
      },
      roles: collectRoles(),
    };

    const payload = {
      label: label.value.trim() || "Telegram ассистент",
      meta_json: newMeta,
    };

    try {
      const r = await fetch(`/api/resources/${id}`, {
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
      console.error("[telegram] save error:", err);
      alert("Ошибка сохранения настроек");
    }
  }

  // ───────────────────────────────
  // АКТИВАЦИЯ TELEGRAM
  // ───────────────────────────────
  async function activate() {
    const payload = {
      phone: phone.value.trim(),
      app_id: appId.value.trim(),
      app_hash: appHash.value.trim(),
      code: null,
    };

    if (!payload.phone || !payload.app_id || !payload.app_hash) {
      alert("Заполните App ID, App Hash и телефон");
      return;
    }

    try {
      const r = await fetch(`/api/resource/${id}/activate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });

      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "Ошибка активации");

      if (data.need_code) {
        openCodeModal();
      } else if (data.activated) {
        alert("Telegram активирован!");
        await loadData();
      }
    } catch (err) {
      console.error("[telegram] activate error:", err);
      alert("Ошибка при активации Telegram");
    }
  }

  async function confirmCode() {
    const code = codeInput.value.trim();
    if (!code) {
      alert("Введите код подтверждения");
      return;
    }

    try {
      const r = await fetch(`/api/resource/${id}/activate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          phone: phone.value.trim(),
          app_id: appId.value.trim(),
          app_hash: appHash.value.trim(),
          code,
        }),
      });

      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "Ошибка подтверждения");

      if (data.activated) {
        alert("Telegram успешно активирован!");
        closeCodeModal();
        await loadData();
      }
    } catch (err) {
      console.error("[telegram] confirm error:", err);
      alert("Ошибка при подтверждении кода");
    }
  }

  // ───────────────────────────────
  // УПРАВЛЕНИЕ БОТОМ
  // ───────────────────────────────
  async function loadBotStatus() {
    const out = document.getElementById("tgBotStatus");
    const btn = document.getElementById("btnToggleBot");
    try {
      const r = await fetch("/api/bot/status", { credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "load failed");
      const enabled = !!data.bot_enabled;
      out.textContent = `БОТ: ${enabled ? "🟢 активен" : "🔴 выключен"}`;
      btn.textContent = enabled ? "💡 Выключить БОТ" : "💡 Включить БОТ";
      btn.dataset.state = enabled ? "on" : "off";
    } catch (err) {
      console.error("[telegram] loadBotStatus error:", err);
      out.textContent = "БОТ: ошибка статуса";
    }
  }

  async function toggleBot() {
    const btn = document.getElementById("btnToggleBot");
    const out = document.getElementById("tgBotStatus");
    btn.disabled = true;
    try {
      const r = await fetch("/api/bot/toggle", {
        method: "POST",
        credentials: "same-origin",
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "toggle failed");
      const enabled = !!data.bot_enabled;
      out.textContent = `БОТ: ${enabled ? "🟢 активен" : "🔴 выключен"}`;
      btn.textContent = enabled ? "💡 Выключить БОТ" : "💡 Включить БОТ";
    } catch (err) {
      console.error("[telegram] toggleBot error:", err);
      out.textContent = "Ошибка переключения БОТа";
    } finally {
      btn.disabled = false;
    }
  }

  // ───────────────────────────────
  // УПРАВЛЕНИЕ РЕСУРСОМ
  // ───────────────────────────────
  async function loadResStatus() {
    const out = document.getElementById("tgResStatus");
    const btn = document.getElementById("btnToggleStatus");
    try {
      const r = await fetch(`/api/resources/${id}`, { credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "load failed");
      const st = data.status || "—";
      out.textContent = `РЕСУРС: ${st}`;
      btn.textContent = st === "active" ? "💡 Остановить ресурс" : "💡 Включить ресурс";
    } catch (err) {
      console.error("[telegram] loadResStatus error:", err);
      out.textContent = "РЕСУРС: ошибка статуса";
    }
  }

  async function toggleResStatus() {
    const btn = document.getElementById("btnToggleStatus");
    const out = document.getElementById("tgResStatus");
    btn.disabled = true;
    try {
      const action = btn.textContent.includes("Остановить") ? "pause" : "activate";
      const r = await fetch("/api/resources/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ id, action }),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) {
        const msg = data.message || data.error || "Ошибка переключения ресурса";
        out.textContent = `РЕСУРС: 🔴 ${msg}`;
        btn.textContent = "💡 Включить ресурс";
        return;
      }
      const st = data.status || (action === "activate" ? "active" : "paused");
      out.textContent = `РЕСУРС: ${st}`;
      btn.textContent = st === "active" ? "💡 Остановить ресурс" : "💡 Включить ресурс";
    } catch (err) {
      console.error("[telegram] toggleResStatus error:", err);
      out.textContent = "Ошибка переключения ресурса";
    } finally {
      btn.disabled = false;
    }
  }

  // ───────────────────────────────
  // СОБЫТИЯ
  // ───────────────────────────────
  btnSave?.addEventListener("click", saveData);
  btnActivate?.addEventListener("click", activate);
  btnConfirmCode?.addEventListener("click", confirmCode);
  btnCancelCode?.addEventListener("click", closeCodeModal);
  document.getElementById("btnToggleBot")?.addEventListener("click", toggleBot);
  document.getElementById("btnToggleStatus")?.addEventListener("click", toggleResStatus);
  btnAddRole?.addEventListener("click", () => {
    const current = $$(".role-card").length;
    if (current >= MAX_ROLES) {
      alert("Можно добавить максимум 5 ролей");
      return;
    }
    const card = makeRoleCard({}, current);
    rolesContainer.appendChild(card);
  });

  // ───────────────────────────────
  // ИНИЦИАЛИЗАЦИЯ
  // ───────────────────────────────
  loadBotStatus();
  loadResStatus();
  loadData();
});

// ───────────────────────────────
  // СКРЫТИЕ / ПОКАЗ НАСТРОЕК ПОДКЛЮЧЕНИЯ
  // ───────────────────────────────
  const btnToggleDetails = document.getElementById("btnToggleDetails");
  const tgConnectionBlock = document.getElementById("tgConnectionBlock");

  btnToggleDetails?.addEventListener("click", () => {
    if (!tgConnectionBlock) return;
    const hidden = tgConnectionBlock.classList.toggle("hidden");
    btnToggleDetails.textContent = hidden
      ? "⚙️ Показать настройки подключения"
      : "🔽 Скрыть настройки подключения";
  });