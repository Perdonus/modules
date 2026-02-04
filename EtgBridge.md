# ETG Bridge (Heroku + Extera)

ETG Bridge — мост между Heroku‑модулями и клиентом Extera (ETG).  
Сервер принимает команды от Heroku, плагин ETG выполняет их на телефоне (UI, буфер, уведомления, рендеры) и возвращает результаты.

**Важно:** плагину нужен `mandre_lib`.

---

## 1) Компоненты

- **Сервер ETG**: HTTP + WebSocket (`/sync`, `/ws`). Хранит очередь действий и результаты.
- **Плагин ETG**: подключается к серверу, получает действия, выполняет их.
- **Heroku модуль**: только настройка сервера и выдача файлов. Для API в модулях используется `EtgBridgeAPI`.

Модуль после настройки можно удалить — сервер продолжит работать (если он запущен как сервис).

---

## 2) Быстрый старт

### Linux (рекомендуется)
1) Установи модуль `etg_bridge.py` в Heroku.
2) Перезагрузи модули.
3) Выполни:

```
.etg 9678
```

Модуль:
- создаст конфиг сервера
- включит автозапуск
- откроет порт
- пришлёт файлы **EtgBridge.plugin** и **mandre_lib.plugin**

### Windows
Модуль покажет готовые команды после установки:
- открыть порт через `netsh`
- запустить сервер через `python etg_server.py`

Если файла сервера нет, модуль скачает его с сервера:  
`https://sosiskibot.ru/etg/etg_server.py`

---

## 3) Пути и файлы

Серверные файлы:
- `modules/ETG/etg_server.py` — сервер моста
- `modules/ETG/etg_server.json` — конфиг сервера

Файлы плагинов:
- `modules/ETG/release/EtgBridge.plugin`
- `modules/ETG/release/mandre_lib.plugin`
- `modules/ETG/beta/*` — бета‑канал

---

## 4) Обновления плагина

Плагин обновляется **только** с домена:
- `https://sosiskibot.ru/etg/release/EtgBridge.plugin`
- `https://sosiskibot.ru/etg/release/mandre_lib.plugin`

Для беты используется `/etg/beta/`.

---

## 5) Настройки плагина

Доступно в настройках ETG Bridge:
- `URL сервера` — `https://<ip>:<port>/sync`
- `ID устройства` — ID клиента
- `Ветка обновлений` — release/beta
- `Язык`
- `Принудительная синхронизация`
- `Проверить обновления`

`auth_token` (опционально):
- Сервер читает `auth_token` из `etg_server.json`
- Плагин шлёт `auth_token` из своего хранилища (если задано вручную)

---

## 6) Протокол сервера

### HTTP
`POST /sync`

Запрос (пример):
```json
{
  "device_id": "abc123",
  "token": "...",
  "info": {...},
  "logs": [...],
  "results": [...],
  "ts": 1712345678901
}
```

Ответ:
```json
{
  "ok": true,
  "actions": [
    {"id": "uuid", "action": "toast", "payload": {"text": "hi"}, "ttl": 300}
  ]
}
```

### WebSocket
`/ws` — тот же формат, но в обе стороны по WS.

---

## 7) Подключение в Heroku‑модуле

Базовая схема:
```python
bridge = self.lookup("EtgBridge")
if not bridge:
    return

# Отправить действие
action_id = bridge.api.dialog(
    "last",
    title="ETG",
    text="Привет",
    buttons=["OK", "Cancel"],
    callback_id="hello_dialog"
)

# Ждать результат
res = await bridge.api.wait_result("last", action_id, timeout=30)
if res and res.get("ok"):
    data = res.get("data")
```

### Выбор устройства
- `"last"` — последнее активное устройство
- Явный `device_id` — смотри `.etg status`

---

## 8) Ответы / результаты

Результат от плагина:
```json
{
  "id": "action_id",
  "ok": true,
  "action": "dialog",
  "data": {...}
}
```
Ошибки:
```json
{
  "id": "action_id",
  "ok": false,
  "error": "...",
  "trace": "..."
}
```

---

## 9) API EtgBridgeAPI (основное)

### UI / диалоги
- `toast(device_id, text)`
- `dialog(device_id, title, text, buttons=None, callback_id=None)`
- `menu(device_id, title, message, items, callback_id=None)`
- `prompt(device_id, title, text="", hint="", multiline=True, max_len=0, callback_id=None)`
- `sheet(device_id, dsl, actions=None, callback_id=None)`
- `sheet_update(device_id, sheet_id, dsl, actions=None, callback_id=None)`
- `sheet_close(device_id, sheet_id)`
- `open_editor(device_id, title, content, filename="", readonly=False, callback_id=None)`
- `ripple(device_id, intensity=1.0, vibrate=True)`
- `select_chat(device_id, title="Выберите чат", callback_id=None)`

### Система
- `open_url(device_id, url)`
- `clipboard_set(device_id, text)`
- `clipboard_get(device_id)`
- `tts(device_id, text)`
- `notify(device_id, title, text)`
- `notify_dialog(device_id, sender_name, message, avatar_url="")`
- `share_text(device_id, text, title="Share")`
- `share_file(device_id, path, title="Share")`

### Медиа / рендер
- `send_png(device_id, url, caption="")`
- `render_html(device_id, html, width=1024, height=768, bg_color=(26,30,36), file_prefix="etg_", send=False, caption="")`

### Данные
- `device_info(device_id)`
- `recent_messages(device_id, dialog_id, limit=20)`
- `data_write(device_id, filename, data)`
- `data_read(device_id, filename)`
- `data_list(device_id)`
- `data_delete(device_id)`

### KV‑хранилище
- `kv_set(device_id, key, value, table="etg_bridge")`
- `kv_get(device_id, key, table="etg_bridge")`
- `kv_get_int(device_id, key, default=0, table="etg_bridge")`
- `kv_delete_prefix(device_id, prefix, table="etg_bridge")`

### Управление
- `pip_install(device_id, packages)`
- `exec(device_id, code)`

### Результаты
- `get_result(device_id, action_id, pop=False)`
- `wait_result(device_id, action_id, timeout=30, pop=True)`

---

## 10) DSL для sheet

Пример:
```xml
<sheet title="ETG" subtext="hello" close_text="Закрыть">
  <tag text="model: gpt" color="#7C4DFF" size="12" />
  <content size="14" align="left">Текст</content>
  <actions>
    <button id="ok" text="OK" />
    <button id="cancel" text="Cancel" />
  </actions>
</sheet>
```

Отлавливание ответа:
```python
action_id = bridge.api.sheet("last", dsl, actions=["ok", "cancel"], callback_id="sheet1")
res = await bridge.api.wait_result("last", action_id)
```

---

## 11) Диагностика

- `.etg status` — список устройств
- `.etg log` — логи установки
- `.seelog` (в плагине) — сетевые и update‑логи

Частые проблемы:
- **нет устройств** → проверь `server_url` в плагине
- **port закрыт** → открой порт (ufw / netsh)
- **обновление не ставится** → переустанови плагин 1 раз, дальше авто‑апдейты работают

---

## 12) Пример использования в модуле

```python
@loader.command()
async def etgtest(self, message: Message):
    bridge = self.lookup("EtgBridge")
    if not bridge:
        return await utils.answer(message, "ETG Bridge не найден")

    action_id = bridge.api.prompt(
        "last",
        title="Введите текст",
        hint="Например: привет",
        callback_id="prompt1"
    )

    res = await bridge.api.wait_result("last", action_id, timeout=40)
    if not res or not res.get("ok"):
        return await utils.answer(message, "Нет ответа от ETG")

    data = res.get("data") or {}
    text = data.get("text") or ""
    await utils.answer(message, f"Ответ: {text}")
```

---

Если нужна конкретная интеграция под модуль — опиши задачу, сделаю точечно.
