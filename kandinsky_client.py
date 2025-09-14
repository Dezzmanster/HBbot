"""
Клиент для работы с Kandinsky API от Fusion Brain.

Основной функционал:
- Генерация изображений по текстовому описанию
- Отслеживание статуса генерации
- Сохранение результатов
"""

import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple

import aiofiles
import aiohttp

from constants import (
    KANDINSKY_API_URL,
    KANDINSKY_MODEL_ID,
    KANDINSKY_GENERATE_TIMEOUT,
    KANDINSKY_CHECK_TIMEOUT,
    KANDINSKY_MAX_RETRIES,
    KANDINSKY_IMAGE_WIDTH,
    KANDINSKY_IMAGE_HEIGHT,
    KANDINSKY_IMAGES_DIR,
    IMAGE_PROMPT_FILE,
)

logger = logging.getLogger(__name__)


class KandinskyClient:
    """Клиент для работы с Kandinsky API"""

    def __init__(self, api_key: str, secret_key: str):
        """
        Инициализирует клиент Kandinsky

        Args:
            api_key: API ключ для доступа к API (X-Key)
            secret_key: Секретный ключ для доступа к API (X-Secret)
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.api_url = KANDINSKY_API_URL
        self.model_id = KANDINSKY_MODEL_ID
        self.images_dir = Path(KANDINSKY_IMAGES_DIR)

        # Создаем папку для изображений если её нет
        self.images_dir.mkdir(exist_ok=True)

        # Флаг доступности API (будет проверен при первом использовании)
        self._api_available = None

    def _load_image_prompt(self) -> str:
        """
        Загружает промпт для генерации изображений из файла

        Returns:
            Текст промпта
        """
        prompt_file = Path(IMAGE_PROMPT_FILE)

        if not prompt_file.exists():
            logger.warning(f"Файл промпта {prompt_file} не найден")
            return "Создай яркую праздничную картинку для поздравления с днем рождения"

        try:
            return prompt_file.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error(f"Ошибка чтения файла промпта: {e}")
            return "Создай яркую праздничную картинку для поздравления с днем рождения"

    async def _check_api_availability(self) -> bool:
        """
        Проверяет доступность API Kandinsky

        Returns:
            True если API доступно
        """
        if self._api_available is not None:
            return self._api_available

        try:
            async with aiohttp.ClientSession() as session:
                # Сначала проверяем availability эндпоинт (если доступен)
                availability_ok = await self._check_service_availability(session)

                # Проверяем пайплайны независимо от availability
                pipeline_id = await self._get_available_models(session)
                self._api_available = pipeline_id is not None

                if self._api_available:
                    logger.info("✅ API Kandinsky доступно и работает")
                else:
                    logger.warning(
                        "⚠️ API Kandinsky недоступно, изображения не будут генерироваться"
                    )

                return self._api_available

        except Exception as e:
            logger.warning(f"Ошибка проверки API Kandinsky: {e}")
            self._api_available = False
            return False

    async def _check_service_availability(self, session: aiohttp.ClientSession) -> bool:
        """
        Проверяет доступность сервиса через availability эндпоинт

        Returns:
            True если сервис доступен
        """
        try:
            headers = {
                "X-Key": f"Key {self.api_key}",
                "X-Secret": f"Secret {self.secret_key}",
            }

            # Пробуем разные варианты availability эндпоинта
            availability_endpoints = [
                "key/api/v1/text2image/availability",
                "key/api/v1/pipeline/availability",
                "key/api/v1/availability",
            ]

            for endpoint in availability_endpoints:
                try:
                    async with session.get(
                        f"{self.api_url}{endpoint}",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as response:
                        if response.status == 200:
                            try:
                                data = await response.json()
                                is_available = data.get("available", True)
                                logger.debug(
                                    f"Сервис доступен через {endpoint}: {is_available}"
                                )
                                return is_available
                            except:
                                # Даже если JSON некорректный, но статус 200 - считаем доступным
                                logger.debug(
                                    f"Сервис отвечает через {endpoint} (статус 200)"
                                )
                                return True

                except Exception:
                    continue

            # Если ни один availability эндпоинт не работает, это не критично
            logger.debug("Availability эндпоинты недоступны, проверяем модели")
            return True

        except Exception:
            return True  # Не критично если availability не работает

    async def _get_available_models(
        self, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """
        Получает список доступных пайплайнов и возвращает ID первого пайплайна

        Args:
            session: HTTP сессия

        Returns:
            ID пайплайна или None при ошибке
        """
        try:
            headers = {
                "X-Key": f"Key {self.api_key}",
                "X-Secret": f"Secret {self.secret_key}",
            }

            async with session.get(
                f"{self.api_url}key/api/v1/pipelines",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    pipelines = await response.json()
                    logger.debug(f"Доступные пайплайны: {pipelines}")
                    if pipelines and len(pipelines) > 0:
                        pipeline_id = pipelines[0]["id"]
                        logger.info(f"Используем пайплайн с ID: {pipeline_id}")
                        return pipeline_id
                    else:
                        logger.error("Список пайплайнов пуст")
                        return None
                else:
                    error_text = await response.text()
                    logger.debug(
                        f"Пайплайны недоступны: {response.status}, {error_text[:100]}..."
                    )
                    return None

        except Exception as e:
            logger.debug(f"Ошибка при получении пайплайнов: {e}")
            return None

    async def _generate_image_request(
        self, session: aiohttp.ClientSession, prompt: str, pipeline_id: str
    ) -> Optional[str]:
        """
        Отправляет запрос на генерацию изображения

        Args:
            session: HTTP сессия
            prompt: Текстовое описание для генерации
            pipeline_id: ID пайплайна для генерации

        Returns:
            UUID запроса или None при ошибке
        """
        try:
            headers = {
                "X-Key": f"Key {self.api_key}",
                "X-Secret": f"Secret {self.secret_key}",
            }

            # Формируем параметры для генерации
            params = {
                "type": "GENERATE",
                "numImages": 1,
                "width": KANDINSKY_IMAGE_WIDTH,
                "height": KANDINSKY_IMAGE_HEIGHT,
                "generateParams": {"query": prompt},
            }

            # Создаем FormData для multipart/form-data запроса
            form_data = aiohttp.FormData()
            form_data.add_field("pipeline_id", pipeline_id)
            form_data.add_field(
                "params", json.dumps(params), content_type="application/json"
            )

            logger.debug(f"Отправляем запрос с параметрами: {params}")
            logger.debug(f"Используем пайплайн ID: {pipeline_id}")

            async with session.post(
                f"{self.api_url}key/api/v1/pipeline/run",
                headers=headers,
                data=form_data,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                response_text = await response.text()
                logger.debug(f"Ответ API ({response.status}): {response_text}")

                if response.status in [200, 201]:
                    result = await response.json()
                    uuid = result.get("uuid")
                    if uuid:
                        logger.info(f"Запрос на генерацию отправлен, UUID: {uuid}")
                        return uuid
                    else:
                        logger.error("UUID не найден в ответе")
                        return None
                else:
                    logger.error(
                        f"Ошибка генерации: {response.status}, {response_text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Ошибка при отправке запроса генерации: {e}")
            return None

    async def _check_generation_status(
        self, session: aiohttp.ClientSession, uuid: str
    ) -> Optional[str]:
        """
        Проверяет статус генерации изображения

        Args:
            session: HTTP сессия
            uuid: UUID запроса

        Returns:
            Base64 данные изображения или None
        """
        try:
            headers = {
                "X-Key": f"Key {self.api_key}",
                "X-Secret": f"Secret {self.secret_key}",
            }

            async with session.get(
                f"{self.api_url}key/api/v1/pipeline/status/{uuid}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response_text = await response.text()
                logger.debug(f"Статус ответ ({response.status}): {response_text}")

                if response.status == 200:
                    result = await response.json()
                    status = result.get("status")
                    logger.debug(f"Статус генерации: {status}")

                    if status == "DONE":
                        files = result.get("result", {}).get("files", [])
                        if files and len(files) > 0:
                            logger.info("Изображение успешно сгенерировано")
                            return files[0]  # Возвращаем первое изображение
                        else:
                            logger.error("Файлы отсутствуют в ответе")
                            return None
                    elif status == "FAIL":
                        logger.error(f"Генерация завершилась с ошибкой: {result}")
                        return None
                    elif status in ["INITIAL", "PROCESSING"]:
                        logger.debug(f"Статус генерации: {status}, ждем...")
                        return "PROCESSING"
                    else:
                        logger.warning(f"Неизвестный статус: {status}")
                        return None

                else:
                    logger.error(
                        f"Ошибка проверки статуса: {response.status}, {response_text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Ошибка при проверке статуса: {e}")
            return None

    async def _save_image(self, image_data: str, filename: str) -> Optional[Path]:
        """
        Сохраняет изображение из base64 в файл

        Args:
            image_data: Base64 данные изображения
            filename: Имя файла для сохранения

        Returns:
            Путь к сохраненному файлу или None
        """
        try:
            # Декодируем base64
            image_bytes = base64.b64decode(image_data)

            # Формируем путь к файлу
            file_path = self.images_dir / filename

            # Сохраняем файл асинхронно
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(image_bytes)

            logger.info(f"Изображение сохранено: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Ошибка сохранения изображения: {e}")
            return None

    async def generate_birthday_image(self, name: str) -> Optional[Path]:
        """
        Генерирует изображение для поздравления с днем рождения

        Args:
            name: Имя именинника

        Returns:
            Путь к сгенерированному изображению или None при ошибке
        """
        try:
            # Загружаем промпт
            base_prompt = self._load_image_prompt()
            prompt = (
                f"{base_prompt}\n\nИзображение для поздравления {name} с днем рождения."
            )

            logger.info(f"Начинаем генерацию изображения для {name}")

            # Проверяем доступность API
            if not await self._check_api_availability():
                logger.info(
                    "API Kandinsky недоступно, пропускаем генерацию изображения"
                )
                return None

            async with aiohttp.ClientSession() as session:
                # Получаем доступные пайплайны и ID первого пайплайна
                pipeline_id = await self._get_available_models(session)
                if not pipeline_id:
                    logger.error(
                        "API Kandinsky недоступно или нет доступных пайплайнов"
                    )
                    self._api_available = False  # Помечаем API как недоступное
                    return None

                # Отправляем запрос на генерацию
                uuid = await self._generate_image_request(session, prompt, pipeline_id)
                if not uuid:
                    return None

                # Ждем завершения генерации
                start_time = time.time()
                retries = 0

                while retries < KANDINSKY_MAX_RETRIES:
                    if time.time() - start_time > KANDINSKY_GENERATE_TIMEOUT:
                        logger.error("Превышен таймаут генерации")
                        return None

                    result = await self._check_generation_status(session, uuid)

                    if result is None:
                        logger.error("Ошибка при проверке статуса")
                        return None
                    elif result == "PROCESSING":
                        # Продолжаем ждать
                        await asyncio.sleep(KANDINSKY_CHECK_TIMEOUT)
                        retries += 1
                        continue
                    else:
                        # Получили изображение
                        timestamp = int(time.time())
                        filename = f"birthday_{name}_{timestamp}.png"

                        # Убираем небезопасные символы из имени файла
                        safe_filename = "".join(
                            c for c in filename if c.isalnum() or c in "._- "
                        ).strip()

                        return await self._save_image(result, safe_filename)

                logger.error(
                    "Превышено максимальное количество попыток проверки статуса"
                )
                return None

        except Exception as e:
            logger.error(f"Критическая ошибка при генерации изображения: {e}")
            return None

    def cleanup_old_images(self, max_age_days: int = 7) -> None:
        """
        Удаляет старые сгенерированные изображения

        Args:
            max_age_days: Максимальный возраст файлов в днях
        """
        try:
            if not self.images_dir.exists():
                return

            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60

            deleted_count = 0

            for image_file in self.images_dir.glob("*.png"):
                file_age = current_time - image_file.stat().st_mtime

                if file_age > max_age_seconds:
                    try:
                        image_file.unlink()
                        deleted_count += 1
                        logger.debug(f"Удален старый файл: {image_file}")
                    except Exception as e:
                        logger.error(f"Ошибка удаления файла {image_file}: {e}")

            if deleted_count > 0:
                logger.info(f"Удалено старых изображений: {deleted_count}")

        except Exception as e:
            logger.error(f"Ошибка очистки старых изображений: {e}")
