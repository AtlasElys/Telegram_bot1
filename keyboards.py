from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import hashlib
import time

# Генерация уникального callback_data для кнопки
def generate_callback_data(user_id):
    timestamp = int(time.time())
    secret = f"{user_id}_{timestamp}_secret_key"
    hash_obj = hashlib.md5(secret.encode()).hexdigest()[:8]
    return f"check_{user_id}_{timestamp}_{hash_obj}"

# Проверка callback_data
def verify_callback_data(callback_data, user_id):
    try:
        parts = callback_data.split('_')
        if len(parts) < 4:
            return False
        
        callback_user_id = int(parts[1])
        timestamp = int(parts[2])
        hash_received = parts[3]
        
        # Проверяем время (не старше 24 часов)
        if time.time() - timestamp > 86400:
            return False
        
        # Проверяем хеш
        secret = f"{callback_user_id}_{timestamp}_secret_key"
        hash_calculated = hashlib.md5(secret.encode()).hexdigest()[:8]
        
        return callback_user_id == user_id and hash_received == hash_calculated
    except:
        return False

# Клавиатура подписки для пользователей
def get_subscription_keyboard(user_id, channel_link, button_text):
    callback_data = generate_callback_data(user_id)
    keyboard = [
        [InlineKeyboardButton(button_text, url=channel_link)],
        [InlineKeyboardButton("✅ Я подписался", callback_data=callback_data)]
    ]
    return InlineKeyboardMarkup(keyboard)

# Главное меню администратора
def get_admin_main_menu():
    keyboard = [
        [InlineKeyboardButton("📢 Управление каналом", callback_data="manage_channel")],
        [InlineKeyboardButton("💬 Управление чатами", callback_data="manage_chats")],
        [InlineKeyboardButton("🛡️ Управление модераторами", callback_data="manage_moderators")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats_menu")],
        [InlineKeyboardButton("⚙️ Настройки проверки", callback_data="check_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Управление каналом
def get_channel_management_menu(has_channel=False):
    if has_channel:
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить канал", callback_data="change_channel")],
            [InlineKeyboardButton("✏️ Изменить текст кнопки", callback_data="change_button_text")],
            [InlineKeyboardButton("❌ Удалить канал", callback_data="delete_channel")],
            [InlineKeyboardButton("📋 Информация о канале", callback_data="channel_info")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
    return InlineKeyboardMarkup(keyboard)

# Управление чатами
def get_chats_management_menu():
    keyboard = [
        [InlineKeyboardButton("✅ Включить в чате", callback_data="enable_in_chat")],
        [InlineKeyboardButton("❌ Выключить в чате", callback_data="disable_in_chat")],
        [InlineKeyboardButton("📋 Список активных чатов", callback_data="active_chats_list")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Настройки проверки
def get_check_settings_menu(chat_id=None, current_value=10):
    keyboard = [
        [
            InlineKeyboardButton("🔢 Каждое сообщение", callback_data="check_1"),
            InlineKeyboardButton("🔢 Каждые 5", callback_data="check_5")
        ],
        [
            InlineKeyboardButton("🔢 Каждые 10", callback_data="check_10"),
            InlineKeyboardButton("🔢 Каждые 20", callback_data="check_20")
        ],
        [
            InlineKeyboardButton("🔢 Каждые 50", callback_data="check_50"),
            InlineKeyboardButton("🔢 Только первое", callback_data="check_0")
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Управление модераторами
def get_moderators_management_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Добавить модератора", callback_data="add_moderator")],
        [InlineKeyboardButton("➖ Удалить модератора", callback_data="remove_moderator")],
        [InlineKeyboardButton("📋 Список модераторов", callback_data="list_moderators")],
        [InlineKeyboardButton("⚙️ Настройки прав", callback_data="moderator_settings")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Меню статистики
def get_stats_menu():
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="stats_today")],
        [InlineKeyboardButton("📆 За неделю", callback_data="stats_week")],
        [InlineKeyboardButton("📈 За месяц", callback_data="stats_month")],
        [InlineKeyboardButton("📊 За год", callback_data="stats_year")],
        [InlineKeyboardButton("📥 Экспорт в Excel", callback_data="export_excel")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Меню настроек
def get_settings_menu():
    keyboard = [
        [InlineKeyboardButton("👥 Управление админами", callback_data="manage_admins")],
        [InlineKeyboardButton("⚡ Быстрые команды", callback_data="quick_commands")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Кнопки для отмены
def get_cancel_keyboard():
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    return InlineKeyboardMarkup(keyboard)

# Кнопка "Назад"
def get_back_keyboard():
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(keyboard)

# Кнопки Да/Нет
def get_yes_no_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data="yes_action"),
            InlineKeyboardButton("❌ Нет", callback_data="no_action")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура подписки для пользователей
def get_subscription_keyboard(user_id, channel_link, button_text):
    keyboard = [
        [InlineKeyboardButton(button_text, url=channel_link)],
        [InlineKeyboardButton("✅ Я подписался", callback_data=f"check_{user_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для списка чатов
def get_chats_list_keyboard(chats, action_prefix):
    keyboard = []
    for chat in chats:
        keyboard.append([InlineKeyboardButton(
            f"Чат {chat.chat_id}", 
            callback_data=f"{action_prefix}_{chat.chat_id}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="manage_chats")])
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для списка модераторов
def get_moderators_list_keyboard(moderators, action_prefix):
    keyboard = []
    for mod in moderators:
        keyboard.append([InlineKeyboardButton(
            f"@{mod.username or mod.user_id}", 
            callback_data=f"{action_prefix}_{mod.user_id}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="manage_moderators")])
    return InlineKeyboardMarkup(keyboard)

# Клавиатура команд модерации
def get_moderation_commands_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("⚠️ Выдать предупреждение", callback_data=f"warn_{user_id}"),
            InlineKeyboardButton("🔇 Выдать мут", callback_data=f"mute_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("🚫 Забанить", callback_data=f"ban_{user_id}"),
            InlineKeyboardButton("✅ Снять ограничения", callback_data=f"unrestrict_{user_id}")
        ],
        [
            InlineKeyboardButton("📊 Информация", callback_data=f"info_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для выбора времени мута
def get_mute_duration_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("5 минут", callback_data=f"mute_5_{user_id}")],
        [InlineKeyboardButton("1 час", callback_data=f"mute_60_{user_id}")],
        [InlineKeyboardButton("1 день", callback_data=f"mute_1440_{user_id}")],
        [InlineKeyboardButton("7 дней", callback_data=f"mute_10080_{user_id}")],
        [InlineKeyboardButton("Навсегда", callback_data=f"mute_0_{user_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"moderation_{user_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)