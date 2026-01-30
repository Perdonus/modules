__version__ = (1, 0, 0)
# meta developer: @etopizdesblin

import datetime
import typing

from herokutl.tl.functions.account import UpdateProfileRequest
from herokutl.tl.types import Message

from .. import loader, utils

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


FULLWIDTH_TRANS = str.maketrans("0123456789:", "０１２３４５６７８９：")


@loader.tds
class TimeNameMod(loader.Module):
    """Show current Moscow time in profile name"""

    strings = {"name": "TimeName"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "enabled",
                False,
                "Enable time-based name",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "style",
                "fullwidth",
                "Time style: fullwidth or plain",
                validator=loader.validators.Choice(["fullwidth", "plain"]),
            ),
        )
        self._orig_first: typing.Optional[str] = None
        self._last_value: typing.Optional[str] = None

    async def client_ready(self):
        await self._capture_original()
        if self.config["enabled"] and not self._name_loop.status:
            self._name_loop.start()

    def _load_saved_name(self) -> typing.Optional[str]:
        saved = self.get("orig_name", None)
        if not isinstance(saved, dict):
            return None
        first = saved.get("first")
        if isinstance(first, str):
            return first
        return None

    async def _capture_original(self, force: bool = False):
        if not force:
            saved = self._load_saved_name()
            if saved is not None:
                self._orig_first = saved
                return
        me = await self._client.get_me()
        self._orig_first = me.first_name or ""
        self.set(
            "orig_name",
            {"first": self._orig_first},
        )

    @staticmethod
    def _moscow_now() -> datetime.datetime:
        if ZoneInfo is not None:
            return datetime.datetime.now(ZoneInfo("Europe/Moscow"))
        return datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=3))
        )

    def _format_time(self) -> str:
        value = self._moscow_now().strftime("%H:%M").replace(" ", "")
        if self.config["style"] == "fullwidth":
            value = value.translate(FULLWIDTH_TRANS)
            value = value.replace(" ", "")
        return value

    async def _apply_name(self, value: str):
        await self._client(
            UpdateProfileRequest(
                first_name=value,
            )
        )

    async def _restore_name(self):
        saved = self._load_saved_name()
        if saved is not None:
            first_name = saved
        else:
            if self._orig_first is None:
                await self._capture_original(force=True)
            first_name = self._orig_first or ""
        await self._client(
            UpdateProfileRequest(
                first_name=first_name,
            )
        )

    @loader.loop(interval=5, autostart=False)
    async def _name_loop(self):
        if not self.config["enabled"]:
            return
        await self._capture_original()
        current = self._format_time()
        if current != self._last_value:
            await self._apply_name(current)
            self._last_value = current

    @loader.command(ru_doc="Вкл/выкл имени-времени")
    async def timename(self, message: Message):
        was_enabled = self.config["enabled"]
        args = utils.get_args_raw(message).strip().lower()
        if args in ("on", "enable", "start", "1", "да"):
            self.config["enabled"] = True
        elif args in ("off", "disable", "stop", "0", "нет"):
            self.config["enabled"] = False
        else:
            self.config["enabled"] = not self.config["enabled"]

        if self.config["enabled"]:
            if not was_enabled:
                await self._capture_original(force=True)
                current = self._format_time()
                await self._apply_name(current)
                self._last_value = current
            if not self._name_loop.status:
                self._name_loop.start()
            await utils.answer(message, "Time name: ON")
        else:
            await self._restore_name()
            await utils.answer(message, "Time name: OFF")
