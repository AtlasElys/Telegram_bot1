import os
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode
import openpyxl
from openpyxl import Workbook
from dotenv import load_dotenv

from database import Database
from keyboards import (
    get_admin_main_menu,
    get_channel_management_menu,
    get_chats_management_menu,
    get_moderators_management_menu,
    get_stats_menu,
    get_settings_menu,
    get_cancel_keyboard,
    get_back_keyboard,
    get_yes_no_keyboard,
    get_subscription_keyboard,
    get_chats_list_keyboard,
    get_moderators_list_keyboard
)

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database()

# Получение конфигурации
TOKEN = os.getenv('TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []

if not TOKEN:
    raise ValueError("TOKEN не найден в переменных окружения!")

# Функция для проверки прав администратора бота
def is_bot_admin(user_id):
    return user_id in ADMIN_IDS

# Функция для проверки прав модератора
def is_moderator(user_id):
    return db.is_moderator(user_id)

# Функция для проверки прав в чате
async def is_chat_admin(bot, chat_id, user_id):
    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки прав в чате: {e}")
        return False

# Проверка прав бота в чате
async def is_bot_chat_admin(bot, chat_id):
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        return bot_member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки прав бота: {e}")
        return False

# Проверка конкретных прав бота
async def check_bot_permissions(bot, chat_id):
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if bot_member.status not in ['administrator', 'creator']:
            return False, "❌ Бот не является администратором в чате!"
        
        # Проверяем права на ограничение пользователей
        if not getattr(bot_member, 'can_restrict_members', False):
            return False, "❌ У бота нет права ограничивать пользователей!"
        
        return True, "✅ У бота достаточно прав"
    except Exception as e:
        logger.error(f"Ошибка проверки прав бота: {e}")
        return False, f"❌ Ошибка: {str(e)}"

# Проверка прав бота в канале
async def is_bot_channel_admin(bot, channel_id):
    try:
        bot_member = await bot.get_chat_member(channel_id, bot.id)
        return bot_member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки прав бота в канале: {e}")
        return False

# Проверка прав на использование команды
def can_use_command(user_id, command_type):
    if is_bot_admin(user_id):
        return True
    
    moderator = db.get_moderator(user_id)
    if not moderator:
        return False
    
    # Проверяем права модератора
    if command_type == 'ban':
        return moderator.can_ban
    elif command_type == 'mute':
        return moderator.can_mute
    elif command_type == 'warn':
        return moderator.can_warn
    elif command_type == 'delete':
        return moderator.can_delete
    
    return False

# Парсинг времени для мутов/банов
def parse_time(time_str):
    time_str = time_str.lower().strip()
    
    if time_str in ["forever", "навсегда", "0"]:
        return 0
    
    multipliers = {
        'm': 1, 'min': 1, 'мин': 1,
        'h': 60, 'hour': 60, 'час': 60,
        'd': 1440, 'day': 1440, 'день': 1440, 'д': 1440,
        'w': 10080, 'week': 10080, 'неделя': 10080, 'нед': 10080
    }
    
    match = re.match(r'(\d+)\s*([a-zа-я]+)', time_str, re.IGNORECASE)
    if not match:
        try:
            return int(time_str)
        except:
            return None
    
    number = int(match.group(1))
    unit = match.group(2).lower()
    
    if unit in multipliers:
        return number * multipliers[unit]
    
    return None

# Форматирование времени
def format_duration(minutes):
    if minutes == 0:
        return "навсегда"
    elif minutes < 60:
        return f"{minutes} минут"
    elif minutes < 1440:
        hours = minutes // 60
        mins = minutes % 60
        if mins > 0:
            return f"{hours} час{'а' if hours > 1 else ''} {mins} минут"
        else:
            return f"{hours} час{'а' if hours > 1 else ''}"
    else:
        days = minutes // 1440
        hours = (minutes % 1440) // 60
        if hours > 0:
            return f"{days} день{'ей' if days > 1 else 'день'} {hours} час{'а' if hours > 1 else ''}"
        else:
            return f"{days} день{'ей' if days > 1 else 'день'}"

# ==================== КОМАНДЫ ====================

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'private':
        await update.message.reply_text(
            "👋 Привет! Я бот для модерации чатов и проверки подписки на канал.\n\n"
            "Для настройки используйте /admin (только для администраторов)\n"
            "Команды модерации: /warn, /mute, /ban, /unmute, /unban"
        )

# Команда /admin - доступна везде
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_admin(update.effective_user.id):
        await update.message.reply_text("❌ У вас нет прав администратора бота!")
        return
    
    # Если команда в чате - включаем/выключаем проверку
    if update.message.chat.type in ['group', 'supergroup']:
        await handle_chat_admin(update, context)
    else:
        # В личных сообщениях - показываем меню
        await show_admin_menu(update, context)

# Включение/выключение проверки в чате
async def handle_chat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    
    # Проверяем права в чате
    if not await is_chat_admin(context.bot, chat_id, update.effective_user.id):
        await update.message.reply_text("❌ Только администраторы чата могут управлять ботом!")
        return
    
    # Проверяем права бота в чате
    has_perms, perm_msg = await check_bot_permissions(context.bot, chat_id)
    if not has_perms:
        await update.message.reply_text(perm_msg)
        return
    
    # Получаем текущий статус
    is_enabled = db.is_chat_enabled(chat_id)
    
    if is_enabled:
        # Выключаем проверку
        db.disable_chat(chat_id)
        await update.message.reply_text(
            "✅ Проверка подписки **выключена** в этом чате.\n"
            "Теперь все могут писать без подписки на канал.\n\n"
            "Чтобы включить снова, используйте /admin",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Проверяем, настроен ли канал
        if not db.has_subscription_channel():
            await update.message.reply_text(
                "❌ Сначала настройте обязательный канал в ЛС бота!\n"
                "Напишите боту /admin в личных сообщениях."
            )
            return
        
        # Включаем проверку
        db.enable_chat(chat_id, update.message.chat.title)
        await update.message.reply_text(
            "✅ Проверка подписки **включена** в этом чате.\n"
            "Теперь пользователи должны быть подписаны на канал для отправки сообщений.\n\n"
            "Чтобы выключить, используйте /admin",
            parse_mode=ParseMode.MARKDOWN
        )

# Показать меню админа в ЛС
async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "👨‍💼 Панель администратора:",
            reply_markup=get_admin_main_menu()
        )
    else:
        await update.message.reply_text(
            "👨‍💼 Панель администратора:",
            reply_markup=get_admin_main_menu()
        )

# ==================== CALLBACK ОБРАБОТЧИКИ ====================

# Главное меню callback'ов
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_bot_admin(query.from_user.id):
        await query.edit_message_text("❌ У вас нет прав администратора!")
        return
    
    if query.data == "back_to_main":
        await show_admin_menu(update, context)
    
    elif query.data == "manage_channel":
        await show_channel_management(update, context)
    
    elif query.data == "manage_chats":
        await show_chats_management(update, context)
    
    elif query.data == "manage_moderators":
        await show_moderators_management(update, context)
    
    elif query.data == "stats_menu":
        await show_stats_menu(update, context)
    
    elif query.data == "settings_menu":
        await query.edit_message_text(
            "⚙️ Настройки (в разработке)",
            reply_markup=get_back_keyboard()
        )
    
    elif query.data == "cancel_action":
        await show_admin_menu(update, context)

# Управление каналом
async def show_channel_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    has_channel = db.has_subscription_channel()
    await query.edit_message_text(
        "📢 Управление обязательной подпиской:",
        reply_markup=get_channel_management_menu(has_channel)
    )

# Добавление/изменение канала
async def add_or_change_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📝 Отправьте ссылку на канал:\n\n"
        "Примеры:\n"
        "• https://t.me/channel_name\n"
        "• @channel_name\n\n"
        "❌ Для отмены нажмите кнопку ниже:",
        reply_markup=get_cancel_keyboard()
    )
    context.user_data['setup_step'] = 'waiting_channel_link'

# Изменение текста кнопки
async def change_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "✏️ Отправьте новый текст для кнопки:\n\n"
        "Пример: 📢 Подписаться на наш канал\n\n"
        "❌ Для отмены нажмите кнопку ниже:",
        reply_markup=get_cancel_keyboard()
    )
    context.user_data['setup_step'] = 'waiting_button_text'

# Удаление канала
async def delete_channel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    channel = db.get_subscription_channel()
    if not channel:
        await query.edit_message_text(
            "❌ Канал не настроен!",
            reply_markup=get_back_keyboard()
        )
        return
    
    await query.edit_message_text(
        f"⚠️ Вы уверены, что хотите удалить канал?\n\n"
        f"📢 Название: {channel.title}\n"
        f"🔗 Ссылка: {channel.link}\n\n"
        f"Это отключит проверку подписки во всех чатах!",
        reply_markup=get_yes_no_keyboard()
    )
    context.user_data['pending_action'] = 'delete_channel'

# Информация о канале
async def show_channel_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    channel = db.get_subscription_channel()
    if not channel:
        await query.edit_message_text(
            "❌ Канал не настроен!",
            reply_markup=get_back_keyboard()
        )
        return
    
    active_chats = db.get_all_enabled_chats()
    today_subs = db.get_today_subscriptions()
    
    text = f"📊 Информация о канале:\n\n"
    text += f"📢 Название: {channel.title}\n"
    text += f"🔗 Ссылка: {channel.link}\n"
    text += f"📝 Текст кнопки: {channel.button_text}\n"
    text += f"🔒 Тип: {'Публичный' if channel.username else 'Приватный'}\n"
    text += f"📅 Добавлен: {channel.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    text += f"📈 Статистика:\n"
    text += f"• Активных чатов: {len(active_chats)}\n"
    text += f"• Подписок сегодня: {today_subs}\n"
    
    await query.edit_message_text(
        text,
        reply_markup=get_back_keyboard()
    )

# Управление чатами
async def show_chats_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "💬 Управление чатами:\n\n"
        "Здесь вы можете управлять в каких чатах работает проверка подписки.",
        reply_markup=get_chats_management_menu()
    )

# Включить проверку в чате
async def enable_in_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Проверяем, настроен ли канал
    if not db.has_subscription_channel():
        await query.edit_message_text(
            "❌ Сначала настройте обязательный канал!\n"
            "Перейдите в 'Управление каналом' → 'Добавить канал'",
            reply_markup=get_back_keyboard()
        )
        return
    
    await query.edit_message_text(
        "➕ Включить проверку в чате:\n\n"
        "Отправьте ID чата, где нужно включить проверку.\n"
        "Чтобы получить ID чата, добавьте @RawDataBot в чат и отправьте /id\n\n"
        "❌ Для отмены нажмите кнопку ниже:",
        reply_markup=get_cancel_keyboard()
    )
    context.user_data['pending_action'] = 'enable_chat'

# Выключить проверку в чате
async def disable_in_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    enabled_chats = db.get_all_enabled_chats()
    
    if not enabled_chats:
        await query.edit_message_text(
            "❌ Нет активных чатов для отключения!",
            reply_markup=get_back_keyboard()
        )
        return
    
    await query.edit_message_text(
        "➖ Выберите чат для отключения:",
        reply_markup=get_chats_list_keyboard(enabled_chats, "disable_chat")
    )

# Список активных чатов
async def show_active_chats_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    enabled_chats = db.get_all_enabled_chats()
    
    if not enabled_chats:
        await query.edit_message_text(
            "📋 Список активных чатов:\n\n"
            "Нет активных чатов",
            reply_markup=get_back_keyboard()
        )
        return
    
    text = "📋 Список активных чатов:\n\n"
    for i, chat in enumerate(enabled_chats, 1):
        title = chat.chat_title or "Без названия"
        text += f"{i}. {title}\n"
        text += f"   ID: {chat.chat_id}\n"
        text += f"   Включен: {chat.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await query.edit_message_text(
        text,
        reply_markup=get_back_keyboard()
    )

# Отключение конкретного чата
async def disable_specific_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = int(query.data.split('_')[2])
    db.disable_chat(chat_id)
    
    await query.edit_message_text(
        f"✅ Проверка в чате {chat_id} отключена!",
        reply_markup=get_back_keyboard()
    )

# Управление модераторами
async def show_moderators_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🛡️ Управление модераторами:\n\n"
        "Модераторы могут использовать команды модерации (/warn, /mute, /ban)\n"
        "но не имеют доступа к настройкам бота.",
        reply_markup=get_moderators_management_menu()
    )

# Добавление модератора
async def add_moderator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "➕ Добавление модератора:\n\n"
        "Отправьте ID пользователя или его username (с @)\n"
        "Примеры:\n"
        "• 123456789\n"
        "• @username\n\n"
        "❌ Для отмены нажмите кнопку ниже:",
        reply_markup=get_cancel_keyboard()
    )
    context.user_data['pending_action'] = 'add_moderator'

# Удаление модератора
async def remove_moderator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    moderators = db.get_all_moderators()
    
    if not moderators:
        await query.edit_message_text(
            "❌ Нет модераторов для удаления!",
            reply_markup=get_back_keyboard()
        )
        return
    
    await query.edit_message_text(
        "➖ Выберите модератора для удаления:",
        reply_markup=get_moderators_list_keyboard(moderators, "remove_mod")
    )

# Список модераторов
async def list_moderators_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    moderators = db.get_all_moderators()
    
    if not moderators:
        await query.edit_message_text(
            "📋 Список модераторов:\n\n"
            "Нет добавленных модераторов",
            reply_markup=get_back_keyboard()
        )
        return
    
    text = "📋 Список модераторов:\n\n"
    for i, mod in enumerate(moderators, 1):
        text += f"{i}. @{mod.username or mod.user_id}\n"
        text += f"   ID: {mod.user_id}\n"
        text += f"   Права: "
        rights = []
        if mod.can_ban: rights.append("бан")
        if mod.can_mute: rights.append("мут")
        if mod.can_warn: rights.append("пред")
        if mod.can_delete: rights.append("удал")
        text += ", ".join(rights) + "\n"
        text += f"   Добавлен: {mod.added_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await query.edit_message_text(
        text,
        reply_markup=get_back_keyboard()
    )

# Удаление конкретного модератора
async def remove_specific_moderator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.split('_')[2])
    
    if db.remove_moderator(user_id):
        await query.edit_message_text(
            f"✅ Модератор {user_id} удален!",
            reply_markup=get_back_keyboard()
        )
    else:
        await query.edit_message_text(
            f"❌ Ошибка при удалении модератора!",
            reply_markup=get_back_keyboard()
        )

# Меню статистики
async def show_stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📊 Статистика:\n\n"
        "Выберите период для просмотра статистики:",
        reply_markup=get_stats_menu()
    )

# Показать статистику за сегодня
async def show_stats_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    today = datetime.utcnow().date()
    enabled_chats = db.get_all_enabled_chats()
    
    if not enabled_chats:
        text = "📊 Статистика за сегодня:\n\nНет активных чатов"
    else:
        text = "📊 Статистика за сегодня:\n\n"
        total_subs = 0
        total_mutes = 0
        total_deleted = 0
        
        for chat in enabled_chats:
            stats = db.get_statistics_period(chat.chat_id, today, today)
            chat_subs = sum(s.new_subscriptions for s in stats)
            chat_mutes = sum(s.mutes_given for s in stats)
            chat_deleted = sum(s.messages_deleted for s in stats)
            
            total_subs += chat_subs
            total_mutes += chat_mutes
            total_deleted += chat_deleted
            
            title = chat.chat_title or f"Чат {chat.chat_id}"
            text += f"**{title}:**\n"
            text += f"• Подписок: {chat_subs}\n"
            text += f"• Мутов: {chat_mutes}\n"
            text += f"• Удалено сообщений: {chat_deleted}\n\n"
        
        text += f"**Итого по всем чатам:**\n"
        text += f"• Подписок: {total_subs}\n"
        text += f"• Мутов: {total_mutes}\n"
        text += f"• Удалено сообщений: {total_deleted}"
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

# Экспорт в Excel
async def export_to_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Статистика"
        
        headers = ["Дата", "ID Чата", "Подписки", "Мутов", "Удалено"]
        ws.append(headers)
        
        all_chats = db.get_all_chats()
        for chat in all_chats:
            stats = db.session.query(db.Statistics).filter_by(chat_id=chat.chat_id).all()
            for stat in stats:
                ws.append([
                    stat.date.strftime('%d.%m.%Y'),
                    chat.chat_id,
                    stat.new_subscriptions,
                    stat.mutes_given,
                    stat.messages_deleted
                ])
        
        filename = f"data/statistics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        wb.save(filename)
        
        with open(filename, 'rb') as file:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=file,
                filename=f"статистика_{datetime.now().strftime('%d.%m.%Y')}.xlsx",
                caption="📊 Статистика за весь период"
            )
        
        await query.answer("✅ Файл отправлен в личные сообщения!")
        
    except Exception as e:
        logger.error(f"Ошибка экспорта: {e}")
        await query.answer("❌ Ошибка при создании файла!", show_alert=True)

# Обработка ответов Да/Нет
async def handle_yes_no_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "yes_action":
        if context.user_data.get('pending_action') == 'delete_channel':
            if db.delete_subscription_channel():
                await query.edit_message_text(
                    "✅ Канал успешно удален!\n"
                    "Проверка подписки отключена во всех чатах.",
                    reply_markup=get_back_keyboard()
                )
            else:
                await query.edit_message_text(
                    "❌ Ошибка при удалении канала!",
                    reply_markup=get_back_keyboard()
                )
            context.user_data.pop('pending_action', None)
    
    elif query.data == "no_action":
        if context.user_data.get('pending_action') == 'delete_channel':
            await query.edit_message_text(
                "❌ Удаление отменено.",
                reply_markup=get_back_keyboard()
            )
            context.user_data.pop('pending_action', None)

# ==================== ОБРАБОТКА СООБЩЕНИЙ ====================

# Обработка сообщений в ЛС (настройки)
async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_admin(update.effective_user.id):
        return
    
    user_data = context.user_data
    
    # Настройка канала
    if user_data.get('setup_step') == 'waiting_channel_link':
        channel_link = update.message.text.strip()
        
        if channel_link.lower() == 'отмена':
            await update.message.reply_text("❌ Настройка отменена.", reply_markup=get_admin_main_menu())
            user_data.pop('setup_step', None)
            return
        
        try:
            # Получаем информацию о канале
            chat = await context.bot.get_chat(channel_link)
            
            # Проверяем права бота в канале
            if not await is_bot_channel_admin(context.bot, chat.id):
                await update.message.reply_text(
                    "❌ Бот не является администратором в этом канале!\n"
                    "Добавьте бота в канал с правами администратора."
                )
                return
            
            # Сохраняем данные канала
            user_data['channel_data'] = {
                'chat_id': str(chat.id),
                'title': chat.title,
                'username': chat.username,
                'link': f"https://t.me/{chat.username}" if chat.username else f"tg://resolve?domain={chat.id}"
            }
            
            await update.message.reply_text(
                f"✅ Канал найден: {chat.title}\n\n"
                f"✏️ Теперь отправьте текст для кнопки подписки:\n"
                f"Пример: 📢 Подписаться на канал\n\n"
                f"❌ Для отмены напишите 'отмена'",
                reply_markup=get_cancel_keyboard()
            )
            
            user_data['setup_step'] = 'waiting_button_text'
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: {str(e)}\n"
                "Проверьте правильность ссылки и убедитесь, что бот имеет доступ к каналу."
            )
    
    # Настройка текста кнопки
    elif user_data.get('setup_step') == 'waiting_button_text':
        button_text = update.message.text.strip()
        
        if button_text.lower() == 'отмена':
            await update.message.reply_text("❌ Настройка отменена.", reply_markup=get_admin_main_menu())
            user_data.pop('setup_step', None)
            user_data.pop('channel_data', None)
            return
        
        # Сохраняем канал в базу
        channel_data = user_data.get('channel_data')
        if channel_data:
            db.add_subscription_channel(
                chat_id=channel_data['chat_id'],
                title=channel_data['title'],
                username=channel_data['username'],
                link=channel_data['link'],
                button_text=button_text
            )
            
            await update.message.reply_text(
                f"✅ Канал успешно настроен!\n\n"
                f"📢 Название: {channel_data['title']}\n"
                f"🔗 Ссылка: {channel_data['link']}\n"
                f"📝 Текст кнопки: {button_text}\n\n"
                f"Теперь бот будет проверять подписку на этот канал.",
                reply_markup=get_admin_main_menu()
            )
        
        user_data.pop('setup_step', None)
        user_data.pop('channel_data', None)
    
    # Включение чата
    elif user_data.get('pending_action') == 'enable_chat':
        chat_input = update.message.text.strip()
        
        if chat_input.lower() == 'отмена':
            await update.message.reply_text("❌ Действие отменено.", reply_markup=get_admin_main_menu())
            user_data.pop('pending_action', None)
            return
        
        try:
            chat_id = int(chat_input)
            
            # Проверяем, есть ли бот в чате
            try:
                chat = await context.bot.get_chat(chat_id)
                
                # Проверяем права бота в чате
                has_perms, perm_msg = await check_bot_permissions(context.bot, chat_id)
                if not has_perms:
                    await update.message.reply_text(perm_msg)
                    return
                
                # Включаем чат
                db.enable_chat(chat_id, chat.title)
                
                await update.message.reply_text(
                    f"✅ Проверка включена в чате:\n"
                    f"📝 Название: {chat.title}\n"
                    f"🔢 ID: {chat_id}\n\n"
                    f"Теперь бот будет проверять подписку в этом чате.\n"
                    f"Для отключения используйте /admin в чате.",
                    reply_markup=get_admin_main_menu()
                )
                
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Ошибка: {str(e)}\n"
                    f"Убедитесь, что:\n"
                    f"1. Бот добавлен в чат\n"
                    f"2. Бот имеет права администратора\n"
                    f"3. ID чата правильный"
                )
            
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID чата! Отправьте числовой ID.")
        
        user_data.pop('pending_action', None)
    
    # Добавление модератора
    elif user_data.get('pending_action') == 'add_moderator':
        user_input = update.message.text.strip()
        
        if user_input.lower() == 'отмена':
            await update.message.reply_text("❌ Действие отменено.", reply_markup=get_admin_main_menu())
            user_data.pop('pending_action', None)
            return
        
        try:
            # Пробуем получить пользователя
            if user_input.startswith('@'):
                user_input = user_input[1:]
                # Пытаемся найти по username
                # В реальности нужно искать в базе или через API
                # Для простоты будем просить ID
                await update.message.reply_text(
                    "⚠️ Для добавления модератора по username используйте его ID.\n"
                    "Отправьте числовой ID пользователя:"
                )
                return
            
            user_id = int(user_input)
            
            # Получаем информацию о пользователе
            try:
                user = await context.bot.get_chat(user_id)
                username = user.username or f"user_{user_id}"
                
                # Добавляем модератора
                db.add_moderator(
                    user_id=user_id,
                    username=username,
                    added_by=update.effective_user.id,
                    can_ban=True,
                    can_mute=True,
                    can_warn=True,
                    can_delete=True
                )
                
                await update.message.reply_text(
                    f"✅ Модератор добавлен!\n\n"
                    f"👤 Пользователь: @{username}\n"
                    f"🔢 ID: {user_id}\n\n"
                    f"Теперь он может использовать команды модерации.",
                    reply_markup=get_admin_main_menu()
                )
                
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Ошибка: {str(e)}\n"
                    f"Не удалось получить информацию о пользователе."
                )
            
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID! Отправьте числовой ID.")
        
        user_data.pop('pending_action', None)

# Обработка сообщений в группах
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type in ['group', 'supergroup']:
        chat_id = update.message.chat.id
        
        # Проверяем, включен ли чат для проверки
        if not db.is_chat_enabled(chat_id):
            return
        
        user_id = update.effective_user.id
        
        # Игнорируем сообщения от ботов
        if update.effective_user.is_bot:
            return
        
        # Проверяем права админа или модератора в чате
        is_admin_or_mod = await is_chat_admin(context.bot, chat_id, user_id) or is_moderator(user_id)
        if is_admin_or_mod:
            return
        
        # Проверяем, настроен ли канал для подписки
        channel = db.get_subscription_channel()
        if not channel:
            return
        
        # Проверяем подписку пользователя
        if not db.is_user_subscribed(user_id):
            try:
                # Удаляем сообщение
                await update.message.delete()
                
                # Проверяем права бота
                has_perms, perm_msg = await check_bot_permissions(context.bot, chat_id)
                if not has_perms:
                    logger.error(f"Недостаточно прав для мута в чате {chat_id}: {perm_msg}")
                    return
                
                # Даем мут пользователю
                until_date = int((datetime.now() + timedelta(days=365)).timestamp())
                
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(
                        can_send_messages=False
                    ),
                    until_date=until_date
                )
                
                # Сохраняем мут в базу
                db.add_mute(
                    user_id=user_id,
                    chat_id=chat_id,
                    muted_by=context.bot.id,
                    duration_minutes=525600,  # Год
                    reason="Не подписан на обязательный канал"
                )
                
                # Обновляем статус в БД
                db.update_user_subscription(
                    user_id=user_id,
                    username=update.effective_user.username or f"user_{user_id}",
                    subscribed=False
                )
                
                # Обновляем статистику
                db.update_statistics(chat_id, mutes_given=1, messages_deleted=1)
                
                # Отправляем сообщение с кнопками
                username = update.effective_user.username or "Пользователь"
                message_text = (
                    f"👤 @{username}, привет!\n"
                    f"📢 Ты не подписан на канал '{channel.title}'!\n"
                    f"Подпишись, чтобы писать в чат!"
                )
                
                keyboard = get_subscription_keyboard(
                    user_id=user_id,
                    channel_link=channel.link,
                    button_text=channel.button_text
                )
                
                await update.message.chat.send_message(
                    message_text,
                    reply_markup=keyboard
                )
                
            except Exception as e:
                logger.error(f"Ошибка при муте пользователя: {e}")

# ==================== КОМАНДЫ МОДЕРАЦИИ ====================

# Функция для снятия мута
async def unmute_user(bot, chat_id, user_id):
    try:
        # Проверяем права бота
        has_perms, perm_msg = await check_bot_permissions(bot, chat_id)
        if not has_perms:
            return False, perm_msg
        
        # Пробуем разные способы снятия ограничений
        try:
            # Способ 1: Установить все разрешения
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions.all_permissions(),
                until_date=int((datetime.now() + timedelta(seconds=1)).timestamp())
            )
        except:
            try:
                # Способ 2: Только отправка сообщений
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(
                        can_send_messages=True
                    ),
                    until_date=int((datetime.now() + timedelta(seconds=1)).timestamp())
                )
            except Exception as e:
                return False, f"Не удалось снять мут: {str(e)}"
        
        # Удаляем из базы
        db.remove_mute(user_id, chat_id)
        
        return True, "Мут успешно снят"
    
    except Exception as e:
        logger.error(f"Ошибка при снятии мута: {e}")
        return False, f"Ошибка: {str(e)}"

# Проверка подписки по нажатию кнопки
async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.split('_')[1])
    
    if query.from_user.id != user_id:
        await query.answer("❌ Это не ваша кнопка!", show_alert=True)
        return
    
    channel = db.get_subscription_channel()
    if not channel:
        await query.edit_message_text("❌ Канал для подписки не настроен!")
        return
    
    try:
        chat_member = await context.bot.get_chat_member(
            chat_id=int(channel.chat_id),
            user_id=user_id
        )
        
        if chat_member.status in ['member', 'administrator', 'creator']:
            # Обновляем статус в БД
            db.update_user_subscription(
                user_id=user_id,
                username=query.from_user.username or f"user_{user_id}",
                subscribed=True
            )
            
            # Снимаем мут во ВСЕХ чатах где пользователь был замьючен
            enabled_chats = db.get_all_enabled_chats()
            unmuted_chats = []
            failed_chats = []
            
            for chat in enabled_chats:
                if db.is_user_muted(user_id, chat.chat_id):
                    success, message = await unmute_user(context.bot, chat.chat_id, user_id)
                    if success:
                        unmuted_chats.append(chat.chat_id)
                        db.remove_mute(user_id, chat.chat_id)
                    else:
                        failed_chats.append((chat.chat_id, message))
            
            # Обновляем статистику
            for chat in enabled_chats:
                db.update_statistics(chat.chat_id, new_subscription=1)
            
            result_message = "✅ Отлично! Вы подписаны и теперь можете писать в чат!\n"
            
            if unmuted_chats:
                result_message += f"🔓 Мут снят в {len(unmuted_chats)} чатах.\n"
            
            if failed_chats:
                result_message += f"⚠️ Не удалось снять мут в {len(failed_chats)} чатах.\n"
                result_message += "Обратитесь к администратору для ручного снятия мута."
            
            await query.edit_message_text(result_message)
            
        else:
            await query.answer("❌ Вы ещё не подписались на канал!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        await query.edit_message_text(f"❌ Ошибка проверки: {str(e)}")

# Команда /warn - выдать предупреждение
async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.effective_user.id
    
    # Проверяем права на использование команды
    if not can_use_command(user_id, 'warn'):
        await update.message.reply_text("❌ У вас нет прав для выдачи предупреждений!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Использование:\n"
            "/warn [причина] - выдать предупреждение пользователю\n"
            "Или ответьте на сообщение пользователя\n\n"
            "Пример:\n"
            "/warn Нарушение правил"
        )
        return
    
    target_user = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) if context.args else "Нарушение правил"
    
    # Нельзя выдать предупреждение самому себе
    if target_user.id == user_id:
        await update.message.reply_text("❌ Нельзя выдать предупреждение самому себе!")
        return
    
    # Нельзя выдать предупреждение админам
    if await is_chat_admin(context.bot, chat_id, target_user.id):
        await update.message.reply_text("❌ Нельзя выдать предупреждение администратору!")
        return
    
    warnings = db.add_warning(
        user_id=target_user.id,
        chat_id=chat_id,
        reason=reason
    )
    
    await update.message.reply_text(
        f"⚠️ Пользователю @{target_user.username or target_user.id} выдано предупреждение!\n"
        f"📝 Причина: {reason}\n"
        f"🔢 Всего предупреждений: {warnings}"
    )

# Команда /unwarn - снять предупреждение
async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.effective_user.id
    
    # Проверяем права на использование команды
    if not can_use_command(user_id, 'warn'):
        await update.message.reply_text("❌ У вас нет прав для управления предупреждениями!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя!")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    if db.remove_warning(target_user.id, chat_id):
        current_warnings = db.get_warnings(target_user.id, chat_id)
        await update.message.reply_text(
            f"✅ Предупреждение снято!\n"
            f"👤 Пользователь: @{target_user.username or target_user.id}\n"
            f"⚠️ Осталось предупреждений: {current_warnings}"
        )
    else:
        await update.message.reply_text(
            f"ℹ️ У пользователя @{target_user.username or target_user.id} нет предупреждений."
        )

# Команда /mute - выдать мут
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.effective_user.id
    
    # Проверяем права на использование команды
    if not can_use_command(user_id, 'mute'):
        await update.message.reply_text("❌ У вас нет прав для выдачи мутов!")
        return
    
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text(
            "❌ Использование:\n"
            "/mute [время] [причина] - замутить пользователя\n"
            "Или ответьте на сообщение пользователя\n\n"
            "Примеры:\n"
            "/mute 30m Спам\n"
            "/mute 2h Оскорбления\n"
            "/mute 1d Нарушение правил\n"
            "/mute forever Повторные нарушения"
        )
        return
    
    # Определяем пользователя
    target_user = None
    duration_str = None
    reason = None
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if context.args:
            # Первый аргумент - время, остальное - причина
            duration_str = context.args[0]
            reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "Нарушение правил"
        else:
            duration_str = "1h"
            reason = "Нарушение правил"
    else:
        # Пытаемся извлечь из аргументов
        if len(context.args) >= 2:
            await update.message.reply_text(
                "⚠️ Для мута по username ответьте на сообщение пользователя"
            )
            return
    
    if not target_user:
        await update.message.reply_text("❌ Не удалось определить пользователя!")
        return
    
    # Нельзя замутить самого себя
    if target_user.id == user_id:
        await update.message.reply_text("❌ Нельзя замутить самого себя!")
        return
    
    # Нельзя замутить админов
    if await is_chat_admin(context.bot, chat_id, target_user.id):
        await update.message.reply_text("❌ Нельзя замутить администратора!")
        return
    
    # Проверяем права бота
    has_perms, perm_msg = await check_bot_permissions(context.bot, chat_id)
    if not has_perms:
        await update.message.reply_text(perm_msg)
        return
    
    # Парсим время
    duration_minutes = 60  # По умолчанию 1 час
    if duration_str:
        parsed = parse_time(duration_str)
        if parsed is not None:
            duration_minutes = parsed
        else:
            await update.message.reply_text("❌ Неверный формат времени! Используйте: 30m, 2h, 1d, forever")
            return
    
    try:
        until_date = None
        if duration_minutes > 0:
            until_date = int((datetime.now() + timedelta(minutes=duration_minutes)).timestamp())
        
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user.id,
            permissions=ChatPermissions(
                can_send_messages=False
            ),
            until_date=until_date
        )
        
        # Сохраняем в базу
        db.add_mute(
            user_id=target_user.id,
            chat_id=chat_id,
            muted_by=user_id,
            duration_minutes=duration_minutes,
            reason=reason
        )
        
        duration_text = format_duration(duration_minutes)
        reason_text = f"\n📝 Причина: {reason}" if reason else ""
        
        await update.message.reply_text(
            f"🔇 Пользователь @{target_user.username or target_user.id} "
            f"получил мут на {duration_text}!{reason_text}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при муте: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Команда /unmute - снять мут
async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.effective_user.id
    
    # Проверяем права на использование команды
    if not can_use_command(user_id, 'mute'):
        await update.message.reply_text("❌ У вас нет прав для снятия мутов!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя!")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    success, message = await unmute_user(context.bot, chat_id, target_user.id)
    
    if success:
        await update.message.reply_text(
            f"✅ Пользователь @{target_user.username or target_user.id} размучен!"
        )
    else:
        await update.message.reply_text(
            f"❌ Не удалось размутить пользователя: {message}"
        )

# Команда /ban - забанить пользователя
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.effective_user.id
    
    # Проверяем права на использование команды
    if not can_use_command(user_id, 'ban'):
        await update.message.reply_text("❌ У вас нет прав для бана пользователей!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Использование:\n"
            "/ban [причина] - забанить пользователя\n"
            "Или ответьте на сообщение пользователя\n\n"
            "Пример:\n"
            "/ban Грубые нарушения"
        )
        return
    
    target_user = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) if context.args else "Нарушение правил"
    
    # Нельзя забанить самого себя
    if target_user.id == user_id:
        await update.message.reply_text("❌ Нельзя забанить самого себя!")
        return
    
    # Нельзя забанить админов
    if await is_chat_admin(context.bot, chat_id, target_user.id):
        await update.message.reply_text("❌ Нельзя забанить администратора!")
        return
    
    try:
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=target_user.id
        )
        
        # Сохраняем в базу
        db.add_ban(
            user_id=target_user.id,
            chat_id=chat_id,
            banned_by=user_id,
            reason=reason
        )
        
        reason_text = f"\n📝 Причина: {reason}" if reason else ""
        await update.message.reply_text(
            f"🚫 Пользователь @{target_user.username or target_user.id} забанен!{reason_text}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Команда /unban - разбанить пользователя
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.effective_user.id
    
    # Проверяем права на использование команды
    if not can_use_command(user_id, 'ban'):
        await update.message.reply_text("❌ У вас нет прав для разбана пользователей!")
        return
    
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text(
            "❌ Использование:\n"
            "/unban - разбанить пользователя\n"
            "Или ответьте на сообщение пользователя"
        )
        return
    
    target_user = None
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif context.args:
        await update.message.reply_text(
            "⚠️ Для разбана по username ответьте на сообщение пользователя"
        )
        return
    
    if not target_user:
        await update.message.reply_text("❌ Не удалось определить пользователя!")
        return
    
    try:
        await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=target_user.id,
            only_if_banned=True
        )
        
        # Удаляем из базы
        db.remove_ban(target_user.id, chat_id)
        
        await update.message.reply_text(
            f"✅ Пользователь @{target_user.username or target_user.id} разбанен!"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# Команда /check - проверить подписку пользователя
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.effective_user.id
    
    # Проверяем права (админ или модератор)
    if not (is_bot_admin(user_id) or is_moderator(user_id)):
        await update.message.reply_text("❌ У вас нет прав для использования этой команды!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя для проверки!")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    channel = db.get_subscription_channel()
    if not channel:
        await update.message.reply_text("❌ Канал для проверки не настроен!")
        return
    
    try:
        # Проверяем подписку
        chat_member = await context.bot.get_chat_member(
            chat_id=int(channel.chat_id),
            user_id=target_user.id
        )
        
        if chat_member.status in ['member', 'administrator', 'creator']:
            # Пользователь подписан
            db.update_user_subscription(
                user_id=target_user.id,
                username=target_user.username or f"user_{target_user.id}",
                subscribed=True
            )
            
            # Снимаем мут если есть
            success, message = await unmute_user(context.bot, chat_id, target_user.id)
            
            if success:
                await update.message.reply_text(
                    f"✅ Пользователь @{target_user.username or target_user.id} подписан на канал!\n"
                    f"📢 Канал: {channel.title}\n"
                    f"🔓 Мут снят автоматически."
                )
            else:
                await update.message.reply_text(
                    f"✅ Пользователь @{target_user.username or target_user.id} подписан на канал!\n"
                    f"📢 Канал: {channel.title}\n"
                    f"⚠️ {message}"
                )
        else:
            # Пользователь не подписан
            await update.message.reply_text(
                f"❌ Пользователь @{target_user.username or target_user.id} НЕ подписан на канал!\n"
                f"📢 Канал: {channel.title}\n"
                f"🔗 Ссылка: {channel.link}"
            )
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка проверки: {str(e)}")

# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    
    # Команды модерации
    application.add_handler(CommandHandler("warn", warn_command))
    application.add_handler(CommandHandler("unwarn", unwarn_command))
    application.add_handler(CommandHandler("mute", mute_command))
    application.add_handler(CommandHandler("unmute", unmute_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("check", check_command))
    
    # Главные callback обработчики
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^back_to_main$"))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^manage_channel$"))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^manage_chats$"))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^manage_moderators$"))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^stats_menu$"))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^settings_menu$"))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^cancel_action$"))
    
    # Управление каналом
    application.add_handler(CallbackQueryHandler(add_or_change_channel, pattern="^(add_channel|change_channel)$"))
    application.add_handler(CallbackQueryHandler(change_button_text, pattern="^change_button_text$"))
    application.add_handler(CallbackQueryHandler(delete_channel_confirm, pattern="^delete_channel$"))
    application.add_handler(CallbackQueryHandler(show_channel_info, pattern="^channel_info$"))
    
    # Управление чатами
    application.add_handler(CallbackQueryHandler(enable_in_chat, pattern="^enable_in_chat$"))
    application.add_handler(CallbackQueryHandler(disable_in_chat, pattern="^disable_in_chat$"))
    application.add_handler(CallbackQueryHandler(show_active_chats_list, pattern="^active_chats_list$"))
    application.add_handler(CallbackQueryHandler(disable_specific_chat, pattern="^disable_chat_"))
    
    # Управление модераторами
    application.add_handler(CallbackQueryHandler(add_moderator_callback, pattern="^add_moderator$"))
    application.add_handler(CallbackQueryHandler(remove_moderator_callback, pattern="^remove_moderator$"))
    application.add_handler(CallbackQueryHandler(list_moderators_callback, pattern="^list_moderators$"))
    application.add_handler(CallbackQueryHandler(remove_specific_moderator, pattern="^remove_mod_"))
    
    # Статистика
    application.add_handler(CallbackQueryHandler(show_stats_today, pattern="^stats_today$"))
    application.add_handler(CallbackQueryHandler(export_to_excel, pattern="^export_excel$"))
    
    # Да/Нет действия
    application.add_handler(CallbackQueryHandler(handle_yes_no_callback, pattern="^(yes_action|no_action)$"))
    
    # Проверка подписки
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_"))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_private_message))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_group_message))
    
    # Обработчик ошибок
    application.add_error_handler(lambda update, context: logger.error(f"Ошибка: {context.error}"))
    
    print("🤖 Бот запущен...")
    print("✨ Команды модерации:")
    print("  /warn [причина] - выдать предупреждение")
    print("  /unwarn - снять предупреждение")
    print("  /mute [время] [причина] - замутить пользователя")
    print("  /unmute - размутить пользователя")
    print("  /ban [причина] - забанить пользователя")
    print("  /unban - разбанить пользователя")
    print("  /check - проверить подписку")
    print("  /admin - управление ботом (только для администраторов)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()