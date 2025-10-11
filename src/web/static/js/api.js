// src/app/static/js/api.js
async function apiPost(url, data) {
  const r = await fetch(url, {
    credentials: "same-origin",
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {})
  });
  const json = await r.json().catch(() => ({}));
  if (!r.ok) throw { status: r.status, ...json };
  return json;
}
