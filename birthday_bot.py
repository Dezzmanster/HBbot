import os
import json

# schedule — это библиотека для планирования периодических задач (job scheduling) в Python.
import schedule
import time
import asyncio
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv
from telegram import Bot
from langchain_gigachat.chat_models import GigaChat

# Загружаем переменные окружения
load_dotenv()


class BirthdayBot:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.gigachat_credentials = os.getenv("GIGACHAT_CREDENTIALS")
        self.gigachat_scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.gigachat_model = os.getenv("GIGACHAT_MODEL", "GigaChat-2")
        self.chat_id = os.getenv("CHAT_ID")

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN не найден в .env файле")
        if not self.gigachat_credentials:
            raise ValueError("GIGACHAT_CREDENTIALS не найден в .env файле")
        if not self.chat_id:
            raise ValueError("CHAT_ID не найден в .env файле")

        # Преобразуем chat_id в int
        try:
            self.chat_id = int(self.chat_id)
        except ValueError:
            raise ValueError("CHAT_ID должен быть числом")

        self.bot = Bot(token=self.bot_token)
        self.gigachat = GigaChat(
            credentials=self.gigachat_credentials,
            scope=self.gigachat_scope,
            verify_ssl_certs=False,
            model=self.gigachat_model,
        )

        self.users_config_path = "users_config.json"
        self.prompt_file_path = "birthday_prompt.txt"

    def load_config(self) -> tuple[List[Dict], str]:
        """Загружает конфигурацию из JSON файла
        Возвращает кортеж (список пользователей, время отправки)
        """
        try:
            with open(self.users_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                users = config.get("users", [])
                birthday_time = config.get("birthday_time", "09:00")
                return users, birthday_time
        except FileNotFoundError:
            print(f"Файл {self.users_config_path} не найден")
            return [], "09:00"
        except json.JSONDecodeError:
            print(f"Ошибка чтения JSON из файла {self.users_config_path}")
            return [], "09:00"

    def load_birthday_prompt(self) -> str:
        """Загружает промпт для генерации поздравлений"""
        try:
            with open(self.prompt_file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            print(f"Файл {self.prompt_file_path} не найден")
            return "Поздравь {name} с днем рождения!"

    def get_today_birthdays(self) -> List[Dict]:
        """Возвращает список пользователей, у которых сегодня день рождения"""
        users, _ = self.load_config()
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
            print(f"Ошибка при генерации поздравления: {e}")
            return f"🎉🎂 Поздравляем {name} с днем рождения! 🌟✨ Желаем крепкого здоровья, безграничного счастья, ярких эмоций и исполнения всех мечт! 🎁💫 Пусть этот день будет наполнен радостью и теплом близких! 🥳💖"

    async def send_birthday_messages(self):
        """Отправляет поздравления всем именинникам"""
        birthday_users = self.get_today_birthdays()

        if not birthday_users:
            print("Сегодня нет именинников")
            return

        for user in birthday_users:
            try:
                name = user.get("name", "Дорогой друг")
                username = user.get("username", "")

                # Генерируем поздравление
                birthday_message = self.generate_birthday_message(name)

                # Формируем финальное сообщение
                if username:
                    final_message = f"@{username}\n\n{birthday_message}"
                else:
                    final_message = f"{name}\n\n{birthday_message}"

                # Отправляем сообщение
                await self.bot.send_message(chat_id=self.chat_id, text=final_message)

                print(f"Поздравление отправлено для {name} в чат {self.chat_id}")

                # Небольшая задержка между сообщениями
                await asyncio.sleep(1)

            except Exception as e:
                print(
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
            print(f"Ошибка при выполнении проверки: {e}")
        finally:
            # Закрываем loop корректно
            if "loop" in locals():
                loop.close()

    def start_scheduler(self):
        """Запускает планировщик для ежедневной проверки"""
        # Получаем время из конфига
        _, birthday_time = self.load_config()

        # Планируем проверку каждый день в указанное время
        schedule.every().day.at(birthday_time).do(self.run_birthday_check)

        print(f"Бот запущен! Проверка дней рождения каждый день в {birthday_time}")
        print("Для остановки нажмите Ctrl+C")

        while True:
            schedule.run_pending()
            time.sleep(60)  # Проверяем каждую минуту


def main():
    """Основная функция запуска бота"""
    try:
        bot = BirthdayBot()

        # Можно сразу проверить, есть ли сегодня именинники
        print("Проверяем именинников на сегодня...")
        bot.run_birthday_check()

        # Запускаем планировщик
        bot.start_scheduler()

    except KeyboardInterrupt:
        print("\nБот остановлен пользователем")
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")


if __name__ == "__main__":
    main()
