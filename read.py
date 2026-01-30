__version__ = (1, 0, 2)
# meta developer: @etopizdesblin

import os
import subprocess
import tempfile

from herokutl.tl.types import Message

from .. import loader, utils


MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_OUTPUT_CHARS = 3800


@loader.tds
class ReadMod(loader.Module):
    """Show replied file contents via cat"""

    strings = {"name": "Read"}

    @loader.command(ru_doc="Показать содержимое файла ответом")
    async def read(self, message: Message):
        reply = await message.get_reply_message() if message.is_reply else None
        if not reply or not reply.media:
            await utils.answer(message, "Ответь на файл.")
            return

        size = getattr(getattr(reply, "file", None), "size", None)
        if size and size > MAX_FILE_SIZE:
            await utils.answer(message, "Файл слишком большой.")
            return

        try:
            data = await reply.download_media(bytes)
        except Exception:
            await utils.answer(message, "Не удалось скачать файл.")
            return
        if not data:
            await utils.answer(message, "Файл пустой.")
            return

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp:
                temp.write(data)
                temp_path = temp.name

            result = subprocess.run(
                ["cat", temp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            output = result.stdout
            if result.stderr:
                output = output + b"\n" + result.stderr
            text = output.decode("utf-8", errors="replace")
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

        text = text.strip() or "(пусто)"
        if len(text) > MAX_OUTPUT_CHARS:
            await utils.answer(message, "Файл слишком большой для вывода.")
            return

        await utils.answer(
            message,
            f"<blockquote expandable>{utils.escape_html(text)}</blockquote>",
        )
