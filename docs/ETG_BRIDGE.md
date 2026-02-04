# ETG Bridge (Heroku)

ETG Bridge — мост между Heroku‑модулями и клиентом ETG (Extera).  
Плагин выполняет действия на телефоне (UI, уведомления, буфер, данные, рендеры),
а серверная часть живёт на Heroku и отдаёт команды по `/sync` и `/ws`.

ВАЖНО: плагину нужен **mandrelib**. Он отвечает за UI и системные функции.
WS работает автоматически, плагин принимает self‑signed сертификаты.

---

## Как это устроено

- **Сервер**: HTTP/WS на твоём сервере. Хранит очередь действий и результаты.
- **Плагин ETG**: подключается к серверу, получает команды, выполняет их.
- **Heroku‑модули**: вызывают `bridge.api.*` и отправляют команды на сервер.

Модуль `EtgBridge` в Heroku **используется только для настройки**
(порты, автозапуск, конфиг, файлы). После настройки сервер работает сам.

---

## Быстрый старт

1) На сервере в Heroku выполни:
   
   `.etg 8955`

   Команда:
   - откроет порт сервера
   - создаст конфиг
   - поставит автозапуск `etg-bridge.service`
   - скопирует файлы плагина в `/root/Heroku/modules/ETG/`
   - выдаст ссылки и пришлёт файлы плагинов
   - запросит подтверждение установкой

2) Установи **ETG Bridge** и **mandrelib** из файлов, которые пришли.

3) В настройках плагина укажи URL сервера и Device ID.
   После `.etg` URL обычно уже вписан в файл, проверь и при необходимости измени.

---

## Пути на сервере

- `/root/Heroku/modules/ETG/etg_server.py` — сервер моста
- `/root/Heroku/modules/ETG/etg_server.json` — конфиг сервера
- `/root/Heroku/modules/ETG/release/` — файлы релиза
- `/root/Heroku/modules/ETG/beta/` — файлы беты

Автозапуск:
- `systemd` сервис: `etg-bridge.service`

---

## Настройки плагина

- **URL сервера** — адрес `/sync` (пример: `https://<ip>:8955/sync`)
- **Device ID** — идентификатор клиента
- **Ветка обновлений** — `Релиз` или `Бета`
- **Язык** — интерфейс плагина
- **Force sync** — принудительная синхронизация
- **Check updates now** — ручная проверка обновлений

WS включен автоматически и отдельной настройки не имеет.

---

## Обновления (release / beta)

Плагин умеет обновляться сам.
Файлы обновлений раздаются самим сервером:

- `https://<ip>:8955/etg/release/EtgBridge.plugin`
- `https://<ip>:8955/etg/release/mandre_lib.plugin`

Для беты используются файлы из `/etg/beta/`.

Плагин проверяет обновления при запуске ETG и по таймеру.

---

## Команды в Heroku

- `.etg <порт>` — установка и настройка сервера
- `.etg status` — статус сервера и список устройств
- `.etg log` — логи установки
- `.unetg` — удалить настройки сервера
- `.reinetg [порт]` — переустановка

---

## API для Heroku‑модулей

Использование:

```python
bridge = self.lookup("EtgBridge")
bridge.api.toast("last", "Hello")
```

Примеры:

```python
bridge.api.toast("last", "Hello from Heroku")
bridge.api.dialog("last", title="Hi", text="Welcome", buttons=["OK", "Cancel"])
bridge.api.menu("last", "Выбор", "Выбери", items=[{"id":"a","text":"A"}])
bridge.api.notify("last", title="Ping", text="ETG active")
bridge.api.open_url("last", "https://example.com")
bridge.api.clipboard_set("last", "copy me")
bridge.api.prompt("last", title="Ввод", hint="Напиши текст")
bridge.api.open_editor("last", title="Код", content="print('hi')", filename="code.py")
```

---

## UI‑панели (Mandre DSL)

Плагин поддерживает DSL‑схемы для красивых UI‑панелей.
Пример:

```xml
<sheet title="Demo" subtext="Hello" sub_size="12" close_text="Закрыть">
  <tag text="model: gpt" color="#7C4DFF" size="12" />
  <content size="14" align="left">Текст</content>
  <actions>
    <button id="ok" text="OK" />
    <button id="close" text="Close" />
  </actions>
</sheet>
```

На стороне Heroku получишь `sheet_action` по `callback_id`.

---

## Доступные действия

```
toast
  {"text":"Hello"}

dialog
  {"title":"Title","text":"Message","buttons":["OK","Cancel"],"callback_id":"id"}

menu
  {"title":"Menu","message":"Pick one","items":[{"id":"a","text":"A"}],"callback_id":"id"}

prompt
  {"title":"Input","text":"","hint":"Type...","multiline":true,"max_len":0,"callback_id":"id"}

open_editor
  {"title":"Editor","content":"...","filename":"file.py","readonly":false,"callback_id":"id"}

sheet / sheet_update / sheet_close
  {"dsl":"<sheet ...>","actions":["ok"],"callback_id":"id","sheet_id":"main"}

select_chat
  {"title":"Выберите чат","callback_id":"id"}

ripple
  {"intensity":1.2,"vibrate":true}

open_url
  {"url":"https://example.com"}

clipboard_set / clipboard_get
  {"text":"copy"} / {}

notify / notify_dialog
  {"title":"Ping","text":"ETG active"}
  {"sender_name":"ETG","message":"Hi","avatar_url":"https://..."}

tts
  {"text":"Hello"}

share_text / share_file
  {"text":"Hello","title":"Share"}
  {"path":"/sdcard/Download/file.txt","title":"Share"}

send_png
  {"url":"https://example.com/img.png","caption":"optional"}

render_html
  {"html":"<html>...</html>","width":1024,"height":768,
   "bg_color":[26,30,36],"file_prefix":"etg_","send":true,"caption":"optional"}

device_info
  {}

recent_messages
  {"dialog_id":123456789,"limit":20}

data_write / data_read / data_list / data_delete
  {"filename":"data.json","data":{"k":"v"}}

kv_set / kv_get / kv_get_int / kv_delete_prefix
  {"key":"user:1","value":"premium","table":"etg_bridge"}
```

---

## Интеграция mandrelib

ETG Bridge рассчитан на mandrelib:
- UI (sheet, menu, dialog)
- системные действия
- автообновление

Если mandrelib не установлен — поставь его файлом, который пришёл после `.etg`.

---

## Траблшутинг

- `.etg status` — проверка статуса и устройств
- `systemctl status etg-bridge` — статус сервиса
- Если сертификат самоподписанный — выключи `Verify SSL` или укажи `CA bundle`
- Для беты выбери ветку `Бета` в настройках
