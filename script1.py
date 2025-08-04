import re
import time
import json
import os
import html
from datetime import datetime, timedelta, timezone
from telethon.sync import TelegramClient, events
from telethon.tl.types import MessageEntityTextUrl

# Конфигурация
API_ID = '22778366'
API_HASH = 'a3074955a868b3eea3aaeb81435ee044'
PHONE = '+79363009030'
KEYWORDS = ['здравствуйте', 'кондей', 'кандей', 'монтаж', 'монтажник',
            'установка', 'сплит', 'мульт-сплит', 'мультисплит', 'мульт']
STATE_FILE = 'monitor_state.json'
TARGET_CHAT_NAME = "Ключи"

# Глобальные переменные
MONITOR_START_TIME = datetime.now(timezone.utc)


def get_time_delta():
    print("\n" + "=" * 40)
    print("Выберите временной интервал для исторического поиска:")
    print("0 - Все время\n1 - День\n2 - 3 дня\n3 - Неделя\n4 - Месяцы")
    print("=" * 40)

    while True:
        choice = input("Ваш выбор (0-4): ")
        now = datetime.now(timezone.utc)

        if choice == '0':
            return None
        elif choice == '1':
            return now - timedelta(days=1)
        elif choice == '2':
            return now - timedelta(days=3)
        elif choice == '3':
            return now - timedelta(weeks=1)
        elif choice == '4':
            months = int(input("Месяцев: "))
            return now - timedelta(days=months * 30)
        print("Неверный ввод!")


def format_time(dt: datetime) -> str:
    local_dt = dt.astimezone()
    return local_dt.strftime("%Y-%m-%d %H:%M")


def format_relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    diff = now - dt

    if diff < timedelta(minutes=1):
        return "только что"
    elif diff < timedelta(hours=1):
        minutes = diff.seconds // 60
        return f"{minutes} минут назад"
    elif diff < timedelta(days=1):
        hours = diff.seconds // 3600
        return f"{hours} часов назад"
    else:
        days = diff.days
        return f"{days} дней назад"


def get_message_link(message):
    """Создает прямую ссылку на сообщение"""
    if hasattr(message.chat, 'username') and message.chat.username:
        return f"https://t.me/{message.chat.username}/{message.id}"
    else:
        # Для приватных чатов и каналов
        chat_id = str(message.chat.id).replace('-100', '')
        return f"https://t.me/c/{chat_id}/{message.id}"


def create_notification_text(message, chat_title):
    relative_time = format_relative_time(message.date)
    exact_time = format_time(message.date)
    message_link = get_message_link(message)

    # Получаем информацию об авторе
    if message.sender:
        author_name = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()
    else:
        author_name = "Неизвестный"

    # Форматируем текст сообщения как цитату
    formatted_text = f"<blockquote>{html.escape(message.text)}</blockquote>" if message.text else ""

    # Форматируем текст уведомления с HTML-разметкой
    text = (
        f"🔑 <b>Чат</b>: {html.escape(chat_title)}\n\n"
        f"⏱ <b>Время</b>: {relative_time} ({exact_time})\n"
        f"👤 <b>Автор</b>: {html.escape(author_name)}\n\n"
        f"💬 <b>Сообщение</b>:\n"
        f"{formatted_text}\n\n"
        f'<a href="{message_link}">👉 ПЕРЕЙТИ К СООБЩЕНИЮ 👈</a>'
    )
    return text, message_link


def find_target_chat(client, name):
    for dialog in client.iter_dialogs():
        if dialog.name.lower() == name.lower():
            return dialog.entity
    return None


def ensure_target_chat(client):
    target_chat = find_target_chat(client, TARGET_CHAT_NAME)
    if target_chat:
        return target_chat

    print(f"⚠️ Чат '{TARGET_CHAT_NAME}' не найден. Создаем новый...")
    try:
        new_chat = client.create_channel(
            TARGET_CHAT_NAME,
            "Чат для уведомлений о ключевых словах"
        )
        print(f"✅ Создан новый чат: {TARGET_CHAT_NAME}")
        return new_chat
    except Exception as e:
        print(f"❌ Ошибка создания чата: {e}")
        return None


def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"processed_messages": {}}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)


def historical_search(client, time_filter, target_chat=None):
    print("\n" + "=" * 40)
    print("🔍 Запущен исторический поиск")
    print("=" * 40 + "\n")

    dialogs = []
    for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            dialogs.append(dialog)

    # Создаем паттерн для поиска
    pattern = re.compile('|'.join(map(re.escape, KEYWORDS)), re.IGNORECASE)

    # Обрабатываем каждый диалог
    for dialog in dialogs:
        chat = dialog.entity
        chat_title = getattr(chat, 'title', f"ID:{chat.id}")

        try:
            offset_id = 0
            while True:
                messages = client.get_messages(chat, limit=100, offset_id=offset_id)
                if not messages:
                    break

                offset_id = messages[-1].id

                for message in messages:
                    # Проверка времени
                    if time_filter and message.date < time_filter:
                        continue

                    # Проверка ключевых слов
                    if message.text and pattern.search(message.text):
                        # Формируем уведомление
                        notification_text, message_link = create_notification_text(message, chat_title)

                        # Отправляем уведомления
                        try:
                            # В избранное
                            client.send_message(
                                'me',
                                notification_text,
                                parse_mode='html'
                            )

                            # В целевой чат "Ключи"
                            if target_chat:
                                client.send_message(
                                    target_chat,
                                    notification_text,
                                    parse_mode='html',
                                    link_preview=False
                                )
                        except Exception as e:
                            print(f"⚠️ Ошибка отправки: {str(e)}")

                # Прерываем после первой пачки для демонстрации
                break

        except Exception as e:
            print(f"⚠️ Ошибка в {chat_title}: {str(e)}")

    print("\n✅ Исторический поиск завершен")


def online_monitor(client, target_chat=None):
    print("\n" + "=" * 40)
    print("🔍 Запущен онлайн-мониторинг в реальном времени")
    print("=" * 40 + "\n")
    print("Программа отслеживает новые сообщения, поступающие после запуска.")
    print("Нажмите Ctrl+C для остановки.")

    # Загружаем состояние
    state = load_state()
    processed_messages = state.get("processed_messages", {})

    # Создаем паттерн для поиска
    pattern = re.compile('|'.join(map(re.escape, KEYWORDS)), re.IGNORECASE)

    # Сбор диалогов
    dialogs = []
    for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            dialogs.append(dialog)
            chat_id = dialog.entity.id
            str_chat_id = str(chat_id)

            # Инициализация состояния
            if str_chat_id not in processed_messages:
                processed_messages[str_chat_id] = []

    # Сохраняем состояние
    state = {"processed_messages": processed_messages}
    save_state(state)

    # Создаем обработчик событий для новых сообщений
    @client.on(events.NewMessage(chats=[d.entity for d in dialogs]))
    async def handler(event):
        message = event.message
        chat = await event.get_chat()
        chat_id = chat.id
        str_chat_id = str(chat_id)
        chat_title = getattr(chat, 'title', str(chat_id))

        # Проверяем, что сообщение поступило после запуска мониторинга
        if message.date < MONITOR_START_TIME:
            return

        # Проверяем, не обрабатывали ли мы уже это сообщение
        if str_chat_id in processed_messages and message.id in processed_messages[str_chat_id]:
            return

        # Добавляем в обработанные
        if str_chat_id not in processed_messages:
            processed_messages[str_chat_id] = []
        processed_messages[str_chat_id].append(message.id)

        # Сохраняем состояние
        state = {"processed_messages": processed_messages}
        save_state(state)

        # Проверяем ключевые слова
        if message.text and pattern.search(message.text):
            # Формируем уведомление
            notification_text, message_link = create_notification_text(message, chat_title)

            try:
                # Отправляем в избранное
                await client.send_message(
                    'me',
                    notification_text,
                    parse_mode='html'
                )

                # Отправляем в чат "Ключи"
                if target_chat:
                    await client.send_message(
                        target_chat,
                        notification_text,
                        parse_mode='html',
                        link_preview=False
                    )
                else:
                    print("⚠️ Целевой чат 'Ключи' недоступен")

            except Exception as e:
                print(f"⚠️ Ошибка отправки уведомления: {str(e)}")

            print(f"🔔 Найдено сообщение в {chat_title}!")

    # Запускаем мониторинг
    print("✅ Мониторинг запущен. Ожидание новых сообщений...")
    client.run_until_disconnected()


def main():
    print("\n" + "=" * 40)
    print("Выберите режим работы:")
    print("1 - Исторический поиск")
    print("2 - Онлайн-мониторинг (реальное время)")
    print("3 - Комбинированный (исторический + онлайн)")
    print("=" * 40)

    choice = input("Ваш выбор (1-3): ")
    if choice not in ['1', '2', '3']:
        print("Неверный выбор")
        return

    with TelegramClient('session', API_ID, API_HASH) as client:
        client.start(PHONE)
        target_chat = ensure_target_chat(client)

        if choice == '1':
            # Только исторический поиск
            time_filter = get_time_delta()
            historical_search(client, time_filter, target_chat)

        elif choice == '2':
            # Только онлайн-мониторинг
            online_monitor(client, target_chat)

        elif choice == '3':
            # Комбинированный режим
            time_filter = get_time_delta()
            historical_search(client, time_filter, target_chat)
            print("\n✅ Исторический поиск завершен. Переходим в онлайн-режим...")
            online_monitor(client, target_chat)


if __name__ == '__main__':
    # Инициализация файла состояния
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'w') as f:
            json.dump({"processed_messages": {}}, f)

    # Запуск основной программы
    main()