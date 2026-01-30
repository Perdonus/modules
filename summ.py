__version__ = (1, 0, 1)
# meta developer: @etopizdesblin

import os
import re
import typing

import requests
from herokutl.tl.types import Message

from .. import loader, utils


MODELS_URL = "https://api.onlysq.ru/ai/models"
CHAT_URL_OPENAI = "https://api.onlysq.ru/ai/openai/chat/completions"
CHAT_URL_V2 = "https://api.onlysq.ru/ai/v2"
DEFAULT_TEXT_MODEL = "gpt-4o-mini"
DEFAULT_API_KEY = "openai"
DEFAULT_API_VERSION = "openai"
MAX_SUMM_MESSAGES = 20_000
MAX_TEXT_CHARS = 400_000
SHORT_PROMPT = (
    "Ты делаешь краткую и точную суммаризацию чатов. "
    "Начинай ответ с названия чата на первой строке. "
    "Дальше 4-8 коротких пунктов с главными темами, решениями и выводами участников. "
    "Не упоминай файл chat.txt, не добавляй вступлений вроде 'Вот ваш суммариз', "
    "не пиши 'Итог', 'Вывод', 'Summary' или похожие финальные блоки. "
    "Не предлагай помощь и не комментируй качество. "
    "Пиши строго по делу, без воды и фантазий."
)


@loader.tds
class SummMod(loader.Module):
    """Chat summarization via OnlySq"""

    strings = {"name": "Summ"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                "",
                "OnlySq API key (empty = use env ONLYSQ_API_KEY or 'openai')",
                validator=loader.validators.Hidden(loader.validators.String()),
            ),
            loader.ConfigValue(
                "summ_model",
                DEFAULT_TEXT_MODEL,
                "Text model for .summ",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "api_version",
                DEFAULT_API_VERSION,
                "API version: openai or v2",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "summ_limit",
                MAX_SUMM_MESSAGES,
                "How many messages to summarize (max 20000)",
                validator=loader.validators.Integer(),
            ),
        )

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

    @staticmethod
    def _strip_summary_noise(text: str) -> str:
        if not text:
            return ""
        drop_prefixes = (
            "итог",
            "вывод",
            "summary",
            "conclusion",
            "вот ваш",
            "ваш суммар",
        )
        cleaned = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and stripped.lower().startswith(drop_prefixes):
                continue
            cleaned.append(line)
        return "\n".join(cleaned).strip()

    @staticmethod
    def _build_summary_file(history: str) -> str:
        return f"chat.txt\n{history}"

    async def _get_chat_title(self, chat: typing.Any) -> str:
        try:
            entity = await self._client.get_entity(chat)
        except Exception:
            return "Чат"
        title = getattr(entity, "title", "") or ""
        if title:
            return title
        first = getattr(entity, "first_name", "") or ""
        last = getattr(entity, "last_name", "") or ""
        name = " ".join(part for part in (first, last) if part).strip()
        if name:
            return name
        username = getattr(entity, "username", "") or ""
        if username:
            return username if username.startswith("@") else f"@{username}"
        return "Чат"

    async def _collect_chat_history(
        self,
        chat: typing.Any,
        skip_id: typing.Optional[int] = None,
        limit: int = MAX_SUMM_MESSAGES,
    ) -> str:
        lines: typing.List[str] = []
        total = 0
        async for msg in self._client.iter_messages(chat, limit=limit):
            if skip_id and getattr(msg, "id", None) == skip_id:
                continue
            text = (msg.raw_text or "").strip()
            if not text:
                continue
            entry = text
            entry_len = len(entry) + 1
            if total + entry_len > MAX_TEXT_CHARS:
                if not lines:
                    lines.append(entry[:MAX_TEXT_CHARS].rstrip() + "\n...[truncated]")
                break
            lines.append(entry)
            total += entry_len
        if not lines:
            return ""
        lines.reverse()
        return "\n".join(lines)

    async def _fetch_models(self) -> dict:
        response = await self._request("GET", MODELS_URL, timeout=20)
        response.raise_for_status()
        return response.json()

    async def _get_model_list(self) -> typing.List[str]:
        data = await self._fetch_models()
        classified = data.get("classified", {})
        models = classified.get("text", [])
        return sorted(models)

    @staticmethod
    def _format_model_list(models: typing.List[str]) -> str:
        return "\n".join(f"{idx + 1}. {name}" for idx, name in enumerate(models))

    async def _request_chat(self, prompt: str, model: str) -> str:
        key = self._get_api_key()
        api_version = (self.config["api_version"] or DEFAULT_API_VERSION).lower().strip()
        headers = {"Authorization": f"Bearer {key}"}
        messages = [
            {"role": "system", "content": SHORT_PROMPT},
            {"role": "user", "content": prompt},
        ]

        if api_version == "v2":
            url = CHAT_URL_V2
            payload = {"model": model, "request": {"messages": messages}}
        else:
            url = CHAT_URL_OPENAI
            payload = {"model": model, "messages": messages, "stream": False}

        response = await self._request(
            "POST",
            url,
            headers=headers,
            json=payload,
            timeout=180,
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

    @loader.command(ru_doc="Краткая суммаризация чата")
    async def summ(self, message: Message):
        chat = message.chat_id or message.peer_id
        status = await self._client.send_message(self.tg_id, "Подождите...")
        await utils.answer(message, "Результат в избранном.")

        chat_title = await self._get_chat_title(chat)
        limit = self.config["summ_limit"] or MAX_SUMM_MESSAGES
        if limit < 1:
            limit = 1
        if limit > MAX_SUMM_MESSAGES:
            limit = MAX_SUMM_MESSAGES

        history = await self._collect_chat_history(
            chat,
            skip_id=message.id,
            limit=limit,
        )
        if not history:
            await status.edit("Нет текстовых сообщений для суммаризации.")
            return

        model = (self.config["summ_model"] or DEFAULT_TEXT_MODEL).strip()
        file_text = self._build_summary_file(history)
        prompt = (
            "Сделай краткую суммаризацию сообщений.\n"
            f"Название чата: {chat_title}\n"
            "Сообщения в файле chat.txt:\n\n"
            f"{file_text}"
        )
        try:
            answer = await self._request_chat(prompt, model)
        except Exception as exc:
            await status.edit(f"Ошибка запроса: {utils.escape_html(str(exc))}")
            return

        answer = self._strip_reasoning(answer)
        answer = self._strip_summary_noise(answer)
        rendered = self._render_markdown(answer) or "Пустой ответ."
        title_html = utils.escape_html(chat_title)
        if chat_title and not (answer.strip().lower().startswith(chat_title.lower())):
            rendered = f"{title_html}\n{rendered}"
        await status.edit(rendered)

    @loader.command(alias="model-summ", ru_doc="Список моделей для суммаризации")
    async def model_summ(self, message: Message):
        args = utils.get_args_raw(message).strip()
        try:
            models = await self._get_model_list()
        except Exception as exc:
            await utils.answer(message, f"Ошибка списка моделей: {utils.escape_html(str(exc))}")
            return
        if not models:
            await utils.answer(message, "Список моделей пуст.")
            return

        if not args:
            listing = self._format_model_list(models)
            current = (self.config["summ_model"] or DEFAULT_TEXT_MODEL).strip()
            await utils.answer(
                message,
                f"{listing}\n\nТекущая модель: {utils.escape_html(current)}",
            )
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
        self.config["summ_model"] = model
        await utils.answer(message, f"Модель суммаризации: {utils.escape_html(model)}")

    @loader.command(aliases=["set-summ"], ru_doc="Выбор количества сообщений для .summ")
    async def set_summ(self, message: Message):
        args = utils.get_args_raw(message).strip()
        if not args:
            current = self.config["summ_limit"] or MAX_SUMM_MESSAGES
            await utils.answer(
                message,
                f"Текущий лимит: {current} (макс {MAX_SUMM_MESSAGES})",
            )
            return

        try:
            value = int(args)
        except ValueError:
            await utils.answer(message, "Нужен числовой лимит.")
            return

        if value < 1 or value > MAX_SUMM_MESSAGES:
            await utils.answer(message, f"Лимит от 1 до {MAX_SUMM_MESSAGES}.")
            return

        self.config["summ_limit"] = value
        await utils.answer(message, f"Лимит .summ: {value}")
