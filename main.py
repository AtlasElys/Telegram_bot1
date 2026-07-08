import json
import logging
import asyncio
from typing import Dict, Any

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

# Данные прямо в коде
TOKEN = "8580365803:AAGki0GmDR6bGPk8fzcwVy3NMh6IrgsCvb8"
OWNER_ID = 191402414

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Данные ---
DATA_FILE = "channels_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"favorite_channel": None, "network_channels": []}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- Кнопки ---
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
    return (text or "") + "\n\n👤 <b>Владелец — @EclipsOwner</b>"

# --- Команды ---
async def start(update, context):
    await update.message.reply_text(
        "🤖 <b>Бот работает</b>\n\n"
        "/set_favorite ID\n/add ID\n/remove ID\n/list\n/check ID",
        parse_mode=ParseMode.HTML,
    )

async def check_channel(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("/check -1001234567890")
        return
    try:
        chat = await context.bot.get_chat(int(context.args[0]))
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        await update.message.reply_text(
            f"✅ <b>{chat.title}</b>\nID: <code>{chat.id}</code>\nСтатус: {member.status}",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def add_channel(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("/add -1001234567890")
        return
    ch_id = int(context.args[0])
    data = load_data()
    if ch_id in data["network_channels"]:
        await update.message.reply_text("⚠️ Уже в сети")
        return
    try:
        chat = await context.bot.get_chat(ch_id)
        data["network_channels"].append(ch_id)
        save_data(data)
        await update.message.reply_text(f"✅ <b>{chat.title}</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def remove_channel(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("/remove -1001234567890")
        return
    ch_id = int(context.args[0])
    data = load_data()
    if ch_id in data["network_channels"]:
        data["network_channels"].remove(ch_id)
        save_data(data)
        await update.message.reply_text(f"✅ Удалён: {ch_id}")
    else:
        await update.message.reply_text("Не найден")

async def list_channels(update, context):
    data = load_data()
    fav = data.get("favorite_channel")
    net = data.get("network_channels", [])
    text = f"🌟 Избранный: {fav or 'нет'}\n\n📢 Сеть ({len(net)}):\n"
    for ch in net:
        try:
            chat = await context.bot.get_chat(ch)
            text += f"• {chat.title}\n"
        except:
            text += f"• {ch}\n"
    await update.message.reply_text(text)

async def set_favorite(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("/set_favorite -1001234567890")
        return
    ch_id = int(context.args[0])
    data = load_data()
    try:
        chat = await context.bot.get_chat(ch_id)
        data["favorite_channel"] = ch_id
        save_data(data)
        await update.message.reply_text(f"✅ <b>{chat.title}</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

# --- Посты ---
async def on_post(update, context):
    msg = update.channel_post
    if not msg:
        return
    
    data = load_data()
    fav = data.get("favorite_channel")
    
    if msg.chat_id != fav:
        return
    
    logger.info(f"📨 Пост #{msg.message_id}")
    
    new_text = sign(msg.text or msg.caption or "")
    btns = post_buttons()
    
    try:
        if msg.text or msg.caption:
            await msg.edit_text(new_text, reply_markup=btns, parse_mode=ParseMode.HTML)
        else:
            await msg.edit_caption(caption=new_text, reply_markup=btns, parse_mode=ParseMode.HTML)
        logger.info(f"✅ Отредактирован")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        try:
            temp = await msg.copy(chat_id=fav)
            await msg.delete()
            if temp.text or temp.caption:
                await temp.edit_text(new_text, reply_markup=btns, parse_mode=ParseMode.HTML)
            else:
                await temp.edit_caption(caption=new_text, reply_markup=btns, parse_mode=ParseMode.HTML)
            msg = temp
        except Exception as e2:
            logger.error(f"❌ Полная ошибка: {e2}")
            return
    
    try:
        await context.bot.send_message(
            OWNER_ID,
            "📢 <b>Опубликовать пост?</b>",
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
        await q.edit_message_text("❌ Отмена")
        return
    
    await q.edit_message_text("⏳ Публикую...")
    
    data = load_data()
    net = data.get("network_channels", [])
    
    if not net:
        await q.message.reply_text("⚠️ Сеть пуста")
        return
    
    ok = 0
    failed = []
    
    for ch in net:
        try:
            await context.bot.copy_message(
                chat_id=ch,
                from_chat_id=chat_id,
                message_id=msg_id,
            )
            ok += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            failed.append((ch, str(e)))
    
    report = f"✅ <b>Готово!</b> {ok}/{len(net)}"
    if failed:
        report += "\n❌ Ошибки:\n"
        for ch, err in failed:
            report += f"• {ch}\n"
    
    await q.message.reply_text(report, parse_mode=ParseMode.HTML)

# --- Запуск ---
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
    import os
    main() Канал {ch}")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"❌ Канал {ch}: {e}")
            failed.append((ch, str(e)))
    
    report = f"✅ <b>Готово!</b>\n\n📊 Опубликовано: {ok}/{len(net)}"
    if failed:
        report += "\n\n❌ <b>Ошибки:</b>\n"
        for ch, err in failed:
            report += f"• <code>{ch}</code>\n"
    
    await q.message.reply_text(report, parse_mode=ParseMode.HTML)
    logger.info(f"📊 Рассылка завершена: {ok}/{len(net)}")

# --- Запуск ---
def main():
    proxies = load_proxies("list.txt")
    
    if proxies:
        rotator = ProxyRotator(proxies)
        request = RotatingRequest(
            rotator,
            connect_timeout=10,
            read_timeout=15,
            write_timeout=10,
        )
        app = Application.builder().token(TOKEN).request(request).build()
    else:
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
