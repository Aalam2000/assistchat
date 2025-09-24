// src/app/static/js/index.js
document.addEventListener("DOMContentLoaded", () => {
  // ───────────────────────────────────────────────
  // Аккордеон
  document.querySelectorAll(".section-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const body = btn.nextElementSibling;
      const willOpen = body.style.display !== "block";
      document.querySelectorAll(".section-body").forEach((b) => (b.style.display = "none"));
      if (willOpen) body.style.display = "block";
    });
  });

  // ───────────────────────────────────────────────
  // QR генератор
  const form = document.getElementById("qr-form");
  if (form) {
    const statusEl = document.getElementById("qr-status");
    const preview = document.getElementById("qr-preview");
    const download = document.getElementById("qr-download");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      statusEl.textContent = "";
      preview?.classList.add("hidden");
      download?.classList.add("hidden");
      download.removeAttribute("href");
      download.removeAttribute("download");

      const fd = new FormData(form);
      const url = "/api/qr/build";

      try {
        const resp = await fetch(url, { method: "POST", body: fd, credentials: "same-origin" });
        if (!resp.ok) {
          const txt = await resp.text().catch(() => "");
          throw new Error(txt || `HTTP ${resp.status}`);
        }
        const blob = await resp.blob();
        const objectUrl = URL.createObjectURL(blob);

        // Скачать ZIP (в нём PNG и PDF)
        download.href = objectUrl;
        download.download = "qr_with_logo.zip";
        download.classList.remove("hidden");

        statusEl.textContent = "Готово. Скачайте архив.";
      } catch (err) {
        console.error("[qr] error:", err);
        statusEl.textContent = "Ошибка генерации QR.";
      }
    });
  }

  // ───────────────────────────────────────────────
  // Авторский блок
  const authorBtn = document.getElementById("author-btn");
  if (authorBtn) {
    authorBtn.addEventListener("click", () => {
      document.getElementById("author-modal").classList.remove("hidden");
    });
  }

  // ───────────────────────────────────────────────
  // Мои подключения
  async function loadUserConnections() {
    const tbody = document.getElementById("svc-tbody");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="3">Загрузка...</td></tr>`;

    try {
      const resp = await fetch("/api/resources/list", { credentials: "same-origin" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const items = data.items || [];

      tbody.innerHTML = "";

      if (items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3">Нет подключений</td></tr>`;
        return;
      }

      for (const it of items) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${it.provider ?? ""}</td>
          <td>${it.label ?? ""}</td>
          <td>${it.status ?? ""}</td>
        `;
        tbody.appendChild(tr);
      }
    } catch (err) {
      console.error("[svc] loadUserConnections error:", err);
      tbody.innerHTML = `<tr><td colspan="3">Ошибка загрузки</td></tr>`;
    }
  }

  loadUserConnections();
});
