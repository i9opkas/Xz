import asyncio
import json
import os
import requests
from datetime import datetime, timedelta
from .. import loader, utils

SETTINGS_FILE = "auto_reply_settings.json"
# Текущая версия проекта
CURRENT_VERSION = "1.2.0"

class AutoReplyMod(loader.Module):
    """(Version 1.2.0) Модуль на автоответчик с автообновлением и проверкой версии"""
    strings = {
        "name": "AutoReply",
        "current_settings": "Текущие настройки:",
        "cooldown_label": "Кулдаун: ",
        "message_label": "Текст автоответа: ",
        "change_cooldown": "Установить кулдаун",
        "change_message": "Установить текст ",
        "cooldown_instruction": "Укажите кулдаун в секундах. Например: `.setcooldown 60` для установки кулдауна в 60 секунд.",
        "message_instruction": "Укажите текст автоответа. Например: `.setmessage Привет, я не в сети сейчас не могу ответить`.",
        "manual_check_version": "Вручную проверяем обновления..."
    }

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self.cooldown_timers = {}
        self.last_reply_ids = {}
        await self._load_settings()
        me = await self.client.get_me()
        self.my_id = me.id
        self.is_online = False  # Флаг статуса аккаунта

        # Запускаем проверку версии
        await self.check_version()

        # Запускаем автообновление в фоне
        self.client.loop.create_task(self.periodic_update())

    async def _load_settings(self):
        """Загрузка настроек из файла"""
        self.cooldown = 30
        self.auto_reply_message = "Привет! Сейчас я не в сети, отвечу позже."
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    settings = json.load(f)
                    self.cooldown = settings.get("cooldown", self.cooldown)
                    self.auto_reply_message = settings.get("auto_reply_message", self.auto_reply_message)
            except (json.JSONDecodeError, ValueError):
                await self._save_settings()
        else:
            await self._save_settings()

    async def _save_settings(self):
        """Сохранение настроек в файл"""
        settings = {"cooldown": self.cooldown, "auto_reply_message": self.auto_reply_message}
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)

    @loader.command(ru_doc="Установить время кулдауна (в секундах).\nПример: `.setcooldown 60`")
    async def setcooldown(self, message):
        """Устанавливает кулдаун между автоответами"""
        args = utils.get_args_raw(message)
        if not args or not args.isdigit():
            await message.edit(self.strings["cooldown_instruction"])
            return
        self.cooldown = int(args)
        await self._save_settings()
        await message.edit(f"Кулдаун успешно установлен на {self.cooldown} секунд.")

    @loader.command(ru_doc="Установить текст автоответа.\nПример: `.setmessage Привет, я не в сети`")
    async def setmessage(self, message):
        """Устанавливает текст для автоответов"""
        args = utils.get_args_raw(message)
        if not args:
            await message.edit(self.strings["message_instruction"])
            return
        self.auto_reply_message = args
        await self._save_settings()
        await message.edit("Текст автоответа успешно обновлен.")

    @loader.command(ru_doc="Показать текущие настройки автоответчика")
    async def showsettings(self, message):
        """Отображает текущие настройки автоответчика"""
        await message.edit(
            f"{self.strings['current_settings']}\n"
            f"{self.strings['cooldown_label']} {self.cooldown} секунд\n"
            f"{self.strings['message_label']} {self.auto_reply_message}"
        )

    @loader.command(ru_doc="Проверить доступность новой версии вручную")
    async def check_version_manual(self, message):
        """Команда для ручной проверки версии"""
        await message.edit(self.strings["manual_check_version"])
        await self.check_version()

    async def set_offline(self):
        """Сбрасывает статус аккаунта в оффлайн через 30 секунд после отправки сообщения"""
        await asyncio.sleep(30)  # 30 секунд
        self.is_online = False
        print("[Статус] Аккаунт теперь оффлайн.")

    async def watcher(self, message):
        """Главный обработчик сообщений"""
        if message.is_private:
            sender = await message.get_sender()
            user_id = sender.id
            if user_id == self.my_id:  # Пропускаем сообщения от самого себя
                return

            # Удаляем старый автоответ, если он существует
            if user_id in self.last_reply_ids:
                try:
                    await self.client.delete_messages(self.my_id, self.last_reply_ids[user_id])
                    del self.last_reply_ids[user_id]
                except Exception as e:
                    print(f"Ошибка при удалении старого автоответа для {user_id}: {e}")

            now = datetime.now()
            last_reply_time = self.cooldown_timers.get(user_id)
            if last_reply_time and now - last_reply_time < timedelta(seconds=self.cooldown):
                return

            if not self.is_online:
                reply = await message.reply(self.auto_reply_message)
                self.last_reply_ids[user_id] = reply.id
                self.cooldown_timers[user_id] = now

    async def client_outgoing_message(self, message):
        if message.sender.id == self.my_id:
            self.is_online = True
            await self.set_offline()

    async def check_version(self):
        """Проверяет текущую версию на наличие обновлений"""
        try:
            response = requests.get('https://api.github.com/repos/i9opkas/Xz/releases/latest')
            data = response.json()
            latest_version = data.get("tag_name", None)

            if not latest_version:
                print("Не удалось найти 'tag_name' в ответе GitHub API.")
                return

            if latest_version != CURRENT_VERSION:
                await self.handle_update(latest_version)
        except Exception as e:
            print(f"Ошибка при проверке версии: {e}")

    async def handle_update(self, latest_version):
        """Обрабатывает обновление, если версия изменена"""
        try:
            url = f"https://raw.githubusercontent.com/i9opkas/Xz/main/auto_reply.py"
            response = requests.get(url)
            if response.status_code == 200:
                with open(__file__, "w") as f:
                    f.write(response.text)
                await self.client.send_message(self.my_id, f"Новая версия ({latest_version}) установлена. Перезапустите Хикку для применения.")
            else:
                await self.client.send_message(self.my_id, f"Не удалось скачать обновление.")
        except Exception as e:
            print(f"Ошибка при обновлении: {e}")

    async def periodic_update(self):
        while True:
            await asyncio.sleep(3600)
            await self.check_version()

    async def main(self):
        with self.client:
            self.client.loop.run_until_complete(self.client.start())
            self.client.loop.run_forever()
