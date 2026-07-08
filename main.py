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
        InlineKeyboardButton("Bot", url="https://t.me/EclipsShopsBot"),
        InlineKeyboardButton("Perehodnik", url="https://t.me/EclipsMod"),
    ]])

def ask_buttons(chat_id, msg_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes", callback_data=f"{APPROVE}:{chat_id}:{msg_id}"),
        InlineKeyboardButton("No", callback_data=f"{DECLINE}:{chat_id}:{msg_id}"),
    ]])

def sign(text):
    return (text or "") + "\n\nOwner - @EclipsOwner"

async def start(update, context):
    await update.message.reply_text(
        "Bot ready\n"
        "/set_favorite ID\n/add ID\n/remove ID\n/list\n/check ID",
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
        await update.message.reply_text(f"OK {chat.title} ID {chat.id} Status {member.status}")
    except Exception as e:
        await update.message.reply_text(f"Error {e}")

async def add_channel(update, context):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("/add -1001234567890")
        return
    ch_id = int(context.args[0])
    data = load_data()
    if ch_id in data["network_channels"]:
        await update.message.reply_text("Already added")
        return
    try:
        chat = await context.bot.get_chat(ch_id)
        data["network_channels"].append(ch_id)
        save_data(data)
        await update.message.reply_text(f"Added {chat.title}")
    except Exception as e:
        await update.message.reply_text(f"Error {e}")

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
        await update.message.reply_text(f"Removed {ch_id}")
    else:
        await update.message.reply_text("Not found")

async def list_channels(update, context):
    data = load_data()
    fav = data.get("favorite_channel")
    net = data.get("network_channels", [])
    text = f"Favorite: {fav or 'none'}\n\nNetwork ({len(net)}):\n"
    for ch in net:
        try:
            chat = await context.bot.get_chat(ch)
            text += f"- {chat.title}\n"
        except:
            text += f"- {ch}\n"
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
        await update.message.reply_text(f"Favorite set {chat.title}")
    except Exception as e:
        await update.message.reply_text(f"Error {e}")

async def on_post(update, context):
    msg = update.channel_post
    if not msg:
        return
    
    data = load_data()
    fav = data.get("favorite_channel")
    
    if msg.chat_id != fav:
        return
    
    logger.info(f"Post #{msg.message_id}")
    
    new_text = sign(msg.text or msg.caption or "")
    btns = post_buttons()
    
    try:
        if msg.text or msg.caption:
            await msg.edit_text(new_text, reply_markup=btns)
        else:
            await msg.edit_caption(caption=new_text, reply_markup=btns)
        logger.info("Edited")
    except Exception as e:
        logger.error(f"Error {e}")
        return
    
    try:
        await context.bot.send_message(
            OWNER_ID,
            "Publish?",
            reply_markup=ask_buttons(msg.chat_id, msg.message_id),
        )
    except Exception as e:
        logger.error(f"Error {e}")

async def on_approve(update, context):
    q = update.callback_query
    await q.answer()
    
    parts = q.data.split(":")
    action = parts[0]
    chat_id = int(parts[1]) if len(parts) > 1 else 0
    msg_id = int(parts[2]) if len(parts) > 2 else 0
    
    if action == DECLINE:
        await q.edit_message_text("Cancel")
        return
    
    await q.edit_message_text("Publishing...")
    
    data = load_data()
    net = data.get("network_channels", [])
    
    if not net:
        await q.message.reply_text("Network empty")
        return
    
    ok = 0
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
            logger.error(f"Error {ch} {e}")
    
    await q.message.reply_text(f"Done {ok}/{len(net)}")

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
    
    logger.info("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()