// src/app/static/js/tg.js
(function () {
  const $ = (sel) => document.querySelector(sel);
  const setNote = (el, text, type) => {
    el.className = "note " + (type || "");
    el.textContent = text || "";
  };

  // ---------- список моих сессий ----------
  async function loadMySessions() {
    const tbody = $("#tg-my-tbody");
    const note = $("#tg-list-note");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="4" class="muted">Загрузка…</td></tr>`;
    setNote(note, "");

    try {
      const r = await fetch("/api/my/sessions", { credentials: "same-origin" });
      const data = await r.json();
      if (!data.ok) throw new Error("UNAUTHORIZED");

      const items = data.items || [];
      if (items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="muted">Пока нет ни одной сессии</td></tr>`;
        return;
      }

      tbody.innerHTML = "";
      items.forEach((it) => {
        const tr = document.createElement("tr");
        const st = (it.status || "").toLowerCase();
        const badge =
          st === "active"
            ? `<span class="badge ok">active</span>`
            : `<span class="badge paused">${st || "unknown"}</span>`;
        const btnText = st === "active" ? "Пауза" : "Включить";
        const disabled = st === "blocked" || st === "invalid" ? "disabled" : "";
        tr.innerHTML = `
          <td>${it.label ?? ""}</td>
          <td>${it.phone ?? ""}</td>
          <td>${badge}</td>
          <td>
            <button class="btn" data-phone="${it.phone}" ${disabled}>${btnText}</button>
          </td>
        `;
        tr.querySelector("button").addEventListener("click", async (e) => {
          const phone = e.currentTarget.getAttribute("data-phone");
          e.currentTarget.disabled = true;
          try {
            const resp = await apiPost("/api/toggle", { phone });
            await loadMySessions();
            setNote(note, `Статус ${phone}: ${resp.status}`, "ok");
          } catch (err) {
            setNote(note, `Ошибка переключения: ${err.detail || err.error || err.message || "UNKNOWN"}`, "err");
          } finally {
            e.currentTarget.disabled = false;
          }
        });
        tbody.appendChild(tr);
      });
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="4" class="muted">Ошибка загрузки</td></tr>`;
      setNote(note, `Ошибка: ${err.message || err}`, "err");
    }
  }

  // ---------- шаг 1: отправка кода ----------
  const s1 = {
    form: $("#frm-step1"),
    label: $("#s1-label"),
    phone: $("#s1-phone"),
    apiId: $("#s1-api-id"),
    apiHash: $("#s1-api-hash"),
    btn: $("#btn-send"),
    note: $("#s1-note"),
  };

  const s2 = {
    fs: $("#fs-step2"),
    form: $("#frm-step2"),
    phone: $("#s2-phone"),
    code: $("#s2-code"),
    pass: $("#s2-2fa"),
    btn: $("#btn-confirm"),
    note: $("#s2-note"),
  };

  s1.form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    setNote(s1.note, "");
    s1.btn.disabled = true;

    const label = (s1.label.value || "").trim();
    const phone = (s1.phone.value || "").trim();
    const api_id = Number(s1.apiId.value || 0);
    const api_hash = (s1.apiHash.value || "").trim();

    if (!label || !phone || !api_id || !api_hash) {
      setNote(s1.note, "Заполни все поля шага 1.", "err");
      s1.btn.disabled = false;
      return;
    }

    try {
      const resp = await apiPost("/api/tg/send_code", {
        label, phone, api_id, api_hash
      });
      setNote(s1.note, "Код отправлен. Проверь Telegram на этом номере.", "ok");
      // включаем шаг 2 и подставляем номер
      s2.fs.disabled = false;
      s2.phone.value = phone;
      s2.code.focus();
    } catch (err) {
      const msg = err.detail || err.error || err.message || "UNKNOWN";
      setNote(s1.note, `Не удалось отправить код: ${msg}`, "err");
    } finally {
      s1.btn.disabled = false;
    }
  });

  // ---------- шаг 2: подтверждение ----------
  s2.form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    setNote(s2.note, "");
    s2.btn.disabled = true;

    const phone = (s2.phone.value || "").trim();
    const code = (s2.code.value || "").trim();
    const twofa = (s2.pass.value || "").trim();

    if (!phone || !code) {
      setNote(s2.note, "Заполни телефон и код.", "err");
      s2.btn.disabled = false;
      return;
    }

    try {
      const resp = await apiPost("/api/tg/confirm", { phone, code, twofa });
      setNote(s2.note, "Сессия сохранена. Статус: paused. Можно включить в таблице выше.", "ok");
      // очистим поля шага 2, заблокируем обратно
      s2.form.reset();
      s2.fs.disabled = true;
      // перезагрузим список
      await loadMySessions();
    } catch (err) {
      const msg = err.detail || err.error || err.message || "UNKNOWN";
      setNote(s2.note, `Не удалось подтвердить код: ${msg}`, "err");
    } finally {
      s2.btn.disabled = false;
    }
  });

  // старт
  loadMySessions();

   // ---------- модальное окно ----------
  console.log("helpBtn=", helpBtn);
  console.log("helpModal=", helpModal);
  console.log("helpClose=", helpClose);
  const helpBtn = document.getElementById("help-btn");
  const helpModal = document.getElementById("help-modal");
  const helpClose = document.getElementById("help-close");

  if (helpBtn && helpModal) {
    helpBtn.addEventListener("click", () => {
      helpModal.style.display = "flex";
    });
  }

  if (helpClose && helpModal) {
    helpClose.addEventListener("click", () => {
      helpModal.style.display = "none";
    });
  }

  window.addEventListener("click", (e) => {
    if (helpModal && e.target === helpModal) {
      helpModal.style.display = "none";
    }
  });


})();
