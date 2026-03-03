#!/bin/bash
set -e

DOMAIN="sadcat.site"
EMAIL=""  # Будет запрошен интерактивно

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "=============================="
echo "  sadcat.site — deploy script"
echo "=============================="
echo ""

# ── 1. Docker ──────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    info "Устанавливаю Docker..."
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $USER
    info "Docker установлен. Перезапустите сессию если нужно: newgrp docker"
else
    info "Docker: $(docker --version)"
fi

if ! docker compose version &>/dev/null; then
    error "docker compose (plugin) не найден. Убедитесь что Docker Engine >= 23"
fi

# ── 2. Проверка .env ───────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    error ".env не найден!\nСкопируйте .env на сервер:\n  scp .env user@SERVER:/path/to/sadcat/.env"
fi
info ".env найден"

# ── 3. Проверка session ───────────────────────────────────────────────────────
mkdir -p sessions
SESSION_FILE=$(ls sessions/*.session 2>/dev/null | head -1)
if [ -z "$SESSION_FILE" ]; then
    error "Telegram session не найден в sessions/\nСкопируйте:\n  scp sessions/sadcat_session.session user@SERVER:/path/to/sadcat/sessions/"
fi
info "Session найден: $SESSION_FILE"

# ── 4. Email для certbot ───────────────────────────────────────────────────────
read -p "Ваш email для Let's Encrypt (уведомления об истечении): " EMAIL
[ -z "$EMAIL" ] && error "Email обязателен"

# ── 5. HTTP-конфиг для первоначального получения сертификата ──────────────────
info "Подготавливаю HTTP-конфиг (этап 1/2)..."
cp nginx/nginx.init.conf nginx/current.conf

# ── 6. Поднимаем сервисы (HTTP) ───────────────────────────────────────────────
info "Запускаю сервисы (HTTP)..."
docker compose -f docker-compose.prod.yml up -d db backend nginx

info "Жду запуска nginx (10 сек)..."
sleep 10

# Проверим доступность nginx
if ! curl -sf -o /dev/null http://localhost; then
    warn "nginx не отвечает на localhost — проверьте порт 80"
fi

# ── 7. Получаем сертификаты ────────────────────────────────────────────────────
info "Получаю SSL сертификат для ${DOMAIN}..."
docker compose -f docker-compose.prod.yml run --rm certbot \
    certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    -d "${DOMAIN}" \
    -d "www.${DOMAIN}"

info "Сертификат получен!"

# ── 8. Переключаемся на HTTPS-конфиг ─────────────────────────────────────────
info "Переключаюсь на HTTPS конфиг (этап 2/2)..."
cp nginx/nginx.prod.conf nginx/current.conf

docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
info "nginx перезагружен с HTTPS!"

# ── 9. Авто-продление сертификата (cron) ──────────────────────────────────────
info "Настраиваю cron для авто-продления сертификата..."
CRON_CMD="0 3 * * * cd $(pwd) && docker compose -f docker-compose.prod.yml run --rm certbot renew --quiet && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload"
(crontab -l 2>/dev/null | grep -v "certbot renew"; echo "$CRON_CMD") | crontab -
info "Cron добавлен (каждый день в 3:00)"

# ── 10. Готово ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}=============================="
echo "  Деплой завершён!"
echo -e "==============================${NC}"
echo ""
echo "  Сайт:    https://${DOMAIN}"
echo "  Гэмблинг: https://${DOMAIN}/gamble"
echo ""
echo "Полезные команды:"
echo "  Логи backend:  docker compose -f docker-compose.prod.yml logs -f backend"
echo "  Рестарт:       docker compose -f docker-compose.prod.yml restart backend"
echo "  Обновить код:  git pull && docker compose -f docker-compose.prod.yml up --build -d"
echo ""
