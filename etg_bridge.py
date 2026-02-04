import asyncio
import base64
import datetime
import hashlib
import io
import json
import os
import platform
import re
import shutil
import socket
import ssl
import struct
import subprocess
import threading
import time
import typing
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests
from herokutl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall

MAX_BODY_BYTES = 4 * 1024 * 1024
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OFFICIAL_UPDATE_BASE = "https://sosiskibot.ru/etg"
OFFICIAL_SERVER_SCRIPT = "https://sosiskibot.ru/etg/etg_server.py"


class _WebSocketConn:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.lock = threading.Lock()
        self.alive = True
        self.device_id: typing.Optional[str] = None

    def _recv_exact(self, size: int) -> typing.Optional[bytes]:
        data = b""
        while len(data) < size:
            try:
                chunk = self.sock.recv(size - len(data))
            except socket.timeout:
                return None
            if not chunk:
                return None
            data += chunk
        return data

    def recv_text(self) -> typing.Optional[str]:
        header = self._recv_exact(2)
        if not header:
            return None
        b1, b2 = header[0], header[1]
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        length = b2 & 0x7F
        if length == 126:
            ext = self._recv_exact(2)
            if not ext:
                return None
            length = struct.unpack("!H", ext)[0]
        elif length == 127:
            ext = self._recv_exact(8)
            if not ext:
                return None
            length = struct.unpack("!Q", ext)[0]
        mask_key = b""
        if masked:
            mask_key = self._recv_exact(4) or b""
        payload = self._recv_exact(length) if length else b""
        if payload is None:
            return None
        if masked and mask_key:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        if opcode == 0x8:
            self.alive = False
            return None
        if opcode == 0x9:
            self.send_pong(payload)
            return ""
        if opcode == 0xA:
            return ""
        if opcode != 0x1:
            return ""
        try:
            return payload.decode("utf-8")
        except Exception:
            return ""

    def send_frame(self, opcode: int, payload: bytes) -> None:
        if not self.alive:
            return
        header = bytearray()
        header.append(0x80 | (opcode & 0x0F))
        length = len(payload)
        if length <= 125:
            header.append(length)
        elif length < 65536:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))
        with self.lock:
            self.sock.sendall(header + payload)

    def send_text(self, text: str) -> None:
        self.send_frame(0x1, text.encode("utf-8"))

    def send_json(self, payload: dict) -> None:
        self.send_text(json.dumps(payload, ensure_ascii=True))

    def send_ping(self) -> None:
        self.send_frame(0x9, b"ping")

    def send_pong(self, payload: bytes) -> None:
        self.send_frame(0xA, payload)

    def close(self) -> None:
        if not self.alive:
            return
        self.alive = False
        try:
            self.send_frame(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class EtgBridgeAPI:
    def __init__(self, module: "EtgBridgeMod"):
        self._mod = module

    def _resolve(self, device_id: typing.Optional[str]) -> typing.Optional[str]:
        if not device_id or device_id == "last":
            return self._mod._pick_device("last")
        return device_id

    def send(
        self,
        device_id: typing.Optional[str],
        action: str,
        payload: typing.Optional[dict] = None,
        ttl: int = 300,
    ) -> typing.Optional[str]:
        target = self._resolve(device_id)
        if not target:
            return None
        return self._mod.queue_action(target, action, payload, ttl)

    def toast(self, device_id: typing.Optional[str], text: str) -> typing.Optional[str]:
        return self.send(device_id, "toast", {"text": text})

    def dialog(
        self,
        device_id: typing.Optional[str],
        title: str,
        text: str,
        buttons: typing.Optional[typing.List[str]] = None,
        callback_id: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        payload = {
            "title": title,
            "text": text,
            "buttons": buttons or ["OK"],
        }
        if callback_id:
            payload["callback_id"] = callback_id
        return self.send(device_id, "dialog", payload)

    def menu(
        self,
        device_id: typing.Optional[str],
        title: str,
        message: str,
        items: typing.List[typing.Union[str, dict]],
        callback_id: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        payload = {"title": title, "message": message, "items": items}
        if callback_id:
            payload["callback_id"] = callback_id
        return self.send(device_id, "menu", payload)

    def prompt(
        self,
        device_id: typing.Optional[str],
        title: str,
        text: str = "",
        hint: str = "",
        multiline: bool = True,
        max_len: int = 0,
        callback_id: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        payload = {
            "title": title,
            "text": text,
            "hint": hint,
            "multiline": bool(multiline),
            "max_len": int(max_len) if max_len else 0,
        }
        if callback_id:
            payload["callback_id"] = callback_id
        return self.send(device_id, "prompt", payload)

    def sheet(
        self,
        device_id: typing.Optional[str],
        dsl: str,
        actions: typing.Optional[typing.List[str]] = None,
        callback_id: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        payload = {"dsl": dsl}
        if actions:
            payload["actions"] = actions
        if callback_id:
            payload["callback_id"] = callback_id
        return self.send(device_id, "sheet", payload)

    def sheet_open(
        self,
        device_id: typing.Optional[str],
        dsl: str,
        actions: typing.Optional[typing.List[str]] = None,
        callback_id: typing.Optional[str] = None,
        sheet_id: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        payload = {"dsl": dsl}
        if actions:
            payload["actions"] = actions
        if callback_id:
            payload["callback_id"] = callback_id
        if sheet_id:
            payload["sheet_id"] = sheet_id
        return self.send(device_id, "sheet", payload)

    def sheet_update(
        self,
        device_id: typing.Optional[str],
        sheet_id: str,
        dsl: str,
        actions: typing.Optional[typing.List[str]] = None,
        callback_id: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        payload = {"sheet_id": sheet_id, "dsl": dsl}
        if actions:
            payload["actions"] = actions
        if callback_id:
            payload["callback_id"] = callback_id
        return self.send(device_id, "sheet_update", payload)

    def sheet_close(
        self,
        device_id: typing.Optional[str],
        sheet_id: str,
    ) -> typing.Optional[str]:
        return self.send(device_id, "sheet_close", {"sheet_id": sheet_id})

    def open_editor(
        self,
        device_id: typing.Optional[str],
        title: str,
        content: str,
        filename: str = "",
        readonly: bool = False,
        callback_id: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        payload = {
            "title": title,
            "content": content,
            "filename": filename,
            "readonly": bool(readonly),
        }
        if callback_id:
            payload["callback_id"] = callback_id
        return self.send(device_id, "open_editor", payload)

    def ripple(
        self,
        device_id: typing.Optional[str],
        intensity: float = 1.0,
        vibrate: bool = True,
    ) -> typing.Optional[str]:
        return self.send(
            device_id,
            "ripple",
            {"intensity": intensity, "vibrate": bool(vibrate)},
        )

    def select_chat(
        self,
        device_id: typing.Optional[str],
        title: str = "Выберите чат",
        callback_id: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        payload = {"title": title}
        if callback_id:
            payload["callback_id"] = callback_id
        return self.send(device_id, "select_chat", payload)

    def open_url(self, device_id: typing.Optional[str], url: str) -> typing.Optional[str]:
        return self.send(device_id, "open_url", {"url": url})

    def clipboard_set(self, device_id: typing.Optional[str], text: str) -> typing.Optional[str]:
        return self.send(device_id, "clipboard_set", {"text": text})

    def clipboard_get(self, device_id: typing.Optional[str]) -> typing.Optional[str]:
        return self.send(device_id, "clipboard_get", {})

    def notify(
        self, device_id: typing.Optional[str], title: str, text: str
    ) -> typing.Optional[str]:
        return self.send(device_id, "notify", {"title": title, "text": text})

    def notify_dialog(
        self,
        device_id: typing.Optional[str],
        sender_name: str,
        message: str,
        avatar_url: str = "",
    ) -> typing.Optional[str]:
        return self.send(
            device_id,
            "notify_dialog",
            {"sender_name": sender_name, "message": message, "avatar_url": avatar_url},
        )

    def tts(self, device_id: typing.Optional[str], text: str) -> typing.Optional[str]:
        return self.send(device_id, "tts", {"text": text})

    def share_text(
        self, device_id: typing.Optional[str], text: str, title: str = "Share"
    ) -> typing.Optional[str]:
        return self.send(device_id, "share_text", {"text": text, "title": title})

    def share_file(
        self, device_id: typing.Optional[str], path: str, title: str = "Share"
    ) -> typing.Optional[str]:
        return self.send(device_id, "share_file", {"path": path, "title": title})

    def send_png(
        self, device_id: typing.Optional[str], url: str, caption: str = ""
    ) -> typing.Optional[str]:
        return self.send(device_id, "send_png", {"url": url, "caption": caption})

    def render_html(
        self,
        device_id: typing.Optional[str],
        html: str,
        width: int = 1024,
        height: int = 768,
        bg_color: typing.Tuple[int, int, int] = (26, 30, 36),
        file_prefix: str = "etg_",
        send: bool = False,
        caption: str = "",
    ) -> typing.Optional[str]:
        return self.send(
            device_id,
            "render_html",
            {
                "html": html,
                "width": width,
                "height": height,
                "bg_color": list(bg_color),
                "file_prefix": file_prefix,
                "send": bool(send),
                "caption": caption,
            },
        )

    def device_info(self, device_id: typing.Optional[str]) -> typing.Optional[str]:
        return self.send(device_id, "device_info", {})

    def recent_messages(
        self, device_id: typing.Optional[str], dialog_id: int, limit: int = 20
    ) -> typing.Optional[str]:
        return self.send(
            device_id,
            "recent_messages",
            {"dialog_id": int(dialog_id), "limit": int(limit)},
        )

    def data_write(
        self, device_id: typing.Optional[str], filename: str, data: typing.Any
    ) -> typing.Optional[str]:
        return self.send(device_id, "data_write", {"filename": filename, "data": data})

    def data_read(
        self, device_id: typing.Optional[str], filename: str
    ) -> typing.Optional[str]:
        return self.send(device_id, "data_read", {"filename": filename})

    def data_list(self, device_id: typing.Optional[str]) -> typing.Optional[str]:
        return self.send(device_id, "data_list", {})

    def data_delete(self, device_id: typing.Optional[str]) -> typing.Optional[str]:
        return self.send(device_id, "data_delete", {})

    def kv_set(
        self,
        device_id: typing.Optional[str],
        key: str,
        value: typing.Any,
        table: str = "etg_bridge",
    ) -> typing.Optional[str]:
        return self.send(
            device_id,
            "kv_set",
            {"key": key, "value": value, "table": table},
        )

    def kv_get(
        self,
        device_id: typing.Optional[str],
        key: str,
        table: str = "etg_bridge",
    ) -> typing.Optional[str]:
        return self.send(device_id, "kv_get", {"key": key, "table": table})

    def kv_get_int(
        self,
        device_id: typing.Optional[str],
        key: str,
        default: int = 0,
        table: str = "etg_bridge",
    ) -> typing.Optional[str]:
        return self.send(
            device_id,
            "kv_get_int",
            {"key": key, "default": int(default), "table": table},
        )

    def kv_delete_prefix(
        self,
        device_id: typing.Optional[str],
        prefix: str,
        table: str = "etg_bridge",
    ) -> typing.Optional[str]:
        return self.send(
            device_id,
            "kv_delete_prefix",
            {"prefix": prefix, "table": table},
        )

    def pip_install(
        self, device_id: typing.Optional[str], packages: typing.Union[str, list]
    ) -> typing.Optional[str]:
        return self.send(device_id, "pip_install", {"packages": packages})

    def exec(self, device_id: typing.Optional[str], code: str) -> typing.Optional[str]:
        return self.send(device_id, "exec", {"code": code})

    def get_result(
        self, device_id: typing.Optional[str], action_id: str, pop: bool = False
    ) -> typing.Optional[dict]:
        target = self._resolve(device_id)
        if not target:
            return None
        return self._mod.get_result(target, action_id, pop=pop)

    async def wait_result(
        self,
        device_id: typing.Optional[str],
        action_id: str,
        timeout: int = 30,
        pop: bool = True,
    ) -> typing.Optional[dict]:
        target = self._resolve(device_id)
        if not target:
            return None
        return await self._mod.wait_result(target, action_id, timeout, pop)


class _BridgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class _BridgeHandler(BaseHTTPRequestHandler):
    server_version = "EtgBridge/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _is_ws_request(self) -> bool:
        upgrade = (self.headers.get("Upgrade") or "").lower()
        connection = (self.headers.get("Connection") or "").lower()
        return upgrade == "websocket" and "upgrade" in connection

    def _upgrade_ws(self) -> bool:
        key = (self.headers.get("Sec-WebSocket-Key") or "").strip()
        if not key:
            self._send_json(400, {"ok": False, "error": "missing_ws_key"})
            return False
        accept_raw = f"{key}{WS_GUID}".encode("utf-8")
        accept = base64.b64encode(hashlib.sha1(accept_raw).digest()).decode("ascii")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.close_connection = False
        return True

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/ws" and self._is_ws_request():
            if not self._upgrade_ws():
                return
            bridge = getattr(self.server, "bridge", None)
            if bridge is None:
                return
            try:
                self.connection.settimeout(None)
            except Exception:
                pass
            conn = _WebSocketConn(self.connection)
            bridge.handle_ws(conn, self.client_address[0])
            return
        if path == "/health":
            self._send_json(200, {"ok": True, "ts": int(time.time() * 1000)})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/sync":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(413, {"ok": False, "error": "payload_too_large"})
            return
        try:
            raw = self.rfile.read(length)
        except Exception:
            self._send_json(400, {"ok": False, "error": "read_failed"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(400, {"ok": False, "error": "invalid_json"})
            return
        bridge = getattr(self.server, "bridge", None)
        if bridge is None:
            self._send_json(500, {"ok": False, "error": "bridge_missing"})
            return
        status, response = bridge.handle_sync(payload, self.client_address[0])
        self._send_json(status, response)


@loader.tds
class EtgBridgeMod(loader.Module):
    """Bridge between Heroku modules and ETG plugins."""

    strings = {"name": "EtgBridge"}

    def __init__(self):
        default_cert = "/root/Heroku/modules/ssl/fullchain.crt"
        default_key = "/root/Heroku/modules/ssl/certificate.key"
        if not os.path.isfile(default_cert):
            default_cert = os.path.normpath(
                os.path.join(utils.get_base_dir(), "..", "modules", "ssl", "fullchain.crt")
            )
        if not os.path.isfile(default_key):
            default_key = os.path.normpath(
                os.path.join(utils.get_base_dir(), "..", "modules", "ssl", "certificate.key")
            )
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "listen_host",
                "0.0.0.0",
                "Host to listen for ETG sync",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "listen_port",
                9678,
                "Port to listen for ETG sync",
                validator=loader.validators.Integer(minimum=1, maximum=65535),
            ),
            loader.ConfigValue(
                "use_external_server",
                True,
                "Use systemd ETG server instead of in-process server",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "tls_enabled",
                True,
                "Enable HTTPS server",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "tls_cert_path",
                default_cert,
                "TLS certificate (fullchain) path",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "tls_key_path",
                default_key,
                "TLS private key path",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "auth_token",
                "",
                "Shared token (optional)",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "device_timeout",
                120,
                "Seconds to consider device online",
                validator=loader.validators.Integer(minimum=10, maximum=86400),
            ),
            loader.ConfigValue(
                "max_queue",
                200,
                "Max queued actions per device",
                validator=loader.validators.Integer(minimum=1, maximum=2000),
            ),
            loader.ConfigValue(
                "max_logs",
                300,
                "Max logs stored per device",
                validator=loader.validators.Integer(minimum=10, maximum=5000),
            ),
            loader.ConfigValue(
                "max_results",
                200,
                "Max results stored per device",
                validator=loader.validators.Integer(minimum=10, maximum=5000),
            ),
            loader.ConfigValue(
                "resend_after",
                5,
                "Resend action after N seconds if not acked",
                validator=loader.validators.Integer(minimum=1, maximum=3600),
            ),
        )
        self._server: typing.Optional[_BridgeHTTPServer] = None
        self._server_thread: typing.Optional[threading.Thread] = None
        self._devices: dict = {}
        self._lock = threading.Lock()
        self._last_error: typing.Optional[str] = None
        self._last_device_id: typing.Optional[str] = None
        self._session = requests.Session()
        self._session.trust_env = False
        self._setup_log: typing.Optional[typing.List[str]] = None
        self.api = EtgBridgeAPI(self)

    async def client_ready(self):
        self._ensure_setup_log()
        if not self._use_external():
            await self._start_server()

    async def on_unload(self):
        if not self._use_external():
            await self._stop_server()

    def _use_external(self) -> bool:
        try:
            return bool(self.config["use_external_server"])
        except Exception:
            return True

    def _ensure_setup_log(self) -> None:
        if self._setup_log is not None:
            return
        try:
            self._setup_log = self.pointer("etg_setup_log", [])
        except Exception:
            self._setup_log = []

    async def _start_server(self) -> None:
        await self._stop_server()
        host = self.config["listen_host"]
        port = self.config["listen_port"]
        try:
            server = _BridgeHTTPServer((host, port), _BridgeHandler)
            server.bridge = self
            if self.config["tls_enabled"]:
                cert_path = self.config["tls_cert_path"]
                key_path = self.config["tls_key_path"]
                if not cert_path or not os.path.isfile(cert_path):
                    raise FileNotFoundError(f"TLS cert not found: {cert_path}")
                if not key_path or not os.path.isfile(key_path):
                    raise FileNotFoundError(f"TLS key not found: {key_path}")
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(certfile=cert_path, keyfile=key_path)
                server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server = server
            self._server_thread = thread
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)

    async def _stop_server(self) -> None:
        server = self._server
        if server is None:
            return
        try:
            await asyncio.to_thread(server.shutdown)
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
        self._server = None
        self._server_thread = None

    def _local_base_url(self) -> str:
        scheme = "https" if self.config["tls_enabled"] else "http"
        return f"{scheme}://127.0.0.1:{self.config['listen_port']}"

    def _local_request(
        self,
        method: str,
        path: str,
        payload: typing.Optional[dict] = None,
        params: typing.Optional[dict] = None,
    ) -> typing.Tuple[typing.Optional[dict], str]:
        url = self._local_base_url() + path
        verify = True
        if self.config["tls_enabled"]:
            verify = False
            try:
                requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            response = self._session.request(
                method,
                url,
                json=payload,
                params=params,
                timeout=10,
                verify=verify,
            )
        except Exception as exc:
            return None, str(exc)
        if response.status_code >= 400:
            return None, f"http {response.status_code}: {response.text[:200]}"
        try:
            return response.json(), ""
        except Exception as exc:
            return None, f"bad json: {exc}"

    def _fetch_status(self) -> typing.Tuple[typing.Optional[dict], str]:
        return self._local_request("GET", "/status")

    def _get_device(self, device_id: str) -> dict:
        device = self._devices.get(device_id)
        if device is None:
            device = {
                "id": device_id,
                "created_at": time.time(),
                "last_seen": 0.0,
                "ip": "",
                "info": {},
                "queue": [],
                "logs": [],
                "results": [],
                "ws": None,
            }
            self._devices[device_id] = device
        return device

    def _log_device(self, device: dict, text: str, level: str = "info") -> None:
        entry = {
            "ts": time.time(),
            "text": text,
            "level": level,
        }
        device["logs"].append(entry)
        max_logs = self.config["max_logs"]
        if len(device["logs"]) > max_logs:
            del device["logs"][:-max_logs]

    def _append_results(self, device: dict, results: list) -> None:
        if not results:
            return
        for item in results:
            if not isinstance(item, dict):
                continue
            entry = {
                "ts": time.time(),
                "id": str(item.get("id") or ""),
                "ok": bool(item.get("ok", False)),
                "action": str(item.get("action") or ""),
                "data": item.get("data"),
                "error": str(item.get("error") or ""),
            }
            device["results"].append(entry)
        max_results = self.config["max_results"]
        if len(device["results"]) > max_results:
            del device["results"][:-max_results]

    def _prune_queue(self, device: dict, ack_ids: set) -> None:
        now = time.time()
        new_queue = []
        for item in device["queue"]:
            item_id = item.get("id")
            if item_id in ack_ids:
                continue
            ttl = int(item.get("ttl", 300))
            created = float(item.get("ts", now))
            if now - created > ttl:
                continue
            new_queue.append(item)
        device["queue"] = new_queue

    def _collect_actions(self, device: dict) -> list:
        now = time.time()
        resend_after = self.config["resend_after"]
        actions = []
        for item in device["queue"]:
            sent_ts = float(item.get("sent_ts") or 0)
            if sent_ts and now - sent_ts < resend_after:
                continue
            item["sent_ts"] = now
            actions.append(
                {
                    "id": item.get("id"),
                    "action": item.get("action"),
                    "payload": item.get("payload"),
                    "ttl": item.get("ttl"),
                    "ts": item.get("ts"),
                }
            )
        return actions

    def _find_result_index(self, device: dict, action_id: str) -> typing.Optional[int]:
        for idx, item in enumerate(device.get("results") or []):
            if str(item.get("id") or "") == action_id:
                return idx
        return None

    def get_result(
        self,
        device_id: str,
        action_id: str,
        pop: bool = False,
    ) -> typing.Optional[dict]:
        if self._use_external():
            data, _err = self._local_request(
                "GET",
                "/result",
                params={
                    "device_id": device_id or "last",
                    "action_id": action_id,
                    "pop": "1" if pop else "0",
                },
            )
            if data and data.get("ok"):
                return data.get("result")
            return None
        with self._lock:
            device = self._get_device(device_id)
            idx = self._find_result_index(device, action_id)
            if idx is None:
                return None
            item = device["results"][idx]
            if pop:
                device["results"].pop(idx)
            return item

    async def wait_result(
        self,
        device_id: str,
        action_id: str,
        timeout: int = 30,
        pop: bool = True,
    ) -> typing.Optional[dict]:
        end = time.time() + max(1, timeout)
        while time.time() < end:
            item = self.get_result(device_id, action_id, pop=pop)
            if item is not None:
                return item
            await asyncio.sleep(0.5)
        return None

    def queue_action(
        self,
        device_id: str,
        action: str,
        payload: typing.Optional[dict] = None,
        ttl: int = 300,
    ) -> str:
        if self._use_external():
            data, err = self._local_request(
                "POST",
                "/queue",
                payload={
                    "device_id": device_id or "last",
                    "action": action,
                    "payload": payload or {},
                    "ttl": int(ttl),
                },
            )
            if data and data.get("ok"):
                return str(data.get("action_id") or "")
            self._last_error = err or (data.get("error") if data else "queue_failed")
            return ""
        action_id = uuid.uuid4().hex
        ws_conn = None
        actions = []
        with self._lock:
            device = self._get_device(device_id)
            item = {
                "id": action_id,
                "action": action,
                "payload": payload or {},
                "ttl": ttl,
                "ts": time.time(),
                "sent_ts": 0.0,
            }
            device["queue"].append(item)
            max_queue = self.config["max_queue"]
            if len(device["queue"]) > max_queue:
                device["queue"] = device["queue"][-max_queue:]
            self._log_device(device, f"queued {action} id={action_id}")
            ws_conn = device.get("ws")
            if ws_conn and getattr(ws_conn, "alive", False):
                actions = self._collect_actions(device)
        if ws_conn and actions:
            self._send_ws_actions(ws_conn, device_id, actions, "push")
        return action_id

    def handle_sync(self, payload: dict, client_ip: str) -> typing.Tuple[int, dict]:
        if not isinstance(payload, dict):
            return 400, {"ok": False, "error": "invalid_payload"}
        token = self.config["auth_token"].strip()
        if token:
            if payload.get("token") != token:
                return 401, {"ok": False, "error": "unauthorized"}
        device_id = str(payload.get("device_id") or "").strip()
        if not device_id:
            return 400, {"ok": False, "error": "missing_device_id"}
        with self._lock:
            device = self._get_device(device_id)
            device["last_seen"] = time.time()
            device["ip"] = client_ip
            info = payload.get("info")
            if isinstance(info, dict):
                device["info"] = info
            self._last_device_id = device_id

            logs = payload.get("logs")
            if isinstance(logs, list):
                for entry in logs:
                    if isinstance(entry, dict):
                        text = entry.get("text") or ""
                    else:
                        text = str(entry)
                    if text:
                        self._log_device(device, text)

            results = payload.get("results")
            if isinstance(results, list):
                self._append_results(device, results)

            ack_ids = set()
            ack = payload.get("ack")
            if isinstance(ack, list):
                ack_ids.update(str(x) for x in ack if x)
            if isinstance(results, list):
                ack_ids.update(str(x.get("id")) for x in results if isinstance(x, dict) and x.get("id"))
            self._prune_queue(device, ack_ids)

            actions = self._collect_actions(device)

        response = {
            "ok": True,
            "device_id": device_id,
            "server_ts": int(time.time() * 1000),
            "actions": actions,
        }
        return 200, response

    def _bind_ws(self, device_id: str, conn: _WebSocketConn) -> None:
        with self._lock:
            device = self._get_device(device_id)
            old = device.get("ws")
            if old and old is not conn:
                try:
                    old.close()
                except Exception:
                    pass
            device["ws"] = conn

    def _unbind_ws(self, conn: _WebSocketConn) -> None:
        device_id = conn.device_id
        if not device_id:
            return
        with self._lock:
            device = self._devices.get(device_id)
            if device and device.get("ws") is conn:
                device["ws"] = None

    def _send_ws_actions(
        self,
        conn: _WebSocketConn,
        device_id: str,
        actions: list,
        reason: str,
    ) -> None:
        payload = {
            "ok": True,
            "device_id": device_id,
            "server_ts": int(time.time() * 1000),
            "actions": actions,
            "type": reason,
        }
        try:
            conn.send_json(payload)
        except Exception as exc:
            conn.close()
            self._unbind_ws(conn)
            self._last_error = f"ws send failed: {exc}"

    def handle_ws(self, conn: _WebSocketConn, client_ip: str) -> None:
        try:
            while conn.alive:
                msg = conn.recv_text()
                if msg is None:
                    break
                if not msg:
                    continue
                try:
                    payload = json.loads(msg)
                except Exception:
                    conn.send_json({"ok": False, "error": "invalid_json"})
                    continue
                status, response = self.handle_sync(payload, client_ip)
                device_id = response.get("device_id") or payload.get("device_id")
                if device_id:
                    conn.device_id = str(device_id)
                    self._bind_ws(conn.device_id, conn)
                if status != 200:
                    response["ok"] = False
                    response["code"] = status
                response.setdefault("type", "sync")
                conn.send_json(response)
        except Exception as exc:
            if conn.device_id:
                with self._lock:
                    device = self._get_device(conn.device_id)
                    self._log_device(device, f"ws error: {exc}", "error")
        finally:
            self._unbind_ws(conn)
            conn.close()

    def _format_age(self, seconds: float) -> str:
        seconds = int(max(0, seconds))
        if seconds < 60:
            return f"{seconds}s"
        minutes, sec = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}m {sec}s"
        hours, minutes = divmod(minutes, 60)
        if hours < 24:
            return f"{hours}h {minutes}m"
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h"

    def _render_device_line(self, device: dict) -> str:
        now = time.time()
        last_seen = device.get("last_seen") or 0
        age = self._format_age(now - float(last_seen)) if last_seen else "never"
        info = device.get("info") or {}
        name = info.get("device_name") or info.get("name") or device.get("id") or "unknown"
        queue_len = device.get("queue")
        logs_len = device.get("logs")
        results_len = device.get("results")
        if not isinstance(queue_len, int):
            queue_len = len(device.get("queue") or [])
        if not isinstance(logs_len, int):
            logs_len = len(device.get("logs") or [])
        if not isinstance(results_len, int):
            results_len = len(device.get("results") or [])
        transport = device.get("transport")
        if not transport:
            ws_conn = device.get("ws")
            transport = "ws" if ws_conn and getattr(ws_conn, "alive", False) else "http"
        return (
            f"- {name} ({device['id']}) | seen {age} | {transport} | "
            f"q={queue_len} logs={logs_len} results={results_len}"
        )

    def _pick_device(self, raw: str) -> typing.Optional[str]:
        if raw and raw != "last":
            return raw
        if self._use_external():
            data, _err = self._fetch_status()
            if data and data.get("ok"):
                last = str(data.get("last_device_id") or "").strip()
                if last:
                    self._last_device_id = last
                    return last
                devices = data.get("devices") or []
                if devices:
                    device = max(devices, key=lambda d: d.get("last_seen", 0.0))
                    picked = str(device.get("id") or "").strip()
                    if picked:
                        self._last_device_id = picked
                        return picked
        if self._last_device_id:
            return self._last_device_id
        if self._devices:
            return next(iter(self._devices.keys()))
        return None

    async def _send_text_or_file(
        self,
        message: Message,
        text: str,
        filename: str,
        caption: str,
    ) -> None:
        if len(text) <= 3500:
            await utils.answer(message, text)
            return
        file = io.BytesIO(text.encode("utf-8"))
        file.name = filename
        await message.reply(file, caption=caption)

    def _set_setup_log(self, logs: typing.List[str]) -> None:
        self._ensure_setup_log()
        if self._setup_log is None:
            return
        del self._setup_log[:]
        if logs:
            self._setup_log.extend(logs[-500:])

    def _format_setup_log(self) -> str:
        self._ensure_setup_log()
        if not self._setup_log:
            return "Логов нет."
        return "\n".join(self._setup_log)

    @staticmethod
    def _exec_shell(args: typing.List[str]) -> typing.Tuple[int, str]:
        try:
            result = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            return result.returncode, (result.stdout or "").strip()
        except Exception as exc:
            return 1, str(exc)

    @staticmethod
    def _etg_root() -> str:
        return os.path.normpath(
            os.path.join(utils.get_base_dir(), "..", "modules", "ETG")
        )

    @staticmethod
    def _etg_server_path(root: str) -> str:
        return os.path.join(root, "etg_server.py")

    @staticmethod
    def _etg_config_path(root: str) -> str:
        return os.path.join(root, "etg_server.json")

    @staticmethod
    def _read_file(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        except Exception:
            return ""

    @staticmethod
    def _write_file(path: str, text: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            return True
        except Exception:
            return False

    def _write_server_config(self, root: str, logs: typing.List[str]) -> None:
        path = self._etg_config_path(root)
        payload = {
            "listen_host": self.config["listen_host"],
            "listen_port": int(self.config["listen_port"]),
            "tls_enabled": bool(self.config["tls_enabled"]),
            "tls_cert_path": self.config["tls_cert_path"],
            "tls_key_path": self.config["tls_key_path"],
            "auth_token": (self.config["auth_token"] or "").strip(),
            "admin_token": "",
            "allow_remote_queue": False,
            "device_timeout": int(self.config["device_timeout"]),
            "max_queue": int(self.config["max_queue"]),
            "max_logs": int(self.config["max_logs"]),
            "max_results": int(self.config["max_results"]),
            "resend_after": int(self.config["resend_after"]),
        }
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2)
            logs.append(f"server config: {path}")
        except Exception as exc:
            logs.append(f"server config write failed: {exc}")

    def _ensure_etg_service(self, root: str, logs: typing.List[str]) -> None:
        if self._is_windows():
            logs.append("systemd: not supported on Windows")
            return
        if not shutil.which("systemctl"):
            logs.append("systemd: systemctl not available")
            return
        server_path = self._etg_server_path(root)
        if not os.path.isfile(server_path):
            logs.append(f"server script missing: {server_path}")
            return
        venv_python = os.path.normpath(
            os.path.join(utils.get_base_dir(), "..", "venv", "bin", "python")
        )
        if not os.path.isfile(venv_python):
            venv_python = shutil.which("python3") or shutil.which("python") or "python3"
        service_text = (
            "[Unit]\n"
            "Description=ETG Bridge Server\n"
            "After=network.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={root}\n"
            f"ExecStart={venv_python} {server_path}\n"
            "Restart=always\n"
            "RestartSec=3\n"
            "User=root\n"
            "Environment=PYTHONUNBUFFERED=1\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )
        service_path = "/etc/systemd/system/etg-bridge.service"
        if not self._write_file(service_path, service_text):
            logs.append("systemd: failed to write service")
            return
        code, out = self._exec_shell(["systemctl", "daemon-reload"])
        logs.append("systemd: daemon-reload ok" if code == 0 else f"systemd: {out}")
        code, out = self._exec_shell(["systemctl", "enable", "--now", "etg-bridge.service"])
        logs.append("systemd: enable ok" if code == 0 else f"systemd: {out}")
        code, out = self._exec_shell(["systemctl", "restart", "etg-bridge.service"])
        logs.append("systemd: restart ok" if code == 0 else f"systemd: {out}")

    def _check_local_health(self, logs: typing.List[str]) -> None:
        data, err = self._local_request("GET", "/health")
        if data and data.get("ok"):
            logs.append("server health: ok")
        else:
            logs.append(f"server health failed: {err or 'no response'}")

    @staticmethod
    def _is_windows() -> bool:
        return platform.system().lower().startswith("win") or os.name == "nt"

    def _ensure_server_script(self, root: str, logs: typing.List[str]) -> bool:
        path = self._etg_server_path(root)
        if os.path.isfile(path):
            return True
        urls = [
            OFFICIAL_SERVER_SCRIPT,
            f"{OFFICIAL_UPDATE_BASE}/etg/etg_server.py",
        ]
        for url in urls:
            try:
                resp = self._session.get(url, timeout=30, verify=False)
                if resp.status_code != 200:
                    logs.append(f"server download failed {url}: http {resp.status_code}")
                    continue
                os.makedirs(root, exist_ok=True)
                with open(path, "wb") as handle:
                    handle.write(resp.content)
                logs.append(f"server script downloaded: {path}")
                return True
            except Exception as exc:
                logs.append(f"server download failed {url}: {exc}")
        logs.append(f"server script missing: {path}")
        return False

    def _read_os_release(self) -> typing.Dict[str, str]:
        data: typing.Dict[str, str] = {}
        try:
            with open("/etc/os-release", "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    data[key] = value.strip().strip('"')
        except Exception:
            return {}
        return data

    def _sudo_command(self, args: typing.List[str], logs: typing.List[str]) -> typing.Optional[typing.List[str]]:
        if os.geteuid() == 0:
            return args
        sudo = shutil.which("sudo")
        if not sudo:
            logs.append("sudo: not available, install ufw manually")
            return None
        return [sudo, "-n"] + args

    def _run_pkg_command(self, args: typing.List[str], logs: typing.List[str], label: str) -> bool:
        cmd = self._sudo_command(args, logs)
        if not cmd:
            return False
        code, out = self._exec_shell(cmd)
        if code == 0:
            logs.append(f"{label}: ok")
            return True
        out_low = (out or "").lower()
        if "password" in out_low or "no tty" in out_low:
            logs.append(f"{label}: sudo requires password, install ufw manually")
            return False
        logs.append(f"{label}: {out}")
        return False

    def _install_ufw(self, logs: typing.List[str]) -> bool:
        if shutil.which("ufw"):
            return True
        osr = self._read_os_release()
        if osr:
            os_id = osr.get("ID", "")
            os_like = osr.get("ID_LIKE", "")
            logs.append(f"os-release: {os_id} {os_like}".strip())

        installers = []
        if shutil.which("apt-get") or shutil.which("apt"):
            installers.append((["apt-get", "install", "-y", "ufw"], "apt-get install ufw"))
        if shutil.which("dnf"):
            installers.append((["dnf", "-y", "install", "ufw"], "dnf install ufw"))
        if shutil.which("yum"):
            installers.append((["yum", "-y", "install", "ufw"], "yum install ufw"))
        if shutil.which("pacman"):
            installers.append((["pacman", "-Sy", "--noconfirm", "ufw"], "pacman install ufw"))
        if shutil.which("zypper"):
            installers.append((["zypper", "--non-interactive", "install", "ufw"], "zypper install ufw"))
        if shutil.which("apk"):
            installers.append((["apk", "add", "--no-cache", "ufw"], "apk add ufw"))

        if not installers:
            logs.append("ufw: no supported package manager found")
            return False

        for cmd, label in installers:
            if self._run_pkg_command(cmd, logs, label):
                if shutil.which("ufw"):
                    logs.append("ufw: installed")
                    return True
        if not shutil.which("ufw"):
            logs.append("ufw: install failed")
        return shutil.which("ufw") is not None

    def _get_ufw_install_command(self) -> str:
        if self._is_windows():
            return ""
        if shutil.which("apt-get") or shutil.which("apt"):
            return "sudo apt-get install -y ufw"
        if shutil.which("dnf"):
            return "sudo dnf -y install ufw"
        if shutil.which("yum"):
            return "sudo yum -y install ufw"
        if shutil.which("pacman"):
            return "sudo pacman -Sy --noconfirm ufw"
        if shutil.which("zypper"):
            return "sudo zypper --non-interactive install ufw"
        if shutil.which("apk"):
            return "sudo apk add --no-cache ufw"
        return ""

    @staticmethod
    def _get_ufw_open_command(port: int) -> str:
        return f"sudo ufw allow {port}"

    def _build_post_install_message(self, port: int, logs: typing.List[str]) -> str:
        lines = ["Всё настроено, установите библиотеки ниже!"]
        if self._is_windows():
            server_path = self._etg_server_path(self._etg_root())
            lines.append("Windows: ufw не поддерживается.")
            lines.append(
                f'Открой порт: `netsh advfirewall firewall add rule name="ETG {port}" dir=in action=allow protocol=TCP localport={port}`'
            )
            lines.append(f'Запуск сервера: `python "{server_path}"`')
            return "\n".join(lines)
        install_cmd = self._get_ufw_install_command()
        if install_cmd:
            lines.append(f"Установка ufw: `{install_cmd}`")
        lines.append(f"Открой порт: `{self._get_ufw_open_command(port)}`")
        if any("sudo requires password" in line for line in logs):
            lines.append("sudo попросит пароль на вашем ПК.")
        return "\n".join(lines)

    async def _send_install_result(
        self,
        message: typing.Optional[Message],
        text: str,
        etg_file: str,
        mandre_file: str,
        chat_id: typing.Optional[int] = None,
    ) -> None:
        if chat_id is None:
            if message is None:
                return
            chat_id = utils.get_chat_id(message)
        await self._client.send_message(chat_id, text)
        if etg_file and os.path.isfile(etg_file):
            await self._client.send_file(chat_id, etg_file)
        if mandre_file and os.path.isfile(mandre_file):
            await self._client.send_file(chat_id, mandre_file)

    def _allow_ports(self, ports: typing.List[int], logs: typing.List[str]) -> None:
        if self._is_windows():
            logs.append("ufw: not supported on Windows")
            return
        if not shutil.which("ufw"):
            logs.append("ufw: not installed, attempting install")
            if not self._install_ufw(logs):
                logs.append("ufw: not installed, skip")
                return
        for port in ports:
            code, out = self._exec_shell(["ufw", "allow", str(port)])
            if code == 0:
                logs.append(f"ufw allow {port}: ok")
            else:
                logs.append(f"ufw allow {port}: {out}")

    def _copy_etg_files(self, logs: typing.List[str]) -> typing.Dict[str, str]:
        root = self._etg_root()
        release_dir = os.path.join(root, "release")
        beta_dir = os.path.join(root, "beta")
        os.makedirs(release_dir, exist_ok=True)
        os.makedirs(beta_dir, exist_ok=True)

        def download(url: str, dst: str) -> bool:
            try:
                try:
                    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
                except Exception:
                    pass
                resp = self._session.get(url, timeout=30, verify=False)
                if resp.status_code != 200:
                    logs.append(f"download failed {url}: http {resp.status_code}")
                    return False
                with open(dst, "wb") as handle:
                    handle.write(resp.content)
                return True
            except Exception as exc:
                logs.append(f"download failed {url}: {exc}")
                return False

        copied: typing.Dict[str, str] = {}
        base = OFFICIAL_UPDATE_BASE.rstrip("/")
        for branch, target_dir in (("release", release_dir), ("beta", beta_dir)):
            for name in ("EtgBridge.plugin", "mandre_lib.plugin"):
                url = f"{base}/{branch}/{name}"
                dst = os.path.join(target_dir, name)
                if download(url, dst):
                    if branch == "release":
                        copied[name] = dst
                else:
                    logs.append(f"missing remote: {url}")
        return copied

    def _patch_plugin_defaults(
        self,
        plugin_path: str,
        sync_url: str,
        ws_url: str,
        logs: typing.List[str],
    ) -> None:
        raw = self._read_file(plugin_path)
        if not raw:
            logs.append(f"plugin patch failed: {os.path.basename(plugin_path)}")
            return
        updated = re.sub(
            r'^(DEFAULT_SERVER_URL\s*=\s*)[\'"].*[\'"]',
            rf'\1"{sync_url}"',
            raw,
            flags=re.M,
        )
        updated = re.sub(
            r'^(DEFAULT_WS_URL\s*=\s*)[\'"].*[\'"]',
            rf'\1"{ws_url}"',
            updated,
            flags=re.M,
        )
        if updated != raw:
            if self._write_file(plugin_path, updated):
                logs.append(f"patched {os.path.basename(plugin_path)} urls")
            else:
                logs.append(f"plugin patch write failed: {plugin_path}")

    def _get_external_ip(self, logs: typing.List[str]) -> str:
        session = requests.Session()
        session.trust_env = False
        providers = [
            "https://api.ipify.org",
            "https://ifconfig.me/ip",
            "https://ipinfo.io/ip",
        ]
        for url in providers:
            try:
                response = session.get(url, timeout=10)
                if response.status_code == 200:
                    ip = response.text.strip()
                    if ip:
                        return ip
            except Exception as exc:
                logs.append(f"ip check failed {url}: {exc}")
        return ""

    @staticmethod
    def _get_local_ip() -> str:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            return ip
        except Exception:
            return ""

    @staticmethod
    def _is_private_ip(ip: str) -> bool:
        return (
            ip.startswith("10.")
            or ip.startswith("192.168.")
            or ip.startswith("172.16.")
            or ip.startswith("172.17.")
            or ip.startswith("172.18.")
            or ip.startswith("172.19.")
            or ip.startswith("172.2")
            or ip.startswith("172.3")
        )

    @staticmethod
    def _parse_port(value: str) -> typing.Optional[int]:
        if not value or not value.isdigit():
            return None
        port = int(value)
        if port < 1 or port > 65535:
            return None
        return port

    @staticmethod
    def _port_is_free(port: int) -> typing.Tuple[bool, str]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
            return True, ""
        except OSError as exc:
            return False, str(exc)
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def _probe_health(self, port: int) -> bool:
        scheme = "https" if self.config["tls_enabled"] else "http"
        url = f"{scheme}://127.0.0.1:{port}/health"
        verify = not bool(self.config["tls_enabled"])
        try:
            if not verify:
                try:
                    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
                except Exception:
                    pass
            resp = self._session.get(url, timeout=4, verify=verify)
        except Exception:
            return False
        if resp.status_code != 200:
            return False
        try:
            data = resp.json()
        except Exception:
            return False
        return bool(data.get("ok"))

    def _run_install(self, port: int) -> typing.Tuple[typing.List[str], str, str]:
        logs: typing.List[str] = []
        root = self._etg_root()
        os.makedirs(root, exist_ok=True)
        self.config["listen_port"] = int(port)
        self.config["use_external_server"] = True

        self._ensure_server_script(root, logs)
        self._write_server_config(root, logs)
        self._ensure_etg_service(root, logs)

        copied = self._copy_etg_files(logs)
        self._allow_ports([int(self.config["listen_port"])], logs)
        self._check_local_health(logs)

        external_ip = self._get_external_ip(logs)
        local_ip = self._get_local_ip()
        if external_ip and local_ip and external_ip != local_ip and self._is_private_ip(local_ip):
            logs.append(
                f"LAN IP: {local_ip}. Внешний IP отличается — нужен проброс порта {self.config['listen_port']}."
            )
        host = external_ip or self.config["listen_host"]
        host_url = host
        if ":" in host and not host.startswith("["):
            host_url = f"[{host}]"
        scheme = "https" if self.config["tls_enabled"] else "http"
        ws_scheme = "wss" if scheme == "https" else "ws"
        sync_url = f"{scheme}://{host_url}:{self.config['listen_port']}/sync"
        ws_url = f"{ws_scheme}://{host_url}:{self.config['listen_port']}/ws"
        update_base = OFFICIAL_UPDATE_BASE.rstrip("/")
        release_url = f"{update_base}/release"
        beta_url = f"{update_base}/beta"
        plugin_url = f"{release_url}/EtgBridge.plugin"
        mandre_url = f"{release_url}/mandre_lib.plugin"

        release_dir = os.path.join(root, "release")
        beta_dir = os.path.join(root, "beta")
        release_plugin = copied.get("EtgBridge.plugin") or os.path.join(
            release_dir, "EtgBridge.plugin"
        )
        beta_plugin = os.path.join(beta_dir, "EtgBridge.plugin")
        if os.path.isfile(release_plugin):
            self._patch_plugin_defaults(release_plugin, sync_url, ws_url, logs)
        if os.path.isfile(beta_plugin):
            self._patch_plugin_defaults(beta_plugin, sync_url, ws_url, logs)

        auth_token = (self.config["auth_token"] or "").strip()
        token_line = f"Token: {auth_token}" if auth_token else "Token: (не задан)"
        lines = [
            "ETG настройка готова.",
            f"Server: {host}",
            f"Sync URL: {sync_url}",
            f"WS URL: {ws_url}",
            f"Update (release): {release_url}",
            f"Update (beta): {beta_url}",
            f"Plugin file: {plugin_url}",
            f"Mandre file: {mandre_url}",
            token_line,
        ]
        log_lines = logs + ["---"] + lines
        self._set_setup_log(log_lines)

        etg_file = copied.get("EtgBridge.plugin") or release_plugin
        mandre_file = copied.get("mandre_lib.plugin") or os.path.join(
            release_dir, "mandre_lib.plugin"
        )
        return log_lines, etg_file, mandre_file

    def _run_uninstall(self) -> typing.List[str]:
        logs: typing.List[str] = []
        service_path = "/etc/systemd/system/etg-bridge.service"
        code, out = self._exec_shell(["systemctl", "stop", "etg-bridge.service"])
        logs.append("systemd: stop ok" if code == 0 else f"systemd: stop {out}")
        code, out = self._exec_shell(["systemctl", "disable", "etg-bridge.service"])
        logs.append("systemd: disable ok" if code == 0 else f"systemd: disable {out}")
        if os.path.isfile(service_path):
            try:
                os.remove(service_path)
                logs.append("systemd: service removed")
            except Exception as exc:
                logs.append(f"systemd: remove failed: {exc}")
        code, out = self._exec_shell(["systemctl", "daemon-reload"])
        logs.append("systemd: daemon-reload ok" if code == 0 else f"systemd: {out}")
        cfg_path = self._etg_config_path(self._etg_root())
        if os.path.isfile(cfg_path):
            try:
                os.remove(cfg_path)
                logs.append(f"config removed: {cfg_path}")
            except Exception as exc:
                logs.append(f"config remove failed: {exc}")
        self._set_setup_log(logs)
        return logs

    def _ensure_release_files(self, logs: typing.List[str]) -> typing.Tuple[str, str]:
        root = self._etg_root()
        release_dir = os.path.join(root, "release")
        etg_file = os.path.join(release_dir, "EtgBridge.plugin")
        mandre_file = os.path.join(release_dir, "mandre_lib.plugin")
        if not os.path.isfile(etg_file) or not os.path.isfile(mandre_file):
            self._copy_etg_files(logs)
        if not os.path.isfile(etg_file):
            logs.append("release file missing: EtgBridge.plugin")
            etg_file = ""
        if not os.path.isfile(mandre_file):
            logs.append("release file missing: mandre_lib.plugin")
            mandre_file = ""
        return etg_file, mandre_file

    async def _etg_confirm(self, call: InlineCall, port: int, chat_id: int):
        await call.edit(f"Устанавливаю ETG на порт {port}...")
        try:
            _log_lines, etg_file, mandre_file = await asyncio.to_thread(
                self._run_install, port
            )
        except Exception as exc:
            self._set_setup_log([f"install failed: {exc}"])
            await call.edit("Ошибка установки. Логи: `.etg log`")
            return
        await call.edit("Установка завершена. Сообщение с командами отправлено.")
        if not (etg_file and os.path.isfile(etg_file)):
            etg_file, _ = self._ensure_release_files([])
        if not (mandre_file and os.path.isfile(mandre_file)):
            _, mandre_file = self._ensure_release_files([])
        await self._send_install_result(
            message=None,
            text=self._build_post_install_message(port, _log_lines),
            etg_file=etg_file,
            mandre_file=mandre_file,
            chat_id=chat_id,
        )

    async def _etg_cancel(self, call: InlineCall):
        await call.edit("Установка отменена.")

    @loader.command(ru_doc="Удалить настройки ETG сервера")
    async def unetg(self, message: Message):
        logs = await asyncio.to_thread(self._run_uninstall)
        text = "\n".join(logs) if logs else "Готово."
        await self._send_text_or_file(message, text, "etg_uninstall_log.txt", "ETG logs")

    @loader.command(ru_doc="Переустановить ETG сервер")
    async def reinetg(self, message: Message):
        args = utils.get_args_raw(message).strip()
        if args:
            port = self._parse_port(args)
            if port is None:
                await utils.answer(message, "Нужен порт 1-65535. Пример: `.reinetg 8955`")
                return
        else:
            port = int(self.config["listen_port"])
        await utils.answer(message, f"Переустанавливаю ETG на порт {port}...")
        try:
            _log_lines, etg_file, mandre_file = await asyncio.to_thread(
                self._run_install, port
            )
        except Exception as exc:
            await utils.answer(message, f"Ошибка переустановки: {exc}")
            return
        if not (etg_file and os.path.isfile(etg_file)):
            etg_file, _ = self._ensure_release_files([])
        if not (mandre_file and os.path.isfile(mandre_file)):
            _, mandre_file = self._ensure_release_files([])
        await self._send_install_result(
            message,
            self._build_post_install_message(port, _log_lines),
            etg_file,
            mandre_file,
        )

    @loader.command(ru_doc="ETG bridge control")
    async def etg(self, message: Message):
        args = utils.get_args_raw(message).strip().lower()
        if args in {"log", "logs"}:
            text = self._format_setup_log()
            await self._send_text_or_file(
                message,
                text,
                "etg_setup_log.txt",
                "ETG logs",
            )
            return
        if args in {"status", "info"}:
            scheme = "https" if self.config["tls_enabled"] else "http"
            server_state = (
                f"{scheme}://{self.config['listen_host']}:{self.config['listen_port']}"
            )
            if self._use_external():
                data, err = self._fetch_status()
                lines = [f"ETG bridge: external ({server_state})"]
                if err:
                    lines.append(f"Server error: {err}")
                devices = []
                if data and data.get("ok"):
                    devices = data.get("devices") or []
                if not devices:
                    lines.append("No devices yet")
                else:
                    lines.append(f"Devices: {len(devices)}")
                    for device in devices:
                        lines.append(self._render_device_line(device))
                await utils.answer(message, "\n".join(lines))
                return

            with self._lock:
                devices = list(self._devices.values())
            status = "running" if self._server else "stopped"
            lines = [f"ETG bridge: {status} ({server_state})"]
            if self._last_error:
                lines.append(f"Server error: {self._last_error}")
            if not devices:
                lines.append("No devices yet")
            else:
                lines.append(f"Devices: {len(devices)}")
                for device in devices:
                    lines.append(self._render_device_line(device))
            await utils.answer(message, "\n".join(lines))
            return

        if not args:
            await utils.answer(message, "Укажите порт: `.etg 8955`")
            return

        port = self._parse_port(args)
        if port is None:
            await utils.answer(message, "Нужен порт 1-65535. Пример: `.etg 8955`")
            return

        free, error = self._port_is_free(port)
        note = ""
        if not free:
            if self._probe_health(port):
                note = f"\nПорт {port} уже занят ETG и будет использован."
            else:
                await utils.answer(message, f"Порт {port} занят: {error}")
                return

        text = f"Установить ETG на порт {port}?"
        if note:
            text += note

        await self.inline.form(
            message=message,
            text=text,
            reply_markup=[
                [
                    {
                        "text": "✅ Установить",
                        "callback": self._etg_confirm,
                        "args": (port, utils.get_chat_id(message)),
                    },
                    {
                        "text": "❌ Отмена",
                        "callback": self._etg_cancel,
                    },
                ]
            ],
            force_me=True,
        )
        return
