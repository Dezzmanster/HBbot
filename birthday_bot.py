import os
import json
import schedule
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv
from langchain_gigachat.chat_models import GigaChat
from telegram.ext import Application

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
    DEFAULT_BIRTHDAY_MESSAGE,
    DEFAULT_BELATED_MESSAGE,
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
        self.belated_prompt_file_path = BELATED_PROMPT_FILE
        self.delivery_tracking_path = DELIVERY_TRACKING_FILE

        # Создаем единый event loop для всего приложения
        self.loop = None

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

    def load_belated_birthday_prompt(self) -> str:
        """
        Загружает промпт для генерации запоздалых поздравлений

        Returns:
            Шаблон промпта для запоздалых поздравлений
        """
        try:
            with open(self.belated_prompt_file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(
                f"Файл {self.belated_prompt_file_path} не найден, используем стандартный промпт"
            )
            return "Поздравь {name} с прошедшим днем рождения! Извинись за опоздание и пожелай всего наилучшего."

    def load_delivery_tracking(self) -> Dict:
        """
        Загружает данные об отправленных поздравлениях

        Returns:
            Словарь с данными об отправленных поздравлениях
        """
        try:
            with open(self.delivery_tracking_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                current_year = datetime.now().year

                # Если год изменился, создаем новую структуру
                if data.get("year") != current_year:
                    logger.info(
                        f"Новый год {current_year}, сбрасываем историю отправок"
                    )
                    return {"year": current_year, "sent_messages": {}}

                return data
        except FileNotFoundError:
            logger.debug(f"Файл {self.delivery_tracking_path} не найден, создаем новый")
            current_year = datetime.now().year
            return {"year": current_year, "sent_messages": {}}
        except json.JSONDecodeError:
            logger.error(f"Ошибка чтения JSON из файла {self.delivery_tracking_path}")
            current_year = datetime.now().year
            return {"year": current_year, "sent_messages": {}}

    def save_delivery_tracking(self, data: Dict) -> None:
        """
        Сохраняет данные об отправленных поздравлениях

        Args:
            data: Словарь с данными для сохранения
        """
        try:
            with open(self.delivery_tracking_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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

    def get_pending_birthdays(self) -> List[Dict]:
        """
        Возвращает список пользователей, которым нужно отправить поздравления
        (в день рождения или в течение 2 дней после)

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
            check_date_str = check_date.strftime(DATE_FORMAT)
            is_belated = days_ago > 0

            # Ищем пользователей с днем рождения в эту дату
            for user in users:
                name = user.get("name", DEFAULT_UNKNOWN_NAME)
                birthday = user.get("birthday")

                if not birthday:
                    continue

                if birthday == check_date_str:
                    # Проверяем, не было ли уже отправлено поздравление
                    if not self.is_message_sent(name, birthday):
                        user_copy = user.copy()
                        user_copy["is_belated"] = is_belated
                        user_copy["days_late"] = days_ago
                        pending_users.append(user_copy)
                        logger.debug(
                            f"Найден неотправленный подарок для {name} ({birthday}), дней назад: {days_ago}"
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

            # Генерируем и отправляем поздравление
            birthday_message = self.generate_birthday_message(name, is_belated)
            final_message = self._format_final_message(username, name, birthday_message)

            await self._send_telegram_message(user_chat_id, final_message)

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

    async def _send_telegram_message(self, chat_id: int, text: str) -> None:
        """
        Отправляет сообщение в Telegram с поддержкой Markdown
        """
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
                read_timeout=30,
                write_timeout=30,
                connect_timeout=30,
                pool_timeout=30,
            )
        except Exception as markdown_error:
            logger.warning(
                f"Ошибка Markdown разметки, отправляем без форматирования: {markdown_error}"
            )
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    read_timeout=30,
                    write_timeout=30,
                    connect_timeout=30,
                    pool_timeout=30,
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


def main():
    """Точка входа в приложение"""
    bot = None
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
    finally:
        if bot:
            bot.cleanup()


if __name__ == "__main__":
    main()
