const btn = document.getElementById('btnCreate');
const textEl = document.getElementById('qrText');
const fileEl = document.getElementById('logoFile');
const statusEl = document.getElementById('status');

btn.addEventListener('click', async () => {
  const text = (textEl.value||'').trim();
  const file = fileEl.files && fileEl.files[0];
  if(!text){ statusEl.textContent = '⚠️ Введите текст/URL.'; return; }
  if(!file){ statusEl.textContent = '⚠️ Загрузите логотип (PNG/TIFF).'; return; }
  statusEl.textContent = '⏳ Генерация…';
  btn.disabled = true;
  try{
    const form = new FormData();
    form.append('text', text);
    form.append('logo', file);

    const resp = await fetch('/api/qr/build', { method: 'POST', body: form });
    if(!resp.ok) throw new Error('HTTP '+resp.status);

    const blob = await resp.blob();
    const fname = (resp.headers.get('X-File-Name') || 'qr_with_logo') + '.zip';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = fname; document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);

    statusEl.textContent = '✅ Скачано.';
  }catch(e){
    statusEl.textContent = '❌ Ошибка: '+(e.message||e);
  }finally{
    btn.disabled = false;
  }
});
