"""
Birthday Bot - автоматическая отправка поздравлений с днем рождения в Telegram.

Функционал:
- Отправка поздравлений в день рождения
- Отслеживание отправленных сообщений
- Повторная отправка в случае неудачи (в течение 2 дней)
- Генерация персонализированных поздравлений с помощью GigaChat
"""

import asyncio
import json
import logging
import os
import schedule
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_gigachat.chat_models import GigaChat
from telegram.ext import Application

# Импортируем Kandinsky клиент
from kandinsky_client import KandinskyClient

# Импортируем константы
from constants import (
    LOG_FILE,
    LOG_FORMAT,
    USERS_CONFIG_FILE,
    PROMPT_FILE,
    BELATED_PROMPT_FILE,
    DELIVERY_TRACKING_FILE,
    DEFAULT_BIRTHDAY_TIME,
    DEFAULT_USER_NAME,
    DEFAULT_UNKNOWN_NAME,
    DATE_FORMAT,
    MESSAGE_DELAY,
    SCHEDULE_CHECK_INTERVAL,
    RETRY_DAYS,
    TELEGRAM_READ_TIMEOUT,
    TELEGRAM_WRITE_TIMEOUT,
    TELEGRAM_CONNECT_TIMEOUT,
    TELEGRAM_POOL_TIMEOUT,
    DEFAULT_BIRTHDAY_MESSAGE,
    DEFAULT_BELATED_MESSAGE,
)

# Загружаем переменные окружения
load_dotenv()

# Определяем типы данных для улучшения читаемости кода
UserConfig = Dict[str, Any]
UserData = Dict[str, Any]
TrackingData = Dict[str, Any]


def setup_logging() -> logging.Logger:
    """
    Настраивает систему логирования для бота.

    Returns:
        Настроенный логгер
    """
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
    """
    Телеграм бот для автоматической отправки поздравлений с днем рождения.

    Основной функционал:
    - Отправка поздравлений в день рождения
    - Отслеживание доставки сообщений
    - Повторная отправка при неудаче
    - Генерация персонализированных поздравлений
    """

    def __init__(self) -> None:
        """Инициализирует бота с необходимыми сервисами и конфигурацией."""
        logger.debug("Инициализация BirthdayBot...")

        # Настройка путей к файлам
        self._setup_file_paths()

        # Загрузка переменных окружения и инициализация сервисов
        self._load_environment_variables()
        self._initialize_services()

        # Event loop для async операций
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        logger.debug("BirthdayBot успешно инициализирован")

    def _setup_file_paths(self) -> None:
        """Настраивает пути к файлам конфигурации."""
        self.users_config_path = Path(USERS_CONFIG_FILE)
        self.prompt_file_path = Path(PROMPT_FILE)
        self.belated_prompt_file_path = Path(BELATED_PROMPT_FILE)
        self.delivery_tracking_path = Path(DELIVERY_TRACKING_FILE)

    def _load_environment_variables(self) -> None:
        """Загружает и валидирует переменные окружения"""
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.gigachat_credentials = os.getenv("GIGACHAT_CREDENTIALS")
        self.gigachat_scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.gigachat_model = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
        self.kandinsky_api_key = os.getenv("KANDINSKY_API_KEY")
        self.kandinsky_secret_key = os.getenv("KANDINSKY_SECRET_KEY")
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
        """Инициализирует внешние сервисы (Telegram Bot, GigaChat и Kandinsky)"""
        logger.debug("Инициализация Telegram Bot...")

        # Создаем Application с настройками пула соединений
        self.application = Application.builder().token(self.bot_token).build()
        self.bot = self.application.bot

        logger.debug("Инициализация GigaChat...")
        self.gigachat = GigaChat(
            credentials=self.gigachat_credentials,
            scope=self.gigachat_scope,
            verify_ssl_certs=False,
            model=self.gigachat_model,
        )

        # Инициализируем Kandinsky клиент если ключи указаны
        if self.kandinsky_api_key and self.kandinsky_secret_key:
            logger.debug("Инициализация Kandinsky...")
            self.kandinsky_client = KandinskyClient(
                self.kandinsky_api_key, self.kandinsky_secret_key
            )
        else:
            logger.warning(
                "KANDINSKY_API_KEY или KANDINSKY_SECRET_KEY не найдены, генерация изображений отключена"
            )
            self.kandinsky_client = None

    def load_config(self) -> Tuple[List[Dict], str, Optional[int]]:
        """
        Загружает конфигурацию пользователей из JSON файла.

        Returns:
            Кортеж (список пользователей, время отправки, default_chat_id)
        """
        if not self.users_config_path.exists():
            logger.error(f"Файл конфигурации {self.users_config_path} не найден")
            return [], DEFAULT_BIRTHDAY_TIME, None

        try:
            logger.debug(f"Загрузка конфигурации из {self.users_config_path}")
            config = json.loads(self.users_config_path.read_text(encoding="utf-8"))

            users = config.get("users", [])
            birthday_time = config.get("birthday_time", DEFAULT_BIRTHDAY_TIME)
            config_default_chat = config.get("default_chat_id")

            logger.debug(
                f"Загружено {len(users)} пользователей, время отправки: {birthday_time}"
            )
            return users, birthday_time, config_default_chat

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON в {self.users_config_path}: {e}")
            return [], DEFAULT_BIRTHDAY_TIME, None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при загрузке конфигурации: {e}")
            return [], DEFAULT_BIRTHDAY_TIME, None

    def _load_prompt_file(self, file_path: Path, default_prompt: str) -> str:
        """
        Универсальный метод для загрузки промпта из файла.

        Args:
            file_path: Путь к файлу промпта
            default_prompt: Промпт по умолчанию при отсутствии файла

        Returns:
            Содержимое промпта
        """
        if not file_path.exists():
            logger.warning(f"Файл {file_path} не найден, используем стандартный промпт")
            return default_prompt

        try:
            return file_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return default_prompt

    def load_birthday_prompt(self) -> str:
        """
        Загружает промпт для генерации обычных поздравлений.

        Returns:
            Шаблон промпта для GigaChat
        """
        return self._load_prompt_file(
            self.prompt_file_path, "Поздравь {name} с днем рождения!"
        )

    def load_belated_birthday_prompt(self) -> str:
        """
        Загружает промпт для генерации запоздалых поздравлений.

        Returns:
            Шаблон промпта для запоздалых поздравлений
        """
        default_prompt = (
            "Поздравь {name} с прошедшим днем рождения! "
            "Извинись за опоздание и пожелай всего наилучшего."
        )
        return self._load_prompt_file(self.belated_prompt_file_path, default_prompt)

    def _create_empty_tracking_data(self) -> Dict:
        """Создает пустую структуру данных отслеживания для текущего года."""
        current_year = datetime.now().year
        return {"year": current_year, "sent_messages": {}}

    def load_delivery_tracking(self) -> Dict:
        """
        Загружает данные об отправленных поздравлениях.

        Returns:
            Словарь с данными об отправленных поздравлениях
        """
        if not self.delivery_tracking_path.exists():
            logger.debug("Файл отслеживания не найден, создаем новую структуру")
            return self._create_empty_tracking_data()

        try:
            data = json.loads(self.delivery_tracking_path.read_text(encoding="utf-8"))
            current_year = datetime.now().year

            # Если год изменился, создаем новую структуру
            if data.get("year") != current_year:
                logger.info(f"Новый год {current_year}, сбрасываем историю отправок")
                return self._create_empty_tracking_data()

            return data

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON в {self.delivery_tracking_path}: {e}")
            return self._create_empty_tracking_data()
        except Exception as e:
            logger.error(f"Неожиданная ошибка при загрузке отслеживания: {e}")
            return self._create_empty_tracking_data()

    def save_delivery_tracking(self, data: Dict) -> None:
        """
        Сохраняет данные об отправленных поздравлениях.

        Args:
            data: Словарь с данными для сохранения
        """
        try:
            self.delivery_tracking_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.debug("Данные отслеживания отправки сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения данных отслеживания: {e}")

    def mark_message_sent(
        self, user_name: str, birthday: str, is_belated: bool = False
    ) -> None:
        """
        Отмечает сообщение как отправленное

        Args:
            user_name: Имя пользователя
            birthday: Дата рождения в формате DD.MM
            is_belated: Флаг запоздалого поздравления
        """
        tracking_data = self.load_delivery_tracking()
        sent_date = datetime.now().strftime("%Y-%m-%d")

        if birthday not in tracking_data["sent_messages"]:
            tracking_data["sent_messages"][birthday] = {}

        tracking_data["sent_messages"][birthday][user_name] = {
            "birthday": birthday,
            "sent": True,
            "sent_date": sent_date,
            "is_belated": is_belated,
            "attempts": tracking_data["sent_messages"][birthday]
            .get(user_name, {})
            .get("attempts", 0)
            + 1,
        }

        self.save_delivery_tracking(tracking_data)
        logger.info(
            f"Отправка поздравления для {user_name} ({birthday}) отмечена как выполненная"
        )

    def is_message_sent(self, user_name: str, birthday: str) -> bool:
        """
        Проверяет, было ли отправлено поздравление для пользователя

        Args:
            user_name: Имя пользователя
            birthday: Дата рождения в формате DD.MM

        Returns:
            True, если поздравление было отправлено
        """
        tracking_data = self.load_delivery_tracking()
        return (
            birthday in tracking_data["sent_messages"]
            and user_name in tracking_data["sent_messages"][birthday]
            and tracking_data["sent_messages"][birthday][user_name].get("sent", False)
        )

    def _is_birthday_match(self, birthday: str, check_date: datetime) -> bool:
        """
        Проверяет, совпадает ли день рождения с проверяемой датой.

        Args:
            birthday: День рождения в формате DD.MM
            check_date: Дата для проверки

        Returns:
            True, если даты совпадают
        """
        if not birthday:
            return False
        return birthday == check_date.strftime(DATE_FORMAT)

    def _create_pending_user(self, user: Dict, days_ago: int) -> Dict:
        """
        Создает объект пользователя с информацией о запоздании.

        Args:
            user: Исходные данные пользователя
            days_ago: Количество дней назад был день рождения

        Returns:
            Обновленный объект пользователя
        """
        user_copy = user.copy()
        user_copy["is_belated"] = days_ago > 0
        user_copy["days_late"] = days_ago
        return user_copy

    def get_pending_birthdays(self) -> List[Dict]:
        """
        Возвращает список пользователей, которым нужно отправить поздравления.
        Проверяет дни рождения за последние RETRY_DAYS дней (включая сегодня).

        Returns:
            Список словарей с данными пользователей и флагом is_belated
        """
        users, _, _ = self.load_config()
        if not users:
            return []

        pending_users = []
        current_date = datetime.now()

        # Проверяем последние RETRY_DAYS + 1 день (включая сегодня)
        for days_ago in range(RETRY_DAYS + 1):
            check_date = current_date - timedelta(days=days_ago)

            for user in users:
                name = user.get("name", DEFAULT_UNKNOWN_NAME)
                birthday = user.get("birthday")

                if self._is_birthday_match(birthday, check_date):
                    # Проверяем, не было ли уже отправлено поздравление
                    if not self.is_message_sent(name, birthday):
                        pending_user = self._create_pending_user(user, days_ago)
                        pending_users.append(pending_user)

                        logger.debug(
                            f"Найден неотправленный подарок для {name} ({birthday}), "
                            f"дней назад: {days_ago}"
                        )

        logger.info(f"Найдено неотправленных поздравлений: {len(pending_users)}")
        return pending_users

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

    def generate_birthday_message(self, name: str, is_belated: bool = False) -> str:
        """
        Генерирует персонализированное поздравление с помощью GigaChat

        Args:
            name: Имя именинника
            is_belated: Флаг запоздалого поздравления

        Returns:
            Текст поздравления
        """
        try:
            # Выбираем подходящий промпт в зависимости от типа поздравления
            if is_belated:
                prompt_template = self.load_belated_birthday_prompt()
            else:
                prompt_template = self.load_birthday_prompt()

            prompt = prompt_template.format(name=name)

            response = self.gigachat.invoke(prompt)
            return response.content

        except Exception as e:
            logger.error(f"Ошибка при генерации поздравления: {e}")
            # Возвращаем красивое стандартное поздравление при ошибке
            if is_belated:
                return DEFAULT_BELATED_MESSAGE.format(name=name)
            else:
                return DEFAULT_BIRTHDAY_MESSAGE.format(name=name)

    async def generate_birthday_image(self, name: str) -> Optional[Path]:
        """
        Генерирует изображение для поздравления с днем рождения

        Args:
            name: Имя именинника

        Returns:
            Путь к сгенерированному изображению или None при ошибке
        """
        if not self.kandinsky_client:
            logger.info(
                "Kandinsky клиент не инициализирован, изображение не будет сгенерировано"
            )
            return None

        try:
            logger.info(f"Генерируем изображение для {name}...")
            image_path = await self.kandinsky_client.generate_birthday_image(name)

            if image_path:
                logger.info(f"Изображение успешно сгенерировано: {image_path}")
            else:
                logger.warning(f"Не удалось сгенерировать изображение для {name}")

            return image_path

        except Exception as e:
            logger.error(f"Ошибка при генерации изображения для {name}: {e}")
            return None

    async def send_birthday_messages(self) -> None:
        """Отправляет поздравления всем именинникам (включая запоздалые)"""
        pending_users = self.get_pending_birthdays()

        if not pending_users:
            logger.info("Нет неотправленных поздравлений")
            return

        # Загружаем конфигурацию для получения default_chat_id
        _, _, config_default_chat = self.load_config()

        for user in pending_users:
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
            birthday = user.get("birthday")
            is_belated = user.get("is_belated", False)
            days_late = user.get("days_late", 0)

            # Определяем chat_id для отправки сообщения
            user_chat_id = self._get_chat_id_for_user(user, config_default_chat, name)
            if not user_chat_id:
                return

            # Генерируем изображение (если возможно)
            image_path = await self.generate_birthday_image(name)

            # Генерируем и отправляем поздравление
            birthday_message = self.generate_birthday_message(name, is_belated)
            final_message = self._format_final_message(username, name, birthday_message)

            await self._send_telegram_message(user_chat_id, final_message, image_path)

            # Отмечаем сообщение как отправленное
            self.mark_message_sent(name, birthday, is_belated)

            status_msg = "запоздалое поздравление" if is_belated else "поздравление"
            if is_belated:
                logger.info(
                    f"{status_msg} отправлено для {name} в чат {user_chat_id} (опоздание: {days_late} дн.)"
                )
            else:
                logger.info(f"{status_msg} отправлено для {name} в чат {user_chat_id}")

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

    async def _send_telegram_message(
        self, chat_id: int, text: str, image_path: Optional[Path] = None
    ) -> None:
        """
        Отправляет сообщение в Telegram с поддержкой Markdown, изображений и fallback без форматирования.

        Args:
            chat_id: ID чата для отправки
            text: Текст сообщения
            image_path: Путь к изображению для отправки (опционально)

        Raises:
            Exception: При критической ошибке отправки
        """
        timeout_kwargs = {
            "read_timeout": TELEGRAM_READ_TIMEOUT,
            "write_timeout": TELEGRAM_WRITE_TIMEOUT,
            "connect_timeout": TELEGRAM_CONNECT_TIMEOUT,
            "pool_timeout": TELEGRAM_POOL_TIMEOUT,
        }

        try:
            # Если есть изображение, отправляем его вместе с текстом
            if image_path and image_path.exists():
                try:
                    with open(image_path, "rb") as photo:
                        await self.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=text,
                            parse_mode="Markdown",
                            **timeout_kwargs,
                        )
                    logger.debug(f"Сообщение с изображением отправлено в чат {chat_id}")
                    return
                except Exception as photo_error:
                    logger.warning(
                        f"Ошибка отправки изображения, отправляем только текст: {photo_error}"
                    )
                    # Продолжаем с отправкой только текста

            # Попытка отправки с Markdown форматированием
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                **timeout_kwargs,
            )
        except Exception as markdown_error:
            logger.warning(
                f"Ошибка Markdown разметки, отправляем без форматирования: {markdown_error}"
            )
            try:
                # Fallback: отправка без форматирования
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    **timeout_kwargs,
                )
            except Exception as send_error:
                logger.error(f"Критическая ошибка отправки сообщения: {send_error}")
                raise

    def run_birthday_check(self) -> None:
        """Выполняет проверку дней рождения (синхронная обертка для asyncio)"""
        try:
            # Используем существующий event loop или создаем новый
            if self.loop is None or self.loop.is_closed():
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)

            # Инициализируем Application если еще не сделали
            if not self.application.running:
                self.loop.run_until_complete(self.application.initialize())

            self.loop.run_until_complete(self.send_birthday_messages())

        except Exception as e:
            logger.error(f"Ошибка при выполнении проверки: {e}")

    def cleanup(self) -> None:
        """Очищает ресурсы при завершении работы"""
        try:
            # Очищаем старые изображения
            if self.kandinsky_client:
                logger.debug("Очистка старых изображений...")
                self.kandinsky_client.cleanup_old_images()

            if self.application.running:
                self.loop.run_until_complete(self.application.shutdown())
            if self.loop and not self.loop.is_closed():
                self.loop.close()
        except Exception as e:
            logger.error(f"Ошибка при очистке ресурсов: {e}")

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


def main() -> None:
    """Точка входа в приложение."""
    bot: Optional[BirthdayBot] = None

    try:
        logger.info("Инициализация бота...")
        bot = BirthdayBot()
        logger.info("Бот успешно инициализирован")

        # Проверяем именинников при запуске
        logger.info("Проверяем неотправленные поздравления...")
        bot.run_birthday_check()

        # Запускаем планировщик для регулярных проверок
        logger.info("Запуск планировщика...")
        bot.start_scheduler()

    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        raise
    finally:
        if bot:
            logger.info("Очистка ресурсов...")
            bot.cleanup()


if __name__ == "__main__":
    main()
