import os
import json
import logging
import asyncio
from typing import Dict, Any, List
from dotenv import load_dotenv

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
from telegram.request import HTTPXRequest
from telegram.error import TelegramError

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Прокси ---
def load_proxies(filename: str = "list.txt") -> List[str]:
    if not os.path.exists(filename):
        return []
    proxies = []
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if not line.startswith("http"):
                    line = f"http://{line}"
                proxies.append(line)
    logger.info(f"Прокси: {len(proxies)}")
    return proxies

class ProxyRotator:
    def __init__(self, proxies):
        self.proxies = proxies
        self.current = 0
        self.dead = set()
    def get(self):
        if not self.proxies:
            return None
        for _ in range(len(self.proxies)):
            p = self.proxies[self.current]
            if p not in self.dead:
                return p
            self.current = (self.current + 1) % len(self.proxies)
        self.dead.clear()
        return self.proxies[0]
    def kill(self, p):
        self.dead.add(p)
        self.current = (self.current + 1) % len(self.proxies)

class RotatingRequest(HTTPXRequest):
    def __init__(self, rotator, **kwargs):
        self.rotator = rotator
        super().__init__(**kwargs)
    async def do_request(self, *args, **kwargs):
        for attempt in range(5):
            proxy = self.rotator.get()
            if proxy:
                self._client.proxy = proxy
            try:
                return await super().do_request(*args, **kwargs)
            except:
                if proxy:
                    self.rotator.kill(proxy)
                if attempt == 4:
                    raise
                await asyncio.sleep(0.5)

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

# Premium эмодзи
OWNER_EMOJI = "5443038326535759644"
BOT_EMOJI = "5172522439917175584"
PEREXOD_EMOJI = "5447410659077661506"

def post_buttons():
    """Кнопки для поста"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            text="Бот",
            url="https://t.me/EclipsShopsBot",
        ),
        InlineKeyboardButton(
            text="Переходник",
            url="https://t.me/EclipsMod",
        ),
    ]])

def ask_buttons(chat_id, msg_id):
    """Кнопки подтверждения"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да", callback_data=f"{APPROVE}:{chat_id}:{msg_id}"),
        InlineKeyboardButton("❌ Нет", callback_data=f"{DECLINE}:{chat_id}:{msg_id}"),
    ]])

def sign(text):
    """Подпись"""
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

# --- Обработка постов ---
async def on_post(update, context):
    """Когда приходит пост в избранный канал"""
    msg = update.channel_post
    if not msg:
        return
    
    data = load_data()
    fav = data.get("favorite_channel")
    
    if msg.chat_id != fav:
        return
    
    logger.info(f"📨 Новый пост #{msg.message_id} в избранном канале {msg.chat_id}")
    
    # Сразу редактируем пост — добавляем подпись и кнопки
    new_text = sign(msg.text or msg.caption or "")
    btns = post_buttons()
    
    try:
        if msg.text or msg.caption:
            await msg.edit_text(
                text=new_text,
                reply_markup=btns,
                parse_mode=ParseMode.HTML,
            )
        else:
            await msg.edit_caption(
                caption=new_text,
                reply_markup=btns,
                parse_mode=ParseMode.HTML,
            )
        logger.info(f"✅ Пост #{msg.message_id} отредактирован")
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования: {e}")
        # Если не получилось отредактировать — пробуем удалить и отправить заново
        try:
            # Копируем оригинал
            temp = await msg.copy(chat_id=fav)
            # Удаляем оригинал
            await msg.delete()
            # Редактируем копию
            if temp.text or temp.caption:
                await temp.edit_text(new_text, reply_markup=btns, parse_mode=ParseMode.HTML)
            else:
                await temp.edit_caption(caption=new_text, reply_markup=btns, parse_mode=ParseMode.HTML)
            msg = temp  # обновляем msg для дальнейшего использования
            logger.info(f"✅ Пост пересоздан и отредактирован")
        except Exception as e2:
            logger.error(f"❌ Полная ошибка: {e2}")
            return
    
    # Отправляем запрос владельцу
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text="📢 <b>Опубликовать этот пост во все каналы?</b>",
            reply_markup=ask_buttons(msg.chat_id, msg.message_id),
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"📤 Запрос отправлен владельцу")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки владельцу: {e}")

async def on_approve(update, context):
    """Обработка кнопок Да/Нет"""
    q = update.callback_query
    await q.answer()
    
    parts = q.data.split(":")
    action = parts[0]
    chat_id = int(parts[1]) if len(parts) > 1 else 0
    msg_id = int(parts[2]) if len(parts) > 2 else 0
    
    if action == DECLINE:
        await q.edit_message_text("❌ Публикация отменена")
        logger.info("❌ Отклонено")
        return
    
    # Подтверждение
    await q.edit_message_text("⏳ Публикую пост во все каналы...")
    
    data = load_data()
    net = data.get("network_channels", [])
    
    if not net:
        await q.message.reply_text("⚠️ Сеть каналов пуста. Добавьте через /add")
        return
    
    logger.info(f"📤 Рассылаю пост #{msg_id} из канала {chat_id}")
    
    # Просто копируем уже отредактированный пост во все каналы
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
            logger.info(f"✅ Канал {ch}")
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