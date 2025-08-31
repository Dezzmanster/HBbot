import os
import json
import schedule
import time
import asyncio
import logging
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv
from telegram import Bot
from langchain_gigachat.chat_models import GigaChat

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("birthday_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class BirthdayBot:
    def __init__(self):
        logger.debug("Загрузка переменных окружения...")
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.gigachat_credentials = os.getenv("GIGACHAT_CREDENTIALS")
        self.gigachat_scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.gigachat_model = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
        self.default_chat_id = os.getenv("CHAT_ID")

        if not self.bot_token:
            logger.error("TELEGRAM_BOT_TOKEN не найден в .env файле")
            raise ValueError("TELEGRAM_BOT_TOKEN не найден в .env файле")
        if not self.gigachat_credentials:
            logger.error("GIGACHAT_CREDENTIALS не найден в .env файле")
            raise ValueError("GIGACHAT_CREDENTIALS не найден в .env файле")

        # Преобразуем default_chat_id в int, если указан
        if self.default_chat_id:
            try:
                self.default_chat_id = int(self.default_chat_id)
                logger.debug(f"Default chat_id установлен: {self.default_chat_id}")
            except ValueError:
                logger.error("CHAT_ID должен быть числом")
                raise ValueError("CHAT_ID должен быть числом")

        logger.debug("Инициализация Telegram Bot...")
        self.bot = Bot(token=self.bot_token)

        logger.debug("Инициализация GigaChat...")
        self.gigachat = GigaChat(
            credentials=self.gigachat_credentials,
            scope=self.gigachat_scope,
            verify_ssl_certs=False,
            model=self.gigachat_model,
        )

        self.users_config_path = "users_config.json"
        self.prompt_file_path = "birthday_prompt.txt"
        logger.debug("BirthdayBot успешно инициализирован")

    def load_config(self) -> tuple[List[Dict], str, int]:
        """Загружает конфигурацию из JSON файла
        Возвращает кортеж (список пользователей, время отправки, default_chat_id)
        """
        try:
            logger.debug(f"Загрузка конфигурации из {self.users_config_path}")
            with open(self.users_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                users = config.get("users", [])
                birthday_time = config.get("birthday_time", "09:00")
                config_default_chat = config.get("default_chat_id")
                logger.debug(
                    f"Загружено {len(users)} пользователей, время отправки: {birthday_time}"
                )
                return users, birthday_time, config_default_chat
        except FileNotFoundError:
            logger.error(f"Файл {self.users_config_path} не найден")
            return [], "09:00", None
        except json.JSONDecodeError:
            logger.error(f"Ошибка чтения JSON из файла {self.users_config_path}")
            return [], "09:00", None

    def load_birthday_prompt(self) -> str:
        """Загружает промпт для генерации поздравлений"""
        try:
            with open(self.prompt_file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(
                f"Файл {self.prompt_file_path} не найден, используем стандартный промпт"
            )
            return "Поздравь {name} с днем рождения!"

    def get_today_birthdays(self) -> List[Dict]:
        """Возвращает список пользователей, у которых сегодня день рождения"""
        users, _, _ = self.load_config()
        if not users:
            return []

        today = datetime.now().strftime("%d.%m")
        birthday_users = [user for user in users if user.get("birthday") == today]
        return birthday_users

    def generate_birthday_message(self, name: str) -> str:
        """Генерирует поздравление с помощью GigaChat"""
        try:
            prompt_template = self.load_birthday_prompt()
            prompt = prompt_template.format(name=name)

            response = self.gigachat.invoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"Ошибка при генерации поздравления: {e}")
            return f"🎉🎂 Поздравляем {name} с днем рождения! 🌟✨ Желаем крепкого здоровья, безграничного счастья, ярких эмоций и исполнения всех мечт! 🎁💫 Пусть этот день будет наполнен радостью и теплом близких! 🥳💖"

    async def send_birthday_messages(self):
        """Отправляет поздравления всем именинникам"""
        birthday_users = self.get_today_birthdays()

        if not birthday_users:
            logger.info("Сегодня нет именинников")
            return

        # Получаем default_chat_id из конфига
        _, _, config_default_chat = self.load_config()

        for user in birthday_users:
            try:
                name = user.get("name", "Дорогой друг")
                username = user.get("username", "")

                # Определяем chat_id для пользователя
                user_chat_id = user.get("chat_id")
                if not user_chat_id:
                    # Используем default_chat_id из конфига или из .env
                    user_chat_id = config_default_chat or self.default_chat_id

                if not user_chat_id:
                    logger.error(
                        f"Не найден chat_id для пользователя {name}. Укажите chat_id в конфигурации или установите CHAT_ID в .env"
                    )
                    continue

                # Генерируем поздравление
                birthday_message = self.generate_birthday_message(name)

                # Формируем финальное сообщение
                if username:
                    final_message = f"@{username}\n\n{birthday_message}"
                else:
                    final_message = f"{name}\n\n{birthday_message}"

                # Отправляем сообщение с поддержкой Markdown
                try:
                    await self.bot.send_message(
                        chat_id=user_chat_id, text=final_message, parse_mode="Markdown"
                    )
                except Exception as markdown_error:
                    # Если ошибка Markdown, отправляем без разметки
                    logger.warning(
                        f"Ошибка Markdown разметки, отправляем без форматирования: {markdown_error}"
                    )
                    await self.bot.send_message(
                        chat_id=user_chat_id, text=final_message
                    )

                logger.info(f"Поздравление отправлено для {name} в чат {user_chat_id}")

                # Небольшая задержка между сообщениями
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(
                    f"Ошибка при отправке поздравления для {user.get('name', 'Unknown')}: {e}"
                )

    def run_birthday_check(self):
        """Запускает проверку дней рождения (синхронная обертка)"""
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

    def start_scheduler(self):
        """Запускает планировщик для ежедневной проверки"""
        # Получаем время из конфига
        _, birthday_time, _ = self.load_config()

        # Планируем проверку каждый день в указанное время
        schedule.every().day.at(birthday_time).do(self.run_birthday_check)

        logger.info(
            f"Бот запущен! Проверка дней рождения каждый день в {birthday_time}"
        )
        logger.info("Для остановки нажмите Ctrl+C")

        while True:
            schedule.run_pending()
            time.sleep(60)  # Проверяем каждую минуту


def main():
    """Основная функция запуска бота"""
    try:
        logger.info("Инициализация бота...")
        bot = BirthdayBot()
        logger.info("Бот успешно инициализирован")

        # Можно сразу проверить, есть ли сегодня именинники
        logger.info("Проверяем именинников на сегодня...")
        bot.run_birthday_check()

        # Запускаем планировщик
        bot.start_scheduler()

    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)


if __name__ == "__main__":
    main()
