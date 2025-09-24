// src/app/static/js/index.js
document.addEventListener("DOMContentLoaded", () => {
  // Аккордеон
  document.querySelectorAll(".section-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const body = btn.nextElementSibling;
      const willOpen = body.style.display !== "block";
      document.querySelectorAll(".section-body").forEach((b) => (b.style.display = "none"));
      if (willOpen) body.style.display = "block";
    });
  });

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
});
const authorBtn = document.getElementById("author-btn");
if (authorBtn) {
  authorBtn.addEventListener("click", () => {
    document.getElementById("author-modal").classList.remove("hidden");
  });
}