(async function () {
  const $ = (s) => document.querySelector(s);
  const tbody = $("#messages-body");
  const form = $("#msg-form");
  const status = $("#status");
  const statusSelect = $("#msg_status"); // селект из формы (id="msg_status" в index.html)
  const btn = $("#submit-btn");

  function setStatus(msg, isErr=false) {
    status.textContent = msg || "";
    status.style.color = isErr ? "#b91c1c" : "#6b7280";
  }

  function tr(msg) {
    const tr = document.createElement("tr");

    const td = (t, cls) => {
      const d = document.createElement("td");
      d.textContent = (t ?? "").toString(); // гарантируем строку
      if (cls) d.className = cls;
      return d;
    };

    // порядок ячеек: ID | Автор | Контент | Статус | Создано
    tr.append(
      td(msg.id, "mono"),
      td(msg.author),
      td(msg.content),
      td(msg.status),                                     // <-- только значение, НЕ td(...)
      td(new Date(msg.ts).toLocaleString(), "mono"),
    );
    return tr;
  }


  async function loadMessages() {
    setStatus("Загружаю...");
    try {
      const res = await fetch("/api/messages");
      if (!res.ok) throw new Error("Ошибка загрузки");
      const data = await res.json();
      tbody.innerHTML = "";
      data.forEach(m => tbody.appendChild(tr(m)));
      setStatus(`Загружено: ${data.length}`);
    } catch (e) {
      setStatus(e.message || "Ошибка запроса", true);
    }
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const author = $("#author").value.trim();
    const content = $("#content").value.trim();
    if (!author || !content) { setStatus("Заполните оба поля", true); return; }
    btn.disabled = true; setStatus("Сохраняю...");
    try {
      const res = await fetch("/api/messages", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ author, content, status: statusSelect ? statusSelect.value : "new" })
      });
      if (!res.ok) throw new Error("Ошибка сохранения");
      $("#content").value = "";
      if (statusSelect) statusSelect.value = "new";
      await loadMessages();
      setStatus("Сохранено");
    } catch (e) {
      setStatus(e.message || "Ошибка запроса", true);
    } finally {
      btn.disabled = false;
    }
  });

  await loadMessages();
})();
