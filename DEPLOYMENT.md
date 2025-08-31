# 🚀 Деплой Birthday Bot на VPS

## 📋 Подготовка сервера

### 1. Подключение к серверу
```bash
ssh root@176.108.246.9
# или
ssh username@176.108.246.9
```

### 2. Обновление системы (Ubuntu/Debian)
```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Установка Python и зависимостей
```bash
# Установка Python 3.11+ и pip
sudo apt install python3 python3-pip python3-venv git -y

# Установка uv (современный менеджер пакетов)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

## 📁 Установка бота

### 1. Клонирование репозитория
```bash
cd /opt
sudo git clone https://github.com/YOUR_USERNAME/HBbot.git
sudo chown -R $USER:$USER /opt/HBbot
cd /opt/HBbot
```

### 2. Создание виртуального окружения
```bash
uv venv
source .venv/bin/activate
```

### 3. Установка зависимостей
```bash
uv pip install -r pyproject.toml
```

### 4. Настройка конфигурации
```bash
# Копируем пример конфигурации
cp users_config.example.json users_config.json

# Создаем .env файл
cp .env.example .env

# Редактируем конфигурацию
nano .env
```

## ⚙️ Настройка .env файла

Заполните следующие переменные в `.env`:

```env
# Telegram Bot Token (получить у @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# GigaChat credentials
GIGACHAT_CREDENTIALS=your_gigachat_credentials
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_MODEL=GigaChat

# Default Chat ID для отправки сообщений
DEFAULT_CHAT_ID=-1001234567890
```

## 👥 Настройка пользователей

Отредактируйте `users_config.json`:

```json
{
    "birthday_time": "09:00",
    "default_chat_id": -1001234567890,
    "users": [
        {
            "name": "Имя",
            "username": "username",
            "birthday": "01.01",
            "chat_id": -1001234567890
        }
    ]
}
```

## 🔄 Настройка автозапуска (systemd)

### 1. Создание service файла
```bash
sudo nano /etc/systemd/system/birthday-bot.service
```

### 2. Перезагрузка systemd и запуск
```bash
sudo systemctl daemon-reload
sudo systemctl enable birthday-bot.service
sudo systemctl start birthday-bot.service
```

### 3. Проверка статуса
```bash
sudo systemctl status birthday-bot.service
sudo journalctl -u birthday-bot.service -f
```

## 📊 Мониторинг

### Просмотр логов
```bash
# Логи системного сервиса
sudo journalctl -u birthday-bot.service -f

# Логи приложения
tail -f /opt/HBbot/birthday_bot.log
```

### Управление сервисом
```bash
# Остановка
sudo systemctl stop birthday-bot.service

# Перезапуск
sudo systemctl restart birthday-bot.service

# Перезагрузка конфигурации
sudo systemctl reload birthday-bot.service
```

## 🔧 Обновление бота

```bash
cd /opt/HBbot
sudo systemctl stop birthday-bot.service
git pull origin master
source .venv/bin/activate
uv pip install -r pyproject.toml
sudo systemctl start birthday-bot.service
```

## 🛡️ Безопасность

1. **Настройте firewall**:
```bash
sudo ufw enable
sudo ufw allow ssh
```

2. **Ограничьте права доступа**:
```bash
chmod 600 /opt/HBbot/.env
chmod 600 /opt/HBbot/users_config.json
```

3. **Создайте отдельного пользователя для бота** (рекомендуется):
```bash
sudo useradd --system --shell /bin/bash --home /opt/HBbot botuser
sudo chown -R botuser:botuser /opt/HBbot
```

## ❗ Возможные проблемы

### Timezone
```bash
sudo timedatectl set-timezone Europe/Moscow
```

### Права доступа
```bash
sudo chown -R $USER:$USER /opt/HBbot
chmod +x /opt/HBbot/birthday_bot.py
```

### Зависимости
```bash
# Если проблемы с установкой
sudo apt install python3-dev build-essential
```
