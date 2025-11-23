// src/app/static/js/index.js
document.addEventListener("DOMContentLoaded", () => {
    // ───────────────────────────────────────────────
    // Возможности (новый блок вместо аккордеона)
    const grid = document.getElementById("features-grid");
    const detail = document.getElementById("feature-detail");

    if (grid && detail) {
        grid.querySelectorAll(".feature-card").forEach(card => {
            card.addEventListener("click", () => {
                const target = card.dataset.target;
                const source = document.querySelector(`#features-sources .section-item[data-id="${target}"] .section-body`);
                if (source) {
                    detail.innerHTML = source.innerHTML;
                    grid.classList.add("hidden");
                    detail.classList.remove("hidden");
                }
            });
        });

        // закрыть по клику
        document.addEventListener("click", (e) => {
            // если сетка уже видна — ничего не делаем
            if (!grid.classList.contains("hidden")) return;

            // исключаем клик по карточке (они уже отработали)
            if (e.target.closest(".feature-card")) return;

            // проверяем: открыт ли QR-блок
            const isQR = detail.querySelector("#qr-form") !== null;

            if (isQR) {
                // для QR-кодов закрываем только если клик ВНЕ detail
                if (!detail.contains(e.target)) {
                    detail.classList.add("hidden");
                    grid.classList.remove("hidden");
                    detail.innerHTML = "";
                }
            } else {
                // для остальных закрываем всегда
                detail.classList.add("hidden");
                grid.classList.remove("hidden");
                detail.innerHTML = "";
            }
        });

    }


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
                const resp = await fetch(url, {method: "POST", body: fd, credentials: "same-origin"});
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
            const resp = await fetch("/api/providers/resources/list", {credentials: "same-origin"});
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
