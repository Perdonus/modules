# ETG Bridge (Heroku module)

Минимальный репозиторий: только модуль и README.

## Файл модуля

- `etg_bridge.py`

## Источник плагинов и обновлений

Модуль скачивает **EtgBridge.plugin** и **mandre_lib.plugin** с официального сервера:

```
https://sosiskibot.ru/etg/release/EtgBridge.plugin
https://sosiskibot.ru/etg/release/mandre_lib.plugin
```

Именно этот домен используется для обновлений в плагине (не IP пользователя).

## Установка

1) Скопируй `etg_bridge.py` в свои Heroku modules.
2) Перезагрузи модули.
3) Запусти установку:

```
.etg 8955
```

## Команды

- `.etg <порт>` — установка и настройка ETG сервера
- `.etg status` — статус и устройства
- `.etg log` — логи установки
- `.unetg` — удалить настройки сервера
- `.reinetg [порт]` — переустановка
