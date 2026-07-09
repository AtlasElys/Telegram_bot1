import os
import json
import logging
import asyncio

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

TOKEN = "8580365803:AAGki0GmDR6bGPk8fzcwVy3NMh6IrgsCvb8"
OWNER_ID = 191402414

# Premium эмодзи ID
OWNER_EMOJI_ID = "5443038326535759644"  # эмодзи владельца

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

DATA_FILE = "channels_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"favorite_channel": None, "network_channels": []}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

APPROVE = "yes"
DECLINE = "no"

def post_buttons():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🦋 Бот", url="https://t.me/EclipsShopsBot"),
        InlineKeyboardButton("🦋 Переходник", url="https://t.me/EclipsMod"),
    ]])

def ask_buttons(chat_id, msg_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да", callback_data=f"{APPROVE}:{chat_id}:{msg_id}"),
        InlineKeyboardButton("❌ Нет", callback_data=f"{DECLINE}:{chat_id}:{msg_id}"),
    ]])

def sign(text):
    """Подпись с Premium-эмодзи и жирным текстом"""
    signature = (
        f'\n\n<tg-emoji emoji-id="{OWNER_EMOJI_ID}">👤</tg-emoji> '
        f'<b>Владелец — @EclipsOwner</b>'
    )
    return (text or "") + signature

async def start(update, context):
    await update.message.reply_text(
        "<b>🤖 Бот работает</b>\n\n"
        "<b>Команды:</b>\n"
        "/set_favorite ID — установить избранный канал\n"
        "/add ID — добавить канал в сеть\n"
        "/remove ID — удалить канал\n"
        "/list — список каналов\n"
        "/check ID — проверить доступ",
        parse_mode=ParseMode.HTML,
    )

async def check_channel(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("<b>❌ Укажи ID:</b> /check -1001234567890", parse_mode=ParseMode.HTML)
        return
    try:
        chat = await context.bot.get_chat(int(context.args[0]))
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        await update.message.reply_text(
            f"<b>✅ {chat.title}</b>\nID: <code>{chat.id}</code>\nСтатус: {member.status}",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await update.message.reply_text(f"<b>❌ Ошибка:</b> {e}", parse_mode=ParseMode.HTML)

async def add_channel(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("<b>❌ Укажи ID:</b> /add -1001234567890", parse_mode=ParseMode.HTML)
        return
    ch_id = int(context.args[0])
    data = load_data()
    if ch_id in data["network_channels"]:
        await update.message.reply_text("<b>⚠️ Уже в сети</b>", parse_mode=ParseMode.HTML)
        return
    try:
        chat = await context.bot.get_chat(ch_id)
        data["network_channels"].append(ch_id)
        save_data(data)
        await update.message.reply_text(f"<b>✅ Добавлен: {chat.title}</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"<b>❌ Ошибка:</b> {e}", parse_mode=ParseMode.HTML)

async def remove_channel(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("<b>❌ Укажи ID:</b> /remove -1001234567890", parse_mode=ParseMode.HTML)
        return
    ch_id = int(context.args[0])
    data = load_data()
    if ch_id in data["network_channels"]:
        data["network_channels"].remove(ch_id)
        save_data(data)
        await update.message.reply_text(f"<b>✅ Удалён: {ch_id}</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("<b>❌ Не найден</b>", parse_mode=ParseMode.HTML)

async def list_channels(update, context):
    data = load_data()
    fav = data.get("favorite_channel")
    net = data.get("network_channels", [])
    text = f"<b>🌟 Избранный:</b> {fav or 'нет'}\n\n<b>📢 Сеть ({len(net)}):</b>\n"
    for ch in net:
        try:
            chat = await context.bot.get_chat(ch)
            text += f"• {chat.title}\n"
        except:
            text += f"• {ch}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def set_favorite(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("<b>❌ Укажи ID:</b> /set_favorite -1001234567890", parse_mode=ParseMode.HTML)
        return
    ch_id = int(context.args[0])
    data = load_data()
    try:
        chat = await context.bot.get_chat(ch_id)
        data["favorite_channel"] = ch_id
        save_data(data)
        await update.message.reply_text(f"<b>✅ Избранный: {chat.title}</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"<b>❌ Ошибка:</b> {e}", parse_mode=ParseMode.HTML)

async def on_post(update, context):
    msg = update.channel_post
    if not msg:
        return
    
    data = load_data()
    fav = data.get("favorite_channel")
    
    if msg.chat_id != fav:
        return
    
    logger.info(f"📨 Пост #{msg.message_id}")
    
    # Получаем оригинальный текст
    original_text = msg.text or msg.caption or ""
    
    # Добавляем подпись с Premium-эмодзи
    new_text = sign(original_text)
    btns = post_buttons()
    
    try:
        if msg.text:
            await msg.edit_text(
                new_text,
                reply_markup=btns,
                parse_mode=ParseMode.HTML,
            )
        elif msg.caption or msg.photo or msg.video or msg.document or msg.audio or msg.animation or msg.voice:
            await msg.edit_caption(
                caption=new_text,
                reply_markup=btns,
                parse_mode=ParseMode.HTML,
            )
        else:
            await msg.edit_text(
                new_text,
                reply_markup=btns,
                parse_mode=ParseMode.HTML,
            )
        
        logger.info("✅ Отредактирован")
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования: {e}")
        # Если не получилось отредактировать — пробуем удалить и создать заново
        try:
            temp = await msg.copy(chat_id=fav)
            await msg.delete()
            if temp.text:
                await temp.edit_text(new_text, reply_markup=btns, parse_mode=ParseMode.HTML)
            else:
                await temp.edit_caption(caption=new_text, reply_markup=btns, parse_mode=ParseMode.HTML)
            msg = temp
            logger.info("✅ Пересоздан")
        except Exception as e2:
            logger.error(f"❌ Полная ошибка: {e2}")
            return
    
    # Отправляем запрос владельцу
    try:
        await context.bot.send_message(
            OWNER_ID,
            "<b>📢 Опубликовать пост во все каналы?</b>",
            reply_markup=ask_buttons(msg.chat_id, msg.message_id),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def on_approve(update, context):
    q = update.callback_query
    await q.answer()
    
    parts = q.data.split(":")
    action = parts[0]
    chat_id = int(parts[1]) if len(parts) > 1 else 0
    msg_id = int(parts[2]) if len(parts) > 2 else 0
    
    if action == DECLINE:
        await q.edit_message_text("<b>❌ Публикация отменена</b>", parse_mode=ParseMode.HTML)
        return
    
    await q.edit_message_text("<b>⏳ Публикую...</b>", parse_mode=ParseMode.HTML)
    
    data = load_data()
    net = data.get("network_channels", [])
    
    if not net:
        await q.message.reply_text("<b>⚠️ Сеть каналов пуста</b>", parse_mode=ParseMode.HTML)
        return
    
    ok = 0
    failed = []
    
    for ch in net:
        try:
            await context.bot.copy_message(
                chat_id=ch,
                from_chat_id=chat_id,
                message_id=msg_id,
                reply_markup=post_buttons(),  # Кнопки при копировании
            )
            ok += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"❌ {ch}: {e}")
            failed.append(ch)
    
    report = f"<b>✅ Готово!</b>\n📊 Опубликовано: {ok}/{len(net)}"
    if failed:
        report += "\n\n<b>❌ Ошибки в каналах:</b>\n"
        for ch in failed:
            report += f"• <code>{ch}</code>\n"
    
    await q.message.reply_text(report, parse_mode=ParseMode.HTML)

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_channel))
    app.add_handler(CommandHandler("remove", remove_channel))
    app.add_handler(CommandHandler("list", list_channels))
    app.add_handler(CommandHandler("set_favorite", set_favorite))
    app.add_handler(CommandHandler("check", check_channel))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, on_post))
    app.add_handler(CallbackQueryHandler(on_approve, pattern=f"^({APPROVE}|{DECLINE}):"))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
