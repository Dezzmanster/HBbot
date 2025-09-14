"""Константы для Birthday Bot"""

# Настройки логирования
LOG_FILE = "birthday_bot.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Файлы конфигурации
USERS_CONFIG_FILE = "users_config.json"
PROMPT_FILE = "birthday_prompt.txt"
BELATED_PROMPT_FILE = "birthday_belated_prompt.txt"
DELIVERY_TRACKING_FILE = "delivery_tracking.json"

# Значения по умолчанию
DEFAULT_BIRTHDAY_TIME = "09:00"
DEFAULT_USER_NAME = "Дорогой друг"
DEFAULT_UNKNOWN_NAME = "Неизвестный"

# Формат даты
DATE_FORMAT = "%d.%m"

# Задержка между сообщениями (в секундах)
MESSAGE_DELAY = 1

# Интервал проверки расписания (в секундах)
SCHEDULE_CHECK_INTERVAL = 60

# Количество дней для повторных попыток отправки
RETRY_DAYS = 2

# Сообщение по умолчанию при ошибке генерации
DEFAULT_BIRTHDAY_MESSAGE = (
    "🎉🎂 Поздравляем {name} с днем рождения! 🌟✨ "
    "Желаем крепкого здоровья, безграничного счастья, "
    "ярких эмоций и исполнения всех мечт! 🎁💫 "
    "Пусть этот день будет наполнен радостью и теплом близких! 🥳💖"
)

# Сообщение для поздравлений с прошедшим днем рождения
DEFAULT_BELATED_MESSAGE = (
    "🎉🎂 Поздравляем {name} с прошедшим днем рождения! 🌟✨ "
    "Извините, что поздравляем с опозданием! "
    "Желаем, чтобы этот новый год жизни принес много радости, "
    "успехов и исполнения всех желаний! 🎁💫🥳💖"
)
