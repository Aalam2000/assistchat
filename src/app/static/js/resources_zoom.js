// src/app/static/js/resources_zoom.js

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("zoom-upload-form");
    const fileInput = document.getElementById("zoom-file");
    const reportsEl = document.getElementById("zoom-reports");
    const rid = (window.location.pathname.split("/").pop());
    const listEl = document.getElementById("zoom-list");

    // modal helpers
    const processingModal = document.getElementById("processing-modal");

    function showProcessing(note = "Идет обработка…") {
        try {
            if (processingModal) {
                processingModal.querySelector(".pm-title").textContent = note;
                processingModal.classList.remove("pm-hidden");
            }
        } catch (_) {
        }
    }

    function hideProcessing() {
        try {
            if (processingModal) {
                processingModal.classList.add("pm-hidden");
            }
        } catch (_) {
        }
    }

    // ── Промпт отчёта (локальное хранение на ресурс) ──────────────────────────
    const promptEl = document.getElementById("report-prompt");
    const PROMPT_KEY = `reportPrompt:${rid}`;
    const DEFAULT_REPORT_PROMPT = `Ты — аналитик встречи. На основе транскрипта составь отчёт в формате:
    1) Краткое резюме (3–5 пунктов).
    2) Ключевые решения.
    3) Задачи: "Задача — Ответственный — Срок".
    4) Открытые вопросы.
    5) Риски и next steps.
    Пиши по-русски, структурировано, без воды.`;

    if (promptEl) {
        try {
            promptEl.value = localStorage.getItem(PROMPT_KEY) || DEFAULT_REPORT_PROMPT;
        } catch (_) {
            promptEl.value = DEFAULT_REPORT_PROMPT;
        }
        const save = () => {
            try {
                localStorage.setItem(PROMPT_KEY, promptEl.value);
            } catch (_) {
            }
        };
        promptEl.addEventListener("input", save);
        promptEl.addEventListener("change", save);
        // доступ из других обработчиков
        window.getReportPrompt = () => (promptEl && promptEl.value) ? promptEl.value : DEFAULT_REPORT_PROMPT;
    } else {
        window.getReportPrompt = () => DEFAULT_REPORT_PROMPT;
    }
    // ───────────────────────────────────────────────────────────────────────────

    loadPairs(rid);

    if (!form || !fileInput) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const file = fileInput.files[0];
        if (!file) {
            alert("Выберите файл .mp3 или .mp4");
            return;
        }

        showProcessing("Загрузка файла…");
        const formData = new FormData();
        formData.append("file", file);

        try {
            const rid = form.dataset.rid || (window.location.pathname.split("/").pop());
            const resp = await fetch(`/api/zoom/${rid}/upload`, {
                method: "POST",
                body: formData,
                credentials: "same-origin"
            });

            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || !data.ok) {
                throw new Error(data.error || "Ошибка загрузки");
            }

            await loadPairs(rid);      // 🔵 сразу перерисуем список
            fileInput.value = "";      // очистим input
            hideProcessing();
        } catch (err) {
            console.error("[zoom] upload error:", err);
        }
    });

    // --- ДОБАВЬТЕ/ЗАМЕНИТЕ ЭТУ ФУНКЦИЮ ВМЕСТО loadFiles:
    async function loadPairs(rid) {
        try {
            const resp = await fetch(`/api/zoom/${rid}/items`, {credentials: "same-origin"});
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || !data.ok) throw new Error(data.error || "Ошибка загрузки списка");

            if (!Array.isArray(data.items) || data.items.length === 0) {
                listEl.innerHTML = `<div class="note">Файлы не найдены</div>`;
                return;
            }

            // верстаем по строкам: слева аудио, по центру транскрипт, справа — ОТДЕЛЬНАЯ карточка отчёта
            listEl.innerHTML = data.items.map(it => {
                const audio = it.audio;
                const tr = it.transcript;
                const report = it.report;

                const left = audio ? `
                <div class="card">
                    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                        <div>
                            <strong>${audio.filename}</strong>
                            <div class="mono">Размер: ${(audio.size / 1024 / 1024).toFixed(2)} MB</div>
                            <div class="mono">Загружен: ${audio.uploaded}</div>
                        </div>
                        <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;">
                            <button class="btn primary" data-act="process" data-file="${audio.filename}">Отработать</button>
                            <button class="btn danger" data-act="del-audio" data-file="${audio.filename}">Удалить</button>
                        </div>
                    </div>
                </div>
            ` : `
                <div class="card"><div class="mono">Исходного файла нет</div></div>
            `;

                const baseName = audio ? audio.filename : (tr?.filename || "").replace(/\.txt$/, "");
                const middle = tr?.exists ? `
                <div class="card">
                    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                        <div>
                            <strong>${tr.filename}</strong>
                            <div class="mono">Размер: ${(tr.size / 1024 / 1024).toFixed(2)} MB</div>
                        </div>
                        <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;">
                            <a class="btn" href="/api/zoom/${rid}/transcript/open?filename=${encodeURIComponent(baseName)}" target="_blank" rel="noopener">Открыть</a>
                            <button class="btn danger" data-act="del-tr" data-file="${baseName}">Удалить</button>
                        </div>
                    </div>
                </div>
            ` : `
                <div class="card"><div class="mono">Транскрипт пока не создан</div></div>
            `;

                const right = tr?.exists ? (
                    report?.exists ? `
                    <div class="card">
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                            <div>
                                <strong>${report.filename}</strong>
                                <div class="mono">Размер: ${(report.size / 1024).toFixed(1)} KB</div>
                            </div>
                            <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;">
                                <a class="btn" href="/api/zoom/${rid}/report/open?filename=${encodeURIComponent(report.filename)}" target="_blank">Показать</a>
                                <button class="btn danger" data-act="del-report" data-file="${report.filename}">Удалить</button>
                            </div>
                        </div>
                    </div>
                ` : `
                    <div class="card">
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                            <div><strong>Отчёт</strong></div>
                            <div>
                                <button class="btn primary" data-act="make-report" data-file="${baseName}">Сделать отчёт</button>
                            </div>
                        </div>
                    </div>
                `
                ) : `
                <div class="card"><div class="mono">Отчёт будет доступен после транскрипта</div></div>
            `;

                return `
                <div class="pair-row" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:10px 0;">
                    ${left}
                    ${middle}
                    ${right}
                </div>
            `;
            }).join("");

            // делегируем обработку кликов
            listEl.querySelectorAll("[data-act]").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const act = btn.dataset.act;
                    const file = btn.dataset.file;

                    try {
                        if (act === "process") {
                            showProcessing("Идет транскрибация…");
                            const resp = await fetch(`/api/zoom/${rid}/process`, {
                                method: "POST",
                                headers: {"Content-Type": "application/json"},
                                credentials: "same-origin",
                                body: JSON.stringify({filename: file}),
                            });
                            hideProcessing();
                            const d = await resp.json().catch(() => ({}));
                            if (!resp.ok || !d.ok) throw new Error(d.error || "Ошибка запуска транскрибации");

                            setTimeout(() => loadPairs(rid), 2000);
                        }

                        if (act === "del-audio") {
                            if (!confirm(`Удалить исходный файл: ${file}?`)) return;
                            const resp = await fetch(`/api/zoom/${rid}/audio?filename=${encodeURIComponent(file)}`, {
                                method: "DELETE",
                                credentials: "same-origin",
                            });
                            const d = await resp.json().catch(() => ({}));
                            if (!resp.ok || !d.ok) throw new Error(d.error || "Ошибка удаления");
                            loadPairs(rid);
                        }

                        if (act === "del-tr") {
                            if (!confirm(`Удалить транскрипт для: ${file}?`)) return;
                            const resp = await fetch(`/api/zoom/${rid}/transcript?filename=${encodeURIComponent(file)}`, {
                                method: "DELETE",
                                credentials: "same-origin",
                            });
                            const d = await resp.json().catch(() => ({}));
                            if (!resp.ok || !d.ok) throw new Error(d.error || "Ошибка удаления");
                            loadPairs(rid);
                        }

                        if (act === "make-report") {
                            const prompt = (window.getReportPrompt && window.getReportPrompt()) || "";
                            showProcessing("Формируем отчёт…");
                            const resp = await fetch(`/api/zoom/${rid}/report`, {
                                method: "POST",
                                headers: {"Content-Type": "application/json"},
                                credentials: "same-origin",
                                body: JSON.stringify({filename: file, prompt}),
                            });
                            hideProcessing();
                            const d = await resp.json().catch(() => ({}));
                            if (!resp.ok || !d.ok) throw new Error(d.error || "Ошибка генерации отчёта");

                            setTimeout(() => loadPairs(rid), 2000);
                        }

                        if (act === "del-report") {
                            if (!confirm(`Удалить отчёт: ${file}?`)) return;
                            const resp = await fetch(`/api/zoom/${rid}/report?filename=${encodeURIComponent(file)}`, {
                                method: "DELETE",
                                credentials: "same-origin",
                            });
                            const d = await resp.json().catch(() => ({}));
                            if (!resp.ok || !d.ok) throw new Error(d.error || "Ошибка удаления отчёта");
                            loadPairs(rid);
                        }

                    } catch (e) {
                        console.error("[zoom] action error:", e);
                        alert(e.message || "Ошибка действия");
                    }
                });
            });

        } catch (err) {
            console.error("[zoom] loadPairs error:", err);
            listEl.innerHTML = `<div class="error">Ошибка загрузки</div>`;
        }
    }


    async function loadReports(rid) {
        try {
            const resp = await fetch(`/api/zoom/${rid}/reports`, {
                credentials: "same-origin"
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || !data.ok) {
                throw new Error(data.error || "Ошибка загрузки отчетов");
            }

            if (!Array.isArray(data.items) || data.items.length === 0) {
                reportsEl.innerHTML = `<div class="note">Пока нет отчетов</div>`;
                return;
            }

            reportsEl.innerHTML = "";
            data.items.forEach((it) => {
                const div = document.createElement("div");
                div.className = "card";
                div.style.margin = "10px 0";
                div.innerHTML = `
                    <h3>Встреча: ${it.filename || "без названия"}</h3>
                    <p><strong>Краткое резюме:</strong><br>${it.summary || "—"}</p>
                    <button class="btn" data-file="${it.filename}">Показать транскрипт</button>
                `;
                reportsEl.appendChild(div);

                const btn = div.querySelector("button");
                btn.addEventListener("click", () => {
                    alert(it.transcript || "Нет транскрипта");
                });
            });
        } catch (err) {
            console.error("[zoom] loadReports error:", err);
            reportsEl.innerHTML = `<div class="error">Ошибка загрузки отчетов</div>`;
        }
    }
});

