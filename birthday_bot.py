import os
import json
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

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN не найден в .env файле")
        if not self.gigachat_credentials:
            raise ValueError("GIGACHAT_CREDENTIALS не найден в .env файле")

        self.bot = Bot(token=self.bot_token)
        self.gigachat = GigaChat(
            credentials=self.gigachat_credentials,
            scope=self.gigachat_scope,
            verify_ssl_certs=False,
        )

        self.users_config_path = "users_config.json"
        self.prompt_file_path = "birthday_prompt.txt"

    def load_users_config(self) -> List[Dict]:
        """Загружает конфигурацию пользователей из JSON файла"""
        try:
            with open(self.users_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("users", [])
        except FileNotFoundError:
            print(f"Файл {self.users_config_path} не найден")
            return []
        except json.JSONDecodeError:
            print(f"Ошибка чтения JSON из файла {self.users_config_path}")
            return []

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
        users = self.load_users_config()
        today = datetime.now().strftime("%d.%m")

        birthday_users = []
        for user in users:
            if user.get("birthday") == today:
                birthday_users.append(user)

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
            return f"🎉 Поздравляем {name} с днем рождения! Желаем здоровья, счастья и всех благ! 🎂"

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
                chat_id = user.get("chat_id")

                if not chat_id:
                    print(f"Не указан chat_id для пользователя {name}")
                    continue

                # Генерируем поздравление
                birthday_message = self.generate_birthday_message(name)

                # Формируем финальное сообщение
                if username:
                    final_message = f"@{username}\n\n{birthday_message}"
                else:
                    final_message = f"{name}\n\n{birthday_message}"

                # Отправляем сообщение
                await self.bot.send_message(chat_id=chat_id, text=final_message)

                print(f"Поздравление отправлено для {name} в чат {chat_id}")

            except Exception as e:
                print(
                    f"Ошибка при отправке поздравления для {user.get('name', 'Unknown')}: {e}"
                )

    def run_birthday_check(self):
        """Запускает проверку дней рождения (синхронная обертка)"""
        asyncio.run(self.send_birthday_messages())

    def start_scheduler(self):
        """Запускает планировщик для ежедневной проверки"""
        # Планируем проверку каждый день в 9:00
        schedule.every().day.at("09:00").do(self.run_birthday_check)

        print("Бот запущен! Проверка дней рождения каждый день в 9:00")
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
        asyncio.run(bot.send_birthday_messages())

        # Запускаем планировщик
        bot.start_scheduler()

    except KeyboardInterrupt:
        print("\nБот остановлен пользователем")
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")


if __name__ == "__main__":
    main()
