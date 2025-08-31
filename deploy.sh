#!/bin/bash

# 🚀 Скрипт автоматической установки Birthday Bot
# Использование: bash deploy.sh

set -e  # Остановка при ошибке

echo "🤖 Birthday Bot - Автоматическая установка"
echo "=========================================="

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Пожалуйста, запустите скрипт с правами root: sudo bash deploy.sh"
    exit 1
fi

# Определение пользователя, который запустил sudo
REAL_USER=${SUDO_USER:-$USER}
echo "👤 Установка для пользователя: $REAL_USER"

# Обновление системы
echo "📦 Обновление системы..."
apt update && apt upgrade -y

# Установка зависимостей
echo "🐍 Установка Python и зависимостей..."
apt install python3 python3-pip python3-venv git curl -y

# Установка uv
echo "⚡ Установка uv (менеджер пакетов)..."
if ! command -v uv &> /dev/null; then
    sudo -u $REAL_USER bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
    sudo -u $REAL_USER bash -c 'source ~/.bashrc'
fi

# Создание директории для бота
BOT_DIR="/opt/HBbot"
echo "📁 Создание директории $BOT_DIR..."
mkdir -p $BOT_DIR

# Копирование файлов (если запускается из директории проекта)
if [ -f "birthday_bot.py" ]; then
    echo "📋 Копирование файлов проекта..."
    cp -r . $BOT_DIR/
    chown -R $REAL_USER:$REAL_USER $BOT_DIR
else
    echo "⚠️  Файлы проекта не найдены в текущей директории"
    echo "    Пожалуйста, клонируйте репозиторий в $BOT_DIR вручную"
fi

cd $BOT_DIR

# Создание виртуального окружения
echo "🌐 Создание виртуального окружения..."
sudo -u $REAL_USER uv venv

# Установка зависимостей Python
echo "📚 Установка зависимостей Python..."
sudo -u $REAL_USER bash -c 'source .venv/bin/activate && uv pip install python-telegram-bot schedule langchain-gigachat python-dotenv'

# Создание конфигурационных файлов
echo "⚙️  Создание конфигурационных файлов..."

# .env файл
if [ ! -f ".env" ]; then
    cat > .env << EOL
# Telegram Bot Token (получить у @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# GigaChat credentials  
GIGACHAT_CREDENTIALS=your_gigachat_credentials
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_MODEL=GigaChat

# Default Chat ID для отправки сообщений
DEFAULT_CHAT_ID=-1001234567890
EOL
    echo "📝 Создан файл .env - не забудьте его настроить!"
fi

# users_config.json файл
if [ ! -f "users_config.json" ] && [ -f "users_config.example.json" ]; then
    cp users_config.example.json users_config.json
    echo "📝 Создан файл users_config.json из примера"
fi

# Настройка прав доступа
echo "🔒 Настройка прав доступа..."
chown -R $REAL_USER:$REAL_USER $BOT_DIR
chmod 600 $BOT_DIR/.env
if [ -f "users_config.json" ]; then
    chmod 600 $BOT_DIR/users_config.json
fi
chmod +x $BOT_DIR/birthday_bot.py

# Установка systemd service
echo "🔄 Настройка автозапуска (systemd)..."
if [ -f "birthday-bot.service" ]; then
    cp birthday-bot.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable birthday-bot.service
    echo "✅ Сервис birthday-bot настроен и включен"
else
    echo "⚠️  Файл birthday-bot.service не найден"
fi

# Настройка timezone
echo "🕐 Настройка часового пояса..."
timedatectl set-timezone Europe/Moscow

# Настройка firewall (базовая)
echo "🛡️  Настройка firewall..."
ufw --force enable
ufw allow ssh

echo ""
echo "🎉 Установка завершена!"
echo "========================"
echo ""
echo "📋 Что нужно сделать дальше:"
echo "1. Настройте .env файл: nano $BOT_DIR/.env"
echo "2. Настройте пользователей: nano $BOT_DIR/users_config.json"
echo "3. Запустите бота: systemctl start birthday-bot.service"
echo "4. Проверьте статус: systemctl status birthday-bot.service"
echo ""
echo "📊 Полезные команды:"
echo "• Просмотр логов: journalctl -u birthday-bot.service -f"
echo "• Перезапуск: systemctl restart birthday-bot.service"
echo "• Остановка: systemctl stop birthday-bot.service"
echo ""
echo "🔗 IP адрес сервера: $(curl -s ifconfig.me)"
echo "📁 Директория бота: $BOT_DIR"
