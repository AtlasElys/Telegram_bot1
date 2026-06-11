import os
import zipfile
import tempfile
import shutil
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8637060105:AAHAxW7BjcUo4g6c2XobCgBcxHzDyQL8D7Y"  # Замените на свой токен
ADMIN_ID = 8103556115

bot = telebot.TeleBot(BOT_TOKEN)

# Хранилище данных пользователей
user_data = {}

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def extract_zip(zip_path, extract_to):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

def get_all_files(directory):
    all_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, directory)
            all_files.append(rel_path)
    return all_files

def split_into_archives(source_dir, output_dir, batch_size):
    files = get_all_files(source_dir)
    total_files = len(files)
    archives_info = []
    
    archive_num = 1
    for i in range(0, total_files, batch_size):
        batch_files = files[i:i + batch_size]
        archive_name = f"archive_{archive_num}.zip"
        archive_path = os.path.join(output_dir, archive_name)
        
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in batch_files:
                full_path = os.path.join(source_dir, file_path)
                zipf.write(full_path, file_path)
        
        archives_info.append({
            'path': archive_path,
            'name': archive_name,
            'count': len(batch_files)
        })
        archive_num += 1
    
    return archives_info, total_files

def create_master_archive(archives_paths, output_path):
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as master_zip:
        for archive_path in archives_paths:
            master_zip.write(archive_path, os.path.basename(archive_path))
    return output_path

def send_admin_report(user, total_files, num_archives, batch_size, send_method):
    user_tag = f"@{user.username}" if user.username else f"{user.first_name} (ID: {user.id})"
    
    report_text = (
        f"📊 Новый запрос архивации\n\n"
        f"👤 Кто: {user_tag}\n"
        f"📁 Всего файлов: {total_files}\n"
        f"📦 Архивов: {num_archives}\n"
        f"🔢 Файлов в архиве: {batch_size}\n"
        f"💾 Способ отправки: {send_method}"
    )
    
    try:
        bot.send_message(ADMIN_ID, report_text)
    except:
        pass

# ===== КЛАВИАТУРЫ =====

def get_cancel_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel"))
    return keyboard

def get_send_method_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📦 Вместе (один архив)", callback_data="send_together"),
        InlineKeyboardButton("📁 По отдельности", callback_data="send_separate")
    )
    return keyboard

# ===== ОБРАБОТЧИКИ КОМАНД =====

@bot.message_handler(commands=['start'])
def start(message):
    user_data[message.chat.id] = {'state': 'waiting_for_archive'}
    bot.send_message(
        message.chat.id,
        "📦 Привет! Отправьте мне ZIP архив с файлами и папками.\n\n"
        "Я найду все файлы внутри и предложу разбить их на архивы."
    )

@bot.message_handler(content_types=['document'])
def handle_archive(message):
    if user_data.get(message.chat.id, {}).get('state') != 'waiting_for_archive':
        bot.send_message(message.chat.id, "❌ Сначала отправьте /start")
        return
    
    if not message.document.file_name.endswith('.zip'):
        bot.send_message(message.chat.id, "❌ Пожалуйста, отправьте файл в формате .zip")
        return
    
    bot.send_message(message.chat.id, "⏳ Скачиваю и обрабатываю архив...")
    
    # Скачиваем файл
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    # Временные папки
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "input.zip")
    
    with open(zip_path, 'wb') as f:
        f.write(downloaded_file)
    
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir)
    extract_zip(zip_path, extract_dir)
    
    all_files = get_all_files(extract_dir)
    total_files = len(all_files)
    
    if total_files == 0:
        bot.send_message(message.chat.id, "❌ В архиве не найдено файлов!")
        shutil.rmtree(temp_dir)
        return
    
    user_data[message.chat.id].update({
        'temp_dir': temp_dir,
        'extract_dir': extract_dir,
        'total_files': total_files,
        'state': 'waiting_for_batch_size'
    })
    
    bot.send_message(
        message.chat.id,
        f"✅ Проверка завершена!\n\nВсего файлов: {total_files}\n\nСколько файлов в одном архиве?",
        reply_markup=get_cancel_keyboard()
    )

@bot.message_handler(func=lambda message: user_data.get(message.chat.id, {}).get('state') == 'waiting_for_batch_size')
def handle_batch_size(message):
    chat_id = message.chat.id
    data = user_data[chat_id]
    
    try:
        batch_size = int(message.text.strip())
        if batch_size <= 0:
            raise ValueError
    except ValueError:
        bot.send_message(chat_id, "❌ Введите положительное число! Например: 100")
        return
    
    total_files = data['total_files']
    extract_dir = data['extract_dir']
    
    archives_dir = tempfile.mkdtemp()
    
    bot.send_message(chat_id, f"⏳ Создаю архивы... (файлов: {total_files})")
    
    archives_info, total_files_count = split_into_archives(extract_dir, archives_dir, batch_size)
    num_archives = len(archives_info)
    
    user_data[chat_id].update({
        'archives_dir': archives_dir,
        'archives_info': archives_info,
        'batch_size': batch_size,
        'num_archives': num_archives,
        'state': 'waiting_for_send_method'
    })
    
    bot.send_message(
        chat_id,
        f"Всего: {total_files_count} файлов\nАрхивов: {num_archives} по {batch_size}\n\nОтправить вместе или отдельно?",
        reply_markup=get_send_method_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cancel_process(call):
    chat_id = call.message.chat.id
    data = user_data.get(chat_id, {})
    
    if 'temp_dir' in data and os.path.exists(data['temp_dir']):
        shutil.rmtree(data['temp_dir'])
    if 'archives_dir' in data and os.path.exists(data['archives_dir']):
        shutil.rmtree(data['archives_dir'])
    
    bot.edit_message_text("❌ Операция отменена.", chat_id, call.message.message_id)
    bot.answer_callback_query(call.id)
    user_data[chat_id] = {'state': 'waiting_for_archive'}

@bot.callback_query_handler(func=lambda call: call.data in ["send_together", "send_separate"])
def handle_send_method(call):
    chat_id = call.message.chat.id
    data = user_data.get(chat_id, {})
    
    if data.get('state') != 'waiting_for_send_method':
        bot.answer_callback_query(call.id, "Сначала отправьте архив")
        return
    
    archives_info = data['archives_info']
    total_files = data['total_files']
    batch_size = data['batch_size']
    num_archives = data['num_archives']
    archives_dir = data['archives_dir']
    
    bot.answer_callback_query(call.id)
    
    if call.data == "send_together":
        bot.edit_message_text("⏳ Создаю мастер-архив...", chat_id, call.message.message_id)
        
        master_zip_path = os.path.join(archives_dir, "all_archives.zip")
        archive_paths = [info['path'] for info in archives_info]
        create_master_archive(archive_paths, master_zip_path)
        
        with open(master_zip_path, 'rb') as f:
            bot.send_document(
                chat_id,
                f,
                caption=(
                    f"✅ Проверка завершена!\n\n"
                    f"Всего файлов: {total_files}\n"
                    f"🟢 Архивов: {num_archives}\n"
                    f"🟣 Количество в архиве: {batch_size}"
                )
            )
        
        bot.edit_message_text("✅ Архивы отправлены!", chat_id, call.message.message_id)
        
    else:  # send_separate
        bot.edit_message_text("⏳ Отправляю архивы...", chat_id, call.message.message_id)
        
        for i, archive_info in enumerate(archives_info, 1):
            with open(archive_info['path'], 'rb') as f:
                if i == num_archives:
                    bot.send_document(
                        chat_id,
                        f,
                        caption=(
                            f"✅ Проверка завершена!\n\n"
                            f"Всего файлов: {total_files}\n"
                            f"🟢 Архивов: {num_archives}\n"
                            f"🟣 Количество в архиве: {batch_size}"
                        )
                    )
                else:
                    bot.send_document(chat_id, f)
        
        bot.edit_message_text("✅ Все архивы отправлены!", chat_id, call.message.message_id)
    
    # Отправляем отчёт админу
    send_admin_report(
        user=call.from_user,
        total_files=total_files,
        num_archives=num_archives,
        batch_size=batch_size,
        send_method="Вместе (один архив)" if call.data == "send_together" else "По отдельности"
    )
    
    # Очищаем временные файлы
    if 'temp_dir' in data and os.path.exists(data['temp_dir']):
        shutil.rmtree(data['temp_dir'])
    if os.path.exists(archives_dir):
        shutil.rmtree(archives_dir)
    
    user_data[chat_id] = {'state': 'waiting_for_archive'}

# ===== ЗАПУСК =====
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()