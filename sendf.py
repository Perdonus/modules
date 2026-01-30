__version__ = (1, 0, 1)
# meta developer: @etopizdesblin

import datetime
import hashlib
import hmac
import mimetypes
import os
import secrets
import tempfile
import time
import typing
from pathlib import Path

import requests

from herokutl.types import Message

from .. import loader, utils

LOG_LIMIT = 200
LOG_FILE = Path("/root/Heroku/modules/log.txt")
DEFAULT_TOKEN = "d727b8521bf2aa83d8a2a037b1baaed69d599c55706cd2b4c1391fd059bbb8ec"


@loader.tds
class FileShareMod(loader.Module):
    """Отправка файлов на локальный файловый сервер"""

    strings = {
        "name": "FileShare",
        "no_media": "Нужен файл или медиа.",
        "saved": "Готово: <code>{}</code>",
        "upload_error": "Ошибка загрузки: {}",
        "quota_error": "Не удалось получить лимиты: {}",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "base_url",
                "http://91.233.168.135:5001",
                "Базовый URL файлового сервера",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "upload_token",
                DEFAULT_TOKEN,
                "Токен для загрузки",
                validator=loader.validators.String(),
            ),
        )
        self._logs = None

    async def client_ready(self, client, db):
        logs = self.get("logs", [])
        self._logs = logs if isinstance(logs, list) else []

    def _log(self, text: str) -> None:
        if self._logs is None:
            logs = self.get("logs", [])
            self._logs = logs if isinstance(logs, list) else []
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self._logs.append(f"{timestamp} {text}")
        if len(self._logs) > LOG_LIMIT:
            self._logs = self._logs[-LOG_LIMIT:]
        self.set("logs", self._logs)
        try:
            LOG_FILE.write_text("\n".join(self._logs), encoding="utf-8")
        except Exception:
            pass

    def _render_logs(self) -> str:
        logs = self._logs
        if logs is None:
            logs = self.get("logs", [])
        if not logs:
            return "<blockquote expandable>(пусто)</blockquote>"
        safe_lines = [utils.escape_html(line) for line in logs]
        return "<blockquote expandable>\n" + "\n".join(safe_lines) + "\n</blockquote>"

    @staticmethod
    def _format_bytes(value: int) -> str:
        mb = value / (1024 * 1024)
        if mb >= 10:
            return f"{mb:.0f} MB"
        return f"{mb:.1f} MB"

    def _get_token(self) -> str:
        token = (self.config.get("upload_token") or "").strip()
        if not token:
            token = DEFAULT_TOKEN
        return token

    @staticmethod
    def _sanitize_name(name: str) -> str:
        safe = os.path.basename((name or "").strip())
        if not safe or safe in {".", ".."}:
            return "file.bin"
        return safe

    @staticmethod
    def _guess_filename(message: Message) -> str:
        file_obj = getattr(message, "file", None)
        if file_obj and getattr(file_obj, "name", None):
            return file_obj.name
        doc = getattr(message, "document", None)
        if doc and getattr(doc, "attributes", None):
            for attr in doc.attributes:
                file_name = getattr(attr, "file_name", None)
                if file_name:
                    return file_name
        mime = ""
        if file_obj and getattr(file_obj, "mime_type", None):
            mime = file_obj.mime_type or ""
        ext = mimetypes.guess_extension(mime) or ""
        if message.photo and not ext:
            ext = ".jpg"
        if message.video and not ext:
            ext = ".mp4"
        if message.audio and not ext:
            ext = ".mp3"
        if message.gif and not ext:
            ext = ".mp4"
        return f"file{ext or '.bin'}"

    @staticmethod
    def _has_media(message: Message) -> bool:
        if not message:
            return False
        return bool(
            message.media
            or message.photo
            or message.video
            or message.audio
            or message.document
            or message.file
            or message.gif
        )

    @classmethod
    async def _pick_source(cls, message: Message) -> typing.Optional[Message]:
        if message.is_reply:
            reply = await message.get_reply_message()
            if reply and cls._has_media(reply):
                return reply
        if cls._has_media(message):
            return message
        return None

    @staticmethod
    async def _get_sender_id(message: Message, source: Message) -> int:
        if source:
            try:
                sender = await source.get_sender()
            except Exception:
                sender = None
            if sender and getattr(sender, "id", None):
                return abs(int(sender.id))
            source_id = getattr(source, "sender_id", None)
            if source_id:
                return abs(int(source_id))
            from_id = getattr(source, "from_id", None)
            if from_id:
                for attr in ("user_id", "channel_id", "chat_id"):
                    value = getattr(from_id, attr, None)
                    if value:
                        return abs(int(value))
            source_chat = getattr(source, "chat_id", None)
            if source_chat:
                return abs(int(source_chat))
        sender_id = getattr(message, "sender_id", None)
        if sender_id:
            return abs(int(sender_id))
        me = await message.client.get_me()
        return abs(int(me.id))

    async def _get_command_sender_id(self, message: Message) -> int:
        try:
            sender = await message.get_sender()
            if sender and getattr(sender, "id", None):
                return abs(int(sender.id))
        except Exception:
            pass
        sender_id = getattr(message, "sender_id", None)
        if sender_id:
            return abs(int(sender_id))
        me = await message.client.get_me()
        return abs(int(me.id))

    def _auth_headers(self, method: str, path: str, user_id: int, content_length: int, filename: str, token: str) -> dict:
        ts = str(int(time.time()))
        nonce = secrets.token_hex(8)
        base = "\n".join(
            [
                method,
                path,
                ts,
                nonce,
                str(user_id),
                str(content_length),
                filename or "",
            ]
        ).encode("utf-8")
        sign = hmac.new(token.encode("utf-8"), base, hashlib.sha256).hexdigest()
        headers = {
            "X-Auth-Ts": ts,
            "X-Auth-Nonce": nonce,
            "X-Auth-Sign": sign,
            "X-User-Id": str(user_id),
        }
        if filename:
            headers["X-Filename"] = filename
        return headers

    async def _upload_to_server(self, base_url: str, token: str, file_path: Path, filename: str, user_id: int) -> typing.Tuple[bool, str]:
        upload_url = base_url.rstrip("/") + "/upload"
        content_length = file_path.stat().st_size
        headers = self._auth_headers("POST", "/upload", user_id, content_length, filename, token)
        headers["Content-Type"] = "application/octet-stream"
        headers["Content-Length"] = str(content_length)

        def _run() -> typing.Tuple[bool, str]:
            try:
                with open(file_path, "rb") as handle:
                    resp = requests.post(upload_url, data=handle, headers=headers, timeout=120)
            except Exception as exc:
                return False, f"Request error: {exc}"
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
            try:
                data = resp.json()
            except Exception:
                return False, "Bad JSON response"
            if not data.get("ok") or not data.get("url"):
                return False, "Invalid response"
            return True, str(data.get("url"))

        return await utils.run_sync(_run)

    async def _quota_from_server(self, base_url: str, token: str, user_id: int) -> typing.Tuple[bool, str]:
        quota_url = base_url.rstrip("/") + "/quota"
        headers = self._auth_headers("GET", "/quota", user_id, 0, "", token)

        def _run() -> typing.Tuple[bool, str]:
            try:
                resp = requests.get(quota_url, headers=headers, timeout=20)
            except Exception as exc:
                return False, f"Request error: {exc}"
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
            try:
                data = resp.json()
            except Exception:
                return False, "Bad JSON response"
            if not data.get("ok"):
                return False, "Invalid response"
            return True, data

        return await utils.run_sync(_run)

    @loader.command(ru_doc="Загрузить файл и получить ссылку")
    async def sendf(self, message: Message):
        args = (utils.get_args_raw(message) or "").strip().lower()
        if args in {"log", "logs"}:
            await utils.answer(message, self._render_logs())
            return
        if args in {"check", "quota"}:
            token = self._get_token()
            base_url = (self.config["base_url"] or "").strip() or "http://91.233.168.135:5001"
            user_id = await self._get_command_sender_id(message)
            ok, data = await self._quota_from_server(base_url, token, user_id)
            if not ok:
                await utils.answer(message, self.strings("quota_error").format(utils.escape_html(str(data))))
                return
            used = self._format_bytes(int(data.get("used", 0)))
            limit = self._format_bytes(int(data.get("limit", 0)))
            remaining = self._format_bytes(int(data.get("remaining", 0)))
            reset = int(data.get("reset", 0))
            hours, rem = divmod(reset, 3600)
            minutes, sec = divmod(rem, 60)
            reset_text = f"{hours:02d}:{minutes:02d}:{sec:02d}"
            content = (
                f"Used: {used} / {limit}\n"
                f"Remaining: {remaining}\n"
                f"Reset: {reset_text}"
            )
            await utils.answer(message, f"<blockquote expandable>{utils.escape_html(content)}</blockquote>")
            return

        self._log("start")
        source = await self._pick_source(message)
        if not source:
            self._log("no media")
            await utils.answer(message, self.strings("no_media"))
            return

        token = self._get_token()

        user_id = await self._get_sender_id(message, source)
        self._log(f"user_id={user_id}")

        base_url = (self.config["base_url"] or "").strip() or "http://91.233.168.135:5001"

        filename = self._sanitize_name(self._guess_filename(source))

        tmp_file = tempfile.NamedTemporaryFile(prefix="sendf_", delete=False)
        tmp_path = Path(tmp_file.name)
        tmp_file.close()
        self._log(f"tmp_path={tmp_path}")

        try:
            result = await source.download_media(file=str(tmp_path))
            self._log(f"download result={type(result).__name__}")
        except Exception as exc:
            self._log(f"download error: {exc}")
            await utils.answer(message, self.strings("upload_error").format(utils.escape_html(str(exc))))
            return

        if isinstance(result, (bytes, bytearray)):
            try:
                with open(tmp_path, "wb") as handle:
                    handle.write(result)
                self._log("bytes written")
            except Exception as exc:
                self._log(f"write bytes error: {exc}")
                await utils.answer(message, self.strings("upload_error").format(utils.escape_html(str(exc))))
                return
        elif isinstance(result, str) and result != str(tmp_path):
            try:
                if os.path.exists(result):
                    os.replace(result, tmp_path)
                    self._log("moved result file")
            except Exception as exc:
                self._log(f"move error: {exc}")

        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            try:
                data = await source.download_media(bytes)
            except Exception:
                data = None
            if not data:
                self._log("download empty")
                await utils.answer(message, self.strings("upload_error").format("Файл не скачался."))
                return
            try:
                with open(tmp_path, "wb") as handle:
                    handle.write(data)
                self._log("fallback bytes written")
            except Exception as exc:
                self._log(f"write fallback error: {exc}")
                await utils.answer(message, self.strings("upload_error").format(utils.escape_html(str(exc))))
                return

        try:
            size = tmp_path.stat().st_size
        except Exception:
            size = 0
        self._log(f"size={size}")
        if size <= 0:
            await utils.answer(message, self.strings("upload_error").format("Файл пустой."))
            return

        ok, result = await self._upload_to_server(base_url, token, tmp_path, filename, user_id)

        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

        if not ok:
            self._log(f"upload error: {result}")
            await utils.answer(message, self.strings("upload_error").format(utils.escape_html(result)))
            return

        self._log("done")
        await utils.answer(message, self.strings("saved").format(utils.escape_html(result)))
