__version__ = (1, 3, 2)
# meta developer: @etopizdesblin

import base64
import io
import mimetypes
import os
import re
import time
import typing

import requests
from PIL import Image
from herokutl.tl.types import Message

from .. import loader, utils


MODELS_URL = "https://api.onlysq.ru/ai/models"
CHAT_URL_OPENAI = "https://api.onlysq.ru/ai/openai/chat/completions"
CHAT_URL_V2 = "https://api.onlysq.ru/ai/v2"
IMAGE_URLS_OPENAI = (
    "https://api.onlysq.ru/ai/openai/images/generations",
    "https://api.onlysq.ru/ai/imagen",
    "https://api.onlysq.ru/ai/v2/imagen",
)
IMAGE_URLS_V2 = (
    "https://api.onlysq.ru/ai/v2/imagen",
    "https://api.onlysq.ru/ai/openai/images/generations",
    "https://api.onlysq.ru/ai/imagen",
)
DEFAULT_TEXT_MODEL = "gpt-4o-mini"
DEFAULT_IMAGE_MODEL = "gpt-image-1-mini"
DEFAULT_API_KEY = "openai"
DEFAULT_API_VERSION = "openai"
PROMPT_DIR_NAME = "prompts"
MAX_IMAGE_BYTES = 1_500_000
MAX_FILE_BYTES = 300_000
MAX_TEXT_CHARS = 400_000
MAX_DISPLAY_CHARS = 900
BUILTIN_PROMPTS = {
    "Short": (
        "Пиши максимально кратко и по делу. "
        "Используй форматирование: заголовки, списки, жирный/курсив, код. "
        "Если есть шаги — нумерованный список. "
        "Если есть данные — список или таблица. "
        "Не выдумывай факты и не добавляй воды."
    )
}


@loader.tds
class NeiroMod(loader.Module):
    """OnlySq AI chat and image tools"""

    strings = {"name": "Neiro"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                "",
                "OnlySq API key (empty = use env ONLYSQ_API_KEY or 'openai')",
                validator=loader.validators.Hidden(loader.validators.String()),
            ),
            loader.ConfigValue(
                "text_model",
                DEFAULT_TEXT_MODEL,
                "Text model for .neiro",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "image_model",
                DEFAULT_IMAGE_MODEL,
                "Image model for .neiro-photo",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "api_version",
                DEFAULT_API_VERSION,
                "API version: openai or v2",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "system_prompt_enabled",
                False,
                "Enable system prompt for .neiro",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "system_prompt_file",
                "",
                "Selected system prompt (builtin:Short or file)",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "system_prompt_entries",
                [],
                "Selected system prompts (builtin/file list)",
                validator=loader.validators.Series(loader.validators.String()),
            ),
            loader.ConfigValue(
                "working_text_models",
                [],
                "Working text models found by .checkmodel",
                validator=loader.validators.Series(loader.validators.String()),
            ),
            loader.ConfigValue(
                "text_models_checked",
                False,
                "Use working_text_models list for .model",
                validator=loader.validators.Boolean(),
            ),
        )

    @staticmethod
    def _prompts_dir() -> str:
        return os.path.normpath(
            os.path.join(utils.get_base_dir(), "..", "modules", PROMPT_DIR_NAME)
        )

    def _list_prompt_files(self) -> typing.List[str]:
        path = self._prompts_dir()
        os.makedirs(path, exist_ok=True)
        files = []
        for entry in os.scandir(path):
            if not entry.is_file():
                continue
            if entry.name.startswith("."):
                continue
            files.append(entry.name)
        return sorted(files, key=str.lower)

    def _list_prompt_entries(self) -> typing.List[typing.Tuple[str, str]]:
        entries = []
        for name in BUILTIN_PROMPTS:
            entries.append((f"builtin:{name}", f"{name}"))
        for filename in self._list_prompt_files():
            entries.append((f"file:{filename}", filename))
        return entries

    @staticmethod
    def _builtin_filename(name: str) -> str:
        return f"{name}.txt"

    def _match_builtin(self, name: str) -> typing.Optional[str]:
        cleaned = name.strip()
        if cleaned.lower().startswith("builtin:"):
            cleaned = cleaned.split(":", 1)[1].strip()
        base = os.path.splitext(cleaned)[0].lower()
        for builtin in BUILTIN_PROMPTS:
            if base == builtin.lower():
                return builtin
        return None

    def _read_builtin_prompt(self, name: str) -> str:
        filename = self._builtin_filename(name)
        path = os.path.join(self._prompts_dir(), filename)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read().strip()
        return BUILTIN_PROMPTS.get(name, "")

    def _write_builtin_prompt(self, name: str, text: str) -> str:
        filename = self._builtin_filename(name)
        return self._save_prompt_text(filename, text)

    def _delete_builtin_prompt(self, name: str) -> None:
        filename = self._builtin_filename(name)
        path = os.path.join(self._prompts_dir(), filename)
        if os.path.isfile(path):
            os.remove(path)

    def _selected_prompt_entries(self) -> typing.List[str]:
        entries = list(self.config["system_prompt_entries"] or [])
        if not entries:
            legacy = (self.config["system_prompt_file"] or "").strip()
            if legacy:
                entries = [legacy]
        return entries

    def _resolve_prompt_entry(self, entry: str) -> str:
        if entry.startswith("builtin:"):
            name = entry.split(":", 1)[1].strip()
            return self._read_builtin_prompt(name)
        if entry.startswith("file:"):
            filename = entry.split(":", 1)[1].strip()
            try:
                return self._read_prompt_file(filename)
            except FileNotFoundError:
                return ""
        try:
            return self._read_prompt_file(entry)
        except FileNotFoundError:
            return ""

    def _read_prompt_file(self, filename: str) -> str:
        path = os.path.join(self._prompts_dir(), filename)
        if not os.path.isfile(path):
            raise FileNotFoundError(filename)
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()

    def _get_system_prompt(self) -> str:
        if not self.config["system_prompt_enabled"]:
            return ""
        entries = self._selected_prompt_entries()
        if not entries:
            return ""
        prompts = []
        for entry in entries:
            text = self._resolve_prompt_entry(entry)
            if text:
                prompts.append(text)
        return "\n\n".join(prompts).strip()

    def _get_api_key(self) -> str:
        key = (self.config["api_key"] or "").strip()
        if key:
            return key
        return (os.environ.get("ONLYSQ_API_KEY") or DEFAULT_API_KEY).strip()

    async def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        def _run():
            session = requests.Session()
            session.trust_env = False
            return session.request(method, url, **kwargs)

        return await utils.run_sync(_run)

    @staticmethod
    def _guess_mime(filename: str, mime: str) -> str:
        if mime:
            return mime
        guess = mimetypes.guess_type(filename)[0]
        return guess or "application/octet-stream"

    @staticmethod
    def _is_image_mime(mime: str) -> bool:
        return mime.startswith("image/")

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "\n...[truncated]"

    @staticmethod
    def _render_inline(text: str) -> str:
        links = []

        def _link_repl(match: re.Match) -> str:
            idx = len(links)
            links.append((match.group(1), match.group(2)))
            return f"@@LINK{idx}@@"

        text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", _link_repl, text)
        text = utils.escape_html(text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)
        text = re.sub(r"~~([^~]+)~~", r"<s>\1</s>", text)
        text = re.sub(r"(?<!\\)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"(?<!\\)_([^_]+)_(?!_)", r"<i>\1</i>", text)
        text = re.sub(r"(?<!\w)'([^'\n]+)'(?!\w)", r"<i>\1</i>", text)

        for idx, (label, url) in enumerate(links):
            safe_label = utils.escape_html(label)
            safe_url = utils.escape_html(url)
            text = text.replace(f"@@LINK{idx}@@", f'<a href="{safe_url}">{safe_label}</a>')

        return text

    def _render_markdown(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\[(?:\d+[,\s-]*)+\]", "", text)
        lines = text.split("\n")
        output = []
        in_code = False
        code_lines: typing.List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code:
                    output.append(
                        "<pre><code>"
                        + utils.escape_html("\n".join(code_lines))
                        + "</code></pre>"
                    )
                    code_lines = []
                    in_code = False
                else:
                    in_code = True
                i += 1
                continue
            if in_code:
                code_lines.append(line)
                i += 1
                continue

            if stripped in ("---", "***", "___"):
                output.append("<code>--------------------</code>")
                i += 1
                continue

            if (
                "|" in line
                and i + 1 < len(lines)
                and re.match(r"^\s*\|?\s*[:-]+\s*\|", lines[i + 1])
            ):
                table_lines = [line, lines[i + 1]]
                i += 2
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                output.append("<pre>" + utils.escape_html("\n".join(table_lines)) + "</pre>")
                continue

            heading_match = re.match(r"^\s*#{1,6}\s+(.*)$", line)
            if heading_match:
                output.append(f"<b>{self._render_inline(heading_match.group(1))}</b>")
                i += 1
                continue

            list_match = re.match(r"^\s*([-*•]|\d+[.)])\s+(.*)$", line)
            if list_match:
                output.append("• " + self._render_inline(list_match.group(2)))
            else:
                output.append(self._render_inline(line))
            i += 1

        if in_code and code_lines:
            output.append(
                "<pre><code>"
                + utils.escape_html("\n".join(code_lines))
                + "</code></pre>"
            )

        return "\n".join(output)

    @staticmethod
    def _strip_reasoning(text: str) -> str:
        if not text:
            return ""
        cleaned = text
        while True:
            start = cleaned.find("<think>")
            if start == -1:
                break
            end = cleaned.find("</think>", start + 7)
            if end == -1:
                cleaned = cleaned[:start]
                break
            cleaned = cleaned[:start] + cleaned[end + 8 :]
        lines = cleaned.splitlines()
        if lines and lines[0].strip().lower().startswith("reasoning"):
            lines = lines[1:]
        return "\n".join(lines).strip()

    def _compress_image(self, raw: bytes, mime: str) -> typing.Tuple[bytes, str]:
        if len(raw) <= MAX_IMAGE_BYTES:
            return raw, mime
        try:
            image = Image.open(io.BytesIO(raw))
        except Exception:
            return raw, mime
        try:
            max_side = 1024
            width, height = image.size
            scale = min(1.0, max_side / max(width, height))
            if scale < 1.0:
                image = image.resize(
                    (int(width * scale), int(height * scale)), Image.LANCZOS
                )
            rgb = image.convert("RGB")
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=70, optimize=True)
            return out.getvalue(), "image/jpeg"
        except Exception:
            return raw, mime

    async def _collect_attachments(
        self, message: typing.Optional[Message], reply: typing.Optional[Message]
    ) -> typing.Tuple[typing.List[dict], typing.List[dict]]:
        images = []
        files = []
        for msg in (message, reply):
            if not msg or not msg.media:
                continue
            try:
                raw = await msg.download_media(bytes)
            except Exception:
                continue
            if not raw:
                continue
            filename = ""
            mime = ""
            if getattr(msg, "file", None):
                filename = msg.file.name or ""
                mime = msg.file.mime_type or ""
            filename = filename or ("photo.jpg" if msg.photo else "file.bin")
            mime = self._guess_mime(filename, mime)
            size = len(raw)

            if msg.photo or self._is_image_mime(mime):
                raw, mime = self._compress_image(raw, mime)
                if not raw:
                    continue
                b64 = base64.b64encode(raw).decode("ascii")
                images.append(
                    {
                        "name": filename,
                        "mime": mime,
                        "size": len(raw),
                        "data_url": f"data:{mime};base64,{b64}",
                    }
                )
            else:
                snippet = raw[:MAX_FILE_BYTES]
                text = snippet.decode("utf-8", errors="replace")
                text = self._truncate_text(text, MAX_TEXT_CHARS)
                truncated = size > MAX_FILE_BYTES
                files.append(
                    {
                        "name": filename,
                        "mime": mime,
                        "size": size,
                        "text": text,
                        "truncated": truncated,
                    }
                )
        return images, files

    @staticmethod
    def _build_files_text(files: typing.List[dict]) -> str:
        parts = []
        for info in files:
            header = f"Файл: {info['name']} ({info['mime']}, {info['size']} bytes)"
            body = info["text"]
            if info.get("truncated"):
                body = body + "\n...[truncated]"
            parts.append(f"{header}\n{body}".strip())
        return "\n\n".join(parts)

    def _build_user_content(
        self,
        prompt: str,
        images: typing.List[dict],
        files: typing.List[dict],
    ) -> typing.Union[str, typing.List[dict]]:
        text = prompt.strip()
        files_text = self._build_files_text(files) if files else ""
        if files_text:
            text = f"{text}\n\n{files_text}".strip()
        if not images:
            return text
        parts = [{"type": "text", "text": text or "Опиши вложение."}]
        for image in images:
            parts.append({"type": "image_url", "image_url": {"url": image["data_url"]}})
        return parts

    def _format_request_block(
        self, prompt: str, images: typing.List[dict], files: typing.List[dict]
    ) -> str:
        safe_prompt = self._truncate_text(prompt.strip() or "—", MAX_DISPLAY_CHARS)
        safe_prompt = utils.escape_html(safe_prompt)
        return f"<blockquote expandable>{safe_prompt}</blockquote>"

    async def _build_photo_prompt(
        self,
        prompt: str,
        images: typing.List[dict],
        files: typing.List[dict],
    ) -> str:
        base = prompt.strip()
        files_text = self._build_files_text(files) if files else ""
        if files_text:
            base = f"{base}\n\n{files_text}".strip()
        if images:
            vision_content = self._build_user_content(
                "Опиши изображения кратко для генерации.", images, []
            )
            try:
                description = await self._request_chat(
                    vision_content,
                    (self.config["text_model"] or DEFAULT_TEXT_MODEL).strip(),
                    system_prompt="",
                )
            except Exception:
                description = ""
            description = self._strip_reasoning(description)
            if description:
                if base:
                    base = f"{base}\n\nРеференсы: {description}".strip()
                else:
                    base = description.strip()
        return base or "Сгенерируй изображение по описанию."

    async def _fetch_models(self) -> dict:
        response = await self._request("GET", MODELS_URL, timeout=20)
        response.raise_for_status()
        return response.json()

    async def _get_model_list(self, modality: str) -> typing.List[str]:
        data = await self._fetch_models()
        classified = data.get("classified", {})
        models = classified.get(modality, [])
        return sorted(models)

    async def _get_text_models(self) -> typing.List[str]:
        if self.config["text_models_checked"]:
            return list(self.config["working_text_models"] or [])
        return await self._get_model_list("text")

    @staticmethod
    def _format_progress_bar(current: int, total: int, width: int = 20) -> str:
        if total <= 0:
            return "[--------------------]"
        ratio = min(max(current / total, 0.0), 1.0)
        filled = int(round(ratio * width))
        return "[" + "#" * filled + "-" * (width - filled) + "]"

    async def _probe_text_model(self, model: str) -> bool:
        try:
            answer = await self._request_chat("ping", model, system_prompt="")
        except Exception:
            return False
        return bool(str(answer or "").strip())

    @staticmethod
    def _format_model_list(models: typing.List[str]) -> str:
        return "\n".join(f"{idx + 1}. {name}" for idx, name in enumerate(models))

    @staticmethod
    def _extract_prompt(
        message: Message,
        reply: typing.Optional[Message],
    ) -> typing.Optional[typing.Tuple[str, str]]:
        args = utils.get_args_raw(message).strip()
        reply_text = reply.raw_text.strip() if reply and reply.raw_text else ""
        if args and reply_text:
            display_prompt = f"{args} | {reply_text}"
            model_prompt = f"{args}\n\nКонтекст: {reply_text}"
            return display_prompt, model_prompt
        if reply_text:
            return reply_text, reply_text
        if args:
            return args, args
        return None

    @staticmethod
    def _sanitize_prompt_filename(name: str) -> str:
        safe = os.path.basename(name.strip())
        if not safe:
            return ""
        if "." not in safe:
            safe = f"{safe}.txt"
        return safe

    def _save_prompt_text(self, filename: str, text: str) -> str:
        os.makedirs(self._prompts_dir(), exist_ok=True)
        safe_name = self._sanitize_prompt_filename(filename)
        if not safe_name:
            safe_name = f"prompt_{int(time.time())}.txt"
        path = os.path.join(self._prompts_dir(), safe_name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.strip() + "\n")
        return safe_name

    async def _get_prompt_attachment(
        self, message: Message, reply: typing.Optional[Message]
    ) -> typing.Optional[typing.Tuple[str, str]]:
        for source in (message, reply):
            if not source or not source.media:
                continue
            try:
                data = await source.download_media(bytes)
            except Exception:
                data = None
            if not data:
                continue
            name = ""
            if getattr(source, "file", None) and getattr(source.file, "name", None):
                name = source.file.name
            else:
                doc = getattr(source, "document", None)
                if doc and getattr(doc, "attributes", None):
                    for attr in doc.attributes:
                        file_name = getattr(attr, "file_name", None)
                        if file_name:
                            name = file_name
                            break
            if not name:
                name = f"prompt_{int(time.time())}.txt"
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("utf-8", errors="replace")
            return name, text
        return None

    def _build_response(self, request_block: str, model: str, answer: str) -> str:
        safe_answer = self._render_markdown(answer)
        return (
            f"{request_block}\n"
            f"<blockquote expandable>{safe_answer}</blockquote>"
        )

    async def _request_chat(
        self,
        content: typing.Union[str, typing.List[dict]],
        model: str,
        system_prompt: typing.Optional[str] = None,
    ) -> str:
        key = self._get_api_key()
        api_version = (self.config["api_version"] or DEFAULT_API_VERSION).lower().strip()
        headers = {"Authorization": f"Bearer {key}"}
        if system_prompt is None:
            system_prompt = self._get_system_prompt()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})

        if api_version == "v2":
            url = CHAT_URL_V2
            payload = {
                "model": model,
                "request": {"messages": messages},
            }
        else:
            url = CHAT_URL_OPENAI
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
            }

        response = await self._request(
            "POST",
            url,
            headers=headers,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message", {})
                content = message.get("content")
                if content is not None:
                    return content
            if data.get("answer"):
                return data["answer"]

        raise ValueError("Empty response")

    async def _generate_image(self, prompt: str, model: str) -> bytes:
        key = self._get_api_key()
        headers = {"Authorization": f"Bearer {key}"}
        api_version = (self.config["api_version"] or DEFAULT_API_VERSION).lower().strip()
        payload = {
            "model": model,
            "prompt": prompt,
            "size": "1024x1024",
            "n": 1,
            "response_format": "b64_json",
        }

        urls = IMAGE_URLS_V2 if api_version == "v2" else IMAGE_URLS_OPENAI
        last_error = None
        for url in urls:
            try:
                response = await self._request(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                    timeout=180,
                )
                if response.status_code == 400 and "response_format" in response.text:
                    retry_payload = dict(payload)
                    retry_payload.pop("response_format", None)
                    response = await self._request(
                        "POST",
                        url,
                        headers=headers,
                        json=retry_payload,
                        timeout=180,
                    )
                response.raise_for_status()
                data = response.json()
                b64 = None
                if isinstance(data, dict):
                    if data.get("data"):
                        b64 = data["data"][0].get("b64_json") or data["data"][0].get("image")
                        if not b64 and data["data"][0].get("url"):
                            url = data["data"][0]["url"]
                            image_resp = await self._request("GET", url, timeout=60)
                            image_resp.raise_for_status()
                            return image_resp.content
                    if not b64 and data.get("image"):
                        b64 = data["image"]
                    if not b64 and data.get("images"):
                        item = data["images"][0]
                        b64 = item.get("b64_json") if isinstance(item, dict) else item
                if not b64:
                    raise ValueError("Empty image response")
                return base64.b64decode(b64)
            except Exception as exc:
                last_error = exc

        raise RuntimeError(str(last_error) if last_error else "Image generation failed")

    @loader.command(ru_doc="Запрос к OnlySq")
    async def neiro(self, message: Message):
        reply = await message.get_reply_message() if message.is_reply else None
        images, files = await self._collect_attachments(message, reply)
        prompt_data = self._extract_prompt(message, reply)
        if not prompt_data:
            if not images and not files:
                await utils.answer(message, "Нужен текст, файл или фото.")
                return
            display_prompt, model_prompt = "", ""
        else:
            display_prompt, model_prompt = prompt_data

        model = (self.config["text_model"] or DEFAULT_TEXT_MODEL).strip()
        request_block = self._format_request_block(display_prompt, images, files)
        content = self._build_user_content(model_prompt, images, files)
        message = await utils.answer(
            message,
            self._build_response(request_block, model, "Думаю..."),
        )
        try:
            answer = await self._request_chat(content, model)
        except Exception as exc:
            await message.edit(f"Ошибка запроса: {utils.escape_html(str(exc))}")
            return

        answer = self._strip_reasoning(answer)
        await message.edit(self._build_response(request_block, model, answer))

    @loader.command(ru_doc="Список моделей или выбор модели")
    async def model(self, message: Message):
        args = utils.get_args_raw(message).strip()
        try:
            models = await self._get_text_models()
        except Exception as exc:
            await utils.answer(message, f"Ошибка списка моделей: {utils.escape_html(str(exc))}")
            return
        if not models:
            if self.config["text_models_checked"]:
                await utils.answer(message, "Список моделей пуст. Запусти .checkmodel.")
            else:
                await utils.answer(message, "Список моделей пуст.")
            return

        if not args:
            await utils.answer(message, self._format_model_list(models))
            return

        try:
            index = int(args)
        except ValueError:
            await utils.answer(message, "Нужен номер модели.")
            return

        if index < 1 or index > len(models):
            await utils.answer(message, "Неверный номер модели.")
            return

        model = models[index - 1]
        self.config["text_model"] = model
        await utils.answer(message, f"Текущая модель: {utils.escape_html(model)}")

    @loader.command(ru_doc="Проверить все текстовые модели и сохранить рабочие")
    async def checkmodel(self, message: Message):
        args = utils.get_args_raw(message).strip().lower()
        if args in {"reset", "clear", "r", "reste"}:
            self.config["working_text_models"] = []
            self.config["text_models_checked"] = False
            await utils.answer(message, "Список рабочих моделей сброшен.")
            return

        msg = await utils.answer(message, "Проверяю модели...")
        try:
            models = await self._get_model_list("text")
        except Exception as exc:
            await msg.edit(f"Ошибка списка моделей: {utils.escape_html(str(exc))}")
            return

        if not models:
            await msg.edit("Список моделей пуст.")
            return

        total = len(models)
        working = []
        last_update = 0.0
        for idx, model in enumerate(models, start=1):
            if await self._probe_text_model(model):
                working.append(model)
            now = time.time()
            if idx == total or idx == 1 or now - last_update > 1.5:
                last_update = now
                bar = self._format_progress_bar(idx, total)
                percent = int(round((idx / total) * 100))
                await msg.edit(
                    "Проверяю модели: {bar} {cur}/{total} ({pct}%)\nРабочих: {ok}".format(
                        bar=bar,
                        cur=idx,
                        total=total,
                        pct=percent,
                        ok=len(working),
                    )
                )

        self.config["working_text_models"] = working
        self.config["text_models_checked"] = True
        bar = self._format_progress_bar(total, total)
        await msg.edit(
            "Готово: {bar} {total}/{total} (100%)\nРабочих: {ok}".format(
                bar=bar,
                total=total,
                ok=len(working),
            )
        )

    @loader.command(aliases=["neiro-photo", "neirophoto"], ru_doc="Генерация изображения OnlySq")
    async def neiro_photo(self, message: Message):
        reply = await message.get_reply_message() if message.is_reply else None
        images, files = await self._collect_attachments(message, reply)
        prompt_data = self._extract_prompt(message, reply)
        if not prompt_data:
            if not images and not files:
                await utils.answer(message, "Нужен текст, файл или фото.")
                return
            display_prompt, model_prompt = "", ""
        else:
            display_prompt, model_prompt = prompt_data

        model = (self.config["image_model"] or DEFAULT_IMAGE_MODEL).strip()
        msg = await utils.answer(message, "Генерирую изображение...")
        try:
            prompt = await self._build_photo_prompt(model_prompt, images, files)
            image_bytes = await self._generate_image(prompt, model)
        except Exception as exc:
            await msg.edit(f"Ошибка запроса: {utils.escape_html(str(exc))}")
            return

        file = io.BytesIO(image_bytes)
        file.name = "neiro.png"
        await utils.answer_file(
            msg,
            file,
            caption=self._format_request_block(display_prompt, images, files),
        )

    @loader.command(aliases=["model-photo", "modelphoto"], ru_doc="Список моделей для генерации")
    async def model_photo(self, message: Message):
        args = utils.get_args_raw(message).strip()
        try:
            models = await self._get_model_list("image")
        except Exception as exc:
            await utils.answer(message, f"Ошибка списка моделей: {utils.escape_html(str(exc))}")
            return
        if not models:
            await utils.answer(message, "Список моделей пуст.")
            return

        if not args:
            await utils.answer(message, self._format_model_list(models))
            return

        try:
            index = int(args)
        except ValueError:
            await utils.answer(message, "Нужен номер модели.")
            return

        if index < 1 or index > len(models):
            await utils.answer(message, "Неверный номер модели.")
            return

        model = models[index - 1]
        self.config["image_model"] = model
        await utils.answer(message, f"Текущая модель: {utils.escape_html(model)}")

    @loader.command(alias="api-ver", ru_doc="Выбор версии API (openai/v2)")
    async def api_ver(self, message: Message):
        args = utils.get_args_raw(message).strip().lower()
        if not args:
            current = (self.config["api_version"] or DEFAULT_API_VERSION).lower()
            await utils.answer(
                message,
                f"Текущая версия API: {utils.escape_html(current)}\nДоступно: openai | v2",
            )
            return

        if args not in ("openai", "v2"):
            await utils.answer(message, "Укажи openai или v2.")
            return

        self.config["api_version"] = args
        await utils.answer(message, f"API версия: {utils.escape_html(args)}")

    @loader.command(ru_doc="Системный промпт для .neiro")
    async def prompt(self, message: Message):
        args_raw = utils.get_args_raw(message).strip()
        if not args_raw:
            enabled = self.config["system_prompt_enabled"]
            selected = self._selected_prompt_entries()
            labels = []
            for key, label in self._list_prompt_entries():
                if key in selected:
                    labels.append(label)
            current = ", ".join(labels) if labels else "—"
            await utils.answer(
                message,
                "Системный промпт: {state}\nФайл: {name}\nПапка: {folder}".format(
                    state="ON" if enabled else "OFF",
                    name=utils.escape_html(current),
                    folder=utils.escape_html(self._prompts_dir()),
                ),
            )
            return

        parts = args_raw.split(maxsplit=1)
        action = parts[0].lower()
        tail = parts[1].strip() if len(parts) > 1 else ""

        if action == "on":
            self.config["system_prompt_enabled"] = True
            current = self._selected_prompt_entries()
            if not current:
                await utils.answer(
                    message,
                    "Системный промпт включен, но файл не выбран. "
                    "Используй .prompt remote",
                )
            else:
                await utils.answer(
                    message,
                    "Системный промпт включен.",
                )
            return

        if action == "off":
            self.config["system_prompt_enabled"] = False
            await utils.answer(message, "Системный промпт выключен.")
            return

        if action == "send":
            reply = await message.get_reply_message() if message.is_reply else None
            attached = await self._get_prompt_attachment(message, reply)
            if attached:
                filename, text = attached
                if tail:
                    override = tail.strip()
                    if override.endswith((".txt", ".md", ".prompt")) or self._match_builtin(override):
                        filename = override
                builtin = self._match_builtin(filename)
                if builtin:
                    saved = self._write_builtin_prompt(builtin, text)
                else:
                    saved = self._save_prompt_text(filename, text)
                await utils.answer(message, f"Промпт сохранен: {utils.escape_html(saved)}")
                return

            reply_text = reply.raw_text.strip() if reply and reply.raw_text else ""
            content = tail or reply_text
            if not content:
                await utils.answer(
                    message,
                    "Нужен текст промпта или файл.",
                )
                return

            filename = ""
            lines = content.splitlines()
            if lines and len(lines) > 1:
                first = lines[0].strip()
                if first.endswith((".txt", ".md", ".prompt")) or self._match_builtin(first):
                    filename = first
                    content = "\n".join(lines[1:]).strip()
            builtin = self._match_builtin(filename or "")
            if builtin:
                saved = self._write_builtin_prompt(builtin, content)
            else:
                saved = self._save_prompt_text(filename, content)
            await utils.answer(message, f"Промпт сохранен: {utils.escape_html(saved)}")
            return

        if action == "get":
            entries = self._list_prompt_entries()
            if not entries:
                await utils.answer(message, "Промптов нет.")
                return
            if not tail:
                listing = "\n".join(
                    f"{idx + 1}. {utils.escape_html(label)}"
                    for idx, (_, label) in enumerate(entries)
                )
                await utils.answer(message, "Промпты:\n" + listing)
                return
            entry_key = ""
            label = ""
            try:
                index = int(tail)
            except ValueError:
                name = tail.strip()
                builtin = self._match_builtin(name)
                if builtin:
                    entry_key = f"builtin:{builtin}"
                    label = builtin
                else:
                    filename = os.path.basename(name)
                    entry_key = f"file:{filename}"
            else:
                if index < 1 or index > len(entries):
                    await utils.answer(message, "Неверный номер промпта.")
                    return
                entry_key, label = entries[index - 1]

            if entry_key.startswith("builtin:"):
                name = entry_key.split(":", 1)[1].strip()
                content = self._read_builtin_prompt(name)
                file = io.BytesIO(content.encode("utf-8"))
                file.name = self._builtin_filename(name)
                await utils.answer_file(message, file)
                return

            filename = entry_key.split(":", 1)[1].strip() if entry_key.startswith("file:") else ""
            files = self._list_prompt_files()
            if filename not in files:
                await utils.answer(message, "Промпт не найден.")
                return
            path = os.path.join(self._prompts_dir(), filename)
            await utils.answer_file(message, path)
            return

        if action == "del":
            entries = self._list_prompt_entries()
            if not entries:
                await utils.answer(message, "Промптов нет.")
                return
            if not tail:
                listing = "\n".join(
                    f"{idx + 1}. {utils.escape_html(label)}"
                    for idx, (_, label) in enumerate(entries)
                )
                await utils.answer(message, "Промпты:\n" + listing)
                return
            entry_key = ""
            label = ""
            try:
                index = int(tail)
            except ValueError:
                name = tail.strip()
                builtin = self._match_builtin(name)
                if builtin:
                    entry_key = f"builtin:{builtin}"
                    label = builtin
                else:
                    filename = os.path.basename(name)
                    entry_key = f"file:{filename}"
            else:
                if index < 1 or index > len(entries):
                    await utils.answer(message, "Неверный номер промпта.")
                    return
                entry_key, label = entries[index - 1]

            selected = self._selected_prompt_entries()
            if entry_key.startswith("builtin:"):
                name = entry_key.split(":", 1)[1].strip()
                try:
                    self._delete_builtin_prompt(name)
                except Exception:
                    await utils.answer(message, "Не удалось удалить промпт.")
                    return
                selected = [item for item in selected if item != entry_key]
                self.config["system_prompt_entries"] = selected
                if not selected:
                    self.config["system_prompt_enabled"] = False
                await utils.answer(message, f"Промпт удален: {utils.escape_html(name)}")
                return

            filename = entry_key.split(":", 1)[1].strip() if entry_key.startswith("file:") else ""
            files = self._list_prompt_files()
            if filename not in files:
                await utils.answer(message, "Промпт не найден.")
                return
            try:
                os.remove(os.path.join(self._prompts_dir(), filename))
            except Exception:
                await utils.answer(message, "Не удалось удалить промпт.")
                return
            selected = [item for item in selected if item != entry_key]
            self.config["system_prompt_entries"] = selected
            if not selected:
                self.config["system_prompt_enabled"] = False
            await utils.answer(message, f"Промпт удален: {utils.escape_html(filename)}")
            return

        if action == "remote":
            entries = self._list_prompt_entries()
            if not entries:
                await utils.answer(
                    message,
                    f"Промптов нет. Положи файлы в {utils.escape_html(self._prompts_dir())}",
                )
                return

            if not tail:
                selected = set(self._selected_prompt_entries())
                listing = []
                for idx, (key, label) in enumerate(entries, start=1):
                    mark = "[x]" if key in selected else "[ ]"
                    listing.append(f"{mark} {idx}. {utils.escape_html(label)}")
                await utils.answer(message, "Доступные промпты:\n" + "\n".join(listing))
                return

            try:
                index = int(tail)
            except ValueError:
                await utils.answer(message, "Нужен номер промпта.")
                return

            if index < 1 or index > len(entries):
                await utils.answer(message, "Неверный номер промпта.")
                return

            selected_key, selected_label = entries[index - 1]
            selected = self._selected_prompt_entries()
            if selected_key in selected:
                selected = [item for item in selected if item != selected_key]
                state = "выключен"
            else:
                selected.append(selected_key)
                state = "включен"
            self.config["system_prompt_entries"] = selected
            self.config["system_prompt_file"] = selected_key if selected else ""
            self.config["system_prompt_enabled"] = True if selected else False
            await utils.answer(
                message,
                f"Промпт {state}: {utils.escape_html(selected_label)}",
            )
            return

        await utils.answer(
            message,
            "Используй: .prompt on | .prompt off | .prompt remote [номер] | .prompt send | .prompt get | .prompt del",
        )
