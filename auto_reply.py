# meta developer: your_username
# meta pic: https://hikka.userpic/url
# meta banner: https://hikka.banner/url

import json
import os
import sys
from datetime import datetime, timedelta
import httpx
from .. import loader, utils

# Путь к файлу настроек
SETTINGS_FILE = "auto_reply_settings.json"

# URL репозитория и путь к файлу скрипта на GitHub
GITHUB_REPO = "your-username/your-repo"
SCRIPT_PATH = "auto_reply.py"


class AutoReplyMod(loader.Module):
    """Автоответчик с настройкой кулдауна, текста и автоматическим обновлением"""
    strings = {"name": "AutoReply"}

    async def client_ready(self, client, db):
        self.client = client
        self.db = db

        # Загружаем настройки при запуске
        await self._load_settings()

        # Инициализация таймера кулдауна и списка автоответов
        self.cooldown_timers = {}
        self.last_reply_ids = {}

        # Получаем ID текущего аккаунта
        self.my_id = (await self.client.get_me()).id

    async def _load_settings(self):
        """Загрузка настроек из файла"""
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                settings = json.load(f)
                self.cooldown = settings.get("cooldown", 30)
                self.auto_reply_message = settings.get(
                    "auto_reply_message", "Привет! Сейчас я не в сети, отвечу позже."
                )
        else:
            self.cooldown = 30
            self.auto_reply_message = "Привет! Сейчас я не в сети, отвечу позже."
            await self._save_settings()

    async def _save_settings(self):
        """Сохранение настроек в файл"""
        settings = {
            "cooldown": self.cooldown,
            "auto_reply_message": self.auto_reply_message,
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)

    @loader.command()
    async def setcooldown(self, message):
        """Установить время кулдауна (в секундах)"""
        args = utils.get_args_raw(message)
        if not args or not args.isdigit():
            await message.edit("Введите корректное время кулдауна (число в секундах).")
            return
        self.cooldown = int(args)
        await self._save_settings()
        await message.edit(f"Кулдаун успешно установлен на {self.cooldown} секунд.")

    @loader.command()
    async def setmessage(self, message):
        """Установить текст автоответа"""
        args = utils.get_args_raw(message)
        if not args:
            await message.edit("Введите текст автоответа.")
            return
        self.auto_reply_message = args
        await self._save_settings()
        await message.edit("Текст автоответа успешно обновлен.")

    @loader.command()
    async def showsettings(self, message):
        """Показать текущие настройки"""
        await message.edit(
            f"Текущие настройки:\n"
            f"Кулдаун: {self.cooldown} секунд\n"
            f"Текст автоответа: {self.auto_reply_message}"
        )

    @loader.command()
    async def checkupdate(self, message):
        """Проверить и установить обновления скрипта"""
        async with httpx.AsyncClient() as client:
            try:
                # Получаем содержимое файла на GitHub
                url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{SCRIPT_PATH}"
                response = await client.get(url)

                if response.status_code == 200:
                    remote_script = response.text

                    # Сравниваем содержимое с локальным файлом
                    with open(__file__, "r", encoding="utf-8") as local_file:
                        local_script = local_file.read()

                    if remote_script.strip() == local_script.strip():
                        await message.edit("Скрипт обновлен. Обновления не требуются.")
                    else:
                        # Сохраняем новый файл
                        with open(__file__, "w", encoding="utf-8") as local_file:
                            local_file.write(remote_script)

                        await message.edit("Обновление загружено. Перезапускаю скрипт...")

                        # Перезапускаем Hikka
                        os.execl(sys.executable, sys.executable, "-m", "hikka")
                else:
                    await message.edit("Не удалось получить данные с GitHub. Проверьте URL.")
            except Exception as e:
                await message.edit(f"Ошибка при проверке обновлений: {e}")

    async def watcher(self, message):
        """Главный обработчик сообщений"""
        if message.is_private and not (await message.get_sender()).bot:
            user_id = utils.get_chat_id(message)

            # Проверяем, чтобы это не было сообщение от самого владельца аккаунта
            if user_id == self.my_id:
                return

            # Проверяем кулдаун
            now = datetime.now()
            last_reply_time = self.cooldown_timers.get(user_id)
            if last_reply_time and now - last_reply_time < timedelta(seconds=self.cooldown):
                return

            # Удаляем старый автоответ, если он существует
            if user_id in self.last_reply_ids:
                try:
                    await self.client.delete_messages(user_id, self.last_reply_ids[user_id])
                except Exception as e:
                    pass  # Игнорируем ошибки при удалении

            # Отправляем новый автоответ
            reply = await message.reply(self.auto_reply_message)
            self.last_reply_ids[user_id] = reply.id  # Сохраняем ID нового автоответа
            self.cooldown_timers[user_id] = now