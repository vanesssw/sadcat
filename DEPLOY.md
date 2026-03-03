# Деплой на сервер (Ubuntu 24.04)

## Что потребуется
- VPS с Ubuntu 24.04
- Домен `sadcat.site` → A-запись на IP сервера
- Locaльные файлы: `.env` и `sessions/sadcat_session.session`

---

## Шаг 1 — DNS

В панели регистратора домена добавьте A-записи:
```
sadcat.site      →  <IP сервера>
www.sadcat.site  →  <IP сервера>
```
Подождите 5–30 минут чтобы DNS разошёлся.

---

## Шаг 2 — Клонируем репозиторий на сервере

```bash
ssh user@<IP сервера>

sudo mkdir -p /var/www/sadcat
sudo chown $USER:$USER /var/www/sadcat

git clone https://github.com/YOURUSER/sadcat.git /var/www/sadcat
cd /var/www/sadcat
```

---

## Шаг 3 — Копируем .env и session со своего компьютера

```bash
# С вашего PC (Windows PowerShell):
scp "c:\Users\User\Desktop\some code\sadcat\.env" user@<IP>:/var/www/sadcat/.env
scp "c:\Users\User\Desktop\some code\sadcat\sessions\sadcat_session.session" user@<IP>:/var/www/sadcat/sessions/
```

> **Важно:** Сначала создайте папку sessions на сервере если её нет:
> `ssh user@<IP> "mkdir -p /var/www/sadcat/sessions"`

---

## Шаг 4 — Запускаем деплой-скрипт

На сервере, в директории `/var/www/sadcat`:

```bash
cd /var/www/sadcat
chmod +x deploy.sh
sudo ./deploy.sh
```

Скрипт сделает всё автоматически:
1. Проверит наличие Docker (установит если нет)
2. Проверит `.env` и session
3. Запросит email для Let's Encrypt
4. Поднимет сервисы на HTTP
5. Получит SSL сертификат через certbot
6. Переключит nginx на HTTPS
7. Добавит cron для авто-продления сертификата

---

## Шаг 5 — Проверка

```bash
# Статус контейнеров
docker compose -f docker-compose.prod.yml ps

# Логи backend
docker compose -f docker-compose.prod.yml logs -f backend

# Тест сайта
curl -I https://sadcat.site
```

---

## Обновление кода

```bash
cd /var/www/sadcat
git pull
docker compose -f docker-compose.prod.yml up --build --no-deps -d backend
# Если фронтенд изменился:
docker compose -f docker-compose.prod.yml up --build --no-deps -d nginx
```

---

## Ручное продление сертификата

```bash
docker compose -f docker-compose.prod.yml run --rm certbot renew
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

---

## Структура файлов после деплоя

```
sadcat/
├── .env                        ← скопировать вручную
├── sessions/
│   └── sadcat_session.session  ← скопировать вручную
├── nginx/
│   ├── nginx.init.conf         ← HTTP (временный, для certbot)
│   ├── nginx.prod.conf         ← HTTPS (финальный)
│   └── current.conf            ← создаётся deploy.sh, gitignored
├── docker-compose.prod.yml
└── deploy.sh
```

---

## Важные замечания

- **Flood wait** Telegram: первый запуск может занять несколько минут пока Telethon
  скачает аватарки и выполнит первый цикл обновлений
- **entity_cache.json** сохраняется в Docker volume `tg_sessions`, не теряется при перезапусках
- **Certbot** автоматически продлевается по cron каждый день в 3:00
