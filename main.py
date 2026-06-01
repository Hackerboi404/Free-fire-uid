import sqlite3
import os
import json
from flask import Flask, request
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import asyncio

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID")) # tera telegram user id
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") # https://your-app.onrender.com/webhook
PORT = int(os.environ.get("PORT", 10000))

app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()

# DB Setup
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS auth_users (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS punished_users (user_id INTEGER, chat_id INTEGER, PRIMARY KEY (user_id, chat_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS locks (chat_id INTEGER, lock_type TEXT, PRIMARY KEY (chat_id, lock_type))''')
    c.execute('INSERT OR IGNORE INTO auth_users VALUES (?)', (OWNER_ID,))
    conn.commit()
    conn.close()

init_db()

# Helper functions
def is_auth(user_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('SELECT 1 FROM auth_users WHERE user_id=?', (user_id,))
    res = c.fetchone()
    conn.close()
    return res is not None

def is_punished(user_id, chat_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('SELECT 1 FROM punished_users WHERE user_id=? AND chat_id=?', (user_id, chat_id))
    res = c.fetchone()
    conn.close()
    return res is not None

def is_locked(chat_id, lock_type):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('SELECT 1 FROM locks WHERE chat_id=? AND lock_type=?', (chat_id, lock_type))
    res = c.fetchone()
    conn.close()
    return res is not None

async def get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if context.args:
        try:
            user_id = int(context.args[0])
            return await context.bot.get_chat_member(update.effective_chat.id, user_id)
        except:
            pass
    await update.message.reply_text("Reply karo ya user_id do")
    return None

# Decorator for auth only
def auth_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_auth(update.effective_user.id):
            return
        return await func(update, context)
    return wrapper

# Commands
@auth_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update, context)
    if not user: return
    await context.bot.ban_chat_member(update.effective_chat.id, user.id)
    await update.message.reply_text(f"Banned {user.first_name}")

@auth_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update, context)
    if not user: return
    await context.bot.unban_chat_member(update.effective_chat.id, user.id)
    await update.message.reply_text(f"Unbanned {user.first_name}")

@auth_only
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update, context)
    if not user: return
    await context.bot.restrict_chat_member(update.effective_chat.id, user.id, ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"Muted {user.first_name}")

@auth_only
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update, context)
    if not user: return
    await context.bot.restrict_chat_member(update.effective_chat.id, user.id, ChatPermissions(
        can_send_messages=True, can_send_other_messages=True, can_add_web_page_previews=True))
    await update.message.reply_text(f"Unmuted {user.first_name}")

@auth_only
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update, context)
    if not user: return
    await context.bot.ban_chat_member(update.effective_chat.id, user.id)
    await context.bot.unban_chat_member(update.effective_chat.id, user.id)
    await update.message.reply_text(f"Kicked {user.first_name}")

@auth_only
async def punish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update, context)
    if not user: return
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO punished_users VALUES (?,?)', (user.id, update.effective_chat.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Punished {user.first_name}. Ab iske saare msgs delete honge.")

@auth_only
async def unpunish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update, context)
    if not user: return
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM punished_users WHERE user_id=? AND chat_id=?', (user.id, update.effective_chat.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Unpunished {user.first_name}")

@auth_only
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Purge ke liye kisi msg pe reply karo")
        return
    start_id = update.message.reply_to_message.message_id
    end_id = update.message.message_id
    for msg_id in range(start_id, end_id + 1):
        try:
            await context.bot.delete_message(update.effective_chat.id, msg_id)
        except: pass
    await context.bot.send_message(update.effective_chat.id, "Purged!")

@auth_only
async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Pin ke liye msg pe reply karo")
        return
    await context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
    await update.message.reply_text("Pinned!")

@auth_only
async def unpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.unpin_all_chat_messages(update.effective_chat.id)
    await update.message.reply_text("Unpinned all")

@auth_only
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /lock text|photo|video|sticker|link")
        return
    lock_type = context.args[0].lower()
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO locks VALUES (?,?)', (update.effective_chat.id, lock_type))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Locked {lock_type}")

@auth_only
async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /unlock text|photo|video|sticker|link")
        return
    lock_type = context.args[0].lower()
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM locks WHERE chat_id=? AND lock_type=?', (update.effective_chat.id, lock_type))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Unlocked {lock_type}")

@auth_only
async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update, context)
    if not user: return
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO auth_users VALUES (?)', (user.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Authorized {user.first_name}")

@auth_only
async def deauth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update, context)
    if not user: return
    if user.id == OWNER_ID:
        await update.message.reply_text("Owner ko deauth nahi kar sakte")
        return
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM auth_users WHERE user_id=?', (user.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Deauthorized {user.first_name}")

# Message handler for punish + locks
async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # 1. Punish check - delete msg if user is punished
    if is_punished(user_id, chat_id) and not is_auth(user_id):
        try: await update.message.delete()
        except: pass
        return

    # 2. Lock checks - skip for auth users
    if is_auth(user_id): return

    if update.message.text and is_locked(chat_id, 'text'):
        await update.message.delete()
    elif update.message.photo and is_locked(chat_id, 'photo'):
        await update.message.delete()
    elif update.message.video and is_locked(chat_id, 'video'):
        await update.message.delete()
    elif update.message.sticker and is_locked(chat_id, 'sticker'):
        await update.message.delete()
    elif update.message.entities:
        for entity in update.message.entities:
            if entity.type in ['url', 'text_link'] and is_locked(chat_id, 'link'):
                await update.message.delete()
                break

# Add handlers
application.add_handler(CommandHandler("ban", ban))
application.add_handler(CommandHandler("unban", unban))
application.add_handler(CommandHandler("mute", mute))
application.add_handler(CommandHandler("unmute", unmute))
application.add_handler(CommandHandler("kick", kick))
application.add_handler(CommandHandler("punish", punish))
application.add_handler(CommandHandler("unpunish", unpunish))
application.add_handler(CommandHandler("purge", purge))
application.add_handler(CommandHandler("pin", pin))
application.add_handler(CommandHandler("unpin", unpin))
application.add_handler(CommandHandler("lock", lock))
application.add_handler(CommandHandler("unlock", unlock))
application.add_handler(CommandHandler("auth", auth))
application.add_handler(CommandHandler("deauth", deauth))
application.add_handler(MessageHandler(filters.ALL, msg_handler))

# Flask webhook
@app.route('/webhook', methods=['POST'])
async def webhook():
    await application.update_queue.put(Update.de_json(request.get_json(force=True), application.bot))
    return 'ok'

@app.route('/')
def index():
    return 'Bot is running!'

async def set_webhook():
    await application.bot.set_webhook(url=WEBHOOK_URL)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_webhook())
    app.run(host='0.0.0.0', port=PORT)
