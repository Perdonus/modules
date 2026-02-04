# ETG Bridge

ETG Bridge — мост между Heroku‑модулями и ETG (Extera). Он состоит из:
- Heroku‑модуля для настройки сервера
- серверного скрипта `/sync` + `/ws`
- ETG‑плагина, который выполняет действия на телефоне
- mandrelib (зависимость для UI)

## Что внутри

```
module/etg_bridge.py
server/etg_server.py
plugin/EtgBridge.plugin
plugin/mandre_lib.plugin
docs/ETG_BRIDGE.md
```

## Быстрый старт

1) Установи `module/etg_bridge.py` в Heroku.
2) В чате выполни `.etg 8955` и подтверди установку.
3) Установи полученные плагины в ETG.
4) В настройках плагина задай URL сервера и Device ID.

## Документация

Полная документация: `docs/ETG_BRIDGE.md`.

## Примечания

- Плагин проверяет обновления при старте и по таймеру.
- Для UI и системных действий нужен `mandre_lib.plugin`.
