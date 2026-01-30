__version__ = (1, 1, 2)
# meta developer: @etopizdesblin

import mimetypes
import os
import typing

from herokutl.tl.types import Message

from .. import loader, utils


MAX_TEXT_FILE_SIZE = 5 * 1024 * 1024
MAX_TEXT_OUTPUT_CHARS = 3800


@loader.tds
class FsMod(loader.Module):
    """Browse filesystem with .ls/.cd/.view"""

    strings = {"name": "FS"}

    def _get_cwd(self) -> str:
        cwd = self.get("cwd") or os.path.expanduser("~")
        if not isinstance(cwd, str) or not cwd:
            cwd = os.path.expanduser("~")
        return os.path.normpath(cwd)

    def _set_cwd(self, path: str) -> None:
        self.set("cwd", path)

    def _resolve_path(self, raw: str) -> str:
        base = self._get_cwd()
        path = (raw or "").strip()
        if not path:
            return base
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isabs(path):
            path = os.path.join(base, path)
        return os.path.normpath(path)

    @staticmethod
    def _human_size(value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _format_listing(self, path: str, entries: typing.List[os.DirEntry]) -> str:
        dirs = []
        files = []
        links = []
        others = []
        for entry in entries:
            try:
                is_link = entry.is_symlink()
            except OSError:
                is_link = False
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            try:
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                is_file = False

            if is_link:
                links.append(entry)
            elif is_dir:
                dirs.append(entry)
            elif is_file:
                files.append(entry)
            else:
                others.append(entry)

        def _sort_key(item: os.DirEntry) -> str:
            return item.name.lower()

        dirs.sort(key=_sort_key)
        files.sort(key=_sort_key)
        links.sort(key=_sort_key)
        others.sort(key=_sort_key)

        lines: typing.List[str] = []
        if dirs:
            lines.append("DIRS:")
            for entry in dirs:
                name = utils.escape_html(entry.name) + "/"
                lines.append(f"- <b>{name}</b>")
            lines.append("")
        if files:
            lines.append("FILES:")
            for entry in files:
                try:
                    size = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    size = 0
                size_text = self._human_size(size)
                name = utils.escape_html(entry.name)
                lines.append(f"- <code>{name}</code> ({size_text})")
            lines.append("")
        if links:
            lines.append("LINKS:")
            for entry in links:
                name = utils.escape_html(entry.name)
                try:
                    target = os.readlink(entry.path)
                    target = utils.escape_html(target)
                    lines.append(f"- <code>{name}</code> -> <code>{target}</code>")
                except OSError:
                    lines.append(f"- <code>{name}</code>")
            lines.append("")
        if others:
            lines.append("OTHER:")
            for entry in others:
                name = utils.escape_html(entry.name)
                lines.append(f"- <code>{name}</code>")
            lines.append("")
        if not lines:
            lines.append("(empty)")

        while lines and lines[-1] == "":
            lines.pop()
        content = "\n".join(lines)
        header = f"<b>Path:</b> <code>{utils.escape_html(path)}</code>"
        return f"{header}\n<blockquote expandable>\n{content}\n</blockquote>"

    @loader.command(ru_doc="Показать содержимое папки")
    async def ls(self, message: Message):
        args = utils.get_args_raw(message).strip()
        path = self._resolve_path(args)
        if not os.path.exists(path):
            await utils.answer(message, "Путь не найден.")
            return
        if not os.path.isdir(path):
            await utils.answer(message, "Это не папка.")
            return
        try:
            entries = list(os.scandir(path))
        except Exception:
            await utils.answer(message, "Не удалось открыть папку.")
            return

        await utils.answer(message, self._format_listing(path, entries))

    @loader.command(ru_doc="Сменить рабочую папку")
    async def cd(self, message: Message):
        args = utils.get_args_raw(message).strip()
        if not args:
            await utils.answer(
                message,
                f"Текущая папка: <code>{utils.escape_html(self._get_cwd())}</code>",
            )
            return
        path = self._resolve_path(args)
        if not os.path.exists(path):
            await utils.answer(message, "Папка не найдена.")
            return
        if not os.path.isdir(path):
            await utils.answer(message, "Это не папка.")
            return
        self._set_cwd(path)
        await utils.answer(
            message,
            f"Текущая папка: <code>{utils.escape_html(path)}</code>",
        )

    @loader.command(ru_doc="Просмотреть файл по пути")
    async def view(self, message: Message):
        args = utils.get_args_raw(message).strip()
        if not args:
            await utils.answer(message, "Нужен путь к файлу.")
            return

        path = self._resolve_path(args)
        if not os.path.exists(path):
            await utils.answer(message, "Файл не найден.")
            return
        if os.path.isdir(path):
            await utils.answer(message, "Это папка. Используй .ls")
            return

        mime, _ = mimetypes.guess_type(path)
        if mime and (mime.startswith("image/") or mime.startswith("video/") or mime.startswith("audio/")):
            await utils.answer_file(
                message,
                path,
                caption=f"<code>{utils.escape_html(path)}</code>",
            )
            return

        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if size > MAX_TEXT_FILE_SIZE:
            await utils.answer(message, "Файл слишком большой для вывода.")
            return

        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except Exception:
            await utils.answer(message, "Не удалось прочитать файл.")
            return

        if b"\x00" in data:
            await utils.answer(message, "Файл не является текстом.")
            return

        text = data.decode("utf-8", errors="replace").strip() or "(пусто)"
        if len(text) > MAX_TEXT_OUTPUT_CHARS:
            await utils.answer(message, "Файл слишком большой для вывода.")
            return
        content = f"<blockquote expandable>{utils.escape_html(text)}</blockquote>"
        header = f"<b>File:</b> <code>{utils.escape_html(path)}</code>"
        await utils.answer(message, f"{header}\n{content}")

    @loader.command(ru_doc="Отправить файл по пути")
    async def getfile(self, message: Message):
        args = utils.get_args_raw(message).strip()
        if not args:
            await utils.answer(message, "Нужен путь к файлу.")
            return

        path = self._resolve_path(args)
        if not os.path.exists(path):
            await utils.answer(message, "Файл не найден.")
            return
        if os.path.isdir(path):
            await utils.answer(message, "Это папка. Используй .ls")
            return

        await utils.answer_file(
            message,
            path,
            caption=f"<code>{utils.escape_html(path)}</code>",
        )

    @loader.command(ru_doc="Создать пустой файл в текущей папке или по пути")
    async def newfile(self, message: Message):
        args_raw = utils.get_args_raw(message)
        if not args_raw:
            await utils.answer(message, "Нужно имя файла в первой строке.")
            return

        name_line, sep, content = args_raw.partition("\n")
        filename = name_line.strip()
        if not filename:
            await utils.answer(message, "Нужно имя файла в первой строке.")
            return

        path = self._resolve_path(filename)
        if os.path.isdir(path):
            await utils.answer(message, "Это папка.")
            return

        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            await utils.answer(message, "Папка не найдена.")
            return

        if os.path.exists(path):
            await utils.answer(message, "Файл уже существует.")
            return

        try:
            with open(path, "x", encoding="utf-8") as handle:
                if sep:
                    handle.write(content)
        except Exception:
            await utils.answer(message, "Не удалось создать файл.")
            return

        await utils.answer(
            message,
            f"Файл создан: <code>{utils.escape_html(path)}</code>",
        )

    @loader.command(ru_doc="Удалить файл в текущей папке или по пути")
    async def delfile(self, message: Message):
        args = utils.get_args_raw(message).strip()
        if not args:
            await utils.answer(message, "Нужен путь к файлу.")
            return

        path = self._resolve_path(args)
        if not os.path.exists(path):
            await utils.answer(message, "Файл не найден.")
            return
        if os.path.isdir(path):
            await utils.answer(message, "Это папка.")
            return

        try:
            os.remove(path)
        except Exception:
            await utils.answer(message, "Не удалось удалить файл.")
            return

        await utils.answer(
            message,
            f"Файл удален: <code>{utils.escape_html(path)}</code>",
        )

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

    @loader.command(ru_doc="Создать папку в текущей директории или по пути")
    async def mkdir(self, message: Message):
        args = utils.get_args_raw(message).strip()
        if not args:
            await utils.answer(message, "Нужно имя папки или путь.")
            return

        path = self._resolve_path(args)
        if os.path.exists(path):
            await utils.answer(message, "Папка уже существует.")
            return

        try:
            os.makedirs(path, exist_ok=False)
        except Exception:
            await utils.answer(message, "Не удалось создать папку.")
            return

        await utils.answer(
            message,
            f"Папка создана: <code>{utils.escape_html(path)}</code>",
        )

    @loader.command(ru_doc="Сохранить файл из сообщения на сервер")
    async def sendfile(self, message: Message):
        source = message
        if message.is_reply:
            reply = await message.get_reply_message()
            if reply and (reply.media or reply.file or reply.document):
                source = reply

        if not (source.media or source.file or source.document or source.photo or source.video):
            await utils.answer(message, "Нужен файл или медиа.")
            return

        args = utils.get_args_raw(message).strip()
        filename = self._guess_filename(source)
        if not filename:
            await utils.answer(message, "Не могу определить имя файла.")
            return

        if args:
            target = self._resolve_path(args)
            if os.path.isdir(target):
                target_path = os.path.join(target, filename)
            else:
                target_path = target
        else:
            target_path = self._resolve_path(filename)

        parent = os.path.dirname(target_path)
        if parent and not os.path.isdir(parent):
            await utils.answer(message, "Папка не найдена.")
            return
        if os.path.exists(target_path):
            await utils.answer(message, "Файл уже существует.")
            return

        try:
            result = await source.download_media(file=str(target_path))
        except Exception:
            await utils.answer(message, "Не удалось скачать файл.")
            return

        if isinstance(result, (bytes, bytearray)):
            try:
                with open(target_path, "wb") as handle:
                    handle.write(result)
            except Exception:
                await utils.answer(message, "Не удалось сохранить файл.")
                return

        if not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
            await utils.answer(message, "Файл не сохранился.")
            return

        await utils.answer(
            message,
            f"Файл сохранён: <code>{utils.escape_html(target_path)}</code>",
        )
