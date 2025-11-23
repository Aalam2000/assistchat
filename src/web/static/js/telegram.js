// src/web/static/js/telegram.js — обновлённая версия под новую архитектуру Telegram API

document.addEventListener("DOMContentLoaded", () => {
  const id = TG_RID;
  if (!id) {
    console.error("[telegram] missing resource id");
    return;
  }

  const $  = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  // ───────────────────────────────
  // ЭЛЕМЕНТЫ И ФОРМА
  // ───────────────────────────────
  const appId      = $("#tgAppId");
  const appHash    = $("#tgAppHash");
  const phone      = $("#tgPhone");
  const label      = $("#tgLabel");
  const whitelist  = $("#tgWhitelist");
  const blacklist  = $("#tgBlacklist");
  const historyLen = $("#tgHistory");
  const btnActivate = $("#btnActivate");
  const btnSave     = $("#btnSave");
  const rolesContainer = $("#rolesContainer");
  const roleTemplate   = $("#roleTemplate");
  const btnAddRole     = $("#btnAddRole");
  const MAX_ROLES = 5;

  const tgCodeModal    = document.getElementById("tgCodeModal");
  const codeInput      = document.getElementById("tgCodeInput");
  const btnConfirmCode = document.getElementById("btnConfirmCode");
  const btnCancelCode  = document.getElementById("btnCancelCode");

  const btnToggleBot   = document.getElementById("btnToggleBot");
  const tgBotStatus    = document.getElementById("tgBotStatus");
  const btnToggleRes   = document.getElementById("btnToggleStatus");
  const tgResStatus    = document.getElementById("tgResStatus");

  // ───────────────────────────────
  // ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
  // ───────────────────────────────
  const parseList = (s) =>
    (s || "")
      .split(/[\n,;]+|,\s*/g)
      .map((x) => x.trim())
      .filter(Boolean);

  function openCodeModal() {
    tgCodeModal?.classList.remove("hidden");
    codeInput?.focus();
  }
  function closeCodeModal() {
    tgCodeModal?.classList.add("hidden");
    if (codeInput) codeInput.value = "";
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

    card.querySelector(".btnDeleteRole").addEventListener("click", () => card.remove());
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
  // ЗАГРУЗКА РЕСУРСА
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

      rolesContainer.innerHTML = "";
      roles.slice(0, MAX_ROLES).forEach((r, i) => rolesContainer.appendChild(makeRoleCard(r, i)));
    } catch (err) {
      console.error("[telegram] load error:", err);
      alert("Ошибка загрузки данных ресурса");
    }
  }

  // ───────────────────────────────
  // СОХРАНЕНИЕ РЕСУРСА
  // ───────────────────────────────
  async function saveData() {
    const newMeta = {
      creds: { app_id: appId.value.trim(), app_hash: appHash.value.trim(), phone: phone.value.trim() },
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
  // АКТИВАЦИЯ TELEGRAM-СЕССИИ
  // ───────────────────────────────
  async function activate() {
    if (!phone.value || !appId.value || !appHash.value) {
      alert("Заполните App ID, App Hash и телефон");
      return;
    }

    try {
      const r = await fetch(`/api/telegram/${id}/activate`, {
        method: "POST",
        credentials: "same-origin",
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "activation failed");
      alert(data.message || "Telegram активирован!");
      await loadData();
    } catch (err) {
      console.error("[telegram] activate error:", err);
      alert("Ошибка активации Telegram");
    }
  }

  // ───────────────────────────────
  // УПРАВЛЕНИЕ БОТОМ
  // ───────────────────────────────
  async function loadBotStatus() {
    try {
      const r = await fetch("/api/bot/status", { credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "load failed");
      const enabled = !!data.bot_enabled;
      tgBotStatus.textContent = `БОТ: ${enabled ? "🟢 активен" : "🔴 выключен"}`;
      btnToggleBot.textContent = enabled ? "💡 Выключить БОТ" : "💡 Включить БОТ";
      btnToggleBot.dataset.state = enabled ? "on" : "off";
    } catch (err) {
      console.error("[telegram] loadBotStatus error:", err);
      tgBotStatus.textContent = "БОТ: ошибка статуса";
    }
  }

  async function toggleBot() {
    btnToggleBot.disabled = true;
    try {
      const r = await fetch("/api/bot/toggle", { method: "POST", credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "toggle failed");
      const enabled = !!data.bot_enabled;
      tgBotStatus.textContent = `БОТ: ${enabled ? "🟢 активен" : "🔴 выключен"}`;
      btnToggleBot.textContent = enabled ? "💡 Выключить БОТ" : "💡 Включить БОТ";
    } catch (err) {
      console.error("[telegram] toggleBot error:", err);
      tgBotStatus.textContent = "Ошибка переключения БОТа";
    } finally {
      btnToggleBot.disabled = false;
    }
  }

  // ───────────────────────────────
  // УПРАВЛЕНИЕ РЕСУРСОМ
  // ───────────────────────────────
  async function loadResStatus() {
    try {
      const r = await fetch(`/api/telegram/${id}/status`, { credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "load failed");
      tgResStatus.textContent = `РЕСУРС: ${data.status}`;
      btnToggleRes.textContent = data.active ? "💡 Остановить ресурс" : "💡 Включить ресурс";
    } catch (err) {
      console.error("[telegram] loadResStatus error:", err);
      tgResStatus.textContent = "РЕСУРС: ошибка статуса";
    }
  }

  async function toggleResStatus() {
    btnToggleRes.disabled = true;
    try {
      const action = btnToggleRes.textContent.includes("Остановить") ? "stop" : "activate";
      const url = `/api/telegram/${id}/${action}`;
      const r = await fetch(url, { method: "POST", credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "toggle failed");
      alert(data.message || "Статус ресурса обновлён");
      await loadResStatus();
    } catch (err) {
      console.error("[telegram] toggleResStatus error:", err);
      tgResStatus.textContent = "Ошибка переключения ресурса";
    } finally {
      btnToggleRes.disabled = false;
    }
  }

  // ───────────────────────────────
  // СОБЫТИЯ
  // ───────────────────────────────
  btnSave?.addEventListener("click", saveData);
  btnActivate?.addEventListener("click", activate);
  btnConfirmCode?.addEventListener("click", closeCodeModal);
  btnCancelCode?.addEventListener("click", closeCodeModal);
  btnAddRole?.addEventListener("click", () => {
    const current = $$(".role-card").length;
    if (current >= MAX_ROLES) return alert("Можно добавить максимум 5 ролей");
    rolesContainer.appendChild(makeRoleCard({}, current));
  });
  btnToggleBot?.addEventListener("click", toggleBot);
  btnToggleRes?.addEventListener("click", toggleResStatus);

  // ───────────────────────────────
  // ИНИЦИАЛИЗАЦИЯ
  // ───────────────────────────────
  loadData();
  loadBotStatus();
  loadResStatus();

  // ───────────────────────────────
  // СКРЫТИЕ/ПОКАЗ НАСТРОЕК
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
});
