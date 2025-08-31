import os
import json
import schedule
import time
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv
from telegram import Bot
from langchain_gigachat.chat_models import GigaChat

# Импортируем константы
from constants import (
    LOG_FILE,
    LOG_FORMAT,
    USERS_CONFIG_FILE,
    PROMPT_FILE,
    DEFAULT_BIRTHDAY_TIME,
    DEFAULT_USER_NAME,
    DEFAULT_UNKNOWN_NAME,
    DATE_FORMAT,
    MESSAGE_DELAY,
    SCHEDULE_CHECK_INTERVAL,
    DEFAULT_BIRTHDAY_MESSAGE,
)

# Загружаем переменные окружения
load_dotenv()


# Настройка логирования
def setup_logging() -> logging.Logger:
    """Настраивает систему логирования для бота"""
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)


logger = setup_logging()


class BirthdayBot:
    """Телеграм бот для автоматической отправки поздравлений с днем рождения"""

    def __init__(self):
        """Инициализирует бота с необходимыми сервисами и конфигурацией"""
        logger.debug("Инициализация BirthdayBot...")

        # Загрузка и проверка обязательных переменных окружения
        self._load_environment_variables()

        # Инициализация сервисов
        self._initialize_services()

        # Пути к файлам конфигурации
        self.users_config_path = USERS_CONFIG_FILE
        self.prompt_file_path = PROMPT_FILE

        logger.debug("BirthdayBot успешно инициализирован")

    def _load_environment_variables(self) -> None:
        """Загружает и валидирует переменные окружения"""
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.gigachat_credentials = os.getenv("GIGACHAT_CREDENTIALS")
        self.gigachat_scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.gigachat_model = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
        self.default_chat_id = os.getenv("CHAT_ID")

        # Проверка обязательных переменных
        if not self.bot_token:
            logger.error("TELEGRAM_BOT_TOKEN не найден в .env файле")
            raise ValueError("TELEGRAM_BOT_TOKEN не найден в .env файле")

        if not self.gigachat_credentials:
            logger.error("GIGACHAT_CREDENTIALS не найден в .env файле")
            raise ValueError("GIGACHAT_CREDENTIALS не найден в .env файле")

        # Преобразование chat_id в число, если указан
        if self.default_chat_id:
            try:
                self.default_chat_id = int(self.default_chat_id)
                logger.debug(f"Default chat_id установлен: {self.default_chat_id}")
            except ValueError:
                logger.error("CHAT_ID должен быть числом")
                raise ValueError("CHAT_ID должен быть числом")

    def _initialize_services(self) -> None:
        """Инициализирует внешние сервисы (Telegram Bot и GigaChat)"""
        logger.debug("Инициализация Telegram Bot...")
        self.bot = Bot(token=self.bot_token)

        logger.debug("Инициализация GigaChat...")
        self.gigachat = GigaChat(
            credentials=self.gigachat_credentials,
            scope=self.gigachat_scope,
            verify_ssl_certs=False,
            model=self.gigachat_model,
        )

    def load_config(self) -> Tuple[List[Dict], str, Optional[int]]:
        """
        Загружает конфигурацию из JSON файла

        Returns:
            Кортеж (список пользователей, время отправки, default_chat_id)
        """
        try:
            logger.debug(f"Загрузка конфигурации из {self.users_config_path}")
            with open(self.users_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            users = config.get("users", [])
            birthday_time = config.get("birthday_time", DEFAULT_BIRTHDAY_TIME)
            config_default_chat = config.get("default_chat_id")

            logger.debug(
                f"Загружено {len(users)} пользователей, время отправки: {birthday_time}"
            )
            return users, birthday_time, config_default_chat

        except FileNotFoundError:
            logger.error(f"Файл {self.users_config_path} не найден")
            return [], DEFAULT_BIRTHDAY_TIME, None
        except json.JSONDecodeError:
            logger.error(f"Ошибка чтения JSON из файла {self.users_config_path}")
            return [], DEFAULT_BIRTHDAY_TIME, None

    def load_birthday_prompt(self) -> str:
        """
        Загружает промпт для генерации поздравлений

        Returns:
            Шаблон промпта для GigaChat
        """
        try:
            with open(self.prompt_file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(
                f"Файл {self.prompt_file_path} не найден, используем стандартный промпт"
            )
            return "Поздравь {name} с днем рождения!"

    def get_today_birthdays(self) -> List[Dict]:
        """
        Возвращает список пользователей, у которых сегодня день рождения

        Returns:
            Список словарей с данными именинников
        """
        users, _, _ = self.load_config()
        if not users:
            return []

        today = datetime.now().strftime(DATE_FORMAT)
        birthday_users = []

        # Проверяем каждого пользователя
        for user in users:
            name = user.get("name", DEFAULT_UNKNOWN_NAME)
            birthday = user.get("birthday")

            # Валидация данных пользователя
            if not birthday:
                logger.warning(f"У пользователя {name} отсутствует дата рождения")
                continue

            if birthday == today:
                birthday_users.append(user)
                logger.debug(f"Найден именинник: {name} ({birthday})")

        logger.info(f"Найдено именинников на сегодня: {len(birthday_users)}")
        return birthday_users

    def generate_birthday_message(self, name: str) -> str:
        """
        Генерирует персонализированное поздравление с помощью GigaChat

        Args:
            name: Имя именинника

        Returns:
            Текст поздравления
        """
        try:
            prompt_template = self.load_birthday_prompt()
            prompt = prompt_template.format(name=name)

            response = self.gigachat.invoke(prompt)
            return response.content

        except Exception as e:
            logger.error(f"Ошибка при генерации поздравления: {e}")
            # Возвращаем красивое стандартное поздравление при ошибке
            return DEFAULT_BIRTHDAY_MESSAGE.format(name=name)

    async def send_birthday_messages(self) -> None:
        """Отправляет поздравления всем сегодняшним именинникам"""
        birthday_users = self.get_today_birthdays()

        if not birthday_users:
            logger.info("Сегодня нет именинников")
            return

        # Загружаем конфигурацию для получения default_chat_id
        _, _, config_default_chat = self.load_config()

        for user in birthday_users:
            await self._send_birthday_message_to_user(user, config_default_chat)

    async def _send_birthday_message_to_user(
        self, user: Dict, config_default_chat: Optional[int]
    ) -> None:
        """
        Отправляет поздравление конкретному пользователю

        Args:
            user: Данные пользователя
            config_default_chat: Chat ID из конфигурации по умолчанию
        """
        try:
            name = user.get("name", DEFAULT_USER_NAME)
            username = user.get("username", "")

            # Определяем chat_id для отправки сообщения
            user_chat_id = self._get_chat_id_for_user(user, config_default_chat, name)
            if not user_chat_id:
                return

            # Генерируем и отправляем поздравление
            birthday_message = self.generate_birthday_message(name)
            final_message = self._format_final_message(username, name, birthday_message)

            await self._send_telegram_message(user_chat_id, final_message)

            logger.info(f"Поздравление отправлено для {name} в чат {user_chat_id}")

            # Небольшая задержка между сообщениями для избежания лимитов
            await asyncio.sleep(MESSAGE_DELAY)

        except Exception as e:
            logger.error(
                f"Ошибка при отправке поздравления для {user.get('name', 'Unknown')}: {e}"
            )

    def _get_chat_id_for_user(
        self, user: Dict, config_default_chat: Optional[int], name: str
    ) -> Optional[int]:
        """
        Определяет chat_id для отправки сообщения пользователю

        Приоритет: user chat_id > config default chat_id > env default chat_id
        """
        user_chat_id = user.get("chat_id")

        if not user_chat_id:
            user_chat_id = config_default_chat or self.default_chat_id

        if not user_chat_id:
            logger.error(
                f"Не найден chat_id для пользователя {name}. "
                f"Укажите chat_id в конфигурации или установите CHAT_ID в .env"
            )
            return None

        return user_chat_id

    def _format_final_message(
        self, username: str, name: str, birthday_message: str
    ) -> str:
        """Форматирует финальное сообщение с учетом наличия username"""
        if username:
            return f"@{username}\n\n{birthday_message}"
        else:
            return f"{name}\n\n{birthday_message}"

    async def _send_telegram_message(self, chat_id: int, text: str) -> None:
        """
        Отправляет сообщение в Telegram с поддержкой Markdown

        При ошибке разметки отправляет сообщение без форматирования
        """
        try:
            await self.bot.send_message(
                chat_id=chat_id, text=text, parse_mode="Markdown"
            )
        except Exception as markdown_error:
            logger.warning(
                f"Ошибка Markdown разметки, отправляем без форматирования: {markdown_error}"
            )
            await self.bot.send_message(chat_id=chat_id, text=text)

    def run_birthday_check(self) -> None:
        """Выполняет проверку дней рождения (синхронная обертка для asyncio)"""
        try:
            # Создаем новый event loop для каждого запуска
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.send_birthday_messages())
        except Exception as e:
            logger.error(f"Ошибка при выполнении проверки: {e}")
        finally:
            # Закрываем loop корректно
            if "loop" in locals():
                loop.close()

    def start_scheduler(self) -> None:
        """Запускает планировщик для ежедневной проверки дней рождения"""
        # Получаем время из конфига
        _, birthday_time, _ = self.load_config()

        # Планируем ежедневную проверку
        schedule.every().day.at(birthday_time).do(self.run_birthday_check)

        logger.info(
            f"Бот запущен! Проверка дней рождения каждый день в {birthday_time}"
        )
        logger.info("Для остановки нажмите Ctrl+C")

        # Бесконечный цикл проверки расписания
        while True:
            schedule.run_pending()
            time.sleep(SCHEDULE_CHECK_INTERVAL)


def main():
    """Точка входа в приложение"""
    try:
        logger.info("Инициализация бота...")
        bot = BirthdayBot()
        logger.info("Бот успешно инициализирован")

        # Проверяем именинников на сегодня при запуске
        logger.info("Проверяем именинников на сегодня...")
        bot.run_birthday_check()

        # Запускаем планировщик для регулярных проверок
        bot.start_scheduler()

    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)


if __name__ == "__main__":
    main()
