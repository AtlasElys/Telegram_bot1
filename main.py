import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler
)
import re
import os
import json
from datetime import datetime, timedelta
from io import StringIO
import csv
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
import signal
import sys
import asyncio
import fcntl
import atexit
import time
import psutil

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    try:
        with open('token.txt', 'r') as f:
            BOT_TOKEN = f.read().strip()
    except FileNotFoundError:
        print("ОШИБКА: Токен бота не найден!")
        print("Создайте файл .env и добавьте в него строку: BOT_TOKEN=ваш_токен_бота")
        print("Или создайте файл token.txt и впишите в него токен")
        exit(1)

# Файл для хранения настроек
CONFIG_FILE = 'bot_config.json'
STATS_FILE = 'bot_stats.json'
PID_FILE = 'bot.pid'
LOCK_FILE = 'bot.lock'

# Функция для проверки единственного экземпляра
def check_single_instance():
    """Проверяет, не запущен ли уже бот"""
    
    # Способ 1: Проверка через psutil (более надежный)
    try:
        current_pid = os.getpid()
        current_process = psutil.Process(current_pid)
        current_process_name = current_process.name()
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Пропускаем текущий процесс
                if proc.info['pid'] == current_pid:
                    continue
                
                # Проверяем процессы Python
                if proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline', [])
                    # Проверяем, есть ли в командной строке наш файл
                    if cmdline and any('tesst.py' in arg for arg in cmdline):
                        print(f"❌ Бот уже запущен в процессе PID: {proc.info['pid']}")
                        print(f"Команда: {' '.join(cmdline)}")
                        return False
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except:
        pass  # Если psutil не работает, используем второй способ
    
    # Способ 2: Проверка через файл блокировки
    try:
        # Пытаемся создать файл с блокировкой
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, 'r') as f:
                    old_pid = int(f.read().strip())
                
                # Проверяем, существует ли процесс с таким PID
                try:
                    os.kill(old_pid, 0)  # Сигнал 0 только проверяет существование процесса
                    print(f"❌ Бот уже запущен в процессе PID: {old_pid}")
                    print("Используйте 'pkill -f python' для остановки всех процессов")
                    print("Или удалите файл bot.pid вручную:")
                    print(f"  rm {PID_FILE}")
                    return False
                except OSError:
                    # Процесс не существует, удаляем старый PID файл
                    os.unlink(PID_FILE)
            except:
                # Если файл поврежден, удаляем его
                try:
                    os.unlink(PID_FILE)
                except:
                    pass
        
        # Создаем новый PID файл
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        
        # Регистрируем удаление PID файла при выходе
        def remove_pid():
            try:
                if os.path.exists(PID_FILE):
                    with open(PID_FILE, 'r') as f:
                        saved_pid = int(f.read().strip())
                    if saved_pid == os.getpid():
                        os.unlink(PID_FILE)
                        print("🧹 PID файл очищен")
            except:
                pass
        
        atexit.register(remove_pid)
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при проверке единственного экземпляра: {e}")
        return False

# Функция для принудительной очистки
def force_cleanup():
    """Принудительно очищает все lock файлы"""
    files_to_remove = [PID_FILE, LOCK_FILE]
    for file in files_to_remove:
        try:
            if os.path.exists(file):
                os.unlink(file)
                print(f"🧹 Удален файл: {file}")
        except:
            pass

# Загружаем или создаем конфигурацию
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Миграция старых данных в новый формат
            updated = False
            for target in config.get('target_groups', []):
                if 'source_id' in target and 'source_ids' not in target:
                    target['source_ids'] = [target['source_id']]
                    del target['source_id']
                    updated = True
            if updated:
                save_config(config)
            return config
    return {
        'source_groups': [],
        'target_groups': [],
    }

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# Загружаем или создаем статистику
def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'users': {},
        'daily': {},
        'tasks': []
    }

def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

config = load_config()
stats = load_stats()

# Веб-сервер для поддержания активности
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is alive!"

def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

# Запускаем Flask в отдельном потоке
flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Хранилище тестов
test_sessions = {}

# Хранилище SMS заданий
sms_sessions = {}

# Состояния для ConversationHandler
(
    SELECT_ACTION,
    SELECT_GROUP_TYPE,
    ADD_SOURCE_GROUP_NAME,
    ADD_TARGET_GROUP_SELECT,
    ADD_TARGET_GROUP_NAME,
    CONFIRM_REMOVE_GROUP,
    SELECT_MULTIPLE_SOURCES
) = range(7)

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def update_user_stats(user_id: int, username: str, first_name: str, task_type: str, action: str):
    """Обновляет статистику пользователя"""
    if str(user_id) not in stats['users']:
        stats['users'][str(user_id)] = {
            'username': username,
            'first_name': first_name,
            'sms_taken': 0,
            'sms_completed': 0,
            'sms_failed': 0,
            'tests_taken': 0,
            'tests_completed': 0,
            'tests_failed': 0,
            'last_activity': datetime.now().isoformat()
        }
    
    user = stats['users'][str(user_id)]
    
    if task_type == 'sms':
        if action == 'take':
            user['sms_taken'] += 1
        elif action == 'complete':
            user['sms_completed'] += 1
        elif action == 'fail':
            user['sms_failed'] += 1
    elif task_type == 'test':
        if action == 'take':
            user['tests_taken'] += 1
        elif action == 'complete':
            user['tests_completed'] += 1
        elif action == 'fail':
            user['tests_failed'] += 1
    
    user['last_activity'] = datetime.now().isoformat()
    
    today = datetime.now().strftime("%Y-%m-%d")
    if today not in stats['daily']:
        stats['daily'][today] = {'sms': 0, 'tests': 0, 'completed': 0, 'failed': 0}
    
    if action == 'take':
        if task_type == 'sms':
            stats['daily'][today]['sms'] += 1
        elif task_type == 'test':
            stats['daily'][today]['tests'] += 1
    elif action == 'complete':
        stats['daily'][today]['completed'] += 1
    elif action == 'fail':
        stats['daily'][today]['failed'] += 1
    
    save_stats(stats)

def add_task_to_history(task_id: int, task_type: str, text: str, user_id: int = None, result: str = None):
    """Добавляет задание в историю"""
    stats['tasks'].append({
        'id': task_id,
        'type': task_type,
        'text': text[:100] + '...' if len(text) > 100 else text,
        'user_id': user_id,
        'result': result,
        'timestamp': datetime.now().isoformat()
    })
    
    if len(stats['tasks']) > 1000:
        stats['tasks'] = stats['tasks'][-1000:]
    
    save_stats(stats)

async def generate_stats_file() -> str:
    """Генерирует красивый файл со статистикой"""
    filename = f"statistics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        
        writer.writerow(['='*80])
        writer.writerow(['СТАТИСТИКА РАБОТЫ БОТА'.center(80)])
        writer.writerow(['='*80])
        writer.writerow([f'Сгенерировано: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}'])
        writer.writerow([])
        
        # Общая статистика
        writer.writerow(['📊 ОБЩАЯ СТАТИСТИКА'])
        writer.writerow(['-'*80])
        
        total_users = len(stats['users'])
        total_sms_taken = sum(u['sms_taken'] for u in stats['users'].values())
        total_sms_completed = sum(u['sms_completed'] for u in stats['users'].values())
        total_sms_failed = sum(u['sms_failed'] for u in stats['users'].values())
        total_tests_taken = sum(u['tests_taken'] for u in stats['users'].values())
        total_tests_completed = sum(u['tests_completed'] for u in stats['users'].values())
        total_tests_failed = sum(u['tests_failed'] for u in stats['users'].values())
        
        sms_success_rate = (total_sms_completed / total_sms_taken * 100) if total_sms_taken > 0 else 0
        tests_success_rate = (total_tests_completed / total_tests_taken * 100) if total_tests_taken > 0 else 0
        
        writer.writerow(['👥 Всего воркеров:', total_users])
        writer.writerow([])
        writer.writerow(['📱 SMS ЗАДАНИЯ:'])
        writer.writerow(['   • Всего создано:', total_sms_taken])
        writer.writerow(['   • ✅ Успешно выполнено:', total_sms_completed])
        writer.writerow(['   • ❌ Провалено:', total_sms_failed])
        writer.writerow(['   • 📊 Успешность:', f'{sms_success_rate:.1f}%'])
        writer.writerow([])
        writer.writerow(['📝 ТЕСТОВЫЕ ЗАДАНИЯ:'])
        writer.writerow(['   • Всего создано:', total_tests_taken])
        writer.writerow(['   • ✅ Успешно выполнено:', total_tests_completed])
        writer.writerow(['   • ❌ Провалено:', total_tests_failed])
        writer.writerow(['   • 📊 Успешность:', f'{tests_success_rate:.1f}%'])
        writer.writerow([])
    
    return filename

# ===== ПРОВЕРКА ПРИВЯЗОК =====
def check_group_connections(chat_id: int) -> dict:
    """Проверяет связи группы"""
    is_source = any(g['id'] == chat_id for g in config['source_groups'])
    
    if is_source:
        # Это исходная группа - проверяем целевые группы для нее
        target_groups = [t for t in config['target_groups'] if chat_id in t.get('source_ids', [])]
        return {
            'is_source': True,
            'is_target': False,
            'connected_groups': target_groups,
            'has_connections': len(target_groups) > 0
        }
    else:
        # Это целевая группа - проверяем исходные группы для нее
        target_group = next((t for t in config['target_groups'] if t['id'] == chat_id), None)
        if target_group:
            source_groups = [s for s in config['source_groups'] if s['id'] in target_group.get('source_ids', [])]
            return {
                'is_source': False,
                'is_target': True,
                'connected_groups': source_groups,
                'has_connections': len(source_groups) > 0
            }
    
    return {
        'is_source': False,
        'is_target': False,
        'connected_groups': [],
        'has_connections': False
    }

# ===== КОМАНДА /id =====
async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает ID чата и пользователя"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    chat_title = update.effective_chat.title
    
    connections = check_group_connections(chat_id)
    
    message = (
        f"🆔 Информация:\n"
        f"• Название чата: {chat_title}\n"
        f"• Тип чата: {chat_type}\n"
        f"• ID чата: `{chat_id}`\n"
        f"• ID пользователя: `{user_id}`\n"
    )
    
    if connections['is_source']:
        message += f"• 📤 Это исходная группа\n"
        if connections['has_connections']:
            message += f"• Привязано целевых групп: {len(connections['connected_groups'])}\n"
        else:
            message += f"• ⚠️ Нет привязанных целевых групп!\n"
    
    if connections['is_target']:
        message += f"• 📥 Это целевая группа\n"
        if connections['has_connections']:
            message += f"• Привязано к исходным группам: {len(connections['connected_groups'])}\n"
        else:
            message += f"• ⚠️ Нет привязанных исходных групп!\n"
    
    if update.effective_user.username:
        message += f"• Username: @{update.effective_user.username}"
    
    await update.message.reply_text(message, parse_mode="Markdown")

# ===== КОМАНДА /warn =====
async def warn_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет предупреждение во все целевые группы"""
    current_chat_id = update.effective_chat.id
    connections = check_group_connections(current_chat_id)
    
    if not connections['is_source']:
        await update.message.reply_text("❌ Эта команда доступна только в исходных группах")
        return

    if not connections['has_connections']:
        await update.message.reply_text(
            "❌ У этой исходной группы нет привязанных целевых групп!\n"
            "Используйте /settings чтобы добавить привязки."
        )
        return

    sent_count = 0
    for target in connections['connected_groups']:
        try:
            await context.bot.send_message(
                chat_id=target['id'],
                text="🚨 АЛО НЕ СПИМ! ВОРК ИДЁТ! РАБОТАЕМ БЫСТРЕЕ! 🚨",
                message_thread_id=target.get('topic_id')
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Ошибка отправки в группу {target['name']}: {e}")

    await update.message.reply_text(f"✅ Предупреждение отправлено в {sent_count} групп!")

# ===== КОМАНДА /settings =====
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню настроек"""
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📁 Статистика файлом", callback_data="stats_file")],
        [InlineKeyboardButton("⚙️ Настройка групп", callback_data="group_settings")],
        [InlineKeyboardButton("🔒 Закрыть админ панель", callback_data="close_admin")]
    ]
    await update.message.reply_text(
        "🔧 Панель администратора\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_ACTION

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок настроек"""
    query = update.callback_query
    await query.answer()

    if query.data == "stats":
        await show_statistics(update, context)
        return SELECT_ACTION
    
    elif query.data == "stats_file":
        await send_stats_file(update, context)
        return SELECT_ACTION
    
    elif query.data == "group_settings":
        await show_group_settings(update, context)
        return SELECT_GROUP_TYPE
    
    elif query.data == "close_admin":
        await query.edit_message_text("🔒 Админ панель закрыта")
        return ConversationHandler.END
    
    elif query.data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("📁 Статистика файлом", callback_data="stats_file")],
            [InlineKeyboardButton("⚙️ Настройка групп", callback_data="group_settings")],
            [InlineKeyboardButton("🔒 Закрыть админ панель", callback_data="close_admin")]
        ]
        await query.edit_message_text(
            "🔧 Панель администратора\n\nВыберите действие:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_ACTION

async def send_stats_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет файл со статистикой"""
    query = update.callback_query
    
    await query.edit_message_text("📊 Генерирую файл со статистикой...")
    
    try:
        filename = await generate_stats_file()
        
        with open(filename, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=filename,
                caption="📊 Полная статистика работы бота"
            )
        
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Ошибка при генерации статистики: {e}")
        await query.message.reply_text("❌ Ошибка при генерации статистики")
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📁 Статистика файлом", callback_data="stats_file")],
        [InlineKeyboardButton("⚙️ Настройка групп", callback_data="group_settings")],
        [InlineKeyboardButton("🔒 Закрыть админ панель", callback_data="close_admin")]
    ]
    await query.message.reply_text(
        "🔧 Панель администратора\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает простую и понятную статистику"""
    query = update.callback_query
    
    total_sms_taken = sum(u['sms_taken'] for u in stats['users'].values())
    total_sms_completed = sum(u['sms_completed'] for u in stats['users'].values())
    total_sms_failed = sum(u['sms_failed'] for u in stats['users'].values())
    total_tests_taken = sum(u['tests_taken'] for u in stats['users'].values())
    total_tests_completed = sum(u['tests_completed'] for u in stats['users'].values())
    total_tests_failed = sum(u['tests_failed'] for u in stats['users'].values())
    
    sms_success_rate = (total_sms_completed / total_sms_taken * 100) if total_sms_taken > 0 else 0
    tests_success_rate = (total_tests_completed / total_tests_taken * 100) if total_tests_taken > 0 else 0
    
    stats_text = (
        "📊 **ПРОСТАЯ СТАТИСТИКА**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "📱 **SMS ЗАДАНИЯ**\n"
        f"┌ Всего создано: {total_sms_taken}\n"
        f"├ ✅ Выполнено: {total_sms_completed}\n"
        f"├ ❌ Провалено: {total_sms_failed}\n"
        f"└ 📊 Успешность: {sms_success_rate:.1f}%\n\n"
        
        "📝 **ТЕСТОВЫЕ ЗАДАНИЯ**\n"
        f"┌ Всего создано: {total_tests_taken}\n"
        f"├ ✅ Выполнено: {total_tests_completed}\n"
        f"├ ❌ Провалено: {total_tests_failed}\n"
        f"└ 📊 Успешность: {tests_success_rate:.1f}%\n\n"
        
        "📈 **ИТОГО**\n"
        f"┌ Всего заданий: {total_sms_taken + total_tests_taken}\n"
        f"├ ✅ Выполнено: {total_sms_completed + total_tests_completed}\n"
        f"├ ❌ Провалено: {total_sms_failed + total_tests_failed}\n"
        f"└ 📊 Успешность: {(total_sms_completed + total_tests_completed) / (total_sms_taken + total_tests_taken) * 100 if (total_sms_taken + total_tests_taken) > 0 else 0:.1f}%\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Всего воркеров: {len(stats['users'])}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📁 Подробная статистика файлом", callback_data="stats_file")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        stats_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_group_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню настроек групп"""
    if update.callback_query:
        query = update.callback_query
    else:
        query = update
    
    text = "⚙️ **Настройка групп**\n\n"
    
    # Показываем исходные группы
    text += f"**📤 Исходные группы ({len(config['source_groups'])}):**\n"
    if config['source_groups']:
        for group in config['source_groups']:
            target_count = len([t for t in config['target_groups'] if group['id'] in t.get('source_ids', [])])
            text += f"• {group['name']} (`{group['id']}`) → привязано: {target_count}\n"
    else:
        text += "• Нет исходных групп\n"
    
    # Показываем целевые группы
    text += f"\n**📥 Целевые группы ({len(config['target_groups'])}):**\n"
    if config['target_groups']:
        for group in config['target_groups']:
            topic = f" (тема {group['topic_id']})" if group.get('topic_id') else ""
            source_names = []
            for source_id in group.get('source_ids', []):
                source = next((s for s in config['source_groups'] if s['id'] == source_id), None)
                if source:
                    source_names.append(source['name'])
            
            sources_text = f" → {', '.join(source_names)}" if source_names else " → ⚠️ нет привязок"
            text += f"• {group['name']}{topic}{sources_text} (`{group['id']}`)\n"
    else:
        text += "• Нет целевых групп\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить исходную группу", callback_data="add_source")],
        [InlineKeyboardButton("➕ Добавить целевую группу", callback_data="add_target")],
        [InlineKeyboardButton("➕ Привязать группы", callback_data="link_groups")],
        [InlineKeyboardButton("🗑 Удалить группу", callback_data="remove_group")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    
    if update.callback_query:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return SELECT_GROUP_TYPE

# ===== ДОБАВЛЕНИЕ ИСХОДНОЙ ГРУППЫ =====
async def add_source_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления исходной группы"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['current_chat_id'] = update.effective_chat.id
    context.user_data['current_chat_name'] = update.effective_chat.title or f"Чат {update.effective_chat.id}"
    
    await query.edit_message_text(
        f"📝 **Добавление исходной группы**\n\n"
        f"Текущий чат: **{context.user_data['current_chat_name']}**\n"
        f"ID: `{context.user_data['current_chat_id']}`\n\n"
        f"Введите название для этой группы (или отправьте /cancel для отмены):",
        parse_mode="Markdown"
    )
    return ADD_SOURCE_GROUP_NAME

async def add_source_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает название и добавляет исходную группу"""
    group_name = update.message.text.strip()
    chat_id = context.user_data['current_chat_id']
    
    existing = next((g for g in config['source_groups'] if g['id'] == chat_id), None)
    
    if existing:
        await update.message.reply_text(
            f"❌ Эта группа уже добавлена как '{existing['name']}'!\n"
            f"Используйте /settings для управления группами."
        )
    else:
        config['source_groups'].append({
            'id': chat_id,
            'name': group_name
        })
        save_config(config)
        
        await update.message.reply_text(
            f"✅ Исходная группа **{group_name}** успешно добавлена!\n"
            f"ID: `{chat_id}`",
            parse_mode="Markdown"
        )
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📁 Статистика файлом", callback_data="stats_file")],
        [InlineKeyboardButton("⚙️ Настройка групп", callback_data="group_settings")],
        [InlineKeyboardButton("🔒 Закрыть админ панель", callback_data="close_admin")]
    ]
    await update.message.reply_text(
        "🔧 Панель администратора\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_ACTION

# ===== ДОБАВЛЕНИЕ ЦЕЛЕВОЙ ГРУППЫ =====
async def add_target_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления целевой группы"""
    query = update.callback_query
    await query.answer()
    
    if not config['source_groups']:
        await query.edit_message_text(
            "❌ **Сначала добавьте исходную группу!**\n\n"
            "Исходная группа - это чат, откуда будут отправляться задания.\n"
            "Добавьте её через кнопку '➕ Добавить исходную группу'",
            parse_mode="Markdown"
        )
        await show_group_settings(update, context)
        return SELECT_GROUP_TYPE
    
    context.user_data['current_chat_id'] = update.effective_chat.id
    context.user_data['current_chat_name'] = update.effective_chat.title or f"Чат {update.effective_chat.id}"
    
    # Создаем клавиатуру для выбора нескольких исходных групп
    keyboard = []
    for group in config['source_groups']:
        keyboard.append([InlineKeyboardButton(
            f"📤 {group['name']}",
            callback_data=f"toggle_source_{group['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("✅ Готово", callback_data="finish_source_selection"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_target")
    ])
    
    if 'selected_sources' not in context.user_data:
        context.user_data['selected_sources'] = []
    
    await query.edit_message_text(
        f"📝 **Добавление целевой группы**\n\n"
        f"Текущий чат: **{context.user_data['current_chat_name']}**\n"
        f"ID: `{context.user_data['current_chat_id']}`\n\n"
        f"**Выберите исходные группы для привязки**\n"
        f"(можно выбрать несколько)\n\n"
        f"Выбрано: {len(context.user_data['selected_sources'])} групп",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADD_TARGET_GROUP_SELECT

async def toggle_source_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмечает/снимает выбор исходной группы"""
    query = update.callback_query
    await query.answer()
    
    source_id = int(query.data.split('_')[-1])
    
    if source_id in context.user_data['selected_sources']:
        context.user_data['selected_sources'].remove(source_id)
    else:
        context.user_data['selected_sources'].append(source_id)
    
    keyboard = []
    for group in config['source_groups']:
        mark = "✅ " if group['id'] in context.user_data['selected_sources'] else ""
        keyboard.append([InlineKeyboardButton(
            f"{mark}📤 {group['name']}",
            callback_data=f"toggle_source_{group['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("✅ Готово", callback_data="finish_source_selection"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_target")
    ])
    
    await query.edit_message_text(
        f"📝 **Добавление целевой группы**\n\n"
        f"Текущий чат: **{context.user_data['current_chat_name']}**\n"
        f"ID: `{context.user_data['current_chat_id']}`\n\n"
        f"**Выберите исходные группы для привязки**\n"
        f"(можно выбрать несколько)\n\n"
        f"Выбрано: {len(context.user_data['selected_sources'])} групп",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADD_TARGET_GROUP_SELECT

async def finish_source_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершает выбор исходных групп"""
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get('selected_sources'):
        await query.answer("⚠️ Выберите хотя бы одну исходную группу!", show_alert=True)
        return ADD_TARGET_GROUP_SELECT
    
    await query.edit_message_text(
        f"📝 **Добавление целевой группы**\n\n"
        f"Исходные группы выбраны: {len(context.user_data['selected_sources'])}\n"
        f"Текущий чат: **{context.user_data['current_chat_name']}**\n\n"
        f"Введите название для целевой группы\n"
        f"Если есть ID темы, добавьте его через пробел:\n"
        f"`Название` - если без темы\n"
        f"`Название 123` - если есть тема (123 - ID темы)\n\n"
        f"Или отправьте /cancel для отмены",
        parse_mode="Markdown"
    )
    return ADD_TARGET_GROUP_NAME

async def add_target_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает название и добавляет целевую группу"""
    text = update.message.text.strip()
    chat_id = context.user_data['current_chat_id']
    selected_sources = context.user_data.get('selected_sources', [])
    
    if not selected_sources:
        await update.message.reply_text("❌ Ошибка: не выбраны исходные группы")
        return SELECT_GROUP_TYPE
    
    parts = text.split(' ', 1)
    group_name = parts[0]
    topic_id = None
    
    if len(parts) > 1:
        try:
            topic_id = int(parts[1])
        except ValueError:
            group_name = text
    
    existing = next(
        (g for g in config['target_groups'] 
         if g['id'] == chat_id and g.get('topic_id') == topic_id),
        None
    )
    
    if existing:
        source_names = []
        for source_id in existing.get('source_ids', []):
            source = next((s for s in config['source_groups'] if s['id'] == source_id), None)
            if source:
                source_names.append(source['name'])
        
        await update.message.reply_text(
            f"❌ Эта группа уже добавлена как целевая!\n"
            f"Название: {existing['name']}\n"
            f"Привязана к: {', '.join(source_names)}\n"
            f"Используйте /settings для управления группами."
        )
    else:
        source_names = []
        for source_id in selected_sources:
            source = next((s for s in config['source_groups'] if s['id'] == source_id), None)
            if source:
                source_names.append(source['name'])
        
        target_group = {
            'id': chat_id,
            'name': group_name,
            'source_ids': selected_sources,
            'topic_id': topic_id
        }
        config['target_groups'].append(target_group)
        save_config(config)
        
        topic_text = f" (тема {topic_id})" if topic_id else ""
        await update.message.reply_text(
            f"✅ Целевая группа **{group_name}**{topic_text} успешно добавлена!\n"
            f"Привязана к исходным группам: **{', '.join(source_names)}**\n"
            f"ID: `{chat_id}`",
            parse_mode="Markdown"
        )
    
    context.user_data.pop('selected_sources', None)
    context.user_data.pop('current_chat_id', None)
    context.user_data.pop('current_chat_name', None)
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📁 Статистика файлом", callback_data="stats_file")],
        [InlineKeyboardButton("⚙️ Настройка групп", callback_data="group_settings")],
        [InlineKeyboardButton("🔒 Закрыть админ панель", callback_data="close_admin")]
    ]
    await update.message.reply_text(
        "🔧 Панель администратора\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_ACTION

async def cancel_add_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена добавления целевой группы"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop('selected_sources', None)
    context.user_data.pop('current_chat_id', None)
    context.user_data.pop('current_chat_name', None)
    
    await query.edit_message_text("❌ Добавление целевой группы отменено")
    await show_group_settings(update, context)
    return SELECT_GROUP_TYPE

# ===== ПРИВЯЗКА ГРУПП =====
async def link_groups_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало привязки существующих групп"""
    query = update.callback_query
    await query.answer()
    
    if not config['source_groups'] or not config['target_groups']:
        await query.edit_message_text(
            "❌ **Нужны и исходные, и целевые группы!**\n\n"
            "Сначала добавьте группы через соответствующие кнопки.",
            parse_mode="Markdown"
        )
        await show_group_settings(update, context)
        return SELECT_GROUP_TYPE
    
    keyboard = []
    for target in config['target_groups']:
        topic = f" (тема {target['topic_id']})" if target.get('topic_id') else ""
        keyboard.append([InlineKeyboardButton(
            f"📥 {target['name']}{topic}",
            callback_data=f"link_target_{target['id']}_{target.get('topic_id', 0)}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="group_settings")])
    
    await query.edit_message_text(
        "🔗 **Привязка групп**\n\n"
        "Выберите **целевую группу**, к которой хотите привязать исходные:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_MULTIPLE_SOURCES

async def select_target_for_linking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор целевой группы для привязки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    target_id = int(data[2])
    
    # ИСПРАВЛЕНИЕ: обрабатываем 'None' правильно
    topic_id = None
    if len(data) > 3:
        topic_value = data[3]
        if topic_value not in ('None', '0'):
            try:
                topic_id = int(topic_value)
            except ValueError:
                topic_id = None
    
    target_group = next(
        (t for t in config['target_groups'] 
         if t['id'] == target_id and t.get('topic_id') == topic_id),
        None
    )
    
    if not target_group:
        await query.edit_message_text("❌ Целевая группа не найдена!")
        return SELECT_GROUP_TYPE
    
    context.user_data['linking_target'] = {
        'id': target_id,
        'topic_id': topic_id,
        'name': target_group['name']
    }
    
    keyboard = []
    for source in config['source_groups']:
        is_linked = source['id'] in target_group.get('source_ids', [])
        mark = "✅ " if is_linked else ""
        keyboard.append([InlineKeyboardButton(
            f"{mark}📤 {source['name']}",
            callback_data=f"toggle_link_{source['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("✅ Сохранить привязки", callback_data="save_links"),
        InlineKeyboardButton("❌ Отмена", callback_data="group_settings")
    ])
    
    if 'selected_links' not in context.user_data:
        context.user_data['selected_links'] = target_group.get('source_ids', [])
    
    await query.edit_message_text(
        f"🔗 **Привязка к целевой группе**\n\n"
        f"Целевая группа: **{target_group['name']}**\n\n"
        f"**Выберите исходные группы для привязки**\n"
        f"(можно выбрать несколько)\n\n"
        f"Выбрано: {len(context.user_data['selected_links'])} групп",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_MULTIPLE_SOURCES

async def toggle_link_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмечает/снимает выбор исходной группы для привязки"""
    query = update.callback_query
    await query.answer()
    
    source_id = int(query.data.split('_')[-1])
    
    if source_id in context.user_data['selected_links']:
        context.user_data['selected_links'].remove(source_id)
    else:
        context.user_data['selected_links'].append(source_id)
    
    keyboard = []
    for source in config['source_groups']:
        mark = "✅ " if source['id'] in context.user_data['selected_links'] else ""
        keyboard.append([InlineKeyboardButton(
            f"{mark}📤 {source['name']}",
            callback_data=f"toggle_link_{source['id']}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("✅ Сохранить привязки", callback_data="save_links"),
        InlineKeyboardButton("❌ Отмена", callback_data="group_settings")
    ])
    
    await query.edit_message_text(
        f"🔗 **Привязка к целевой группе**\n\n"
        f"Целевая группа: **{context.user_data['linking_target']['name']}**\n\n"
        f"**Выберите исходные группы для привязки**\n"
        f"(можно выбрать несколько)\n\n"
        f"Выбрано: {len(context.user_data['selected_links'])} групп",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_MULTIPLE_SOURCES

async def save_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет привязки групп"""
    query = update.callback_query
    await query.answer()
    
    target_info = context.user_data.get('linking_target')
    selected_sources = context.user_data.get('selected_links', [])
    
    if not target_info:
        await query.edit_message_text("❌ Ошибка: не выбрана целевая группа")
        return SELECT_GROUP_TYPE
    
    for target in config['target_groups']:
        if target['id'] == target_info['id'] and target.get('topic_id') == target_info['topic_id']:
            target['source_ids'] = selected_sources
            break
    
    save_config(config)
    
    source_names = []
    for source_id in selected_sources:
        source = next((s for s in config['source_groups'] if s['id'] == source_id), None)
        if source:
            source_names.append(source['name'])
    
    await query.edit_message_text(
        f"✅ **Привязки сохранены!**\n\n"
        f"Целевая группа **{target_info['name']}**\n"
        f"привязана к исходным группам:\n"
        f"{chr(10).join(['• ' + name for name in source_names]) if source_names else '• Нет привязок'}",
        parse_mode="Markdown"
    )
    
    context.user_data.pop('linking_target', None)
    context.user_data.pop('selected_links', None)
    
    await show_group_settings(update, context)
    return SELECT_GROUP_TYPE

# ===== УДАЛЕНИЕ ГРУПП =====
async def remove_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало удаления группы"""
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    
    if config['source_groups']:
        keyboard.append([InlineKeyboardButton("📤 ИСХОДНЫЕ ГРУППЫ:", callback_data="ignore")])
        for group in config['source_groups']:
            keyboard.append([InlineKeyboardButton(
                f"🗑 {group['name']}",
                callback_data=f"remove_source_{group['id']}"
            )])
    
    if config['target_groups']:
        if keyboard:
            keyboard.append([])
        keyboard.append([InlineKeyboardButton("📥 ЦЕЛЕВЫЕ ГРУППЫ:", callback_data="ignore")])
        for group in config['target_groups']:
            topic = f" (тема {group['topic_id']})" if group.get('topic_id') else ""
            source_names = []
            for source_id in group.get('source_ids', []):
                source = next((s for s in config['source_groups'] if s['id'] == source_id), None)
                if source:
                    source_names.append(source['name'])
            
            sources_text = f" → {', '.join(source_names)}" if source_names else ""
            
            # ИСПРАВЛЕНИЕ: используем строку 'None' вместо 0
            topic_value = group.get('topic_id')
            if topic_value is None:
                topic_str = 'None'
            else:
                topic_str = str(topic_value)
            
            keyboard.append([InlineKeyboardButton(
                f"🗑 {group['name']}{topic}{sources_text}",
                callback_data=f"remove_target_{group['id']}_{topic_str}"
            )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="group_settings")])
    
    await query.edit_message_text(
        "🗑 **Удаление группы**\n\nВыберите группу для удаления:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM_REMOVE_GROUP

async def confirm_remove_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления группы"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    
    if data[1] == "source":
        group_id = int(data[2])
        group = next((g for g in config['source_groups'] if g['id'] == group_id), None)
        
        if group:
            config['source_groups'] = [g for g in config['source_groups'] if g['id'] != group_id]
            
            # Удаляем эту исходную группу из привязок целевых групп
            for target in config['target_groups']:
                if group_id in target.get('source_ids', []):
                    target['source_ids'].remove(group_id)
            
            save_config(config)
            
            await query.edit_message_text(f"✅ Исходная группа '{group['name']}' удалена!")
    
    elif data[1] == "target":
        group_id = int(data[2])
        
        # ИСПРАВЛЕНИЕ: проверяем наличие и значение topic_id
        topic_id = None
        if len(data) > 3:
            topic_value = data[3]
            if topic_value not in ('None', '0'):
                try:
                    topic_id = int(topic_value)
                except ValueError:
                    topic_id = None
        
        group = next(
            (g for g in config['target_groups'] 
             if g['id'] == group_id and g.get('topic_id') == topic_id),
            None
        )
        
        if group:
            config['target_groups'] = [
                t for t in config['target_groups'] 
                if not (t['id'] == group_id and t.get('topic_id') == topic_id)
            ]
            save_config(config)
            
            topic_text = f" (тема {topic_id})" if topic_id else ""
            await query.edit_message_text(f"✅ Целевая группа '{group['name']}'{topic_text} удалена!")
    
    await show_group_settings(update, context)
    return SELECT_GROUP_TYPE

# ===== SMS СИСТЕМА =====
async def start_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс создания SMS задания"""
    current_chat_id = update.effective_chat.id
    connections = check_group_connections(current_chat_id)
    
    if not connections['is_source']:
        await update.message.reply_text("❌ Эта команда доступна только в исходных группах")
        return ConversationHandler.END

    if not connections['has_connections']:
        await update.message.reply_text(
            "❌ У этой исходной группы нет привязанных целевых групп!\n"
            "Используйте /settings чтобы добавить привязки."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Отправьте шаблон SMS задания:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel_sms")]])
    )
    return 10

async def handle_sms_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текст SMS задания и отправляет его во все целевые группы"""
    sms_id = update.message.message_id
    sms_text = update.message.text
    
    current_chat_id = update.effective_chat.id
    connections = check_group_connections(current_chat_id)

    sent_count = 0
    for target in connections['connected_groups']:
        try:
            keyboard = [[InlineKeyboardButton("✅ Я выполню", callback_data=f"do_sms_{sms_id}")]]
            await context.bot.send_message(
                chat_id=target['id'],
                text=f"{sms_text}",
                message_thread_id=target.get('topic_id'),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Ошибка отправки в группу {target['name']}: {e}")

    sms_sessions[sms_id] = {
        'text': sms_text,
        'status': 'active',
        'user_data': None
    }
    
    add_task_to_history(sms_id, 'sms', sms_text)

    await update.message.reply_text(f"✅ Шаблон отправлен в {sent_count} групп!")
    return ConversationHandler.END

async def start_sms_execution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие кнопки 'Я выполню' для SMS"""
    query = update.callback_query
    await query.answer()

    sms_id = int(query.data.split('_')[-1])
    if sms_id not in sms_sessions or sms_sessions[sms_id]['status'] != 'active':
        await query.answer("⚠ Это SMS задание уже взято", show_alert=True)
        return

    user = query.from_user
    user_mention = f"@{user.username}" if user.username else user.first_name

    sms_sessions[sms_id]['status'] = 'in_progress'
    sms_sessions[sms_id]['user_data'] = {
        'id': user.id,
        'mention': user_mention
    }

    update_user_stats(user.id, user.username or '', user.first_name or '', 'sms', 'take')

    await query.edit_message_text(
        text=f"{query.message.text}\n\n👤 Выполняет: {user_mention}",
        reply_markup=None
    )

    chat_id = query.message.chat_id
    target_group = next((t for t in config['target_groups'] if t['id'] == chat_id), None)
    
    if target_group:
        for source_id in target_group.get('source_ids', []):
            try:
                await context.bot.send_message(
                    chat_id=source_id,
                    text=f"ℹ️ SMS шаблон взят воркером {user_mention}\nОжидайте скриншот выполнения..."
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления в исходную группу: {e}")

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"{user_mention}, отправьте скриншот выполнения SMS задания",
        message_thread_id=query.message.message_thread_id
    )

async def handle_sms_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает скриншот от пользователя для SMS задания"""
    try:
        user_id = update.effective_user.id

        sms_id = None
        for k, v in sms_sessions.items():
            if v['status'] == 'in_progress' and v['user_data'] and v['user_data']['id'] == user_id:
                sms_id = k
                break

        if not sms_id:
            return

        if update.message.photo:
            photo = update.message.photo[-1]
            caption = update.message.caption or ""

            chat_id = update.effective_chat.id
            target_group = next((t for t in config['target_groups'] if t['id'] == chat_id), None)
            
            if target_group:
                for source_id in target_group.get('source_ids', []):
                    try:
                        await context.bot.send_photo(
                            chat_id=source_id,
                            photo=photo.file_id,
                            caption=f"📱 Скриншот выполнения SMS задания от {sms_sessions[sms_id]['user_data']['mention']}\n{caption}" if caption else f"📱 Скриншот выполнения SMS задания от {sms_sessions[sms_id]['user_data']['mention']}"
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки скриншота в исходную группу: {e}")

            sms_sessions[sms_id]['status'] = 'completed'
            update_user_stats(user_id, update.effective_user.username or '', update.effective_user.first_name or '', 'sms', 'complete')
            add_task_to_history(sms_id, 'sms', sms_sessions[sms_id]['text'], user_id, 'completed')

            await update.message.reply_text("✅ Скриншот отправлен! Спасибо за выполнение задания.")

            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo.file_id,
                caption=f"✅ SMS задание выполнено {sms_sessions[sms_id]['user_data']['mention']}!",
                message_thread_id=target_group.get('topic_id') if target_group else None
            )

    except Exception as e:
        logger.error(f"Ошибка в handle_sms_screenshot: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при отправке скриншота. Попробуйте еще раз.")

async def cancel_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет создание SMS задания"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Создание SMS задания отменено")
    return ConversationHandler.END

# ===== ТЕСТОВАЯ СИСТЕМА =====
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс создания теста"""
    current_chat_id = update.effective_chat.id
    connections = check_group_connections(current_chat_id)
    
    if not connections['is_source']:
        await update.message.reply_text("❌ Эта команда доступна только в исходных группах")
        return ConversationHandler.END

    if not connections['has_connections']:
        await update.message.reply_text(
            "❌ У этой исходной группы нет привязанных целевых групп!\n"
            "Используйте /settings чтобы добавить привязки."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Отправьте текст тестового задания:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel_test")]])
    )
    return 20

async def handle_test_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текст теста и отправляет его во все целевые группы"""
    test_id = update.message.message_id
    test_text = update.message.text
    
    current_chat_id = update.effective_chat.id
    connections = check_group_connections(current_chat_id)

    sent_count = 0
    for target in connections['connected_groups']:
        try:
            keyboard = [[InlineKeyboardButton("✅ Я выполню", callback_data=f"do_test_{test_id}")]]
            await context.bot.send_message(
                chat_id=target['id'],
                text=f"🛑 ТЕСТ 🛑\n\n{test_text}",
                message_thread_id=target.get('topic_id'),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Ошибка отправки в группу {target['name']}: {e}")

    test_sessions[test_id] = {
        'text': test_text,
        'status': 'active',
        'user_data': None
    }
    
    add_task_to_history(test_id, 'test', test_text)

    await update.message.reply_text(f"✅ Шаблон отправлен в {sent_count} групп!")
    return ConversationHandler.END

async def start_test_execution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатие кнопки 'Я выполню' для теста"""
    query = update.callback_query
    await query.answer()

    test_id = int(query.data.split('_')[-1])
    if test_id not in test_sessions or test_sessions[test_id]['status'] != 'active':
        await query.answer("⚠ Этот тест уже завершен", show_alert=True)
        return

    user = query.from_user
    user_mention = f"@{user.username}" if user.username else user.first_name

    test_sessions[test_id]['status'] = 'in_progress'
    test_sessions[test_id]['user_data'] = {
        'id': user.id,
        'mention': user_mention,
        'photo': None,
        'number': None
    }

    update_user_stats(user.id, user.username or '', user.first_name or '', 'test', 'take')

    await query.edit_message_text(
        text=f"{query.message.text}\n\n👤 Выполняет: {user_mention}",
        reply_markup=None
    )

    chat_id = query.message.chat_id
    target_group = next((t for t in config['target_groups'] if t['id'] == chat_id), None)
    
    if target_group:
        for source_id in target_group.get('source_ids', []):
            try:
                await context.bot.send_message(
                    chat_id=source_id,
                    text=f"ℹ️ Тестовый шаблон взят воркером {user_mention}\nОжидайте скриншот выполнения..."
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления в исходную группу: {e}")

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"{user_mention}, для выполнения отправьте:\n1. Скриншот выполнения (можно с 4 цифрами номера в подписи)\n2. Если цифр нет в подписи - отправьте их отдельно",
        message_thread_id=query.message.message_thread_id
    )

async def handle_test_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает скриншот и номер от пользователя для теста"""
    try:
        user_id = update.effective_user.id

        test_id = None
        for k, v in test_sessions.items():
            if v['status'] == 'in_progress' and v['user_data'] and v['user_data']['id'] == user_id:
                test_id = k
                break

        if not test_id:
            return

        test = test_sessions[test_id]

        if update.message.photo:
            photo = update.message.photo[-1]
            test['user_data']['photo'] = photo.file_id

            caption = update.message.caption or ""
            match = re.search(r'\d{4}', caption)
            
            if match:
                four_digits = match.group()
                test['user_data']['number'] = four_digits

                keyboard = [
                    [InlineKeyboardButton("✅ Тест пройден", callback_data=f"test_passed_{test_id}")],
                    [InlineKeyboardButton("❌ Тест не пройден", callback_data=f"test_failed_{test_id}")]
                ]

                chat_id = update.effective_chat.id
                target_group = next((t for t in config['target_groups'] if t['id'] == chat_id), None)
                
                if target_group:
                    for source_id in target_group.get('source_ids', []):
                        try:
                            await context.bot.send_photo(
                                chat_id=source_id,
                                photo=test['user_data']['photo'],
                                caption=(
                                    f"🛑 Проверка теста\n\n"
                                    f"Номер: {test['user_data']['number']}\n"
                                    f"От: {test['user_data']['mention']}"
                                ),
                                reply_markup=InlineKeyboardMarkup(keyboard)
                            )
                        except Exception as e:
                            logger.error(f"Ошибка отправки в исходную группу: {e}")

                await update.message.reply_text("✅ Данные отправлены на проверку!")
            else:
                await update.message.reply_text("✅ Скриншот получен! Теперь отправьте 4 цифры номера.")

        elif update.message.text and len(update.message.text) == 4 and update.message.text.isdigit():
            test['user_data']['number'] = update.message.text

            if not test['user_data']['photo']:
                await update.message.reply_text("❌ Сначала отправьте скриншот!")
                return

            keyboard = [
                [InlineKeyboardButton("✅ Тест пройден", callback_data=f"test_passed_{test_id}")],
                [InlineKeyboardButton("❌ Тест не пройден", callback_data=f"test_failed_{test_id}")]
            ]

            chat_id = update.effective_chat.id
            target_group = next((t for t in config['target_groups'] if t['id'] == chat_id), None)
            
            if target_group:
                for source_id in target_group.get('source_ids', []):
                    try:
                        await context.bot.send_photo(
                            chat_id=source_id,
                            photo=test['user_data']['photo'],
                            caption=(
                                f"🛑 Проверка теста\n\n"
                                f"Номер: {test['user_data']['number']}\n"
                                f"От: {test['user_data']['mention']}"
                            ),
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки в исходную группу: {e}")

            await update.message.reply_text("✅ Данные отправлены на проверку!")

    except Exception as e:
        logger.error(f"Ошибка в handle_test_data: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при обработке данных. Попробуйте еще раз.")

async def handle_test_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает результат проверки теста админом"""
    try:
        query = update.callback_query
        await query.answer()

        action = query.data.split('_')[1]
        test_id = int(query.data.split('_')[-1])
        
        if test_id not in test_sessions:
            await query.answer("⚠ Тест не найден", show_alert=True)
            return

        test = test_sessions[test_id]
        user_mention = test['user_data']['mention']
        user_id = test['user_data']['id']

        if action == "passed":
            test['status'] = 'completed'
            update_user_stats(user_id, '', '', 'test', 'complete')
            add_task_to_history(test_id, 'test', test['text'], user_id, 'completed')
            
            source_chat_id = query.message.chat_id
            target_groups = [t for t in config['target_groups'] if source_chat_id in t.get('source_ids', [])]
            
            for target in target_groups:
                try:
                    await context.bot.send_photo(
                        chat_id=target['id'],
                        photo=test['user_data']['photo'],
                        caption=f"✅ Тест успешно пройден {user_mention}!",
                        message_thread_id=target.get('topic_id')
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления в группу {target['name']}: {e}")
        else:
            update_user_stats(user_id, '', '', 'test', 'fail')
            add_task_to_history(test_id, 'test', test['text'], user_id, 'failed')
            
            source_chat_id = query.message.chat_id
            target_groups = [t for t in config['target_groups'] if source_chat_id in t.get('source_ids', [])]
            
            for target in target_groups:
                try:
                    await context.bot.send_photo(
                        chat_id=target['id'],
                        photo=test['user_data']['photo'],
                        caption=f"❌ Тест не пройден {user_mention}",
                        message_thread_id=target.get('topic_id')
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления в группу {target['name']}: {e}")

            keyboard = [[InlineKeyboardButton("✅ Я выполню", callback_data=f"do_test_{test_id}")]]
            for target in target_groups:
                try:
                    await context.bot.send_message(
                        chat_id=target['id'],
                        text=f"🛑 ТЕСТ 🛑\n\n{test['text']}",
                        message_thread_id=target.get('topic_id'),
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки в группу {target['name']}: {e}")
            
            test_sessions[test_id]['status'] = 'active'
            test_sessions[test_id]['user_data'] = None

        await query.message.edit_reply_markup(reply_markup=None)

    except Exception as e:
        logger.error(f"Ошибка в handle_test_verification: {e}", exc_info=True)
        await query.answer("⚠ Произошла ошибка", show_alert=True)

async def cancel_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет создание теста"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Создание теста отменено")
    return ConversationHandler.END

# ===== УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ФОТО =====
async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Универсальный обработчик всех фото из рабочих чатов"""
    try:
        user_id = update.effective_user.id
        
        is_target_group = any(
            update.effective_chat.id == target['id'] 
            for target in config['target_groups']
        )
        
        if not is_target_group:
            return
        
        sms_id = None
        for k, v in sms_sessions.items():
            if v['status'] == 'in_progress' and v['user_data'] and v['user_data']['id'] == user_id:
                sms_id = k
                break
        
        test_id = None
        for k, v in test_sessions.items():
            if v['status'] == 'in_progress' and v['user_data'] and v['user_data']['id'] == user_id:
                test_id = k
                break
        
        if sms_id:
            await handle_sms_screenshot(update, context)
        elif test_id:
            await handle_test_data(update, context)
        else:
            await update.message.reply_text("❌ У вас нет активных заданий")
            
    except Exception as e:
        logger.error(f"Ошибка в handle_photo_message: {e}", exc_info=True)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

# ===== ОБРАБОТКА ЗАВЕРШЕНИЯ =====
def signal_handler(sig, frame):
    """Обработчик сигналов завершения"""
    print("\n🛑 Получен сигнал завершения. Останавливаю бота...")
    # Принудительно удаляем PID файл
    try:
        if os.path.exists(PID_FILE):
            os.unlink(PID_FILE)
            print("🧹 PID файл удален")
    except:
        pass
    sys.exit(0)

# ===== ЗАПУСК БОТА =====
def main() -> None:
    # Принудительно очищаем старые lock файлы
    force_cleanup()
    
    # Проверка на единственный экземпляр
    if not check_single_instance():
        print("\n💡 Если вы уверены, что бот не запущен, выполните:")
        print(f"  rm {PID_FILE}")
        print("Или используйте принудительную очистку:")
        print("  python -c \"import os; [os.unlink(f) for f in ['bot.pid', 'bot.lock'] if os.path.exists(f)]\"")
        sys.exit(1)
    
    # Устанавливаем обработчик сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Обработчик тестов
    test_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('test', start_test)],
        states={
            20: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_test_text)],
        },
        fallbacks=[CallbackQueryHandler(cancel_test, pattern="^cancel_test$")],
    )

    # Обработчик SMS заданий
    sms_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('sms', start_sms)],
        states={
            10: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sms_text)],
        },
        fallbacks=[CallbackQueryHandler(cancel_sms, pattern="^cancel_sms$")],
    )

    # Обработчик настроек
    settings_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('settings', settings_menu)],
        states={
            SELECT_ACTION: [
                CallbackQueryHandler(settings_callback, pattern="^(stats|stats_file|group_settings|close_admin|back_to_main)$"),
            ],
            SELECT_GROUP_TYPE: [
                CallbackQueryHandler(settings_callback, pattern="^(stats|stats_file|group_settings|close_admin|back_to_main)$"),
                CallbackQueryHandler(add_source_group_start, pattern="^add_source$"),
                CallbackQueryHandler(add_target_group_start, pattern="^add_target$"),
                CallbackQueryHandler(link_groups_start, pattern="^link_groups$"),
                CallbackQueryHandler(remove_group_start, pattern="^remove_group$"),
            ],
            ADD_SOURCE_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_group_name)],
            ADD_TARGET_GROUP_SELECT: [
                CallbackQueryHandler(toggle_source_selection, pattern="^toggle_source_"),
                CallbackQueryHandler(finish_source_selection, pattern="^finish_source_selection$"),
                CallbackQueryHandler(cancel_add_target, pattern="^cancel_add_target$"),
            ],
            ADD_TARGET_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_target_group_name)],
            SELECT_MULTIPLE_SOURCES: [
                CallbackQueryHandler(select_target_for_linking, pattern="^link_target_"),
                CallbackQueryHandler(toggle_link_selection, pattern="^toggle_link_"),
                CallbackQueryHandler(save_links, pattern="^save_links$"),
                CallbackQueryHandler(show_group_settings, pattern="^group_settings$"),
            ],
            CONFIRM_REMOVE_GROUP: [
                CallbackQueryHandler(confirm_remove_group, pattern="^remove_(source|target)_"),
                CallbackQueryHandler(show_group_settings, pattern="^group_settings$"),
            ],
        },
        fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("id", show_id))
    application.add_handler(CommandHandler("warn", warn_workers))
    application.add_handler(test_conv_handler)
    application.add_handler(sms_conv_handler)
    application.add_handler(settings_conv_handler)
    application.add_handler(CallbackQueryHandler(start_test_execution, pattern="^do_test_"))
    application.add_handler(CallbackQueryHandler(start_sms_execution, pattern="^do_sms_"))
    application.add_handler(CallbackQueryHandler(handle_test_verification, pattern="^test_(passed|failed)_"))

    if config['target_groups']:
        target_group_ids = [t['id'] for t in config['target_groups']]
        application.add_handler(MessageHandler(
            filters.Chat(chat_id=target_group_ids) & filters.PHOTO,
            handle_photo_message
        ))

        application.add_handler(MessageHandler(
            filters.Chat(chat_id=target_group_ids) & filters.TEXT & ~filters.COMMAND,
            handle_test_data
        ))

    application.add_error_handler(error_handler)

    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    print("✅ Бот успешно запущен! Нажмите Ctrl+C для остановки.")
    
    try:
        application.run_polling()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
    finally:
        # Очищаем PID файл при выходе
        try:
            if os.path.exists(PID_FILE):
                os.unlink(PID_FILE)
                print("🧹 PID файл очищен")
        except:
            pass
        print("👋 До свидания!")

if __name__ == "__main__":
    print("🚀 Запуск бота...")
    # Устанавливаем переменную окружения для Flask
    os.environ['FLASK_ENV'] = 'production'
    main()