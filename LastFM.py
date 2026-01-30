__version__ = (1, 1, 0)
# meta developer: @etopizdesblin
# requires: aiohttp
# scope: hikka_only
# scope: hikka_min 1.2.10

import asyncio
import io
import logging
import math
import textwrap
import urllib.parse
import typing
import time
from typing import Optional, Dict, Any

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import aiohttp
from .. import loader, utils
from herokutl.types import Message

logger = logging.getLogger(__name__)

# Last.fm API URL
LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={}&api_key={}&format=json&limit=1"
LASTFM_TRACK_INFO_URL = (
    "http://ws.audioscrobbler.com/2.0/?method=track.getInfo&artist={}&track={}"
    "&api_key={}&format=json&autocorrect=1"
)

STOP_GRACE_SECONDS = 90
class Banners:
    def __init__(
        self,
        title: str,
        artists: list,
        duration: int,
        progress: int,
        track_cover: bytes,
        album_title: str = "Сингл",
        meta_info: str = "Last.fm",
        blur_strength: int = 0,
        blur_style: str = "gaussian",
    ):
        self.title = title
        self.artists = artists
        self.duration = duration
        self.progress = progress
        self.track_cover = track_cover
        self.album_title = album_title
        self.meta_info = meta_info
        self.blur_strength = blur_strength
        self.blur_style = blur_style

        self.fonts_urls = [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat-Bold.ttf",
            "https://raw.githubusercontent.com/kamekuro/assets/master/fonts/Onest-Bold.ttf",
        ]

        self.onest_b = "https://raw.githubusercontent.com/kamekuro/assets/master/fonts/Onest-Bold.ttf"
        self.onest_r = "https://raw.githubusercontent.com/kamekuro/assets/master/fonts/Onest-Regular.ttf"

    def measure(
        self, text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw
    ):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def _normalize_blur_strength(self) -> int:
        try:
            strength = int(self.blur_strength)
        except (TypeError, ValueError):
            return 0
        return max(0, min(100, strength))

    def _apply_wave(self, image: Image.Image, strength: int) -> Image.Image:
        if strength <= 0:
            return image
        width, height = image.size
        amplitude = max(1, int(strength / 8))
        period = max(20, int(120 - strength))
        result = Image.new("RGBA", (width, height))
        for y in range(height):
            offset = int(math.sin(y / period) * amplitude)
            row = image.crop((0, y, width, y + 1))
            result.paste(row, (offset, y))
        return result

    def _apply_blur(self, image: Image.Image) -> Image.Image:
        strength = self._normalize_blur_strength()
        if strength <= 0:
            return image
        radius = max(1, int(round(strength / 4)))
        style = (self.blur_style or "gaussian").lower().strip()
        if style == "wave":
            image = self._apply_wave(image, strength)
            return image.filter(ImageFilter.GaussianBlur(radius=max(1, radius // 2)))
        if style == "matte":
            image = image.filter(ImageFilter.BoxBlur(radius))
            size = max(3, radius if radius % 2 == 1 else radius + 1)
            return image.filter(ImageFilter.MedianFilter(size=size))
        if style == "box":
            return image.filter(ImageFilter.BoxBlur(radius))
        return image.filter(ImageFilter.GaussianBlur(radius=radius))

    def ultra(self):
        WIDTH, HEIGHT = 2560, 1220

        font_bytes = None
        for url in self.fonts_urls:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    font_bytes = resp.content
                    break
            except Exception:
                continue

        def get_font(size):
            if font_bytes:
                try:
                    return ImageFont.truetype(io.BytesIO(font_bytes), size)
                except Exception:
                    pass
            return ImageFont.load_default()

        original_cover = Image.open(io.BytesIO(self.track_cover)).convert("RGBA")

        dominant_color_img = original_cover.resize((1, 1), Image.Resampling.LANCZOS)
        dominant_color = dominant_color_img.getpixel((0, 0))

        r, g, b, a = dominant_color
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        if brightness < 60:
            r = min(255, r + 60)
            g = min(255, g + 60)
            b = min(255, b + 60)
            dominant_color = (r, g, b, 255)

        background = original_cover.copy()
        bg_w, bg_h = background.size

        target_ratio = WIDTH / HEIGHT
        current_ratio = bg_w / bg_h

        if current_ratio > target_ratio:
            new_w = int(bg_h * target_ratio)
            offset = (bg_w - new_w) // 2
            background = background.crop((offset, 0, offset + new_w, bg_h))
        else:
            new_h = int(bg_w / target_ratio)
            offset = (bg_h - new_h) // 2
            background = background.crop((0, offset, bg_w, offset + new_h))

        background = background.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        background = self._apply_blur(background)

        dark_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 180))
        background = Image.alpha_composite(background, dark_overlay)

        cover_size = 500
        cover_x = (WIDTH - cover_size) // 2
        cover_y = 160

        glow_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw_glow = ImageDraw.Draw(glow_layer)

        glow_rect_size = 620
        g_x = (WIDTH - glow_rect_size) // 2
        g_y = cover_y + (cover_size - glow_rect_size) // 2

        draw_glow.rounded_rectangle(
            (g_x, g_y, g_x + glow_rect_size, g_y + glow_rect_size),
            radius=50,
            fill=dominant_color,
        )

        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=60))
        glow_layer = ImageEnhance.Brightness(glow_layer).enhance(1.4)
        glow_layer = ImageEnhance.Color(glow_layer).enhance(1.2)

        background = Image.alpha_composite(background, glow_layer)

        cover_img = original_cover.resize((cover_size, cover_size), Image.Resampling.LANCZOS)

        mask = Image.new("L", (cover_size, cover_size), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle((0, 0, cover_size, cover_size), radius=45, fill=255)

        background.paste(cover_img, (cover_x, cover_y), mask)

        draw = ImageDraw.Draw(background)
        center_x = WIDTH // 2
        current_y = cover_y + cover_size + 130

        def draw_text_shadow(text, pos, font, fill="white", anchor="ms"):
            x, y = pos
            draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 240), anchor=anchor)
            draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

        font_title = get_font(100)
        title_text = self.title
        if len(title_text) > 30:
            title_text = title_text[:30] + "..."
        draw_text_shadow(title_text.upper(), (center_x, current_y), font_title)

        current_y += 85

        font_artist = get_font(65)
        artist_text = ", ".join(self.artists)
        if len(artist_text) > 45:
            artist_text = artist_text[:45] + "..."
        draw_text_shadow(artist_text.upper(), (center_x, current_y), font_artist, fill=(255, 255, 255, 240))

        current_y += 80

        bar_width = 800
        bar_height = 6
        font_time = get_font(40)

        bar_start_x = center_x - (bar_width // 2)
        bar_end_x = center_x + (bar_width // 2)
        bar_y = current_y

        total_mins = self.duration // 1000 // 60
        total_secs = (self.duration // 1000) % 60
        total_time_str = f"{total_mins}:{total_secs:02d}"

        cur_mins = self.progress // 1000 // 60
        cur_secs = (self.progress // 1000) % 60
        cur_time_str = f"{cur_mins}:{cur_secs:02d}"

        draw_text_shadow(cur_time_str, (bar_start_x - 30, bar_y), font_time, anchor="rm")
        draw_text_shadow(total_time_str, (bar_end_x + 30, bar_y), font_time, anchor="lm")

        draw.line([(bar_start_x, bar_y), (bar_end_x, bar_y)], fill=(255, 255, 255, 80), width=bar_height)

        if self.duration > 0:
            progress_ratio = self.progress / self.duration
        else:
            progress_ratio = 0
        progress_px = int(bar_width * progress_ratio)
        if progress_px > bar_width:
            progress_px = bar_width

        draw.line([(bar_start_x, bar_y), (bar_start_x + progress_px, bar_y)], fill="white", width=bar_height + 5)
        draw.ellipse((bar_start_x + progress_px - 10, bar_y - 10, bar_start_x + progress_px + 10, bar_y + 10), fill="white")

        current_y += 80

        font_album = get_font(50)
        album_text = self.album_title
        if len(album_text) > 50:
            album_text = album_text[:50] + "..."
        draw_text_shadow(album_text, (center_x, current_y), font_album, fill=(230, 230, 230))
        current_y += 60

        font_meta = get_font(40)
        draw_text_shadow(self.meta_info, (center_x, current_y), font_meta, fill=(210, 210, 210))

        by = io.BytesIO()
        background.save(by, format="PNG")
        by.seek(0)
        by.name = "banner.png"
        return by

    def new(self):
        W, H = 1920, 768
        try:
            title_font = ImageFont.truetype(io.BytesIO(requests.get(self.onest_b).content), 80)
            artist_font = ImageFont.truetype(io.BytesIO(requests.get(self.onest_b).content), 55)
            time_font = ImageFont.truetype(io.BytesIO(requests.get(self.onest_b).content), 36)
        except Exception:
            title_font = artist_font = time_font = ImageFont.load_default()

        track_cov = Image.open(io.BytesIO(self.track_cover)).convert("RGBA")
        banner = (
            track_cov.resize((W, W))
            .crop((0, (W - H) // 2, W, ((W - H) // 2) + H))
        )
        banner = self._apply_blur(banner)
        banner = ImageEnhance.Brightness(banner).enhance(0.3)
        draw = ImageDraw.Draw(banner)

        track_cov = track_cov.resize((H - 250, H - 250))
        mask = Image.new("L", track_cov.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, track_cov.size[0], track_cov.size[1]), radius=35, fill=255
        )
        track_cov.putalpha(mask)
        track_cov = track_cov.crop(track_cov.getbbox())
        banner.paste(track_cov, (75, 75), mask)

        space = (643, 75, 1870, 593)
        title_lines = textwrap.wrap(self.title, width=23)
        if len(title_lines) > 2:
            title_lines = title_lines[:2]
            title_lines[-1] = title_lines[-1][:-1] + "…"
        artist_lines = textwrap.wrap(", ".join(self.artists), width=23)
        if len(artist_lines) > 1:
            artist_lines = artist_lines[:1]
            artist_lines[-1] = artist_lines[-1][:-1] + "…"
        lines = title_lines + artist_lines
        lines_sizes = [
            self.measure(
                line, artist_font if (i == len(lines) - 1) else title_font, draw
            )
            for i, line in enumerate(lines)
        ]
        total_sizes = [sum(w for w, _ in lines_sizes), sum(h for _, h in lines_sizes)]
        spacing = (title_font.size if hasattr(title_font, "size") else 80) + 10
        y_start = space[1] + ((space[3] - space[1] - total_sizes[1]) / 2)
        for i, line in enumerate(lines):
            w, _ = lines_sizes[i]
            draw.text(
                (space[0] + (space[2] - space[0] - w) / 2, y_start),
                line,
                font=(artist_font if (i == (len(lines) - 1)) else title_font),
                fill="#FFFFFF",
            )
            y_start += spacing

        draw.text(
            (768, 600),
            f"{(self.progress // 1000 // 60):02}:{(self.progress // 1000 % 60):02}",
            font=time_font,
            fill="#FFFFFF",
        )
        draw.text(
            (1745, 600),
            f"{(self.duration // 1000 // 60):02}:{(self.duration // 1000 % 60):02}",
            font=time_font,
            fill="#FFFFFF",
        )

        draw.rounded_rectangle(
            [768, 650, 768 + 1072, 650 + 15], radius=15 // 2, fill="#A0A0A0"
        )
        if self.duration > 0:
            progress_ratio = min(max(self.progress / self.duration, 0), 1)
        else:
            progress_ratio = 0
        draw.rounded_rectangle(
            [768, 650, 768 + int(1072 * progress_ratio), 650 + 15],
            radius=15 // 2,
            fill="#FFFFFF",
        )

        by = io.BytesIO()
        banner.save(by, format="PNG")
        by.seek(0)
        by.name = "banner.png"
        return by

    def old(self):
        w, h = 1920, 768
        try:
            title_font = ImageFont.truetype(io.BytesIO(requests.get(self.onest_b).content), 80)
            art_font = ImageFont.truetype(io.BytesIO(requests.get(self.onest_r).content), 55)
            time_font = ImageFont.truetype(io.BytesIO(requests.get(self.onest_b).content), 36)
        except Exception:
            title_font = art_font = time_font = ImageFont.load_default()

        track_cov = Image.open(io.BytesIO(self.track_cover)).convert("RGBA")
        banner = (
            track_cov.resize((w, w))
            .crop((0, (w - h) // 2, w, ((w - h) // 2) + h))
        )
        banner = self._apply_blur(banner)
        banner = ImageEnhance.Brightness(banner).enhance(0.3)

        track_cov = track_cov.resize((banner.size[1] - 150, banner.size[1] - 150))
        mask = Image.new("L", track_cov.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, track_cov.size[0], track_cov.size[1]), radius=35, fill=255
        )
        track_cov.putalpha(mask)
        track_cov = track_cov.crop(track_cov.getbbox())
        banner.paste(track_cov, (75, 75), mask)

        title_lines = textwrap.wrap(self.title, 23)
        if len(title_lines) > 1:
            title_lines[1] = (
                title_lines[1] + "..." if len(title_lines) > 2 else title_lines[1]
            )
        title_lines = title_lines[:2]
        artists_lines = textwrap.wrap(" • ".join(self.artists), width=40)
        if len(artists_lines) > 1:
            for index, art in enumerate(artists_lines):
                if "•" in art[-2:]:
                    artists_lines[index] = art[: art.rfind("•") - 1]

        draw = ImageDraw.Draw(banner)
        x, y = 150 + track_cov.size[0], 110
        for index, line in enumerate(title_lines):
            draw.text((x, y), line, font=title_font, fill="#FFFFFF")
            if index != len(title_lines) - 1:
                y += 70
        x, y = 150 + track_cov.size[0], 110 * 2
        if len(title_lines) > 1:
            y += 70
        for index, line in enumerate(artists_lines):
            draw.text((x, y), line, font=art_font, fill="#A0A0A0")
            if index != len(artists_lines) - 1:
                y += 50

        draw.text(
            (75, 650),
            f"{(self.progress // 1000 // 60):02}:{(self.progress // 1000 % 60):02}",
            font=time_font,
            fill="#FFFFFF",
        )
        draw.text(
            (1745, 650),
            f"{(self.duration // 1000 // 60):02}:{(self.duration // 1000 % 60):02}",
            font=time_font,
            fill="#FFFFFF",
        )
        draw.rounded_rectangle([75, 700, 1845, 715], radius=15 // 2, fill="#A0A0A0")

        progress_width = 1770
        if self.duration > 0:
            fill_width = int(progress_width * (self.progress / self.duration))
        else:
            fill_width = 0

        draw.rounded_rectangle(
            [75, 700, 75 + fill_width, 715],
            radius=15 // 2,
            fill="#FFFFFF",
        )

        by = io.BytesIO()
        banner.save(by, format="PNG")
        by.seek(0)
        by.name = "banner.png"
        return by

@loader.tds
class LastFMNowPlayingMod(loader.Module):
    """Отслеживание текущего трека из Last.fm с обновлением сообщения"""
    
    strings = {
        "name": "LastFm",
        "now_playing": "{time} • {artist} - {title}",
        "not_playing": "🎵 Сейчас ничего не играет",
        "config_api_key_doc": "Ваш API ключ Last.fm (обязательно).",
        "config_username_doc": "Ваш логин Last.fm.",
        "config_chat_doc": "ID чата или @username канала, куда отправлять статус.",
        "config_msg_doc": "ID сообщения, которое нужно постоянно редактировать.",
        "config_format_doc": "Формат сообщения\n{artist} - исполнитель\n{title} - название\n{album} - альбом\n{time} - время\n{track} - artist - title",
        "config_interval_doc": "Интервал проверки в секундах",
        "config_no_track_doc": "Текст когда ничего не играет",
        "config_now_playing_text_doc": "Текст для .ynow (карточка)\n{artist} {title} {album} {link}",
        "config_banner_version_doc": "Версия карточки: old | new | ultra",
        "config_blur_strength_doc": "Размытие фона в .ynow (0-100)",
        "config_blur_style_doc": "Тип размытия фона: gaussian | matte | wave | box",
        "config_empty_cover_url_doc": "URL пустой картинки для статуса 'Сейчас ничего не играет'",
        "started": "✅ <b>Отслеживание запущено!</b>",
        "stopped": "🛑 <b>Отслеживание остановлено</b>",
        "no_creds": "❌ <b>Не указаны данные Last.fm!</b>",
        "status": "📊 <b>Статус LastFMNowPlaying:</b>",
        "track_details": "🎤 <b>Исполнитель:</b> {artist}\n🎵 <b>Трек:</b> {title}\n💿 <b>Альбом:</b> {album}\n🕐 <b>Время:</b> {time}",
        "_cmd_doc_lfmstart": "Запустить отслеживание треков",
        "_cmd_doc_lfmstop": "Остановить отслеживание треков",
        "_cmd_doc_lfmstatus": "Показать статус отслеживания",
        "_cmd_doc_lfmnow": "Показать текущий трек",
        "_cmd_doc_lfmtest": "Протестировать формат с примерным треком",
    }

    strings_ru = {
        "_cls_doc": "Отслеживание текущего трека из Last.fm",
        "_cmd_doc_lfmstart": "Запустить отслеживание треков",
        "_cmd_doc_lfmstop": "Остановить отслеживание треков",
        "_cmd_doc_lfmstatus": "Показать статус отслеживания",
        "_cmd_doc_lfmnow": "Показать текущий трек",
        "_cmd_doc_lfmtest": "Протестировать формат с примерным треком",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                "",
                lambda: self.strings("config_api_key_doc"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "username",
                "",
                lambda: self.strings("config_username_doc"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "chat_id",
                None,
                lambda: self.strings("config_chat_doc"),
                validator=loader.validators.TelegramID(),
            ),
            loader.ConfigValue(
                "message_id",
                None,
                lambda: self.strings("config_msg_doc"),
                validator=loader.validators.Integer(),
            ),
            loader.ConfigValue(
                "format",
                "{time} • {artist} - {title}",
                lambda: self.strings("config_format_doc"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "interval",
                15,
                lambda: self.strings("config_interval_doc"),
                validator=loader.validators.Integer(minimum=5, maximum=300),
            ),
            loader.ConfigValue(
                "no_track_text",
                "Сейчас ничего не играет",
                lambda: self.strings("config_no_track_doc"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "empty_cover_url",
                "",
                lambda: self.strings("config_empty_cover_url_doc"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "now_playing_text",
                (
                    "<emoji document_id=5474304919651491706>🎧</emoji> <b>{artist} — {title}</b>\n"
                    "<emoji document_id=6039630677182254664>💿</emoji> <b>{album}</b>\n"
                    "<emoji document_id=5242574232688298747>🔗</emoji> <b>{link}</b>"
                ),
                lambda: self.strings("config_now_playing_text_doc"),
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "banner_version",
                "ultra",
                lambda: self.strings("config_banner_version_doc"),
                validator=loader.validators.Choice(["old", "new", "ultra"]),
            ),
            loader.ConfigValue(
                "set_blur",
                35,
                lambda: self.strings("config_blur_strength_doc"),
                validator=loader.validators.Integer(minimum=0, maximum=100),
            ),
            loader.ConfigValue(
                "blur_style",
                "gaussian",
                lambda: self.strings("config_blur_style_doc"),
                validator=loader.validators.Choice(["gaussian", "matte", "wave", "box"]),
            ),
        )
        self._tracking = False
        self._task: Optional[asyncio.Task] = None
        self._last_track_id = None
        self._track_started_at = None
        self._no_track_hits = 0
        self._track_duration_ms = None
        self._blocked_track_id = None
        self._target_peer = None
        self._card_message_id = None
        self._http_session = None
        self._is_ready = False

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self._http_session = aiohttp.ClientSession()
        await self._resolve_peer()
        self._is_ready = True
        
    async def on_unload(self):
        if self._tracking:
            self._tracking = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        if self._http_session:
            await self._http_session.close()

    async def _resolve_peer(self):
        """Разрешает ID чата в InputPeer для использования в Telegram API."""
        chat_id_raw = self.config["chat_id"]
        
        if not chat_id_raw:
            self._target_peer = None
            return False

        chat_id_str = str(chat_id_raw)
        
        if chat_id_str.isdigit() and len(chat_id_str) >= 10:
            chat_id = int(f"-100{chat_id_str}")
        elif chat_id_str.startswith('-') and chat_id_str[1:].isdigit():
            chat_id = int(chat_id_str)
        else:
            chat_id = chat_id_raw

        try:
            self._target_peer = await self.client.get_input_entity(chat_id)
            return True
        except Exception as e:
            logger.error(f"Could not resolve chat ID {chat_id_raw} ({chat_id}): {e}") 
            self._target_peer = None
            return False

    async def _set_target_peer_from_message(self, message: Message) -> bool:
        try:
            chat_id = utils.get_chat_id(message)
        except Exception as e:
            logger.error(f"Could not read chat id: {e}")
            return False
        try:
            self._target_peer = await self.client.get_input_entity(chat_id)
            return True
        except Exception as e:
            logger.error(f"Could not resolve chat ID {chat_id}: {e}")
            self._target_peer = None
            return False

    @staticmethod
    def _track_key(artist: str, title: str) -> str:
        base = f"{artist or ''} {title or ''}".lower()
        return " ".join(base.split())

    def _ensure_track_start(self, track_info: Dict[str, Any]) -> None:
        track_id = track_info.get("unique_id")
        if not track_id:
            return
        if track_id != self._last_track_id:
            self._last_track_id = track_id
            start_ts = track_info.get("start_ts")
            if start_ts:
                if start_ts > 10_000_000_000:
                    self._track_started_at = start_ts / 1000
                else:
                    self._track_started_at = float(start_ts)
            else:
                self._track_started_at = time.time()
            self._track_duration_ms = None
            self._blocked_track_id = None

    def _estimate_progress(
        self,
        track_info: Dict[str, Any],
        duration: int,
    ) -> typing.Tuple[int, int]:
        now_ms = int(time.time() * 1000)
        progress = 0
        start_ts = track_info.get("start_ts")
        if start_ts and duration:
            progress = max(0, min(now_ms - start_ts, duration))
        elif self._track_started_at and duration:
            elapsed_ms = int((time.time() - self._track_started_at) * 1000)
            progress = max(0, min(elapsed_ms, duration))
        return progress, duration

    async def _build_no_track_card(self, text: str) -> io.BytesIO:
        url = (self.config["empty_cover_url"] or "").strip()
        if url:
            try:
                cover = await self._download_cover_bytes(url)
            except Exception:
                cover = None
            if cover:
                try:
                    image = Image.open(io.BytesIO(cover)).convert("RGB")
                    buf = io.BytesIO()
                    image.save(buf, format="PNG")
                    buf.seek(0)
                    buf.name = "status.png"
                    return buf
                except Exception:
                    pass

        image = Image.new("RGB", (32, 32), (12, 12, 12))
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        buf.name = "status.png"
        return buf

    async def _build_now_playing_card(
        self, track_info: Dict[str, Any]
    ) -> typing.Tuple[str, io.BytesIO]:
        details = await self._get_track_details(
            track_info.get("artist", ""),
            track_info.get("title", ""),
            track_info.get("images"),
        )

        images = details.get("images") or track_info.get("images") or []
        cover_url = self._pick_image_url(images)
        cover_bytes = await self._download_cover_bytes(cover_url)
        if not cover_bytes:
            cover_bytes = self._placeholder_cover()

        album_title = details.get("album_title") or track_info.get("album") or "Сингл"
        track_info["album"] = album_title
        duration = details.get("duration") or 0
        meta_info = details.get("meta_info") or "Last.fm"

        link = details.get("url") or track_info.get("url") or ""
        if not link:
            artist_slug = urllib.parse.quote(track_info.get("artist", ""), safe="")
            title_slug = urllib.parse.quote(track_info.get("title", ""), safe="")
            link = f"https://www.last.fm/music/{artist_slug}/_/{title_slug}"

        self._ensure_track_start(track_info)
        if duration:
            self._track_duration_ms = duration
        progress, duration = self._estimate_progress(track_info, duration)
        meta_info = f"{meta_info} • Last.fm" if meta_info else "Last.fm"

        out = self._format_now_playing_text(track_info, link)
        banners = Banners(
            title=track_info.get("title", "Unknown Track"),
            artists=[track_info.get("artist", "Unknown Artist")],
            duration=duration,
            progress=progress,
            track_cover=cover_bytes,
            album_title=album_title,
            meta_info=meta_info,
            blur_strength=self.config["set_blur"],
            blur_style=self.config["blur_style"],
        )
        file = getattr(banners, self.config["banner_version"], banners.new)()
        return out, file

    async def _send_or_update_text(self, text: str):
        file = await self._build_no_track_card(text)
        if self._card_message_id and self._target_peer:
            try:
                await self.client.edit_message(
                    self._target_peer,
                    self._card_message_id,
                    text,
                    file=file,
                    parse_mode="HTML",
                )
                return
            except Exception as e:
                if "message was not modified" in str(e).lower():
                    return
                logger.warning(f"Failed to edit status card: {e}")
                return

        if not self._target_peer:
            return
        try:
            msg = await self.client.send_message(
                self._target_peer,
                text,
                file=file,
                parse_mode="HTML",
            )
            self._card_message_id = msg.id
        except Exception as e:
            logger.error(f"Failed to send status card: {e}")

    async def _send_or_update_card(self, track_info: Dict[str, Any]):
        out, file = await self._build_now_playing_card(track_info)
        if self._card_message_id and self._target_peer:
            try:
                await self.client.edit_message(
                    self._target_peer,
                    self._card_message_id,
                    out,
                    file=file,
                    parse_mode="HTML",
                )
                return
            except Exception as e:
                if "message was not modified" in str(e).lower():
                    return
                logger.warning(f"Failed to edit card message: {e}")
                return

        if not self._target_peer:
            return
        try:
            msg = await self.client.send_message(
                self._target_peer,
                out,
                file=file,
                parse_mode="HTML",
            )
            self._card_message_id = msg.id
        except Exception as e:
            logger.error(f"Failed to send card message: {e}")

    async def _get_track_info(self) -> Optional[Dict[str, Any]]:
        """Получает информацию о текущем треке из Last.fm"""
        if not self.config["api_key"] or not self.config["username"]:
            return None

        url = LASTFM_API_URL.format(self.config["username"], self.config["api_key"])

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self._http_session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                
            if data.get("error"):
                logger.error(f"Last.fm API error [{data.get('error')}] returned: {data.get('message')}")
                return None
                
        except aiohttp.ClientError as e:
            logger.error(f"Last.fm API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing Last.fm response: {e}")
            return None

        tracks = data.get("recenttracks", {}).get("track", [])
        
        if not tracks:
            return None

        track = tracks[0]
        now_playing_attr = track.get("@attr", {}).get("nowplaying")
        is_playing = now_playing_attr == "true"
        
        if not is_playing:
            return None

        images = track.get("image") or []
        track_url = track.get("url") or ""
        artist = track.get("artist", {}).get("#text", "Unknown Artist")
        title = track.get("name", "Unknown Track")
        return {
            "artist": artist,
            "title": title,
            "album": track.get("album", {}).get("#text", ""),
            "nowplaying": is_playing,
            "unique_id": f"PLAYING|{self._track_key(artist, title)}",
            "images": images,
            "url": track_url,
            "start_ts": int(track.get("date", {}).get("uts")) * 1000
            if track.get("date", {}).get("uts")
            else None,
        }

    @staticmethod
    def _pick_image_url(images: Any) -> str:
        if not images:
            return ""
        if isinstance(images, dict):
            images = [images]
        size_order = {"mega": 5, "extralarge": 4, "large": 3, "medium": 2, "small": 1}
        best_url = ""
        best_rank = -1
        for item in images:
            if not isinstance(item, dict):
                continue
            url = item.get("#text") or item.get("url") or ""
            size = str(item.get("size") or "").lower()
            rank = size_order.get(size, 0)
            if url and rank >= best_rank:
                best_url = url
                best_rank = rank
        return best_url

    async def _get_track_details(
        self, artist: str, title: str, fallback_images: Any
    ) -> Dict[str, Any]:
        url = LASTFM_TRACK_INFO_URL.format(
            urllib.parse.quote_plus(artist),
            urllib.parse.quote_plus(title),
            self.config["api_key"],
        )
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with self._http_session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
        except Exception:
            return {}

        track = data.get("track") or {}
        duration_raw = track.get("duration") or 0
        try:
            duration = int(duration_raw)
        except (TypeError, ValueError):
            duration = 0

        album = track.get("album") or {}
        album_title = album.get("title") or ""
        images = album.get("image") or track.get("image") or fallback_images or []

        tags = track.get("toptags", {}).get("tag") or []
        if isinstance(tags, dict):
            tags = [tags]
        genre = ""
        if tags and isinstance(tags, list):
            genre = str(tags[0].get("name") or "")

        meta_info = genre.capitalize() if genre else "Last.fm"
        return {
            "duration": duration,
            "album_title": album_title,
            "images": images,
            "meta_info": meta_info,
            "url": track.get("url") or "",
        }

    async def _download_cover_bytes(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self._http_session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception:
            return None

    @staticmethod
    def _placeholder_cover() -> bytes:
        image = Image.new("RGB", (1000, 1000), (18, 18, 18))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        text = "NO COVER"
        box = draw.textbbox((0, 0), text, font=font)
        x = (1000 - (box[2] - box[0])) // 2
        y = (1000 - (box[3] - box[1])) // 2
        draw.text((x, y), text, fill=(210, 210, 210), font=font)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    def _format_now_playing_text(self, track: Dict[str, Any], link: str) -> str:
        artist = utils.escape_html(track.get("artist", "Unknown Artist"))
        title = utils.escape_html(track.get("title", "Unknown Track"))
        album = utils.escape_html(track.get("album") or "Сингл")
        link_html = f'<a href="{link}">Last.fm</a>' if link else "Last.fm"
        variables = {
            "artist": artist,
            "performer": artist,
            "title": title,
            "album": album,
            "device": "Last.fm",
            "volume": "—",
            "track_id": "",
            "album_id": "",
            "playing_from": "Last.fm",
            "link": link_html,
        }
        try:
            return self.config["now_playing_text"].format(**variables)
        except Exception:
            return f"🎧 {artist} — {title}\n💿 {album}\n🔗 {link_html}"

    async def _tracking_loop(self):
        """Основной цикл отслеживания"""
        while self._tracking:
            try:
                if not self._is_ready or not self.config["api_key"] or not self.config["username"]:
                    await asyncio.sleep(10)
                    continue

                track_info = await self._get_track_info()

                if track_info:
                    track_id = track_info.get("unique_id")
                    if self._blocked_track_id and track_id == self._blocked_track_id:
                        await asyncio.sleep(self.config["interval"])
                        continue
                    if self._blocked_track_id and track_id != self._blocked_track_id:
                        self._blocked_track_id = None

                    self._no_track_hits = 0
                    if track_id != self._last_track_id:
                        await self._send_or_update_card(track_info)
                    else:
                        if self._track_duration_ms and self._track_started_at:
                            elapsed = time.time() - self._track_started_at
                            if elapsed > (self._track_duration_ms / 1000) + STOP_GRACE_SECONDS:
                                self._blocked_track_id = track_id
                                self._last_track_id = None
                                self._track_started_at = None
                                self._track_duration_ms = None
                                await self._send_or_update_text(self.config["no_track_text"])
                else:
                    self._no_track_hits += 1
                    if self._last_track_id is not None and self._no_track_hits >= 2:
                        self._last_track_id = None
                        self._track_started_at = None
                        self._track_duration_ms = None
                        self._no_track_hits = 0
                        await self._send_or_update_text(self.config["no_track_text"])
                
                await asyncio.sleep(self.config["interval"])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in tracking loop: {e}")
                await asyncio.sleep(30)

    @loader.command(
        ru_doc="Запустить отслеживание карточки в текущем чате"
    )
    async def ystartcmd(self, message):
        """Запустить отслеживание"""
        if not self.config["api_key"] or not self.config["username"]:
            await utils.answer(message, self.strings["no_creds"])
            return

        if self._tracking:
            await utils.answer(message, "🔄 <b>Отслеживание уже запущено</b>")
            return

        ok = await self._set_target_peer_from_message(message)
        if not ok or not self._target_peer:
            await utils.answer(message, "❌ <b>Не удалось определить чат</b>")
            return

        self._card_message_id = None
        self._last_track_id = None
        self._track_started_at = None
        self._track_duration_ms = None
        self._blocked_track_id = None
        self._no_track_hits = 0
        self._tracking = True
        self._task = asyncio.create_task(self._tracking_loop())

        await utils.answer(message, self.strings["started"])

    @loader.command(
        ru_doc="Остановить отслеживание карточки"
    )
    async def ystopcmd(self, message):
        """Остановить отслеживание"""
        if not self._tracking:
            await utils.answer(message, "🛑 <b>Отслеживание не запущено</b>")
            return

        self._tracking = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        await utils.answer(message, self.strings["stopped"])


    @loader.command(ru_doc="👉 Получить баннер трека из Last.fm", alias="ynow")
    async def ynowcmd(self, message):
        if not self.config["api_key"] or not self.config["username"]:
            await utils.answer(message, self.strings["no_creds"])
            return

        await utils.answer(message, "⏳ <b>Генерирую карточку...</b>")

        track_info = await self._get_track_info()
        if not track_info:
            await utils.answer(message, self.config["no_track_text"])
            return
        out, file = await self._build_now_playing_card(track_info)
        await utils.answer(message=message, response=out, file=file)
