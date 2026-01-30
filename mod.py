__version__ = (1, 2, 1)
# meta developer: @etopizdesblin

import io
import mimetypes
import os
import re
import secrets
import time
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
AI_DIR_NAME = "ai_plug"
MODULE_FILENAME = "module.py"
CHANGELOG_FILENAME = "changelog.txt"
FILENAME_FILENAME = "filename.txt"
PROMPT_DIR_NAME = "prompts"
BUILTIN_PROMPTS = {}
MAX_ATTACH_BYTES = 200_000
MAX_ATTACH_FILES = 8

HEROKU_DOC = '''
# Quickstart Development

In order to write your first module, let's take a look at the basic structure:

```python
from herokutl.types import Message
from .. import loader, utils


@loader.tds
class MyModule(loader.Module):
    """My module"""
    strings = {"name": "MyModule", "hello": "Hello world!"}
    strings_ru = {"hello": "Привет мир!"}
    strings_de = {"hello": "Hallo Welt!"}

    @loader.command(
        ru_doc="Привет мир!",
        de_doc="Hallo Welt!",
        # ...
    )
    async def helloworld(self, message: Message):
        """Hello world"""
        await utils.answer(message, self.strings["hello"])
```

The first line imports the `Message` type from herokutl.types and the loader module from `..`. The `loader` module contains all the necessary functions and classes to create a module.

`@loader.tds` is a decorator that makes module translateable (`tds` comes from `translateable_docstring`). In the class docstring you should specify brief information about the module so that user, that reads it can understand, what it does.

The `strings` dictionary is a special object, that contains translations for translateable strings. Suffix with desired language will allow user to use the module in the selected language. If there is no translation for the selected language, the default one will be used.

The `@loader.command` decorator is used to mark a function as a command. It takes a lot of arguments. Most important ones are translations. `XX_doc` makes description for command in the language XX.

`utils.answer` is an asyncronous function that answers the message. If it's possible to edit the message, it will edit it, otherwise it will send a new message. It always returns the resulted message so you can edit it again in the same command.

---

# Watcher and command tags

Tags were introduced not long ago and continue to be developed. They are used to make filters for commands and watchers. An example of tags usage is as follows:

```python
@loader.command(only_pm=True, only_photos=True, from_id=123456789)
async def mycommand(self, message: Message):
    ...
```

The `only_pm` tag makes the command work only in PMs. The `only_photos` tag makes the command work only with photos. The `from_id` tag makes the command work only if the message was sent by the user with the specified ID.

## Full list of available tags:

---

- `no_commands` - Ignore all userbot commands in watcher
- `only_commands` - Capture only userbot commands in watcher
- `out` - Capture only outgoing events
- `in` - Capture only incoming events
- `only_message`s - Capture only messages (not join events)
- `editable` - Capture only messages, which can be edited (no forwards etc.)
- `no_media` - Capture only messages without media and files
- `only_media` - Capture only messages with media and files
- `only_photos` - Capture only messages with photos
- `only_videos` - Capture only messages with videos
- `only_audios` - Capture only messages with audios
- `only_docs` - Capture only messages with documents
- `only_stickers` - Capture only messages with stickers
- `only_inline` - Capture only messages with inline queries
- `only_channels` - Capture only messages with channels
- `only_groups` - Capture only messages with groups
- `only_pm` - Capture only messages with private chats
- `no_pm` - Exclude messages with private chats
- `no_channels` - Exclude messages with channels
- `no_groups` - Exclude messages with groups
- `no_inline` - Exclude messages with inline queries
- `no_stickers` - Exclude messages with stickers
- `no_docs` - Exclude messages with documents
- `no_audios` - Exclude messages with audios
- `no_videos` - Exclude messages with videos
- `no_photos` - Exclude messages with photos
- `no_forwards` - Exclude forwarded messages
- `no_reply` - Exclude messages with replies
- `no_mention` - Exclude messages with mentions
- `mention` - Capture only messages with mentions
- `only_reply` - Capture only messages with replies
- `only_forwards` - Capture only forwarded messages
- `startswith` - Capture only messages that start with given text
- `endswith` - Capture only messages that end with given text
- `contains` - Capture only messages that contain given text
- `regex` - Capture only messages that match given regex
- `filter` - Capture only messages that pass given function
- `from_id` - Capture only messages from given user
- `chat_id` - Capture only messages from given chat
- `thumb_url` - Works for inline command handlers. Will be shown in help
- `alias` - Set single alias for a command
- `aliases` - Set multiple aliases for a command

---

# Config validators

Validators are used to sanitize input config data. See the following example for usage:

```python
@loader.tds
class MyModule(loader.Module):
    ...

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "task_delay",
                60,
                "Delay between tasks in seconds",
                validator=loader.validators.Integer(minimum=0),
            ),
            loader.ConfigValue(
                "sleep_between_tasks",
                False,
                "Sleep between tasks instead of waiting for them to finish",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "tasks_to_run",
                [],
                "Tasks to run",
                validator=loader.validators.MultiChoice(["task1", "task2", "task3"]),
            ),
        )
```

## Full list of available validators:

- `Boolean` - True or False
- `Integer` - Integer number
- `Choice` - One of the given options
- `MultiChoice` - One or more of the given options
- `Series` - One or more options (not from the given list)
- `Link` - Valid URL
- `String` - Any string
- `RegExp` - String that matches the given regular expression
- `Float` - Float number
- `TelegramID` - Telegram ID
- `Union` - Used to combine multiple validators (Integer or Float etc.)
- `NoneType` - None
- `Hidden` - Good for tokens and over sensitive data
- `Emoji` - Valid emoji(-s)
- `EntityLike` - Valid entity (user, chat, channel etc.) - link, id or url

### You can create your own validators. For this purpose use the base class `Validator` (`heroku.loader.validators.Validator`):

```python
class Cat(Validator):
    def __init__(self):
        super().__init__(self._validate, {"en": "cat's name", "ru": "именем кошечки"})

    @staticmethod
    def _validate(value: typing.Any) -> str:
        if not isinstance(value, str):
            raise ValidationError("Cat's name must be a string")

        if value not in {"Mittens", "Fluffy", "Garfield"}:
            raise ValidationError("This cat is not allowed")

        return f"Cat {value}"


...

loader.ConfigValue(
    "cat",
    "Mittens",
    "Cat's name",
    validator=Cat(),
)
```

---

# Database operations

Heroku has a built-in database. You can use it to persistently store data required for your module to work. First way is to use database object directly:

- `self._db.get(owner, value, default)`
- `self._db.set(owner, value, data)`
- `self._db.pointer(owner, value, default)`
  Much better approach is to use wrappers:
- `self.db.get(value, default)`
- `self.db.set(value, data)`
- `self.db.pointer(value, default)`

`self.get` and `self.set` are pretty straight-forward, whereas `self.pointer` is a bit more complicated. It returns a pointer to the value in the database. This pointer can be used to change the value in the database without having to call `self.set` again. This is useful for example when you want to periodically add / remove items from a list in the database. See the following example:

```python
self._users = self.pointer("users", [])
self._users.append("John")
self._users.extend(["Jane", "Joe", "Doe"])
self._users.remove("Doe")
```

```python
self._state = self.get("state", False)
self._state = not self._state
self.set("state", self._state)
```
'''


@loader.tds
class ModMakerMod(loader.Module):
    """Generate Heroku modules via OnlySq"""

    strings = {"name": "ModMaker"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                "",
                "OnlySq API key (empty = use env ONLYSQ_API_KEY or 'openai')",
                validator=loader.validators.Hidden(loader.validators.String()),
            ),
            loader.ConfigValue(
                "model",
                DEFAULT_TEXT_MODEL,
                "Text model for .mod",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "api_version",
                DEFAULT_API_VERSION,
                "API version: openai or v2",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "prompt_enabled",
                False,
                "Enable extra system prompts for .mod/.editmod",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "prompt_entries",
                [],
                "Selected system prompts (builtin/file list)",
                validator=loader.validators.Series(loader.validators.String()),
            ),
        )
        self._dialogs = None
        self._last_patch_error = ""

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
    def _base_root() -> str:
        return os.path.normpath(os.path.join(utils.get_base_dir(), ".."))

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
            entries.append((f"builtin:{name}", f"{name} (builtin)"))
        for filename in self._list_prompt_files():
            entries.append((f"file:{filename}", filename))
        return entries

    def _selected_prompt_entries(self) -> typing.List[str]:
        return list(self.config["prompt_entries"] or [])

    def _resolve_prompt_entry(self, entry: str) -> str:
        if entry.startswith("builtin:"):
            name = entry.split(":", 1)[1].strip()
            return BUILTIN_PROMPTS.get(name, "")
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

    def _read_prompt_file(self, filename: str) -> str:
        path = os.path.join(self._prompts_dir(), filename)
        if not os.path.isfile(path):
            raise FileNotFoundError(filename)
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()

    @staticmethod
    def _guess_mime(filename: str, mime: str) -> str:
        if mime:
            return mime
        guess = mimetypes.guess_type(filename)[0]
        return guess or "application/octet-stream"

    @staticmethod
    def _looks_like_text(text: str) -> bool:
        if not text:
            return False
        printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t")
        return printable / max(len(text), 1) > 0.85

    async def _collect_attachments(
        self,
        message: typing.Optional[Message],
        reply: typing.Optional[Message],
        *,
        exclude_names: typing.Optional[typing.Set[str]] = None,
    ) -> typing.List[dict]:
        items: typing.List[dict] = []
        exclude_names = exclude_names or set()
        for msg in (message, reply):
            if not msg or not msg.media:
                continue
            if len(items) >= MAX_ATTACH_FILES:
                break
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
            if filename in exclude_names:
                continue
            mime = self._guess_mime(filename, mime)
            size = len(raw)

            is_binary = True
            text = ""
            truncated = False
            if msg.photo or mime.startswith(("image/", "video/", "audio/")):
                is_binary = True
            else:
                snippet = raw[:MAX_ATTACH_BYTES]
                truncated = size > MAX_ATTACH_BYTES
                if b"\x00" not in snippet:
                    decoded = snippet.decode("utf-8", errors="replace")
                    if self._looks_like_text(decoded):
                        text = decoded
                        is_binary = False

            items.append(
                {
                    "name": filename,
                    "mime": mime,
                    "size": size,
                    "binary": is_binary,
                    "text": text,
                    "truncated": truncated,
                }
            )
        return items

    @staticmethod
    def _format_attachments(items: typing.List[dict]) -> str:
        parts = []
        for info in items:
            header = f"{info['name']} ({info['mime']}, {info['size']} bytes)"
            if info.get("binary"):
                parts.append(f"Файл: {header}\n[БИНАРНОЕ ВЛОЖЕНИЕ]")
                continue
            body = info.get("text", "")
            if info.get("truncated"):
                body = (body + "\n...[truncated]").strip()
            parts.append(f"Файл: {header}\n{body}".strip())
        return "\n\n".join(parts)

    def _ai_root(self) -> str:
        root = os.path.join(self._base_root(), AI_DIR_NAME)
        os.makedirs(root, exist_ok=True)
        return root

    def _dialogs_list(self) -> typing.List[str]:
        if self._dialogs is None:
            self._dialogs = self.pointer("dialogs", [])
        return list(self._dialogs)

    def _add_dialog(self, dialog_id: str) -> None:
        if self._dialogs is None:
            self._dialogs = self.pointer("dialogs", [])
        if dialog_id not in self._dialogs:
            self._dialogs.append(dialog_id)

    def _remove_dialog(self, dialog_id: str) -> None:
        if self._dialogs is None:
            self._dialogs = self.pointer("dialogs", [])
        if dialog_id in self._dialogs:
            self._dialogs.remove(dialog_id)

    def _active_dialog(self) -> str:
        return (self.get("active_dialog") or "").strip()

    def _set_active_dialog(self, dialog_id: str) -> None:
        self.set("active_dialog", dialog_id)

    def _clear_active_dialog(self) -> None:
        self.set("active_dialog", "")

    def _dialog_dir(self, dialog_id: str) -> str:
        return os.path.join(self._ai_root(), dialog_id)

    def _module_path(self, dialog_id: str) -> str:
        return os.path.join(self._dialog_dir(dialog_id), MODULE_FILENAME)

    def _changelog_path(self, dialog_id: str) -> str:
        return os.path.join(self._dialog_dir(dialog_id), CHANGELOG_FILENAME)

    def _filename_path(self, dialog_id: str) -> str:
        return os.path.join(self._dialog_dir(dialog_id), FILENAME_FILENAME)

    def _dialog_exists(self, dialog_id: str) -> bool:
        return os.path.isdir(self._dialog_dir(dialog_id))

    def _new_dialog_id(self) -> str:
        while True:
            dialog_id = secrets.token_hex(4)
            if not self._dialog_exists(dialog_id):
                return dialog_id

    def _create_dialog(self) -> str:
        dialog_id = self._new_dialog_id()
        path = self._dialog_dir(dialog_id)
        os.makedirs(path, exist_ok=True)
        module_path = self._module_path(dialog_id)
        changelog_path = self._changelog_path(dialog_id)
        filename_path = self._filename_path(dialog_id)
        if not os.path.exists(module_path):
            with open(module_path, "w", encoding="utf-8") as handle:
                handle.write("")
        if not os.path.exists(changelog_path):
            with open(changelog_path, "w", encoding="utf-8") as handle:
                handle.write("")
        if not os.path.exists(filename_path):
            with open(filename_path, "w", encoding="utf-8") as handle:
                handle.write(MODULE_FILENAME)
        self._add_dialog(dialog_id)
        self._set_active_dialog(dialog_id)
        return dialog_id

    def _read_text(self, path: str) -> str:
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read().strip()
        except Exception:
            return ""

    def _write_text(self, path: str, text: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.strip() + "\n")

    def _read_filename(self, dialog_id: str) -> str:
        name = self._read_text(self._filename_path(dialog_id))
        if name and name.endswith(".py"):
            return name
        return MODULE_FILENAME

    def _write_filename(self, dialog_id: str, name: str) -> None:
        if not name or not name.endswith(".py"):
            return
        self._write_text(self._filename_path(dialog_id), name)

    def _append_changelog(self, path: str, text: str) -> None:
        if not text.strip():
            return
        existing = self._read_text(path)
        combined = text.strip() if not existing else existing.rstrip() + "\n\n" + text.strip()
        self._write_text(path, combined)

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
    def _looks_like_code(text: str) -> bool:
        markers = ("import ", "from ", "@loader.", "class ", "async def ")
        return any(marker in text for marker in markers)

    @staticmethod
    def _extract_filename(text: str) -> typing.Optional[str]:
        patterns = (
            r"(?im)^\s*filename\s*[:=]\s*([\w.-]+\.py)\s*$",
            r"(?im)^\s*file\s*[:=]\s*([\w.-]+\.py)\s*$",
            r"(?im)^\s*имя\s*файла\s*[:=]\s*([\w.-]+\.py)\s*$",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _strip_filename_line(code: str) -> str:
        lines = code.splitlines()
        if not lines:
            return code
        if re.match(
            r"(?im)^\s*(filename|file|имя\s*файла)\s*[:=]\s*[\w.-]+\.py\s*$",
            lines[0],
        ):
            return "\n".join(lines[1:]).strip()
        return code.strip()

    def _extract_blocks(self, text: str) -> typing.Optional[typing.Tuple[str, str, str]]:
        filename = self._extract_filename(text) or ""
        blocks = list(
            re.finditer(r"```(?:[a-zA-Z0-9_-]+)?\n(.*?)```", text, re.S)
        )
        if len(blocks) >= 2:
            code = self._strip_filename_line(blocks[0].group(1).strip())
            changelog = blocks[1].group(1).strip()
            if code and changelog:
                return code, changelog, filename

        if len(blocks) == 1:
            block = blocks[0]
            before = text[: block.start()].strip()
            inside = self._strip_filename_line(block.group(1).strip())
            after = text[block.end() :].strip()
            if before and inside:
                if self._looks_like_code(before) and not self._looks_like_code(inside):
                    return before, inside, filename
                if self._looks_like_code(inside) and after:
                    return inside, after, filename
                if not after:
                    return before, inside, filename

        markers = ("CHANGELOG:", "Changelog:", "Изменения:", "ИЗМЕНЕНИЯ:")
        for marker in markers:
            if marker in text:
                before, _, after = text.partition(marker)
                code = before.strip()
                changelog = after.strip()
                if code and changelog:
                    return code, changelog, filename

        return None

    @staticmethod
    def _extract_patch_filename(patch_text: str) -> str:
        for line in patch_text.splitlines():
            if line.startswith("*** Update File:"):
                return line.split(":", 1)[1].strip()
            if line.startswith("*** Add File:"):
                return line.split(":", 1)[1].strip()
        return ""

    def _extract_patch_blocks(self, text: str) -> typing.Optional[typing.Tuple[str, str, str]]:
        blocks = list(
            re.finditer(r"```(?:[a-zA-Z0-9_-]+)?\n(.*?)```", text, re.S)
        )
        if len(blocks) >= 2:
            patch = blocks[0].group(1).strip()
            changelog = blocks[1].group(1).strip()
            filename = self._extract_patch_filename(patch)
            if patch and changelog:
                return patch, changelog, filename

        lines = text.splitlines()
        start_idx = None
        end_idx = None
        for idx, line in enumerate(lines):
            if line.strip().startswith("*** Begin Patch"):
                start_idx = idx
                break
        if start_idx is None:
            for idx, line in enumerate(lines):
                if line.strip().startswith("*** Update File:"):
                    start_idx = idx
                    break
        if start_idx is not None:
            for idx in range(start_idx + 1, len(lines)):
                if lines[idx].strip().startswith("*** End Patch"):
                    end_idx = idx
                    break
        if start_idx is not None and end_idx is not None:
            patch = "\n".join(lines[start_idx : end_idx + 1]).strip()
            filename = self._extract_patch_filename(patch)

            changelog = ""
            begin_ch = None
            end_ch = None
            for idx, line in enumerate(lines):
                if re.match(r"(?i)^\\*\\*\\*\\s*begin\\s+changelog", line.strip()):
                    begin_ch = idx + 1
                    continue
                if re.match(r"(?i)^\\*\\*\\*\\s*end\\s+changelog", line.strip()):
                    end_ch = idx
                    break
            if begin_ch is not None:
                if end_ch is None:
                    end_ch = len(lines)
                changelog = "\n".join(lines[begin_ch:end_ch]).strip()
            else:
                for idx, line in enumerate(lines[end_idx + 1 :], start=end_idx + 1):
                    if re.match(r"(?i)^\\s*changelog\\s*[:=]", line.strip()):
                        changelog = "\n".join(lines[idx + 1 :]).strip()
                        break
                if not changelog:
                    tail_lines = lines[end_idx + 1 :]
                    if tail_lines:
                        filtered = [ln for ln in tail_lines if ln.strip().startswith(("+", "~", "-"))]
                        if filtered:
                            changelog = "\n".join(filtered).strip()
                        else:
                            tail = "\n".join(tail_lines).strip()
                            if tail:
                                changelog = tail

            if patch and changelog:
                return patch, changelog, filename
        return None

    @staticmethod
    def _find_subsequence(
        haystack: typing.List[str],
        needle: typing.List[str],
        start: int,
    ) -> typing.Optional[int]:
        if not needle:
            return start
        end = len(haystack) - len(needle) + 1
        for idx in range(start, max(end, start)):
            if haystack[idx : idx + len(needle)] == needle:
                return idx
        return None

    def _apply_patch_text(
        self, original: str, patch_text: str, expected_filename: str = ""
    ) -> typing.Optional[str]:
        self._last_patch_error = ""
        lines = original.splitlines()
        patch_lines = patch_text.splitlines()
        if not patch_lines:
            self._last_patch_error = "Пустой patch."
            return None

        if patch_lines[0].strip() != "*** Begin Patch":
            if any(line.startswith("*** Update File:") for line in patch_lines):
                patch_lines = ["*** Begin Patch"] + patch_lines + ["*** End Patch"]
            else:
                self._last_patch_error = "Patch должен начинаться с *** Begin Patch."
                return None

        i = 1
        search_start = 0
        update_file = ""

        def parse_hunk(hunk_lines: typing.List[str], *, lenient: bool) -> typing.Tuple[typing.List[str], typing.List[str]]:
            old_lines: typing.List[str] = []
            new_lines: typing.List[str] = []
            for hunk_line in hunk_lines:
                if not hunk_line:
                    old_lines.append("")
                    new_lines.append("")
                    continue
                prefix = hunk_line[0]
                if prefix == "+":
                    new_lines.append(hunk_line[1:])
                elif prefix == "-":
                    old_lines.append(hunk_line[1:])
                elif prefix == " ":
                    if lenient:
                        old_lines.append(hunk_line)
                        new_lines.append(hunk_line)
                    else:
                        old_lines.append(hunk_line[1:])
                        new_lines.append(hunk_line[1:])
                else:
                    old_lines.append(hunk_line)
                    new_lines.append(hunk_line)
            return old_lines, new_lines

        while i < len(patch_lines):
            line = patch_lines[i]
            if line.startswith("*** End Patch"):
                break
            if line.startswith("*** Update File:") or line.startswith("*** Add File:"):
                if line.startswith("*** Update File:"):
                    update_file = line.split(":", 1)[1].strip()
                i += 1
                continue
            if line.startswith("*** Delete File:"):
                self._last_patch_error = "Delete File запрещён без запроса."
                return ""
            if line.startswith("@@"):
                i += 1
                hunk_lines = []
                while i < len(patch_lines):
                    marker = patch_lines[i]
                    if marker.startswith(("@@", "*** End Patch", "*** Update File:", "*** Add File:", "*** Delete File:")):
                        break
                    if marker.startswith("\\"):
                        i += 1
                        continue
                    hunk_lines.append(marker)
                    i += 1

                old, new = parse_hunk(hunk_lines, lenient=False)
                idx = self._find_subsequence(lines, old, search_start)
                if idx is None:
                    old, new = parse_hunk(hunk_lines, lenient=True)
                    idx = self._find_subsequence(lines, old, search_start)
                if idx is None:
                    snippet = "\n".join(old[:5]).strip()
                    if snippet:
                        self._last_patch_error = (
                            "Контекст хунка не найден в файле.\n" + snippet
                        )
                    else:
                        self._last_patch_error = "Контекст хунка не найден в файле."
                    return None
                lines = lines[:idx] + new + lines[idx + len(old) :]
                search_start = idx + len(new)
                continue

            i += 1

        if expected_filename and update_file and update_file != expected_filename:
            self._last_patch_error = (
                f"Файл в patch: {update_file} (ожидался {expected_filename})"
            )
            return None

        return "\n".join(lines)

    @staticmethod
    def _format_changelog(changelog: str) -> str:
        lines = [line.strip() for line in changelog.splitlines() if line.strip()]
        if not lines:
            return "<blockquote expandable>(пусто)</blockquote>"
        safe_lines = [utils.escape_html(line) for line in lines]
        return "<blockquote expandable>\n" + "\n".join(safe_lines) + "\n</blockquote>"

    @staticmethod
    def _raw_block(text: str) -> str:
        safe = utils.escape_html(text or "")
        return f"<blockquote expandable>{safe}</blockquote>"

    @staticmethod
    def _find_bad_patch_lines(patch_text: str) -> typing.List[str]:
        bad = []
        markers = ("todo", "здесь", "пример", "placeholder", "часть кода")
        for line in patch_text.splitlines():
            if not line.startswith("+"):
                continue
            content = line[1:].strip()
            if not content:
                continue
            lowered = content.lower()
            if content == "pass" or content == "...":
                bad.append(line)
                continue
            if lowered.startswith("#") and any(m in lowered for m in markers):
                bad.append(line)
                continue
            if "todo" in lowered and lowered.startswith("#"):
                bad.append(line)
                continue
        return bad

    def _get_extra_prompts(self) -> str:
        if not self.config["prompt_enabled"]:
            return ""
        entries = self._selected_prompt_entries()
        if not entries:
            return ""
        parts = []
        for entry in entries:
            text = self._resolve_prompt_entry(entry)
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    def _compose_system_prompt(self, patch_mode: bool) -> str:
        base = self._system_prompt_patch() if patch_mode else self._system_prompt()
        extra = self._get_extra_prompts()
        if extra:
            return base + "\n\n=== EXTRA_PROMPTS ===\n" + extra + "\n=== END_EXTRA ===\n"
        return base

    def _system_prompt(self) -> str:
        lines = [line.rstrip() for line in HEROKU_DOC.splitlines()]
        compact = []
        blank = False
        for line in lines:
            if not line.strip():
                if not blank:
                    compact.append("")
                blank = True
                continue
            blank = False
            compact.append(line)
        doc = "\n".join(compact).strip()
        return (
            "ТЫ ПИШЕШЬ КОД МОДУЛЕЙ HEROKU USERBOT. "
            "ОТВЕЧАЙ СТРОГО ДВУМЯ CODE-БЛОКАМИ И БОЛЬШЕ НИЧЕМ.\n"
            "БЛОК 1: ПОЛНЫЙ КОД МОДУЛЯ (Python). ПЕРВАЯ строка: FILENAME: <имя_файла>.py\n"
            "БЛОК 2: CHANGELOG текущих изменений (добавления/изменения/удаления).\n"
            "CHANGELOG: КАЖДАЯ строка начинается с + (добавлено), ~ (изменено), - (удалено).\n"
            "CHANGELOG ТОЛЬКО ЗА ЭТОТ ЗАПРОС, БЕЗ ЗАГОЛОВКОВ.\n"
            "НИКАКИХ вступлений, пояснений, итогов, просьб, благодарностей.\n"
            "НЕ используй слово 'плагин', только 'модуль'.\n"
            "ВСЕГДА используй @loader.tds и структуру модулей Heroku.\n"
            "ЕСЛИ модуль уже существует, делай МИНИМАЛЬНЫЕ правки и сохраняй стиль.\n"
            "НЕ переписывай всё с нуля, только точечные изменения.\n"
            "НЕ добавляй медиа/тесты/комментарии без необходимости.\n"
            "НЕ используй заглушки и placeholders (например: '...','часть кода','TODO').\n"
            "ЗАПРЕЩЕНЫ 'pass' и комментарии вместо реализации. Если нужна функция — пиши полный код.\n"
            "КОД должен быть рабочим и самодостаточным.\n"
            "\n=== HEROKU_DOC ===\n"
            + doc
            + "\n=== END_DOC ===\n"
        )

    def _system_prompt_patch(self) -> str:
        lines = [line.rstrip() for line in HEROKU_DOC.splitlines()]
        compact = []
        blank = False
        for line in lines:
            if not line.strip():
                if not blank:
                    compact.append("")
                blank = True
                continue
            blank = False
            compact.append(line)
        doc = "\n".join(compact).strip()
        return (
            "Ты редактор модулей Heroku Userbot.\n"
            "Отвечай СТРОГО двумя code-блоками и больше ничем.\n"
            "Блок 1: PATCH в формате apply_patch.\n"
            "Блок 2: CHANGELOG (только строки, каждая начинается с +, ~, -).\n"
            "НИКАКИХ заголовков, пояснений, итогов, просьб.\n"
            "НЕ сокращай, НЕ опускай строки, НЕ используй '...'.\n"
            "Пиши ВСЕ строки полностью и точно, без пропусков.\n"
            "PATCH ДОЛЖЕН ПРИМЕНЯТЬСЯ БЕЗ ОШИБОК.\n"
            "ИСПОЛЬЗУЙ ТОЛЬКО СТРОКИ ИЗ ТЕКУЩЕГО ФАЙЛА КАК КОНТЕКСТ.\n"
            "НЕ ДОБАВЛЯЙ НОВЫЕ ФУНКЦИИ/ПОЛЯ, ЕСЛИ ЭТО НЕ ТРЕБУЕТСЯ ЗАДАНИЕМ.\n"
            "ЗАПРЕЩЕНЫ 'pass', 'TODO', 'здесь будет код', 'пример', '...'.\n"
            "ЗАПРЕЩЕНЫ КОММЕНТАРИИ ВМЕСТО КОДА. ПИШИ ПОЛНУЮ РЕАЛИЗАЦИЮ.\n"
            "PATCH ОБЯЗАТЕЛЬНО:\n"
            "- Начинается '*** Begin Patch'\n"
            "- Содержит '*** Update File: <имя_файла>.py' (имя строго из поля ИМЯ ФАЙЛА)\n"
            "- Ханки с @@ и строки только с префиксом ' ', '+', '-'\n"
            "- Заканчивается '*** End Patch'\n"
            "ЗАПРЕЩЕНО:\n"
            "- 'Begin Changelog', 'End Changelog'\n"
            "- любые заглушки/комментарии про части кода\n"
            "- 'TODO', '...'\n"
            "- любой текст вне двух code-блоков\n"
            "\nФОРМАТ ОТВЕТА (строго):\n"
            "```patch\n"
            "*** Begin Patch\n"
            "*** Update File: module.py\n"
            "@@\n"
            " ...\n"
            "*** End Patch\n"
            "```\n"
            "```text\n"
            "+ ...\n"
            "```\n"
            "\n=== HEROKU_DOC ===\n"
            + doc
            + "\n=== END_DOC ===\n"
        )

    def _build_user_prompt(self, request: str, code: str, changelog: str, filename: str) -> str:
        return (
            "ЗАДАНИЕ:\n"
            f"{request.strip()}\n\n"
            f"ИМЯ ФАЙЛА: {filename}\n\n"
            "ТЕКУЩИЙ МОДУЛЬ (module.py):\n"
            "```python\n"
            f"{code.strip()}\n"
            "```\n\n"
            "ТЕКУЩИЙ CHANGELOG (changelog.txt):\n"
            "```text\n"
            f"{changelog.strip()}\n"
            "```\n"
        )

    def _build_patch_prompt(
        self, request: str, code: str, changelog: str, filename: str
    ) -> str:
        return (
            "ЗАДАНИЕ:\n"
            f"{request.strip()}\n\n"
            f"ИМЯ ФАЙЛА: {filename}\n\n"
            "ТЕКУЩИЙ ФАЙЛ:\n"
            "```python\n"
            f"{code.strip()}\n"
            "```\n\n"
            "ТЕКУЩИЙ CHANGELOG:\n"
            "```text\n"
            f"{changelog.strip()}\n"
            "```\n"
        )

    def _build_patch_retry_prompt(
        self,
        request: str,
        code: str,
        changelog: str,
        filename: str,
        error: str,
    ) -> str:
        return (
            "ПРЕДЫДУЩИЙ PATCH НЕ ПОДХОДИТ.\n"
            f"ОШИБКА:\n{error.strip()}\n"
            "ИСПРАВЬ PATCH. НЕ ПОВТОРЯЙ ОШИБКУ.\n"
            "ИСПОЛЬЗУЙ ТОЧНЫЕ СТРОКИ ИЗ ТЕКУЩЕГО ФАЙЛА КАК КОНТЕКСТ.\n\n"
            + self._build_patch_prompt(request, code, changelog, filename)
        )

    async def _run_patch_flow(
        self,
        msg: Message,
        request: str,
        current_code: str,
        current_changelog: str,
        current_filename: str,
        model: str,
    ) -> typing.Optional[typing.Tuple[str, str, str, str]]:
        prompt = self._build_patch_prompt(
            request, current_code, current_changelog, current_filename
        )
        last_raw = ""
        last_error = ""
        for attempt in range(2):
            try:
                answer = await self._request_chat(prompt, model, patch_mode=True)
            except Exception as exc:
                await msg.edit("Ошибка запроса:\n" + self._raw_block(str(exc)))
                return None

            raw_answer = answer
            last_raw = raw_answer
            answer = self._strip_reasoning(answer)
            blocks = self._extract_patch_blocks(answer)
            if not blocks:
                last_error = "Ответ должен содержать PATCH и changelog."
                if attempt == 0:
                    prompt = self._build_patch_retry_prompt(
                        request,
                        current_code,
                        current_changelog,
                        current_filename,
                        last_error,
                    )
                    continue
                await msg.edit(
                    self._raw_block("Ошибка: ответ должен содержать PATCH и changelog.")
                    + "\n"
                    + self._raw_block(last_raw)
                )
                return None

            patch, changelog, filename = blocks
            bad_lines = self._find_bad_patch_lines(patch)
            if bad_lines:
                last_error = "Запрещённые заглушки:\n" + "\n".join(bad_lines[:10])
                if attempt == 0:
                    prompt = self._build_patch_retry_prompt(
                        request,
                        current_code,
                        current_changelog,
                        current_filename,
                        last_error,
                    )
                    continue
                await msg.edit(
                    self._raw_block("Ошибка: в PATCH есть заглушки.")
                    + "\n"
                    + self._raw_block(last_raw)
                    + "\n"
                    + self._raw_block(last_error)
                )
                return None

            updated = self._apply_patch_text(
                current_code, patch, expected_filename=current_filename
            )
            if updated is None:
                last_error = self._last_patch_error or "Patch не применился."
                if attempt == 0:
                    prompt = self._build_patch_retry_prompt(
                        request,
                        current_code,
                        current_changelog,
                        current_filename,
                        last_error,
                    )
                    continue
                await msg.edit(
                    self._raw_block("Ошибка: не удалось применить patch.")
                    + "\n"
                    + self._raw_block(last_raw)
                    + ("\n" + self._raw_block(last_error) if last_error else "")
                )
                return None

            filename = filename or current_filename or MODULE_FILENAME
            return updated, changelog, filename, raw_answer
        return None

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

    @staticmethod
    def _extract_api_error(response: requests.Response) -> str:
        raw = response.text.strip()
        if not raw:
            try:
                raw = response.content.decode("utf-8", errors="replace").strip()
            except Exception:
                raw = ""
        return raw or f"HTTP {response.status_code}"

    async def _request_chat(self, prompt: str, model: str, *, patch_mode: bool = False) -> str:
        key = self._get_api_key()
        headers = {"Authorization": f"Bearer {key}"}
        messages = [
            {"role": "system", "content": self._compose_system_prompt(patch_mode)},
            {"role": "user", "content": prompt},
        ]

        api_version = (self.config["api_version"] or DEFAULT_API_VERSION).lower().strip()
        versions = [api_version]
        fallback = "v2" if api_version == "openai" else "openai"
        if fallback not in versions:
            versions.append(fallback)

        last_error = None
        for version in versions:
            if version == "v2":
                url = CHAT_URL_V2
                payload = {"model": model, "request": {"messages": messages}}
            else:
                url = CHAT_URL_OPENAI
                payload = {"model": model, "messages": messages, "stream": False}

            try:
                response = await self._request(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                    timeout=180,
                )
                if response.status_code >= 400:
                    raise RuntimeError(self._extract_api_error(response))
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                last_error = exc
                continue

            if isinstance(data, dict):
                choices = data.get("choices")
                if isinstance(choices, list) and choices:
                    message = choices[0].get("message", {})
                    content = message.get("content")
                    if content is not None:
                        return content
                if data.get("answer"):
                    return data["answer"]

        if last_error:
            raise last_error

        raise ValueError("Empty response")

    @staticmethod
    def _extract_prompt(message: Message, reply: typing.Optional[Message]) -> str:
        args = utils.get_args_raw(message).strip()
        reply_text = reply.raw_text.strip() if reply and reply.raw_text else ""
        if args and reply_text:
            return f"{args}\n\nКонтекст: {reply_text}"
        if reply_text:
            return reply_text
        if args:
            return args
        return ""

    @staticmethod
    async def _get_attached_file(
        message: Message, reply: typing.Optional[Message]
    ) -> typing.Optional[typing.Tuple[str, bytes]]:
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
                name = MODULE_FILENAME
            return name, data
        return None

    @loader.command(ru_doc="Создать/обновить модуль через AI")
    async def mod(self, message: Message):
        reply = await message.get_reply_message() if message.is_reply else None
        request = self._extract_prompt(message, reply)
        attachments = await self._collect_attachments(message, reply)
        if attachments:
            att_text = self._format_attachments(attachments)
            request = (request or "").strip()
            request = f"{request}\n\nВЛОЖЕНИЯ:\n{att_text}".strip()
        if not request:
            await utils.answer(message, "Нужен текст запроса.")
            return

        dialog_id = self._active_dialog()
        if not dialog_id:
            dialog_id = self._create_dialog()
        elif not self._dialog_exists(dialog_id):
            dialog_id = self._create_dialog()

        module_path = self._module_path(dialog_id)
        changelog_path = self._changelog_path(dialog_id)
        current_code = self._read_text(module_path)
        current_changelog = self._read_text(changelog_path)
        current_filename = self._read_filename(dialog_id)

        model = (self.config["model"] or DEFAULT_TEXT_MODEL).strip()
        msg = await utils.answer(message, "Думаю...")
        if current_code.strip():
            result = await self._run_patch_flow(
                msg,
                request,
                current_code,
                current_changelog,
                current_filename,
                model,
            )
            if not result:
                return
            updated, changelog, filename, _raw = result
            self._write_text(module_path, updated)
            self._append_changelog(changelog_path, changelog)
            self._write_filename(dialog_id, filename)

            file = io.BytesIO(updated.encode("utf-8"))
            file.name = filename
            await utils.answer_file(
                msg,
                file,
                caption=self._format_changelog(changelog),
            )
            return

        prompt = self._build_user_prompt(
            request, current_code, current_changelog, current_filename
        )
        try:
            answer = await self._request_chat(prompt, model)
        except Exception as exc:
            await msg.edit(
                "Ошибка запроса:\n" + self._raw_block(str(exc))
            )
            return

        raw_answer = answer
        answer = self._strip_reasoning(answer)
        blocks = self._extract_blocks(answer)
        if not blocks:
            await msg.edit(
                "Ошибка: ответ должен содержать два code-блока.\n"
                + self._raw_block(raw_answer)
            )
            return

        code, changelog, filename = blocks
        filename = filename or current_filename or MODULE_FILENAME
        self._write_text(module_path, code)
        self._append_changelog(changelog_path, changelog)
        self._write_filename(dialog_id, filename)

        file = io.BytesIO(code.encode("utf-8"))
        file.name = filename
        await utils.answer_file(
            msg,
            file,
            caption=self._format_changelog(changelog),
        )

    @loader.command(ru_doc="Системные промпты для ModMaker")
    async def modprompt(self, message: Message):
        args_raw = utils.get_args_raw(message).strip()
        if not args_raw:
            enabled = self.config["prompt_enabled"]
            selected = set(self._selected_prompt_entries())
            labels = []
            for key, label in self._list_prompt_entries():
                if key in selected:
                    labels.append(label)
            current = ", ".join(labels) if labels else "—"
            await utils.answer(
                message,
                "Системные промпты: {state}\nВыбрано: {name}\nПапка: {folder}".format(
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
            self.config["prompt_enabled"] = True
            await utils.answer(message, "Системные промпты включены.")
            return

        if action == "off":
            self.config["prompt_enabled"] = False
            await utils.answer(message, "Системные промпты выключены.")
            return

        if action == "send":
            reply = await message.get_reply_message() if message.is_reply else None
            attached = await self._get_prompt_attachment(message, reply)
            if attached:
                filename, text = attached
                if tail and tail.strip().endswith((".txt", ".md", ".prompt")):
                    filename = tail.strip()
                saved = self._save_prompt_text(filename, text)
                await utils.answer(
                    message,
                    f"Промпт сохранен: {utils.escape_html(saved)}",
                )
                return

            reply_text = reply.raw_text.strip() if reply and reply.raw_text else ""
            content = tail or reply_text
            if not content:
                await utils.answer(message, "Нужен текст промпта или файл.")
                return

            filename = ""
            lines = content.splitlines()
            if (
                lines
                and lines[0].strip().endswith((".txt", ".md", ".prompt"))
                and len(lines) > 1
            ):
                filename = lines[0].strip()
                content = "\n".join(lines[1:]).strip()
            saved = self._save_prompt_text(filename, content)
            await utils.answer(
                message,
                f"Промпт сохранен: {utils.escape_html(saved)}",
            )
            return

        if action == "get":
            files = self._list_prompt_files()
            if not files:
                await utils.answer(message, "Промптов нет.")
                return
            if not tail:
                listing = "\n".join(
                    f"{idx + 1}. {utils.escape_html(name)}"
                    for idx, name in enumerate(files)
                )
                await utils.answer(message, "Промпты:\n" + listing)
                return
            filename = ""
            try:
                index = int(tail)
            except ValueError:
                filename = os.path.basename(tail.strip())
            else:
                if index < 1 or index > len(files):
                    await utils.answer(message, "Неверный номер промпта.")
                    return
                filename = files[index - 1]
            if filename not in files:
                await utils.answer(message, "Промпт не найден.")
                return
            path = os.path.join(self._prompts_dir(), filename)
            await utils.answer_file(message, path)
            return

        if action == "del":
            files = self._list_prompt_files()
            if not files:
                await utils.answer(message, "Промптов нет.")
                return
            if not tail:
                listing = "\n".join(
                    f"{idx + 1}. {utils.escape_html(name)}"
                    for idx, name in enumerate(files)
                )
                await utils.answer(message, "Промпты:\n" + listing)
                return
            filename = ""
            try:
                index = int(tail)
            except ValueError:
                filename = os.path.basename(tail.strip())
            else:
                if index < 1 or index > len(files):
                    await utils.answer(message, "Неверный номер промпта.")
                    return
                filename = files[index - 1]
            if filename not in files:
                await utils.answer(message, "Промпт не найден.")
                return
            try:
                os.remove(os.path.join(self._prompts_dir(), filename))
            except Exception:
                await utils.answer(message, "Не удалось удалить промпт.")
                return
            await utils.answer(
                message,
                f"Промпт удален: {utils.escape_html(filename)}",
            )
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
            self.config["prompt_entries"] = selected
            self.config["prompt_enabled"] = True if selected else False
            await utils.answer(
                message,
                f"Промпт {state}: {utils.escape_html(selected_label)}",
            )
            return

        await utils.answer(
            message,
            "Используй: .modprompt on | .modprompt off | .modprompt remote [номер] | .modprompt send | .modprompt get | .modprompt del",
        )

    @loader.command(ru_doc="Редактировать модуль через AI (patch-режим)")
    async def editmod(self, message: Message):
        reply = await message.get_reply_message() if message.is_reply else None
        request = self._extract_prompt(message, reply)
        if not request:
            await utils.answer(message, "Нужен текст запроса.")
            return

        dialog_id = self._active_dialog()
        if not dialog_id:
            dialog_id = self._create_dialog()
        elif not self._dialog_exists(dialog_id):
            dialog_id = self._create_dialog()

        module_path = self._module_path(dialog_id)
        changelog_path = self._changelog_path(dialog_id)
        current_changelog = self._read_text(changelog_path)
        current_filename = self._read_filename(dialog_id)

        attached = await self._get_attached_file(message, reply)
        if attached:
            filename, data = attached
            if not filename.endswith(".py"):
                await utils.answer(message, "Нужен .py файл.")
                return
            if b"\x00" in data:
                await utils.answer(message, "Файл должен быть текстовым.")
                return
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("utf-8", errors="replace")
            self._write_text(module_path, text)
            self._write_filename(dialog_id, filename)
            current_filename = filename

        exclude_names = {current_filename} if current_filename else set()
        attachments = await self._collect_attachments(
            message, reply, exclude_names=exclude_names
        )
        if attachments:
            att_text = self._format_attachments(attachments)
            request = f"{request}\n\nВЛОЖЕНИЯ:\n{att_text}".strip()

        current_code = self._read_text(module_path)
        if not current_code:
            await utils.answer(message, "Файл пустой или не найден.")
            return

        model = (self.config["model"] or DEFAULT_TEXT_MODEL).strip()
        msg = await utils.answer(message, "Думаю...")
        result = await self._run_patch_flow(
            msg,
            request,
            current_code,
            current_changelog,
            current_filename,
            model,
        )
        if not result:
            return
        updated, changelog, filename, _raw = result

        self._write_text(module_path, updated)
        self._write_filename(dialog_id, filename)
        self._append_changelog(changelog_path, changelog)

        file = io.BytesIO(updated.encode("utf-8"))
        file.name = filename
        await utils.answer_file(
            msg,
            file,
            caption=self._format_changelog(changelog),
        )

    @loader.command(ru_doc="Список моделей или выбор модели для .mod")
    async def modmodel(self, message: Message):
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
        self.config["model"] = model
        await utils.answer(message, f"Текущая модель: {utils.escape_html(model)}")

    @loader.command(aliases=["modapi", "mod-ver"], ru_doc="Выбор версии API (openai/v2)")
    async def modapi(self, message: Message):
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

    @loader.command(ru_doc="Переключить/показать диалоги")
    async def dial(self, message: Message):
        args = utils.get_args_raw(message).strip()
        dialogs = self._dialogs_list()
        active = self._active_dialog()

        if not args:
            if not dialogs:
                await utils.answer(message, "Диалоги отсутствуют.")
                return
            lines = [f"Активный: <code>{utils.escape_html(active or '—')}</code>"]
            for idx, dialog_id in enumerate(dialogs, start=1):
                lines.append(f"{idx}. <code>{utils.escape_html(dialog_id)}</code>")
            await utils.answer(message, "\n".join(lines))
            return

        dialog_id = args
        if dialog_id not in dialogs and not self._dialog_exists(dialog_id):
            await utils.answer(message, "Диалог не найден.")
            return

        if dialog_id not in dialogs:
            self._add_dialog(dialog_id)
        self._set_active_dialog(dialog_id)
        await utils.answer(message, f"Активный диалог: <code>{utils.escape_html(dialog_id)}</code>")

    @loader.command(ru_doc="Выйти из текущего диалога")
    async def exitdial(self, message: Message):
        self._clear_active_dialog()
        await utils.answer(message, "Диалог сброшен.")

    @loader.command(ru_doc="Удалить активный диалог")
    async def deldial(self, message: Message):
        args = utils.get_args_raw(message).strip()
        dialog_id = args or self._active_dialog()
        if not dialog_id:
            await utils.answer(message, "Нет выбранного диалога.")
            return
        if not self._dialog_exists(dialog_id):
            await utils.answer(message, "Диалог не найден.")
            return

        try:
            import shutil

            shutil.rmtree(self._dialog_dir(dialog_id))
        except Exception:
            await utils.answer(message, "Не удалось удалить диалог.")
            return

        self._remove_dialog(dialog_id)
        if self._active_dialog() == dialog_id:
            self._clear_active_dialog()
        await utils.answer(message, f"Диалог удален: <code>{utils.escape_html(dialog_id)}</code>")

    @loader.command(ru_doc="Удалить все диалоги и модули")
    async def delalldial(self, message: Message):
        try:
            import shutil

            root = self._ai_root()
            if os.path.isdir(root):
                shutil.rmtree(root)
            os.makedirs(root, exist_ok=True)
        except Exception:
            await utils.answer(message, "Не удалось удалить диалоги.")
            return

        if self._dialogs is None:
            self._dialogs = self.pointer("dialogs", [])
        self._dialogs.clear()
        self._clear_active_dialog()
        await utils.answer(message, "Все диалоги удалены.")
