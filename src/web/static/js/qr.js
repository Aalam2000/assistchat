// src/app/static/js/qr.js
console.log("📜 [qr.js] Скрипт QR инициализирован");

document.addEventListener("submit", async (e) => {
  if (!e.target || e.target.id !== "qr-form") return;
  e.preventDefault();

  const form = e.target;
  const statusEl = form.querySelector("#qr-status");
  const previewBig = form.querySelector("#qr-preview-big");
  const downloadEl = form.querySelector("#qr-download");
  const formData = new FormData(form);

  const text = (formData.get("text") || "").trim();
  if (!text) {
    statusEl.textContent = "⚠️ Введите текст или URL.";
    return;
  }

  // Генерация превью PNG
  try {
    statusEl.textContent = "⏳ Генерация...";
    previewBig.classList.add("hidden");
    downloadEl.classList.add("hidden");

    console.log("📤 [qr.js] Запрос превью /api/qr/preview");
    const resp = await fetch("/api/qr/preview", { method: "POST", body: formData });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const blob = await resp.blob();

    const imgURL = URL.createObjectURL(blob);
    previewBig.src = imgURL;
    previewBig.classList.remove("hidden");

    statusEl.textContent = "✅ QR готов.";
  } catch (err) {
    console.error("❌ [qr.js] Ошибка превью:", err);
    statusEl.textContent = "❌ Ошибка: " + (err.message || err);
    return;
  }

  // Генерация ZIP для скачивания
  try {
    console.log("📦 [qr.js] Генерация архива /api/qr/build");
    const respZip = await fetch("/api/qr/build", { method: "POST", body: formData });
    if (!respZip.ok) throw new Error("HTTP " + respZip.status);
    const zipBlob = await respZip.blob();

    const zipUrl = URL.createObjectURL(zipBlob);
    downloadEl.href = zipUrl;
    downloadEl.download = "qr_with_logo.zip";
    downloadEl.textContent = "⬇️ Скачать ZIP";
    downloadEl.classList.remove("hidden");

    console.log("✅ [qr.js] ZIP готов для скачивания");
  } catch (err) {
    console.error("❌ [qr.js] Ошибка генерации ZIP:", err);
  }
});
