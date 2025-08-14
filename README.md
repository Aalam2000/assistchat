# assistchat

**1️⃣ Пересборка с нуля и запуск**

```bash
cd /var/www/assistchat
docker compose down --remove-orphans
docker compose up -d --build
```

* `--remove-orphans` удаляет лишние контейнеры, которых нет в `docker-compose.yml`.
* `--build` пересобирает образы по Dockerfile.

---

**2️⃣ Перезапуск без пересборки**

```bash
cd /var/www/assistchat
docker compose restart
```

---

**3️⃣ Остановка контейнеров**

```bash
cd /var/www/assistchat
docker compose down
```

> Это остановит и удалит контейнеры, но оставит образы и volume'ы.

---

**4️⃣ Проверка статуса**

```bash
cd /var/www/assistchat
docker compose ps
```

**5️⃣ Просмотр логов**

```bash
docker compose logs -f
# или только сервиса api
docker compose logs -f api
```

```bash
# Посмотреть тома
docker volume ls
```
---

Хочешь, я тебе сделаю одну короткую команду `deploy`, чтобы на сервере можно было просто ввести `deploy` и оно всё пересобирало и запускало? Так будет быстрее работать при выкладках.
