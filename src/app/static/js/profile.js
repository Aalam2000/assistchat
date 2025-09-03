// src/app/static/js/profile.js
document.addEventListener("DOMContentLoaded", () => {
  const logout = document.getElementById("logout-btn");
  logout?.addEventListener("click", async () => {
    try {
      const { ok, redirect } = await apiPost(window.APP_CONFIG.endpoints.logout, {});
      if (ok && redirect) window.location.href = redirect;
    } catch { /* ignore */ }
  });
});

// Загрузка списка моих сессий (с логами)
async function loadMySessions() {
  console.log("[profile] loadMySessions: start");
  const tbody = document.getElementById("my-sessions-tbody");
  if (!tbody) { console.log("[profile] tbody not found"); return; }

  try {
    const r = await fetch("/api/my/sessions", { credentials: "same-origin" });
    console.log("[profile] /api/my/sessions status:", r.status);
    const data = await r.json();
    console.log("[profile] data:", data);

    tbody.innerHTML = "";
    (data.items || []).forEach(it => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${it.label ?? ""}</td>
        <td>${it.phone ?? ""}</td>
        <td class="status">${it.status ?? ""}</td>
        <td>
          <button class="btn tg-toggle" data-phone="${it.phone}">
            ${it.status === "active" ? "Выключить" : "Включить"}
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
    if ((data.items || []).length === 0) {
      tbody.innerHTML = `<tr><td colspan="3">Пока нет ни одной сессии</td></tr>`;
    }
  } catch (e) {
    console.error("[profile] loadMySessions error:", e);
    tbody.innerHTML = `<tr><td colspan="3">Ошибка загрузки</td></tr>`;
  }
}
document.addEventListener("DOMContentLoaded", loadMySessions);

document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("my-sessions-tbody");
  if (!tbody) return;

  tbody.addEventListener("click", async (e) => {
    const btn = e.target.closest(".tg-toggle");
    if (!btn) return;

    const phone = btn.dataset.phone;
    btn.disabled = true;
    try {
      const r = await fetch("/api/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ phone })
      });
      const data = await r.json();
      const row = btn.closest("tr");
      row.querySelector(".status").textContent = data.status || "";
      btn.textContent = (data.status === "active") ? "Выключить" : "Включить";
    } catch {
      alert("Ошибка переключения сессии");
    } finally {
      btn.disabled = false;
    }
  });
});
