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

INSTALL_LANGS = [
    ("ru", "🇷🇺 Русский"),
    ("be", "🇧🇾 Беларуская"),
    ("uk", "🇺🇦 Українська"),
    ("kk", "🇰🇿 Қазақша"),
    ("en", "🇬🇧 English"),
    ("fr", "🇫🇷 Français"),
    ("ja", "🇯🇵 日本語"),
    ("zh", "🇨🇳 中文"),
    ("ko", "🇰🇷 한국어"),
    ("kp", "🇰🇵 조선말"),
    ("pir_ru", "🏴‍☠️ Пиратский RU"),
    ("pir_en", "🏴‍☠️ Pirate EN"),
    ("meme", "🤪 Мемчик"),
]

_INSTALL_I18N = {
    "en": {
        "choose_lang_title": "Choose install language",
        "choose_lang_hint": "Language affects only the installer messages.",
        "confirm_install": "Install ETG on port {port}?",
        "confirm_note_existing": "Port {port} is already used by ETG and will be reused.",
        "btn_install": "✅ Install",
        "btn_cancel": "❌ Cancel",
        "installing": "Installing ETG on port {port}...",
        "install_error": "Install failed. Logs: `.etg log`",
        "install_done": "Install finished. Commands were sent.",
        "install_done_with_errors": "Install finished with errors. Logs + manual steps were sent.",
        "install_cancel": "Install cancelled.",
        "port_prompt": "Provide a port: `.etg 8955`",
        "port_invalid": "Port must be 1-65535. Example: `.etg 8955`",
        "port_busy": "Port {port} is busy: {error}",
        "manual_title": "Install had errors. Try manual steps:",
        "manual_hint": "Commands can be executed from userbot via `.terminal`.",
        "manual_step_iptables": "1) Disable iptables",
        "manual_step_ufw_install": "2) Install ufw",
        "manual_step_ufw_allow": "3) Open port {port}",
        "manual_step_server": "4) Start ETG server",
        "manual_step_check": "5) Check port reachability",
        "manual_step_forward": "If external IP fails — set up port forwarding on router.",
        "post_ok_title": "All set. Install libraries below!",
        "post_install_ufw": "Install ufw: `{cmd}`",
        "post_open_port": "Open port: `{cmd}`",
        "post_open_port_win": "Open port: `{cmd}`",
        "post_start_server": "Start server: `{cmd}`",
        "post_win_note": "Windows: ufw is not supported.",
        "sudo_password": "sudo may ask for password on your PC.",
        "port_check_external": "External check",
        "port_check_local": "Local check",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "Port check: external {ext} / local {loc}",
        "q_vps_title": "Is this a VPS?",
        "q_vps_desc": "VPS is a public server with its own external IP.",
        "q_public_title": "Do you have a public (external) IP?",
        "q_public_desc": "External IP is what you see on sites like 2ip/ifconfig. Without it you need the same LAN.",
        "q_device_title": "Is your userbot on the same device?",
        "q_device_desc": "If not, it will work only within the same local network.",
        "btn_yes": "✅ Yes",
        "btn_no": "❌ No",
        "btn_same_device": "✅ Same device",
        "btn_other_device": "📡 Another device",
        "sudo_request_title": "Sudo password required",
        "sudo_request_desc": "Open `.cfg EtgBridge` and fill `sudo_password`. After you enter it, install continues.",
        "sudo_wrong_password": "Wrong sudo password. Try again.",
        "install_paused": "Waiting for sudo password...",
        "contact_hint": "Need help? @etopizdesblin",
        "warning_local_same": "Local mode: works only in the same network.",
        "warning_local_other": "Local mode: server and client must be in the same LAN.",
        "warning_vpn": "Disable VPN/Proxy while using ETG API (they can change IP).",
        "etgtest_hint": "Run `.etgtest` to check access from plugin side.",
        "port_forward_hint": "Port forwarding is required on your router.",
    },
    "ru": {
        "choose_lang_title": "Выберите язык установки",
        "choose_lang_hint": "Язык влияет только на сообщения установщика.",
        "confirm_install": "Установить ETG на порт {port}?",
        "confirm_note_existing": "Порт {port} уже занят ETG и будет использован.",
        "btn_install": "✅ Установить",
        "btn_cancel": "❌ Отмена",
        "installing": "Устанавливаю ETG на порт {port}...",
        "install_error": "Ошибка установки. Логи: `.etg log`",
        "install_done": "Установка завершена. Сообщение с командами отправлено.",
        "install_done_with_errors": "Установка завершена с ошибками. Логи и шаги отправлены.",
        "install_cancel": "Установка отменена.",
        "port_prompt": "Укажите порт: `.etg 8955`",
        "port_invalid": "Нужен порт 1-65535. Пример: `.etg 8955`",
        "port_busy": "Порт {port} занят: {error}",
        "manual_title": "Установка выполнена с ошибками. Попробуйте вручную:",
        "manual_hint": "Команды можно запускать из юзербота через `.terminal`.",
        "manual_step_iptables": "1) Отключить iptables",
        "manual_step_ufw_install": "2) Установить ufw",
        "manual_step_ufw_allow": "3) Открыть порт {port}",
        "manual_step_server": "4) Запустить ETG сервер",
        "manual_step_check": "5) Проверить доступность порта",
        "manual_step_forward": "Если внешний адрес недоступен — нужен проброс порта на роутере.",
        "post_ok_title": "Всё настроено, установите библиотеки ниже!",
        "post_install_ufw": "Установка ufw: `{cmd}`",
        "post_open_port": "Открой порт: `{cmd}`",
        "post_open_port_win": "Открой порт: `{cmd}`",
        "post_start_server": "Запуск сервера: `{cmd}`",
        "post_win_note": "Windows: ufw не поддерживается.",
        "sudo_password": "sudo попросит пароль на вашем ПК.",
        "port_check_external": "Проверка внешнего",
        "port_check_local": "Проверка локального",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "Проверка порта: внешний {ext} / локальный {loc}",
        "q_vps_title": "У вас VPS?",
        "q_vps_desc": "VPS — это сервер с внешним IP.",
        "q_public_title": "У вас есть внешний IP?",
        "q_public_desc": "Внешний IP — как на сайтах 2ip/ifconfig. Без него нужна одна сеть.",
        "q_device_title": "Юзербот на этом же устройстве?",
        "q_device_desc": "Если нет — всё будет работать только в одной сети.",
        "btn_yes": "✅ Да",
        "btn_no": "❌ Нет",
        "btn_same_device": "✅ На этом",
        "btn_other_device": "📡 На другом",
        "sudo_request_title": "Нужен пароль sudo",
        "sudo_request_desc": "Открой `.cfg EtgBridge` и заполни `sudo_password`. После ввода установка продолжится.",
        "sudo_wrong_password": "Пароль sudo неверный. Попробуйте снова.",
        "install_paused": "Ожидаю пароль sudo...",
        "contact_hint": "Нужна помощь? @etopizdesblin",
        "warning_local_same": "Локальный режим: работает только в одной сети.",
        "warning_local_other": "Локальный режим: сервер и клиент должны быть в одной сети.",
        "warning_vpn": "Выключите VPN/Proxy при работе с ETG API (они меняют IP).",
        "etgtest_hint": "Запусти `.etgtest` для проверки доступа со стороны плагина.",
        "port_forward_hint": "Нужен проброс порта на роутере.",
    },
    "be": {
        "choose_lang_title": "Абярыце мову ўстаноўкі",
        "choose_lang_hint": "Мова ўплывае толькі на паведамленні ўстаноўкі.",
        "confirm_install": "Усталяваць ETG на порт {port}?",
        "confirm_note_existing": "Порт {port} ужо заняты ETG і будзе выкарыстаны.",
        "btn_install": "✅ Усталяваць",
        "btn_cancel": "❌ Адмена",
        "installing": "Усталёўваю ETG на порт {port}...",
        "install_error": "Памылка ўстаноўкі. Лагі: `.etg log`",
        "install_done": "Устаноўка завершана. Каманды адпраўлены.",
        "install_done_with_errors": "Устаноўка з памылкамі. Лагі і крокі адпраўлены.",
        "install_cancel": "Устаноўка адменена.",
        "port_prompt": "Пакажыце порт: `.etg 8955`",
        "port_invalid": "Порт 1-65535. Прыклад: `.etg 8955`",
        "port_busy": "Порт {port} заняты: {error}",
        "manual_title": "Устаноўка з памылкамі. Паспрабуйце ўручную:",
        "manual_hint": "Каманды можна запускаць праз `.terminal`.",
        "manual_step_iptables": "1) Адключыць iptables",
        "manual_step_ufw_install": "2) Усталяваць ufw",
        "manual_step_ufw_allow": "3) Адкрыць порт {port}",
        "manual_step_server": "4) Запусціць ETG сервер",
        "manual_step_check": "5) Праверыць даступнасць порта",
        "manual_step_forward": "Калі вонкавы IP недаступны — патрэбны пракід порта.",
        "post_ok_title": "Усё гатова, усталюйце бібліятэкі ніжэй!",
        "post_install_ufw": "Устаноўка ufw: `{cmd}`",
        "post_open_port": "Адкрый порт: `{cmd}`",
        "post_open_port_win": "Адкрый порт: `{cmd}`",
        "post_start_server": "Запуск сервера: `{cmd}`",
        "post_win_note": "Windows: ufw не падтрымліваецца.",
        "sudo_password": "sudo можа запытаць пароль.",
        "port_check_external": "Праверка знешняга",
        "port_check_local": "Праверка лакальнага",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "Праверка порта: знешні {ext} / лакальны {loc}",
        "q_vps_title": "У вас VPS?",
        "q_vps_desc": "VPS — сервер з вонкавым IP.",
        "q_public_title": "Ёсць знешні IP?",
        "q_public_desc": "Знешні IP — як на 2ip/ifconfig. Без яго патрэбна адна сетка.",
        "q_device_title": "Юзербот на гэтым жа прыладзе?",
        "q_device_desc": "Калі не — будзе працаваць толькі ў адной сетцы.",
        "btn_yes": "✅ Так",
        "btn_no": "❌ Не",
        "btn_same_device": "✅ На гэтым",
        "btn_other_device": "📡 На іншым",
        "sudo_request_title": "Патрэбны пароль sudo",
        "sudo_request_desc": "Адкрый `.cfg EtgBridge` і запоўні `sudo_password`. Пасля ўводу ўстаноўка працягнецца.",
        "sudo_wrong_password": "Няправільны пароль sudo. Паспрабуйце зноў.",
        "install_paused": "Чакаю пароль sudo...",
        "contact_hint": "Патрэбна дапамога? @etopizdesblin",
        "warning_local_same": "Лакальны рэжым: працуе толькі ў адной сетцы.",
        "warning_local_other": "Лакальны рэжым: сервер і кліент павінны быць у адной сетцы.",
        "warning_vpn": "Адключыце VPN/Proxy пры працы з ETG API (могуць змяняць IP).",
        "etgtest_hint": "Запусціце `.etgtest` для праверкі доступу з боку плагіна.",
        "port_forward_hint": "Патрэбны пракід порта на роутары.",
    },
    "uk": {
        "choose_lang_title": "Оберіть мову встановлення",
        "choose_lang_hint": "Мова впливає лише на повідомлення встановлювача.",
        "confirm_install": "Встановити ETG на порт {port}?",
        "confirm_note_existing": "Порт {port} вже зайнятий ETG і буде використаний.",
        "btn_install": "✅ Встановити",
        "btn_cancel": "❌ Скасувати",
        "installing": "Встановлюю ETG на порт {port}...",
        "install_error": "Помилка встановлення. Логи: `.etg log`",
        "install_done": "Встановлення завершено. Команди надіслано.",
        "install_done_with_errors": "Встановлення з помилками. Логи та кроки надіслано.",
        "install_cancel": "Встановлення скасовано.",
        "port_prompt": "Вкажіть порт: `.etg 8955`",
        "port_invalid": "Порт 1-65535. Приклад: `.etg 8955`",
        "port_busy": "Порт {port} зайнятий: {error}",
        "manual_title": "Встановлення з помилками. Спробуйте вручну:",
        "manual_hint": "Команди можна запускати через `.terminal`.",
        "manual_step_iptables": "1) Вимкнути iptables",
        "manual_step_ufw_install": "2) Встановити ufw",
        "manual_step_ufw_allow": "3) Відкрити порт {port}",
        "manual_step_server": "4) Запустити ETG сервер",
        "manual_step_check": "5) Перевірити доступність порту",
        "manual_step_forward": "Якщо зовнішній IP недоступний — потрібен проброс порту.",
        "post_ok_title": "Все готово, встановіть бібліотеки нижче!",
        "post_install_ufw": "Встановити ufw: `{cmd}`",
        "post_open_port": "Відкрий порт: `{cmd}`",
        "post_open_port_win": "Відкрий порт: `{cmd}`",
        "post_start_server": "Запуск сервера: `{cmd}`",
        "post_win_note": "Windows: ufw не підтримується.",
        "sudo_password": "sudo може запросити пароль.",
        "port_check_external": "Перевірка зовнішнього",
        "port_check_local": "Перевірка локального",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "Перевірка порту: зовнішній {ext} / локальний {loc}",
        "q_vps_title": "У вас VPS?",
        "q_vps_desc": "VPS — сервер із зовнішнім IP.",
        "q_public_title": "Є зовнішній IP?",
        "q_public_desc": "Зовнішній IP — як на 2ip/ifconfig. Без нього потрібна одна мережа.",
        "q_device_title": "Юзербот на цьому ж пристрої?",
        "q_device_desc": "Якщо ні — працюватиме тільки в одній мережі.",
        "btn_yes": "✅ Так",
        "btn_no": "❌ Ні",
        "btn_same_device": "✅ На цьому",
        "btn_other_device": "📡 На іншому",
        "sudo_request_title": "Потрібен пароль sudo",
        "sudo_request_desc": "Відкрий `.cfg EtgBridge` і заповни `sudo_password`. Після вводу встановлення продовжиться.",
        "sudo_wrong_password": "Невірний пароль sudo. Спробуйте ще раз.",
        "install_paused": "Очікую пароль sudo...",
        "contact_hint": "Потрібна допомога? @etopizdesblin",
        "warning_local_same": "Локальний режим: працює лише в одній мережі.",
        "warning_local_other": "Локальний режим: сервер і клієнт мають бути в одній мережі.",
        "warning_vpn": "Вимкніть VPN/Proxy під час роботи з ETG API (можуть змінювати IP).",
        "etgtest_hint": "Запусти `.etgtest` для перевірки доступу з боку плагіна.",
        "port_forward_hint": "Потрібен проброс порту на роутері.",
    },
    "kk": {
        "choose_lang_title": "Орнату тілін таңдаңыз",
        "choose_lang_hint": "Тіл тек орнатушы хабарламаларына әсер етеді.",
        "confirm_install": "{port} портына ETG орнату керек пе?",
        "confirm_note_existing": "{port} порты ETG арқылы бос емес, қайта қолданылады.",
        "btn_install": "✅ Орнату",
        "btn_cancel": "❌ Бас тарту",
        "installing": "{port} портына ETG орнатылуда...",
        "install_error": "Орнату қатесі. Логтар: `.etg log`",
        "install_done": "Орнату аяқталды. Командалар жіберілді.",
        "install_done_with_errors": "Қателермен аяқталды. Логтар мен қадамдар жіберілді.",
        "install_cancel": "Орнату тоқтатылды.",
        "port_prompt": "Порт көрсетіңіз: `.etg 8955`",
        "port_invalid": "Порт 1-65535. Мысал: `.etg 8955`",
        "port_busy": "{port} порты бос емес: {error}",
        "manual_title": "Қателер бар. Қолмен жасап көріңіз:",
        "manual_hint": "Командаларды `.terminal` арқылы іске қоса аласыз.",
        "manual_step_iptables": "1) iptables өшіру",
        "manual_step_ufw_install": "2) ufw орнату",
        "manual_step_ufw_allow": "3) {port} портын ашу",
        "manual_step_server": "4) ETG серверін іске қосу",
        "manual_step_check": "5) Порт қолжетімділігін тексеру",
        "manual_step_forward": "Сыртқы IP ашылмаса — роутерде проброс керек.",
        "post_ok_title": "Бәрі дайын, төменде кітапханаларды орнатыңыз!",
        "post_install_ufw": "ufw орнату: `{cmd}`",
        "post_open_port": "Порт ашу: `{cmd}`",
        "post_open_port_win": "Порт ашу: `{cmd}`",
        "post_start_server": "Серверді іске қосу: `{cmd}`",
        "post_win_note": "Windows: ufw қолжетімсіз.",
        "sudo_password": "sudo құпиясөз сұрауы мүмкін.",
        "port_check_external": "Сыртқы тексеру",
        "port_check_local": "Жергілікті тексеру",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "Порт тексеруі: сыртқы {ext} / жергілікті {loc}",
        "q_vps_title": "Сізде VPS бар ма?",
        "q_vps_desc": "VPS — сыртқы IP бар сервер.",
        "q_public_title": "Сыртқы IP бар ма?",
        "q_public_desc": "Сыртқы IP — 2ip/ifconfig сияқты сайттардағы адрес. Онсыз бір желі керек.",
        "q_device_title": "Юзербот осы құрылғыда ма?",
        "q_device_desc": "Жоқ болса — тек бір желі ішінде жұмыс істейді.",
        "btn_yes": "✅ Иә",
        "btn_no": "❌ Жоқ",
        "btn_same_device": "✅ Осы құрылғы",
        "btn_other_device": "📡 Басқа құрылғы",
        "sudo_request_title": "sudo паролі керек",
        "sudo_request_desc": "`.cfg EtgBridge` ашып, `sudo_password` толтырыңыз. Енгізгеннен кейін орнату жалғасады.",
        "sudo_wrong_password": "sudo паролі қате. Қайта енгізіңіз.",
        "install_paused": "sudo паролін күтіп тұрмын...",
        "contact_hint": "Көмек керек пе? @etopizdesblin",
        "warning_local_same": "Жергілікті режим: тек бір желіде жұмыс істейді.",
        "warning_local_other": "Жергілікті режим: сервер мен клиент бір желіде болуы керек.",
        "warning_vpn": "ETG API қолданғанда VPN/Proxy өшіріңіз (IP өзгеруі мүмкін).",
        "etgtest_hint": "Плагин жағынан тексеру үшін `.etgtest` іске қосыңыз.",
        "port_forward_hint": "Маршрутизаторда портты бағыттау қажет.",
    },
    "fr": {
        "choose_lang_title": "Choisissez la langue d'installation",
        "choose_lang_hint": "La langue n'affecte que les messages d'installation.",
        "confirm_install": "Installer ETG sur le port {port} ?",
        "confirm_note_existing": "Le port {port} est déjà utilisé par ETG et sera réutilisé.",
        "btn_install": "✅ Installer",
        "btn_cancel": "❌ Annuler",
        "installing": "Installation d'ETG sur le port {port}...",
        "install_error": "Erreur d'installation. Logs : `.etg log`",
        "install_done": "Installation terminée. Les commandes ont été envoyées.",
        "install_done_with_errors": "Installation avec erreurs. Logs et étapes envoyés.",
        "install_cancel": "Installation annulée.",
        "port_prompt": "Indiquez un port : `.etg 8955`",
        "port_invalid": "Port 1-65535. Exemple : `.etg 8955`",
        "port_busy": "Le port {port} est occupé : {error}",
        "manual_title": "Installation avec erreurs. Essayez manuellement :",
        "manual_hint": "Les commandes peuvent être exécutées via `.terminal`.",
        "manual_step_iptables": "1) Désactiver iptables",
        "manual_step_ufw_install": "2) Installer ufw",
        "manual_step_ufw_allow": "3) Ouvrir le port {port}",
        "manual_step_server": "4) Démarrer le serveur ETG",
        "manual_step_check": "5) Vérifier l'accès au port",
        "manual_step_forward": "Si l'IP externe échoue — configurer le port forwarding.",
        "post_ok_title": "Tout est prêt, installez les bibliothèques ci-dessous !",
        "post_install_ufw": "Installer ufw : `{cmd}`",
        "post_open_port": "Ouvrir le port : `{cmd}`",
        "post_open_port_win": "Ouvrir le port : `{cmd}`",
        "post_start_server": "Démarrer le serveur : `{cmd}`",
        "post_win_note": "Windows : ufw n'est pas pris en charge.",
        "sudo_password": "sudo peut demander un mot de passe.",
        "port_check_external": "Vérification externe",
        "port_check_local": "Vérification locale",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "Test du port : externe {ext} / local {loc}",
        "q_vps_title": "Vous avez un VPS ?",
        "q_vps_desc": "Un VPS est un serveur public avec une IP externe.",
        "q_public_title": "Avez-vous une IP publique ?",
        "q_public_desc": "IP publique = celle affichée sur 2ip/ifconfig. Sans elle, même LAN requis.",
        "q_device_title": "Le userbot est sur le même appareil ?",
        "q_device_desc": "Sinon, ça marche uniquement dans le même réseau local.",
        "btn_yes": "✅ Oui",
        "btn_no": "❌ Non",
        "btn_same_device": "✅ Même appareil",
        "btn_other_device": "📡 Autre appareil",
        "sudo_request_title": "Mot de passe sudo requis",
        "sudo_request_desc": "Ouvrez `.cfg EtgBridge` et remplissez `sudo_password`. L'installation continuera ensuite.",
        "sudo_wrong_password": "Mot de passe sudo incorrect. Réessayez.",
        "install_paused": "En attente du mot de passe sudo...",
        "contact_hint": "Besoin d'aide ? @etopizdesblin",
        "warning_local_same": "Mode local : fonctionne uniquement dans le même réseau.",
        "warning_local_other": "Mode local : serveur et client doivent être dans le même réseau.",
        "warning_vpn": "Désactivez VPN/Proxy lors de l'utilisation de l'API ETG (ils changent l'IP).",
        "etgtest_hint": "Lancez `.etgtest` pour vérifier l'accès côté plugin.",
        "port_forward_hint": "Redirection de port requise sur le routeur.",
    },
    "ja": {
        "choose_lang_title": "インストール言語を選択",
        "choose_lang_hint": "言語はインストーラーの表示のみ変更します。",
        "confirm_install": "ポート{port}にETGをインストールしますか？",
        "confirm_note_existing": "ポート{port}はETGで使用中のため再利用します。",
        "btn_install": "✅ インストール",
        "btn_cancel": "❌ キャンセル",
        "installing": "ポート{port}にETGをインストール中...",
        "install_error": "インストール失敗。ログ: `.etg log`",
        "install_done": "インストール完了。コマンドを送信しました。",
        "install_done_with_errors": "エラーあり。ログと手順を送信しました。",
        "install_cancel": "インストールを中止しました。",
        "port_prompt": "ポート指定: `.etg 8955`",
        "port_invalid": "ポートは1-65535。例: `.etg 8955`",
        "port_busy": "ポート{port}は使用中: {error}",
        "manual_title": "エラーが出ました。手動で試してください：",
        "manual_hint": "`.terminal`で実行できます。",
        "manual_step_iptables": "1) iptablesを無効化",
        "manual_step_ufw_install": "2) ufwをインストール",
        "manual_step_ufw_allow": "3) ポート{port}を開放",
        "manual_step_server": "4) ETGサーバー起動",
        "manual_step_check": "5) ポート疎通チェック",
        "manual_step_forward": "外部IPがNGならルータでポート開放が必要。",
        "post_ok_title": "準備完了。以下のライブラリを入れてください！",
        "post_install_ufw": "ufwインストール: `{cmd}`",
        "post_open_port": "ポート開放: `{cmd}`",
        "post_open_port_win": "ポート開放: `{cmd}`",
        "post_start_server": "サーバー起動: `{cmd}`",
        "post_win_note": "Windows: ufwは非対応。",
        "sudo_password": "sudoがパスワードを要求する場合があります。",
        "port_check_external": "外部チェック",
        "port_check_local": "ローカルチェック",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "ポート確認: 外部 {ext} / ローカル {loc}",
        "q_vps_title": "VPSですか？",
        "q_vps_desc": "VPSは外部IPを持つサーバーです。",
        "q_public_title": "外部IPはありますか？",
        "q_public_desc": "外部IPは2ip/ifconfigに表示されるIP。ない場合は同一LANが必要。",
        "q_device_title": "ユーザーボットは同じ端末？",
        "q_device_desc": "違う場合は同じLAN内でのみ動作します。",
        "btn_yes": "✅ はい",
        "btn_no": "❌ いいえ",
        "btn_same_device": "✅ 同じ端末",
        "btn_other_device": "📡 別端末",
        "sudo_request_title": "sudoパスワードが必要",
        "sudo_request_desc": "`.cfg EtgBridge`で`sudo_password`を入力。入力後にインストール再開。",
        "sudo_wrong_password": "sudoパスワードが違います。再入力してください。",
        "install_paused": "sudoパスワード待ち...",
        "contact_hint": "ヘルプ: @etopizdesblin",
        "warning_local_same": "ローカルモード: 同一LAN内のみ。",
        "warning_local_other": "ローカルモード: サーバーとクライアントが同一LAN内。",
        "warning_vpn": "ETG API使用時はVPN/Proxyをオフにしてください。",
        "etgtest_hint": "プラグイン側の確認は `.etgtest`。",
        "port_forward_hint": "ルーターでポート開放が必要。",
    },
    "zh": {
        "choose_lang_title": "选择安装语言",
        "choose_lang_hint": "语言仅影响安装器提示。",
        "confirm_install": "在端口{port}安装ETG？",
        "confirm_note_existing": "端口{port}已被ETG占用，将复用。",
        "btn_install": "✅ 安装",
        "btn_cancel": "❌ 取消",
        "installing": "正在端口{port}安装ETG...",
        "install_error": "安装失败。日志: `.etg log`",
        "install_done": "安装完成。命令已发送。",
        "install_done_with_errors": "安装有错误。日志和步骤已发送。",
        "install_cancel": "安装已取消。",
        "port_prompt": "输入端口：`.etg 8955`",
        "port_invalid": "端口范围1-65535。示例：`.etg 8955`",
        "port_busy": "端口{port}被占用：{error}",
        "manual_title": "安装有错误，请手动尝试：",
        "manual_hint": "可通过`.terminal`执行命令。",
        "manual_step_iptables": "1) 关闭iptables",
        "manual_step_ufw_install": "2) 安装ufw",
        "manual_step_ufw_allow": "3) 放行端口{port}",
        "manual_step_server": "4) 启动ETG服务器",
        "manual_step_check": "5) 检查端口连通性",
        "manual_step_forward": "外网不可达需在路由器做端口映射。",
        "post_ok_title": "准备完成，请安装下面的库！",
        "post_install_ufw": "安装ufw：`{cmd}`",
        "post_open_port": "放行端口：`{cmd}`",
        "post_open_port_win": "放行端口：`{cmd}`",
        "post_start_server": "启动服务器：`{cmd}`",
        "post_win_note": "Windows不支持ufw。",
        "sudo_password": "sudo 可能需要密码。",
        "port_check_external": "外网检查",
        "port_check_local": "本地检查",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "端口检查：外网 {ext} / 本地 {loc}",
        "q_vps_title": "你用的是VPS吗？",
        "q_vps_desc": "VPS是带外网IP的服务器。",
        "q_public_title": "有公网IP吗？",
        "q_public_desc": "公网IP可在2ip/ifconfig看到。没有则需同一局域网。",
        "q_device_title": "用户机器人在同一设备吗？",
        "q_device_desc": "否则仅同一局域网可用。",
        "btn_yes": "✅ 是",
        "btn_no": "❌ 否",
        "btn_same_device": "✅ 同一设备",
        "btn_other_device": "📡 其他设备",
        "sudo_request_title": "需要sudo密码",
        "sudo_request_desc": "打开`.cfg EtgBridge`填写`sudo_password`，填写后继续安装。",
        "sudo_wrong_password": "sudo密码错误，请重试。",
        "install_paused": "等待sudo密码...",
        "contact_hint": "需要帮助？@etopizdesblin",
        "warning_local_same": "本地模式：仅同一网络可用。",
        "warning_local_other": "本地模式：服务器和客户端需同一局域网。",
        "warning_vpn": "使用ETG API时请关闭VPN/代理（可能改变IP）。",
        "etgtest_hint": "运行`.etgtest`检查插件侧访问。",
        "port_forward_hint": "需要在路由器上做端口映射。",
    },
    "ko": {
        "choose_lang_title": "설치 언어 선택",
        "choose_lang_hint": "언어는 설치 메시지만 변경합니다.",
        "confirm_install": "{port} 포트에 ETG 설치?",
        "confirm_note_existing": "{port} 포트는 이미 ETG가 사용 중입니다.",
        "btn_install": "✅ 설치",
        "btn_cancel": "❌ 취소",
        "installing": "{port} 포트에 ETG 설치 중...",
        "install_error": "설치 실패. 로그: `.etg log`",
        "install_done": "설치 완료. 명령이 전송됨.",
        "install_done_with_errors": "오류 포함. 로그와 단계 전송됨.",
        "install_cancel": "설치 취소됨.",
        "port_prompt": "포트 입력: `.etg 8955`",
        "port_invalid": "포트 1-65535. 예: `.etg 8955`",
        "port_busy": "{port} 포트 사용 중: {error}",
        "manual_title": "오류가 있습니다. 수동으로 시도:",
        "manual_hint": "`.terminal`로 실행 가능.",
        "manual_step_iptables": "1) iptables 비활성화",
        "manual_step_ufw_install": "2) ufw 설치",
        "manual_step_ufw_allow": "3) 포트 {port} 허용",
        "manual_step_server": "4) ETG 서버 시작",
        "manual_step_check": "5) 포트 연결 확인",
        "manual_step_forward": "외부 IP 실패 시 라우터 포트포워딩 필요.",
        "post_ok_title": "완료! 아래 라이브러리를 설치하세요.",
        "post_install_ufw": "ufw 설치: `{cmd}`",
        "post_open_port": "포트 허용: `{cmd}`",
        "post_open_port_win": "포트 허용: `{cmd}`",
        "post_start_server": "서버 시작: `{cmd}`",
        "post_win_note": "Windows는 ufw 미지원.",
        "sudo_password": "sudo가 비밀번호를 요구할 수 있음.",
        "port_check_external": "외부 체크",
        "port_check_local": "로컬 체크",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "포트 체크: 외부 {ext} / 로컬 {loc}",
        "q_vps_title": "VPS인가요?",
        "q_vps_desc": "VPS는 외부 IP가 있는 서버입니다.",
        "q_public_title": "외부 IP가 있나요?",
        "q_public_desc": "외부 IP는 2ip/ifconfig에 보이는 IP입니다. 없으면 같은 LAN 필요.",
        "q_device_title": "유저봇이 같은 기기인가요?",
        "q_device_desc": "아니면 같은 로컬 네트워크에서만 동작합니다.",
        "btn_yes": "✅ 예",
        "btn_no": "❌ 아니오",
        "btn_same_device": "✅ 같은 기기",
        "btn_other_device": "📡 다른 기기",
        "sudo_request_title": "sudo 비밀번호 필요",
        "sudo_request_desc": "`.cfg EtgBridge`에서 `sudo_password` 입력. 입력 후 설치 계속.",
        "sudo_wrong_password": "sudo 비밀번호가 잘못되었습니다. 다시 입력하세요.",
        "install_paused": "sudo 비밀번호 대기...",
        "contact_hint": "도움: @etopizdesblin",
        "warning_local_same": "로컬 모드: 동일 네트워크에서만.",
        "warning_local_other": "로컬 모드: 서버와 클라이언트가 동일 LAN이어야 합니다.",
        "warning_vpn": "ETG API 사용 시 VPN/Proxy 끄기.",
        "etgtest_hint": "`.etgtest`로 플러그인 측 확인.",
        "port_forward_hint": "라우터에서 포트 포워딩 필요.",
    },
    "kp": {
        "choose_lang_title": "설치 언어 선택",
        "choose_lang_hint": "언어는 설치 메시지만 바꿉니다.",
        "confirm_install": "{port} 포트에 ETG 설치?",
        "confirm_note_existing": "{port} 포트는 이미 ETG가 사용 중입니다.",
        "btn_install": "✅ 설치",
        "btn_cancel": "❌ 취소",
        "installing": "{port} 포트에 ETG 설치중...",
        "install_error": "설치 실패. 로그: `.etg log`",
        "install_done": "설치 완료. 명령 전송됨.",
        "install_done_with_errors": "오류 있음. 로그/단계 전송됨.",
        "install_cancel": "설치 취소됨.",
        "port_prompt": "포트 입력: `.etg 8955`",
        "port_invalid": "포트 1-65535. 예: `.etg 8955`",
        "port_busy": "{port} 포트 사용 중: {error}",
        "manual_title": "오류가 있습니다. 수동으로:",
        "manual_hint": "`.terminal`로 실행.",
        "manual_step_iptables": "1) iptables 끄기",
        "manual_step_ufw_install": "2) ufw 설치",
        "manual_step_ufw_allow": "3) 포트 {port} 허용",
        "manual_step_server": "4) ETG 서버 시작",
        "manual_step_check": "5) 포트 확인",
        "manual_step_forward": "외부 IP 실패 시 포트포워딩 필요.",
        "post_ok_title": "완료! 아래 라이브러리 설치.",
        "post_install_ufw": "ufw 설치: `{cmd}`",
        "post_open_port": "포트 허용: `{cmd}`",
        "post_open_port_win": "포트 허용: `{cmd}`",
        "post_start_server": "서버 시작: `{cmd}`",
        "post_win_note": "Windows는 ufw 미지원.",
        "sudo_password": "sudo가 비밀번호를 요구할 수 있음.",
        "port_check_external": "외부 체크",
        "port_check_local": "로컬 체크",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "포트 체크: 외부 {ext} / 로컬 {loc}",
        "q_vps_title": "VPS입니까?",
        "q_vps_desc": "VPS는 외부 IP가 있는 서버입니다.",
        "q_public_title": "외부 IP가 있습니까?",
        "q_public_desc": "외부 IP는 2ip/ifconfig에 보이는 IP입니다. 없으면 같은 LAN 필요.",
        "q_device_title": "유저봇이 같은 기기입니까?",
        "q_device_desc": "아니면 같은 로컬 네트워크에서만 동작합니다.",
        "btn_yes": "✅ 예",
        "btn_no": "❌ 아니오",
        "btn_same_device": "✅ 같은 기기",
        "btn_other_device": "📡 다른 기기",
        "sudo_request_title": "sudo 비밀번호 필요",
        "sudo_request_desc": "`.cfg EtgBridge`에서 `sudo_password` 입력. 입력 후 설치 계속.",
        "sudo_wrong_password": "sudo 비밀번호가 틀렸습니다. 다시 입력하세요.",
        "install_paused": "sudo 비밀번호 대기...",
        "contact_hint": "도움: @etopizdesblin",
        "warning_local_same": "로컬 모드: 동일 네트워크에서만.",
        "warning_local_other": "로컬 모드: 서버와 클라이언트가 동일 LAN이어야 합니다.",
        "warning_vpn": "ETG API 사용 시 VPN/Proxy 끄기.",
        "etgtest_hint": "`.etgtest`로 플러그인 측 확인.",
        "port_forward_hint": "라우터에서 포트 포워딩 필요.",
    },
    "pir_ru": {
        "choose_lang_title": "Выбери язык, йо-хо-хо",
        "choose_lang_hint": "Язык влияет лишь на болтовню установщика.",
        "confirm_install": "Ставим ETG на порт {port}, капитан?",
        "confirm_note_existing": "Порт {port} занят, но мы его всё равно возьмём.",
        "btn_install": "✅ Йо-хо",
        "btn_cancel": "❌ Отбой",
        "installing": "Куем ETG на порт {port}...",
        "install_error": "Провал. Логи: `.etg log`",
        "install_done": "Готово. Команды отправлены.",
        "install_done_with_errors": "С косяками. Логи и шаги отправлены.",
        "install_cancel": "Отмена.",
        "port_prompt": "Дай порт: `.etg 8955`",
        "port_invalid": "Порт 1-65535. Пример: `.etg 8955`",
        "port_busy": "Порт {port} занят: {error}",
        "manual_title": "Ошибка. Делай вручную:",
        "manual_hint": "Команды через `.terminal`.",
        "manual_step_iptables": "1) Выруби iptables",
        "manual_step_ufw_install": "2) Поставь ufw",
        "manual_step_ufw_allow": "3) Открой порт {port}",
        "manual_step_server": "4) Запусти сервер",
        "manual_step_check": "5) Проверь порт",
        "manual_step_forward": "Нет внешнего — пробрось порт на роутере.",
        "post_ok_title": "Готово, ставь библиотеки ниже!",
        "post_install_ufw": "Установка ufw: `{cmd}`",
        "post_open_port": "Открой порт: `{cmd}`",
        "post_open_port_win": "Открой порт: `{cmd}`",
        "post_start_server": "Запуск сервера: `{cmd}`",
        "post_win_note": "Windows: ufw не работает.",
        "sudo_password": "sudo может спросить пароль.",
        "port_check_external": "Внешний чек",
        "port_check_local": "Локальный чек",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "Чек порта: внешний {ext} / локальный {loc}",
        "q_vps_title": "У тебя VPS, капитан?",
        "q_vps_desc": "VPS — сервер с внешним IP.",
        "q_public_title": "Есть внешний IP, моряк?",
        "q_public_desc": "Внешний IP — на 2ip/ifconfig. Нет — нужна одна сеть.",
        "q_device_title": "Юзербот на этом же корыте?",
        "q_device_desc": "Если нет — работает только в одной сети.",
        "btn_yes": "✅ Да, капитан",
        "btn_no": "❌ Нет, капитан",
        "btn_same_device": "✅ На этом",
        "btn_other_device": "📡 На другом",
        "sudo_request_title": "Нужен пароль sudo",
        "sudo_request_desc": "Открой `.cfg EtgBridge` и вбей `sudo_password`. Потом продолжим.",
        "sudo_wrong_password": "Пароль sudo неверный. Еще раз.",
        "install_paused": "Ждём пароль sudo...",
        "contact_hint": "Нужна помощь? @etopizdesblin",
        "warning_local_same": "Локальный режим: только одна сеть.",
        "warning_local_other": "Локальный режим: сервер и клиент в одной сети.",
        "warning_vpn": "Выруби VPN/Proxy, они меняют IP.",
        "etgtest_hint": "Запусти `.etgtest` для проверки.",
        "port_forward_hint": "Нужен проброс порта на роутере.",
    },
    "pir_en": {
        "choose_lang_title": "Choose yer install tongue, matey",
        "choose_lang_hint": "Language only changes installer chatter.",
        "confirm_install": "Hoist ETG on port {port}?",
        "confirm_note_existing": "Port {port} be taken by ETG, we reuse it.",
        "btn_install": "✅ Aye",
        "btn_cancel": "❌ Nay",
        "installing": "Hoisting ETG on port {port}...",
        "install_error": "Failed. Logs: `.etg log`",
        "install_done": "Done. Commands sent.",
        "install_done_with_errors": "With errors. Logs and steps sent.",
        "install_cancel": "Cancelled.",
        "port_prompt": "Give a port: `.etg 8955`",
        "port_invalid": "Port 1-65535. Example: `.etg 8955`",
        "port_busy": "Port {port} busy: {error}",
        "manual_title": "Errors. Try manual steps:",
        "manual_hint": "Commands via `.terminal`.",
        "manual_step_iptables": "1) Disable iptables",
        "manual_step_ufw_install": "2) Install ufw",
        "manual_step_ufw_allow": "3) Open port {port}",
        "manual_step_server": "4) Start ETG server",
        "manual_step_check": "5) Check port",
        "manual_step_forward": "If external fails — port-forward on router.",
        "post_ok_title": "All set, install libs below!",
        "post_install_ufw": "Install ufw: `{cmd}`",
        "post_open_port": "Open port: `{cmd}`",
        "post_open_port_win": "Open port: `{cmd}`",
        "post_start_server": "Start server: `{cmd}`",
        "post_win_note": "Windows: ufw unsupported.",
        "sudo_password": "sudo may ask password.",
        "port_check_external": "External check",
        "port_check_local": "Local check",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "Port check: external {ext} / local {loc}",
        "q_vps_title": "Got a VPS, matey?",
        "q_vps_desc": "VPS be a server with external IP.",
        "q_public_title": "Got a public IP?",
        "q_public_desc": "Public IP be what 2ip/ifconfig shows. If none, same LAN needed.",
        "q_device_title": "Userbot on the same ship?",
        "q_device_desc": "If not — only same LAN.",
        "btn_yes": "✅ Aye",
        "btn_no": "❌ Nay",
        "btn_same_device": "✅ Same ship",
        "btn_other_device": "📡 Other ship",
        "sudo_request_title": "Need sudo password",
        "sudo_request_desc": "Open `.cfg EtgBridge` and set `sudo_password`. Then we continue.",
        "sudo_wrong_password": "Bad sudo password. Try again.",
        "install_paused": "Waiting for sudo...",
        "contact_hint": "Need help? @etopizdesblin",
        "warning_local_same": "Local mode: same LAN only.",
        "warning_local_other": "Local mode: server and client must be in same LAN.",
        "warning_vpn": "Disable VPN/Proxy, they change IP.",
        "etgtest_hint": "Run `.etgtest` to check.",
        "port_forward_hint": "Port forwarding needed on router.",
    },
    "meme": {
        "choose_lang_title": "Выбери язык, мемчик",
        "choose_lang_hint": "Язык меняет только болтовню установщика.",
        "confirm_install": "Ставим ETG на {port}?",
        "confirm_note_existing": "Порт {port} занят ETG, юзаем его.",
        "btn_install": "✅ Поехали",
        "btn_cancel": "❌ Стопэ",
        "installing": "Ставлю ETG на {port}...",
        "install_error": "Ошибочка. Логи: `.etg log`",
        "install_done": "Готово. Команды отправил.",
        "install_done_with_errors": "С ошибками. Логи и шаги отправил.",
        "install_cancel": "Отмена.",
        "port_prompt": "Порт: `.etg 8955`",
        "port_invalid": "Порт 1-65535. Пример: `.etg 8955`",
        "port_busy": "Порт {port} занят: {error}",
        "manual_title": "Не ок. Делай руками:",
        "manual_hint": "Команды через `.terminal`.",
        "manual_step_iptables": "1) Выключи iptables",
        "manual_step_ufw_install": "2) Поставь ufw",
        "manual_step_ufw_allow": "3) Открой порт {port}",
        "manual_step_server": "4) Запусти сервер",
        "manual_step_check": "5) Проверь порт",
        "manual_step_forward": "Внешний не алё — пробрось порт.",
        "post_ok_title": "Всё ок, ставь либы ниже!",
        "post_install_ufw": "Установка ufw: `{cmd}`",
        "post_open_port": "Открой порт: `{cmd}`",
        "post_open_port_win": "Открой порт: `{cmd}`",
        "post_start_server": "Запуск сервера: `{cmd}`",
        "post_win_note": "Windows: ufw мимо.",
        "sudo_password": "sudo может попросить пароль.",
        "port_check_external": "Внешний чек",
        "port_check_local": "Локальный чек",
        "port_check_ok": "ok",
        "port_check_fail": "fail",
        "check_summary": "Чек порта: внешний {ext} / локальный {loc}",
        "q_vps_title": "Это VPS?",
        "q_vps_desc": "VPS = сервер с внешним IP.",
        "q_public_title": "Есть внешний IP?",
        "q_public_desc": "Внешний IP — как на 2ip/ifconfig. Без него только одна сеть.",
        "q_device_title": "Юзербот на этом устройстве?",
        "q_device_desc": "Если нет — только одна сеть.",
        "btn_yes": "✅ Да",
        "btn_no": "❌ Нет",
        "btn_same_device": "✅ Этот девайс",
        "btn_other_device": "📡 Другой девайс",
        "sudo_request_title": "Нужен sudo пароль",
        "sudo_request_desc": "Открой `.cfg EtgBridge` и впиши `sudo_password`. Потом всё продолжится.",
        "sudo_wrong_password": "Пароль sudo мимо. Попробуй ещё.",
        "install_paused": "Жду пароль sudo...",
        "contact_hint": "Помощь: @etopizdesblin",
        "warning_local_same": "Локалка: только одна сеть.",
        "warning_local_other": "Локалка: сервер и клиент в одной сети.",
        "warning_vpn": "Выключи VPN/Proxy, IP скачет.",
        "etgtest_hint": "Жми `.etgtest` для проверки.",
        "port_forward_hint": "Нужен проброс порта.",
    },
}


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

    def net_test(
        self,
        device_id: typing.Optional[str],
        url: str = "",
        timeout: int = 5,
    ) -> typing.Optional[str]:
        payload = {"timeout": int(timeout)}
        if url:
            payload["url"] = url
        return self.send(device_id, "net_test", payload)

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
                "sudo_password",
                "",
                "Sudo password (leave empty if not needed)",
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
        self._pending_install: typing.Optional[dict] = None
        self._pending_task: typing.Optional[asyncio.Task] = None
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

    async def _send_text_or_file_chat(
        self,
        chat_id: int,
        text: str,
        filename: str,
        caption: str,
    ) -> None:
        if len(text) <= 3500:
            await self._client.send_message(chat_id, text)
            return
        file = io.BytesIO(text.encode("utf-8"))
        file.name = filename
        await self._client.send_file(chat_id, file, caption=caption)

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
    def _get_install_langs() -> typing.List[typing.Tuple[str, str]]:
        return list(INSTALL_LANGS)

    def _t(self, lang: str, key: str, **kwargs) -> str:
        base = _INSTALL_I18N.get("en", {})
        table = _INSTALL_I18N.get(lang or "", {})
        text = table.get(key) or base.get(key) or key
        try:
            return text.format(**kwargs)
        except Exception:
            return text

    def _with_contact(self, lang: str, text: str) -> str:
        contact = self._t(lang, "contact_hint")
        return f"{text}\n{contact}" if contact else text

    def _sudo_check_password(self, password: str, sudo_path: str) -> bool:
        cmd = [sudo_path, "-S", "-k", "-p", "", "true"]
        code, _out = self._exec_shell_input(cmd, f"{password}\n")
        return code == 0

    def _get_sudo_ctx(self) -> dict:
        ctx = {
            "use_sudo": False,
            "is_root": False,
            "sudo_available": False,
            "sudo_path": "",
            "needs_password": False,
            "password": "",
            "password_invalid": False,
        }
        if self._is_windows():
            return ctx
        try:
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                ctx["is_root"] = True
                return ctx
        except Exception:
            pass
        sudo_path = shutil.which("sudo") or ""
        if not sudo_path:
            return ctx
        ctx["sudo_available"] = True
        ctx["use_sudo"] = True
        ctx["sudo_path"] = sudo_path
        code, out = self._exec_shell([sudo_path, "-n", "true"])
        if code == 0:
            return ctx
        ctx["needs_password"] = True
        password = (self.config["sudo_password"] or "").strip()
        if not password:
            return ctx
        if self._sudo_check_password(password, sudo_path):
            ctx["password"] = password
            return ctx
        ctx["password_invalid"] = True
        return ctx

    def _exec_cmd(
        self,
        args: typing.List[str],
        ctx: dict,
        use_sudo: bool,
        logs: typing.List[str],
        label: str,
    ) -> typing.Tuple[int, str]:
        if use_sudo and ctx.get("use_sudo"):
            sudo_path = ctx.get("sudo_path") or "sudo"
            password = ctx.get("password") or ""
            if password:
                cmd = [sudo_path, "-S", "-k", "-p", ""] + args
                return self._exec_shell_input(cmd, f"{password}\n")
            cmd = [sudo_path, "-n"] + args
            return self._exec_shell(cmd)
        return self._exec_shell(args)

    async def _prompt_sudo_password(
        self,
        chat_id: int,
        lang: str,
        wrong: bool = False,
    ) -> None:
        await self._client.send_message(chat_id, ".cfg EtgBridge")
        title = self._t(lang, "sudo_request_title")
        desc = self._t(lang, "sudo_request_desc")
        if wrong:
            desc = f"{self._t(lang, 'sudo_wrong_password')}\n{desc}"
        text = f"{title}\n{desc}"
        await self._client.send_message(chat_id, text)

    def _build_lang_keyboard(
        self,
        port: int,
        chat_id: int,
        note_key: str,
    ) -> typing.List[typing.List[dict]]:
        rows: typing.List[typing.List[dict]] = []
        row: typing.List[dict] = []
        for code, label in self._get_install_langs():
            row.append(
                {
                    "text": label,
                    "callback": self._etg_choose_lang,
                    "args": (port, chat_id, code, note_key),
                }
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return rows

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
    def _exec_shell_input(
        args: typing.List[str],
        input_text: str,
    ) -> typing.Tuple[int, str]:
        try:
            result = subprocess.run(
                args,
                input=input_text,
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

    def _run_pkg_command(
        self,
        args: typing.List[str],
        logs: typing.List[str],
        label: str,
        sudo_ctx: dict,
    ) -> bool:
        code, out = self._exec_cmd(args, sudo_ctx, True, logs, label)
        if code == 0:
            logs.append(f"{label}: ok")
            return True
        out_low = (out or "").lower()
        if "password" in out_low or "no tty" in out_low:
            logs.append(f"{label}: sudo requires password, install ufw manually")
            return False
        logs.append(f"{label}: {out}")
        return False

    def _install_ufw(self, logs: typing.List[str], sudo_ctx: dict) -> bool:
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
            if self._run_pkg_command(cmd, logs, label, sudo_ctx):
                if shutil.which("ufw"):
                    logs.append("ufw: installed")
                    return True
        if not shutil.which("ufw"):
            logs.append("ufw: install failed")
        return shutil.which("ufw") is not None

    def _run_shell_with_fallback(
        self,
        args: typing.List[str],
        logs: typing.List[str],
        label: str,
        ok_tokens: typing.Optional[typing.List[str]] = None,
    ) -> bool:
        def _attempt(use_sudo: bool) -> bool:
            cmd = args
            tag = "sudo" if use_sudo else "nosudo"
            if use_sudo:
                cmd = self._sudo_command(args, logs)
                if not cmd:
                    logs.append(f"{label} ({tag}): sudo unavailable")
                    return False
            code, out = self._exec_shell(cmd)
            out_low = (out or "").lower()
            if "password" in out_low or "no tty" in out_low:
                logs.append(f"{label} ({tag}): sudo requires password")
                return False
            ok = code == 0
            if ok_tokens:
                ok = ok or any(token in out_low for token in ok_tokens)
            logs.append(f"{label} ({tag}): {out if out else ('ok' if ok else 'failed')}")
            return ok

        if _attempt(True):
            return True
        return _attempt(False)

    def _disable_iptables(self, logs: typing.List[str], sudo_ctx: dict) -> bool:
        if self._is_windows():
            logs.append("iptables: skip on Windows")
            return True
        ok_tokens = ["not loaded", "not-found", "not running", "could not be found"]

        def _run(cmd: typing.List[str], label: str) -> bool:
            code, out = self._exec_cmd(cmd, sudo_ctx, True, logs, label)
            out_low = (out or "").lower()
            ok = code == 0 or any(token in out_low for token in ok_tokens)
            if not ok:
                code, out = self._exec_cmd(cmd, sudo_ctx, False, logs, label)
                out_low = (out or "").lower()
                ok = code == 0 or any(token in out_low for token in ok_tokens)
            logs.append(f"{label}: {out if out else ('ok' if ok else 'failed')}")
            return ok

        stop_ok = _run(["systemctl", "stop", "iptables"], "iptables stop")
        disable_ok = _run(["systemctl", "disable", "iptables"], "iptables disable")
        return stop_ok and disable_ok

    def _ufw_allow_port(self, port: int, logs: typing.List[str], sudo_ctx: dict) -> bool:
        if self._is_windows():
            logs.append("ufw: not supported on Windows")
            return True

        ok_tokens = ["rule added", "added", "existing", "already", "skipping", "updated"]

        def _attempt(use_sudo: bool) -> bool:
            cmd = ["ufw", "allow", str(port)]
            tag = "sudo" if use_sudo else "nosudo"
            code, out = self._exec_cmd(cmd, sudo_ctx, use_sudo, logs, f"ufw allow {port}")
            out_low = (out or "").lower()
            if "password" in out_low or "no tty" in out_low:
                logs.append(f"ufw allow {port} ({tag}): sudo requires password")
                return False
            ok = code == 0 and any(token in out_low for token in ok_tokens)
            logs.append(f"ufw allow {port} ({tag}): {out if out else ('ok' if ok else 'failed')}")
            return ok

        if _attempt(True) or _attempt(False):
            return True
        if not shutil.which("ufw"):
            logs.append("ufw: not installed, attempting install")
            self._install_ufw(logs, sudo_ctx)
        if _attempt(True) or _attempt(False):
            return True
        logs.append(f"ufw allow {port}: failed")
        return False

    @staticmethod
    def _tcp_ping(host: str, port: int, timeout: float = 2.0) -> typing.Tuple[bool, int, str]:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            ms = int((time.time() - start) * 1000)
            return True, ms, ""
        except Exception as exc:
            return False, 0, str(exc)
        finally:
            try:
                sock.close()
            except Exception:
                pass

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

    def _build_post_install_message(
        self,
        port: int,
        logs: typing.List[str],
        lang: str,
        sudo_ctx: dict,
    ) -> str:
        lines = [self._t(lang, "post_ok_title")]
        if self._is_windows():
            server_path = self._etg_server_path(self._etg_root())
            lines.append(self._t(lang, "post_win_note"))
            lines.append(
                self._t(
                    lang,
                    "post_open_port_win",
                    cmd=(
                        f'netsh advfirewall firewall add rule name="ETG {port}" '
                        f"dir=in action=allow protocol=TCP localport={port}"
                    ),
                )
            )
            lines.append(
                self._t(lang, "post_start_server", cmd=f'python "{server_path}"')
            )
            return "\n".join(lines)
        install_cmd = self._get_ufw_install_command()
        sudo_prefix = "sudo " if sudo_ctx.get("use_sudo") else ""
        if install_cmd:
            if not sudo_prefix:
                install_cmd = install_cmd.replace("sudo ", "")
            lines.append(self._t(lang, "post_install_ufw", cmd=install_cmd))
        lines.append(
            self._t(
                lang,
                "post_open_port",
                cmd=(
                    self._get_ufw_open_command(port)
                    if sudo_prefix
                    else self._get_ufw_open_command(port).replace("sudo ", "")
                ),
            )
        )
        if any("sudo requires password" in line for line in logs):
            lines.append(self._t(lang, "sudo_password"))
        return "\n".join(lines)

    def _format_check_result(self, lang: str, ok: bool, ms: int) -> str:
        label = self._t(lang, "port_check_ok") if ok else self._t(lang, "port_check_fail")
        if ok and ms > 0:
            return f"{label} {ms}ms"
        return label

    def _curl_health_cmd(self, scheme: str, host: str, port: int) -> str:
        if scheme == "https":
            return f"curl -k {scheme}://{host}:{port}/health"
        return f"curl {scheme}://{host}:{port}/health"

    def _build_manual_steps(
        self,
        port: int,
        lang: str,
        status: dict,
        scheme: str,
        sudo_ctx: dict,
    ) -> str:
        ext_status = self._format_check_result(
            lang,
            bool(status.get("external_ok")),
            int(status.get("external_ms") or 0),
        )
        loc_status = self._format_check_result(
            lang,
            bool(status.get("local_ok")),
            int(status.get("local_ms") or 0),
        )
        lines = [
            self._t(lang, "manual_title"),
            self._t(lang, "manual_hint"),
            self._t(lang, "check_summary", ext=ext_status, loc=loc_status),
        ]

        sudo_prefix = "sudo " if sudo_ctx.get("use_sudo") else ""
        if not self._is_windows():
            lines.append(self._t(lang, "manual_step_iptables"))
            lines.append(f"` .terminal {sudo_prefix}systemctl stop iptables`")
            lines.append(f"` .terminal {sudo_prefix}systemctl disable iptables`")

            install_cmd = self._get_ufw_install_command()
            if install_cmd:
                lines.append(self._t(lang, "manual_step_ufw_install"))
                install_cmd = install_cmd if sudo_prefix else install_cmd.replace("sudo ", "")
                lines.append(f"` .terminal {install_cmd}`")

            lines.append(self._t(lang, "manual_step_ufw_allow", port=port))
            open_cmd = self._get_ufw_open_command(port)
            open_cmd = open_cmd if sudo_prefix else open_cmd.replace("sudo ", "")
            lines.append(f"` .terminal {open_cmd}`")
        else:
            lines.append(self._t(lang, "manual_step_ufw_allow", port=port))
            lines.append(
                f'` .terminal netsh advfirewall firewall add rule name="ETG {port}" '
                f"dir=in action=allow protocol=TCP localport={port}`"
            )

        server_path = self._etg_server_path(self._etg_root())
        lines.append(self._t(lang, "manual_step_server"))
        lines.append(f'` .terminal python "{server_path}"`')

        lines.append(self._t(lang, "manual_step_check"))
        external_ip = status.get("external_ip") or ""
        local_ip = status.get("local_ip") or ""
        if external_ip:
            lines.append(
                f"` .terminal {self._curl_health_cmd(scheme, external_ip, port)}`"
            )
        if local_ip and local_ip != external_ip:
            lines.append(f"` .terminal {self._curl_health_cmd(scheme, local_ip, port)}`")
        lines.append(self._t(lang, "manual_step_forward"))
        return "\n".join(lines)

    def _build_local_warning(self, lang: str, same_device: bool) -> str:
        lines = []
        if same_device:
            lines.append(self._t(lang, "warning_local_same"))
        else:
            lines.append(self._t(lang, "warning_local_other"))
        lines.append(self._t(lang, "warning_vpn"))
        lines.append(self._t(lang, "etgtest_hint"))
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
        for port in ports:
            self._ufw_allow_port(port, logs)

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

    def _run_install(
        self,
        port: int,
        sudo_ctx: dict,
    ) -> typing.Tuple[typing.List[str], str, str, dict]:
        logs: typing.List[str] = []
        root = self._etg_root()
        os.makedirs(root, exist_ok=True)
        self.config["listen_port"] = int(port)
        self.config["use_external_server"] = True

        self._ensure_server_script(root, logs)
        self._write_server_config(root, logs)
        self._ensure_etg_service(root, logs)

        copied = self._copy_etg_files(logs)
        iptables_ok = self._disable_iptables(logs, sudo_ctx)
        ufw_ok = self._ufw_allow_port(int(self.config["listen_port"]), logs, sudo_ctx)
        self._check_local_health(logs)

        external_ip = self._get_external_ip(logs)
        local_ip = self._get_local_ip()
        if external_ip and local_ip and external_ip != local_ip and self._is_private_ip(local_ip):
            logs.append(
                f"LAN IP: {local_ip}. Внешний IP отличается — нужен проброс порта {self.config['listen_port']}."
            )

        ext_ok = False
        ext_ms = 0
        ext_err = ""
        loc_ok = False
        loc_ms = 0
        loc_err = ""
        if external_ip:
            ext_ok, ext_ms, ext_err = self._tcp_ping(external_ip, port)
            if ext_ok:
                logs.append(f"port check external {external_ip}:{port}: ok {ext_ms}ms")
            else:
                logs.append(f"port check external {external_ip}:{port}: fail {ext_err}")
        else:
            logs.append("external ip not detected")

        if not ext_ok and local_ip:
            loc_ok, loc_ms, loc_err = self._tcp_ping(local_ip, port)
            if loc_ok:
                logs.append(f"port check local {local_ip}:{port}: ok {loc_ms}ms")
            else:
                logs.append(f"port check local {local_ip}:{port}: fail {loc_err}")

        host = external_ip or local_ip or self.config["listen_host"]
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
        status = {
            "iptables_ok": iptables_ok,
            "ufw_ok": ufw_ok,
            "external_ok": ext_ok,
            "external_ms": ext_ms,
            "external_err": ext_err,
            "local_ok": loc_ok,
            "local_ms": loc_ms,
            "local_err": loc_err,
            "external_ip": external_ip,
            "local_ip": local_ip,
        }
        return log_lines, etg_file, mandre_file, status

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

    async def _etg_choose_lang(
        self,
        call: InlineCall,
        port: int,
        chat_id: int,
        lang: str,
        note_key: str,
    ):
        await self._etg_question_vps(call, port, chat_id, lang, note_key)

    async def _etg_question_vps(
        self,
        call: InlineCall,
        port: int,
        chat_id: int,
        lang: str,
        note_key: str,
    ):
        text = f"{self._t(lang, 'q_vps_title')}\n{self._t(lang, 'q_vps_desc')}"
        if note_key:
            text = f"{text}\n{self._t(lang, note_key, port=port)}"
        await call.edit(
            text,
            reply_markup=[
                [
                    {
                        "text": self._t(lang, "btn_yes"),
                        "callback": self._etg_set_vps,
                        "args": (port, chat_id, lang, note_key, True),
                    },
                    {
                        "text": self._t(lang, "btn_no"),
                        "callback": self._etg_set_vps,
                        "args": (port, chat_id, lang, note_key, False),
                    },
                ]
            ],
        )

    async def _etg_set_vps(
        self,
        call: InlineCall,
        port: int,
        chat_id: int,
        lang: str,
        note_key: str,
        is_vps: bool,
    ):
        if is_vps:
            await self._etg_confirm_prompt(call, port, chat_id, lang, True, None, note_key)
            return
        await self._etg_question_public(call, port, chat_id, lang, note_key)

    async def _etg_question_public(
        self,
        call: InlineCall,
        port: int,
        chat_id: int,
        lang: str,
        note_key: str,
    ):
        text = f"{self._t(lang, 'q_public_title')}\n{self._t(lang, 'q_public_desc')}"
        await call.edit(
            text,
            reply_markup=[
                [
                    {
                        "text": self._t(lang, "btn_yes"),
                        "callback": self._etg_set_public,
                        "args": (port, chat_id, lang, note_key, True),
                    },
                    {
                        "text": self._t(lang, "btn_no"),
                        "callback": self._etg_set_public,
                        "args": (port, chat_id, lang, note_key, False),
                    },
                ]
            ],
        )

    async def _etg_set_public(
        self,
        call: InlineCall,
        port: int,
        chat_id: int,
        lang: str,
        note_key: str,
        has_public: bool,
    ):
        if has_public:
            await self._etg_confirm_prompt(call, port, chat_id, lang, True, None, note_key)
            return
        await self._etg_question_device(call, port, chat_id, lang, note_key)

    async def _etg_question_device(
        self,
        call: InlineCall,
        port: int,
        chat_id: int,
        lang: str,
        note_key: str,
    ):
        text = f"{self._t(lang, 'q_device_title')}\n{self._t(lang, 'q_device_desc')}"
        await call.edit(
            text,
            reply_markup=[
                [
                    {
                        "text": self._t(lang, "btn_same_device"),
                        "callback": self._etg_set_device,
                        "args": (port, chat_id, lang, note_key, True),
                    },
                    {
                        "text": self._t(lang, "btn_other_device"),
                        "callback": self._etg_set_device,
                        "args": (port, chat_id, lang, note_key, False),
                    },
                ]
            ],
        )

    async def _etg_set_device(
        self,
        call: InlineCall,
        port: int,
        chat_id: int,
        lang: str,
        note_key: str,
        same_device: bool,
    ):
        await self._etg_confirm_prompt(call, port, chat_id, lang, False, same_device, note_key)

    async def _etg_confirm_prompt(
        self,
        call: InlineCall,
        port: int,
        chat_id: int,
        lang: str,
        has_public: bool,
        same_device: typing.Optional[bool],
        note_key: str,
    ):
        text = self._t(lang, "confirm_install", port=port)
        if note_key:
            text = f"{text}\n{self._t(lang, note_key, port=port)}"
        await call.edit(
            text,
            reply_markup=[
                [
                    {
                        "text": self._t(lang, "btn_install"),
                        "callback": self._etg_confirm,
                        "args": (port, chat_id, lang, has_public, same_device),
                    },
                    {
                        "text": self._t(lang, "btn_cancel"),
                        "callback": self._etg_cancel,
                        "args": (lang,),
                    },
                ]
            ],
        )

    async def _etg_confirm(
        self,
        call: InlineCall,
        port: int,
        chat_id: int,
        lang: str,
        has_public: bool,
        same_device: typing.Optional[bool],
    ):
        await call.edit(self._t(lang, "installing", port=port))
        sudo_ctx = self._get_sudo_ctx()
        if sudo_ctx.get("needs_password") and not sudo_ctx.get("password"):
            self._pending_install = {
                "port": port,
                "chat_id": chat_id,
                "lang": lang,
                "has_public": has_public,
                "same_device": same_device,
            }
            await call.edit(self._t(lang, "install_paused"))
            await self._prompt_sudo_password(chat_id, lang, wrong=bool(sudo_ctx.get("password_invalid")))
            self._start_pending_install_wait()
            return

        ok = await self._perform_install(chat_id, lang, port, has_public, same_device, sudo_ctx)
        if ok:
            await call.edit(self._t(lang, "install_done"))
        else:
            await call.edit(self._with_contact(lang, self._t(lang, "install_done_with_errors")))

    async def _etg_cancel(self, call: InlineCall, lang: str):
        await call.edit(self._t(lang, "install_cancel"))

    def _start_pending_install_wait(self) -> None:
        if self._pending_task and not self._pending_task.done():
            return
        self._pending_task = asyncio.create_task(self._wait_for_sudo_password())

    async def _wait_for_sudo_password(self) -> None:
        while self._pending_install:
            await asyncio.sleep(2)
            data = self._pending_install
            if not data:
                return
            password = (self.config["sudo_password"] or "").strip()
            if not password:
                continue
            sudo_ctx = self._get_sudo_ctx()
            if sudo_ctx.get("password_invalid"):
                try:
                    self.config["sudo_password"] = ""
                except Exception:
                    pass
                await self._prompt_sudo_password(
                    data["chat_id"], data["lang"], wrong=True
                )
                continue
            await self._perform_install(
                data["chat_id"],
                data["lang"],
                data["port"],
                data["has_public"],
                data["same_device"],
                sudo_ctx,
            )
            self._pending_install = None
            return

    async def _perform_install(
        self,
        chat_id: int,
        lang: str,
        port: int,
        has_public: bool,
        same_device: typing.Optional[bool],
        sudo_ctx: dict,
    ) -> bool:
        try:
            _log_lines, etg_file, mandre_file, status = await asyncio.to_thread(
                self._run_install, port, sudo_ctx
            )
        except Exception as exc:
            self._set_setup_log([f"install failed: {exc}"])
            await self._client.send_message(
                chat_id, self._with_contact(lang, self._t(lang, "install_error"))
            )
            return False

        scheme = "https" if self.config["tls_enabled"] else "http"
        external_ok = bool(status.get("external_ok"))
        local_ok = bool(status.get("local_ok"))
        if has_public:
            ok = external_ok
        else:
            ok = local_ok or external_ok

        if not ok:
            manual_text = self._build_manual_steps(port, lang, status, scheme, sudo_ctx)
            if has_public and not external_ok:
                manual_text = f"{manual_text}\n{self._t(lang, 'port_forward_hint')}"
            manual_text = self._with_contact(lang, manual_text)
            await self._client.send_message(chat_id, manual_text)
            return False

        if not (etg_file and os.path.isfile(etg_file)):
            etg_file, _ = self._ensure_release_files([])
        if not (mandre_file and os.path.isfile(mandre_file)):
            _, mandre_file = self._ensure_release_files([])

        await self._send_install_result(
            message=None,
            text=self._build_post_install_message(port, _log_lines, lang, sudo_ctx),
            etg_file=etg_file,
            mandre_file=mandre_file,
            chat_id=chat_id,
        )

        if not has_public:
            warn = self._build_local_warning(lang, bool(same_device))
            await self._client.send_message(chat_id, warn)
        return True

    @loader.command(ru_doc="Удалить настройки ETG сервера")
    async def unetg(self, message: Message):
        logs = await asyncio.to_thread(self._run_uninstall)
        text = "\n".join(logs) if logs else "Готово."
        await self._send_text_or_file(message, text, "etg_uninstall_log.txt", "ETG logs")

    @loader.command(ru_doc="Переустановить ETG сервер")
    async def reinetg(self, message: Message):
        await self.etg(message)

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
            await utils.answer(message, self._t("ru", "port_prompt"))
            return

        port = self._parse_port(args)
        if port is None:
            await utils.answer(
                message, self._with_contact("ru", self._t("ru", "port_invalid"))
            )
            return

        free, error = self._port_is_free(port)
        note_key = ""
        if not free:
            if self._probe_health(port):
                note_key = "confirm_note_existing"
            else:
                await utils.answer(
                    message,
                    self._with_contact(
                        "ru", self._t("ru", "port_busy", port=port, error=error)
                    ),
                )
                return

        text = f"{self._t('ru', 'choose_lang_title')} / {self._t('en', 'choose_lang_title')}\n"
        text += f"{self._t('ru', 'choose_lang_hint')} / {self._t('en', 'choose_lang_hint')}"
        await self.inline.form(
            message=message,
            text=text,
            reply_markup=self._build_lang_keyboard(port, utils.get_chat_id(message), note_key),
            force_me=True,
        )
        return

    @loader.command(ru_doc="Проверить доступность сервера со стороны плагина")
    async def etgtest(self, message: Message):
        args = utils.get_args_raw(message).strip()
        device_id = args or "last"
        action_id = self.api.net_test(device_id)
        if not action_id:
            await utils.answer(message, self._with_contact("ru", "Нет подключенных устройств."))
            return
        await utils.answer(message, "Проверяю доступ со стороны плагина...")
        result = await self.api.wait_result(device_id, action_id, timeout=20)
        if not result:
            await utils.answer(
                message,
                self._with_contact("ru", "Нет ответа от плагина. Попробуйте позже."),
            )
            return
        data = result.get("data") or {}
        ok = bool(data.get("ok"))
        url = data.get("url") or ""
        latency = data.get("latency_ms")
        status = data.get("status")
        if ok:
            text = f"ETG test: ok"
            if latency is not None:
                text += f" {latency}ms"
            if status:
                text += f" (HTTP {status})"
            if url:
                text += f"\nURL: {url}"
            await utils.answer(message, text)
            return
        err = data.get("error") or "unknown error"
        text = f"ETG test: fail\n{err}"
        if url:
            text += f"\nURL: {url}"
        await utils.answer(message, self._with_contact("ru", text))
