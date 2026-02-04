import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import time
import typing
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MAX_BODY_BYTES = 4 * 1024 * 1024
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
try:
    _BASE_DIR = os.path.dirname(__file__)
except NameError:
    _BASE_DIR = os.path.abspath(os.getcwd())
    candidate = os.path.join(_BASE_DIR, "modules", "ETG")
    if os.path.isdir(candidate):
        _BASE_DIR = candidate
CONFIG_PATH = os.path.join(_BASE_DIR, "etg_server.json")

DEFAULT_CONFIG = {
    "listen_host": "0.0.0.0",
    "listen_port": 8955,
    "tls_enabled": True,
    "tls_cert_path": "/root/Heroku/modules/ssl/fullchain.crt",
    "tls_key_path": "/root/Heroku/modules/ssl/certificate.key",
    "auth_token": "",
    "admin_token": "",
    "allow_remote_queue": False,
    "device_timeout": 120,
    "max_queue": 200,
    "max_logs": 300,
    "max_results": 200,
    "resend_after": 5,
}


def _log(text: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [etg_server] {text}", flush=True)


def _load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in config:
                        config[key] = value
        except Exception as exc:
            _log(f"config read failed: {exc}")
    return config


def _is_local_ip(ip: str) -> bool:
    return ip in {"127.0.0.1", "::1"} or ip.startswith("::ffff:127.")


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


class BridgeState:
    def __init__(self, config: dict):
        self.config = config
        self._devices: dict = {}
        self._lock = threading.Lock()
        self._last_device_id: typing.Optional[str] = None

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
        max_logs = int(self.config.get("max_logs", 300))
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
        max_results = int(self.config.get("max_results", 200))
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
        resend_after = int(self.config.get("resend_after", 5))
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

    def _pick_device(self, raw: str) -> typing.Optional[str]:
        if raw and raw != "last":
            return raw
        if self._last_device_id:
            return self._last_device_id
        if self._devices:
            return next(iter(self._devices.keys()))
        return None

    def queue_action(
        self,
        device_id: str,
        action: str,
        payload: typing.Optional[dict] = None,
        ttl: int = 300,
    ) -> typing.Tuple[typing.Optional[str], typing.Optional[str]]:
        device_id = str(device_id or "").strip()
        if device_id == "last":
            device_id = self._pick_device("last") or ""
        if not device_id:
            return None, None
        action_id = uuid.uuid4().hex
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
            max_queue = int(self.config.get("max_queue", 200))
            if len(device["queue"]) > max_queue:
                device["queue"] = device["queue"][-max_queue:]
            self._log_device(device, f"queued {action} id={action_id}")
            ws_conn = device.get("ws")
            actions = []
            if ws_conn and getattr(ws_conn, "alive", False):
                actions = self._collect_actions(device)
        if ws_conn and actions:
            self._send_ws_actions(ws_conn, device_id, actions, "push")
        return action_id, device_id

    def get_result(
        self,
        device_id: str,
        action_id: str,
        pop: bool = False,
    ) -> typing.Optional[dict]:
        device_id = str(device_id or "").strip()
        if device_id == "last":
            device_id = self._pick_device("last") or ""
        if not device_id:
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

    def handle_sync(self, payload: dict, client_ip: str) -> typing.Tuple[int, dict]:
        if not isinstance(payload, dict):
            return 400, {"ok": False, "error": "invalid_payload"}
        token = str(self.config.get("auth_token") or "").strip()
        if token and payload.get("token") != token:
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
                ack_ids.update(
                    str(x.get("id")) for x in results if isinstance(x, dict) and x.get("id")
                )
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
            _log(f"ws send failed: {exc}")

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

    def status_payload(self) -> dict:
        now = time.time()
        devices = []
        with self._lock:
            for device in self._devices.values():
                ws_conn = device.get("ws")
                transport = "ws" if ws_conn and getattr(ws_conn, "alive", False) else "http"
                devices.append(
                    {
                        "id": device.get("id"),
                        "last_seen": device.get("last_seen", 0.0),
                        "ip": device.get("ip", ""),
                        "info": device.get("info") or {},
                        "queue": len(device.get("queue") or []),
                        "logs": len(device.get("logs") or []),
                        "results": len(device.get("results") or []),
                        "transport": transport,
                    }
                )
        return {
            "ok": True,
            "server_ts": int(now * 1000),
            "devices": devices,
            "last_device_id": self._last_device_id,
        }

    def logs_payload(self, device_id: str, limit: int = 100) -> dict:
        device_id = str(device_id or "").strip()
        if device_id == "last":
            device_id = self._pick_device("last") or ""
        if not device_id:
            return {"ok": False, "error": "missing_device_id"}
        with self._lock:
            device = self._get_device(device_id)
            logs = list(device.get("logs") or [])
        if limit > 0:
            logs = logs[-limit:]
        return {"ok": True, "device_id": device_id, "logs": logs}


class BridgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "EtgBridgeServer/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_etg_file(self, path: str) -> None:
        if not path.startswith("/etg/"):
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        rel = path[len("/etg/") :].lstrip("/")
        if not rel:
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        root = _BASE_DIR
        full = os.path.normpath(os.path.join(root, rel))
        if not full.startswith(root):
            self._send_json(403, {"ok": False, "error": "forbidden"})
            return
        if not os.path.isfile(full):
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        try:
            with open(full, "rb") as handle:
                data = handle.read()
        except Exception:
            self._send_json(500, {"ok": False, "error": "read_failed"})
            return
        if full.endswith(".plugin"):
            ctype = "application/octet-stream"
        elif full.endswith(".md"):
            ctype = "text/markdown; charset=utf-8"
        else:
            ctype = "application/octet-stream"
        self._send_bytes(200, data, ctype)

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

    def _require_local(self, payload: typing.Optional[dict] = None) -> bool:
        bridge = getattr(self.server, "bridge", None)
        client_ip = self.client_address[0]
        allow_remote = bool(getattr(self.server, "allow_remote_queue", False))
        admin_token = str(getattr(self.server, "admin_token", "") or "").strip()
        if allow_remote:
            return True
        if not _is_local_ip(client_ip):
            if admin_token:
                token = ""
                if payload and isinstance(payload, dict):
                    token = str(payload.get("token") or "")
                header = self.headers.get("X-ETG-Token") or ""
                if token == admin_token or header == admin_token:
                    return True
            self._send_json(403, {"ok": False, "error": "forbidden"})
            return False
        return True

    def _read_json_body(self) -> typing.Optional[dict]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(413, {"ok": False, "error": "payload_too_large"})
            return None
        try:
            raw = self.rfile.read(length)
        except Exception:
            self._send_json(400, {"ok": False, "error": "read_failed"})
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(400, {"ok": False, "error": "invalid_json"})
            return None

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path.startswith("/etg"):
            self._serve_etg_file(path)
            return
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
        if path == "/status":
            if not self._require_local():
                return
            bridge = getattr(self.server, "bridge", None)
            if bridge is None:
                self._send_json(500, {"ok": False, "error": "bridge_missing"})
                return
            self._send_json(200, bridge.status_payload())
            return
        if path == "/result":
            if not self._require_local():
                return
            bridge = getattr(self.server, "bridge", None)
            if bridge is None:
                self._send_json(500, {"ok": False, "error": "bridge_missing"})
                return
            query = parse_qs(urlparse(self.path).query)
            device_id = (query.get("device_id") or [""])[0]
            action_id = (query.get("action_id") or [""])[0]
            pop = (query.get("pop") or ["0"])[0] in {"1", "true", "yes"}
            if not device_id or not action_id:
                self._send_json(400, {"ok": False, "error": "missing_params"})
                return
            result = bridge.get_result(device_id, action_id, pop=pop)
            if result is None:
                self._send_json(404, {"ok": False, "error": "not_found"})
                return
            self._send_json(200, {"ok": True, "result": result})
            return
        if path == "/logs":
            if not self._require_local():
                return
            bridge = getattr(self.server, "bridge", None)
            if bridge is None:
                self._send_json(500, {"ok": False, "error": "bridge_missing"})
                return
            query = parse_qs(urlparse(self.path).query)
            device_id = (query.get("device_id") or [""])[0]
            limit = int((query.get("limit") or ["100"])[0] or 100)
            payload = bridge.logs_payload(device_id, limit=limit)
            code = 200 if payload.get("ok") else 400
            self._send_json(code, payload)
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/sync":
            payload = self._read_json_body()
            if payload is None:
                return
            bridge = getattr(self.server, "bridge", None)
            if bridge is None:
                self._send_json(500, {"ok": False, "error": "bridge_missing"})
                return
            status, response = bridge.handle_sync(payload, self.client_address[0])
            self._send_json(status, response)
            return
        if path == "/queue":
            payload = self._read_json_body()
            if payload is None:
                return
            if not self._require_local(payload):
                return
            bridge = getattr(self.server, "bridge", None)
            if bridge is None:
                self._send_json(500, {"ok": False, "error": "bridge_missing"})
                return
            device_id = str(payload.get("device_id") or "last")
            action = str(payload.get("action") or "")
            action_payload = payload.get("payload") or {}
            ttl = int(payload.get("ttl") or 300)
            if not action:
                self._send_json(400, {"ok": False, "error": "missing_action"})
                return
            action_id, resolved = bridge.queue_action(device_id, action, action_payload, ttl)
            if not action_id:
                self._send_json(404, {"ok": False, "error": "device_not_found"})
                return
            self._send_json(
                200,
                {"ok": True, "action_id": action_id, "device_id": resolved},
            )
            return
        self._send_json(404, {"ok": False, "error": "not_found"})


def main() -> None:
    config = _load_config()
    host = str(config.get("listen_host") or "0.0.0.0")
    port = int(config.get("listen_port") or 8955)
    server = BridgeHTTPServer((host, port), BridgeHandler)
    server.bridge = BridgeState(config)
    server.allow_remote_queue = bool(config.get("allow_remote_queue", False))
    server.admin_token = str(config.get("admin_token") or "")

    if config.get("tls_enabled"):
        cert_path = str(config.get("tls_cert_path") or "").strip()
        key_path = str(config.get("tls_key_path") or "").strip()
        if not cert_path or not os.path.isfile(cert_path):
            raise FileNotFoundError(f"TLS cert not found: {cert_path}")
        if not key_path or not os.path.isfile(key_path):
            raise FileNotFoundError(f"TLS key not found: {key_path}")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        server.socket = context.wrap_socket(server.socket, server_side=True)

    scheme = "https" if config.get("tls_enabled") else "http"
    _log(f"listening on {scheme}://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

try:
    from herokutl.types import Message
    from .. import loader, utils
except Exception:
    try:
        from heroku import loader, utils
    except Exception:
        loader = None

if loader:
    @loader.tds
    class EtgServerStub(loader.Module):
        """ETG server helper (не модуль для установки)."""

        strings = {"name": "EtgServerStub"}

        @loader.command(ru_doc="Подсказка по ETG серверу")
        async def etgserver(self, message: Message):
            await utils.answer(
                message,
                "Это серверный скрипт ETG. Не загружай его как модуль. "
                "Установи `etg_bridge.py` и запускай `.etg`.",
            )
