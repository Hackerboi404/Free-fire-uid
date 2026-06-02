import os
import logging
import sqlite3
from flask import Flask, request
from telegram import Update, BotCommand, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext

# --- CONFIGURATION ---
# Render Environment Variables se uthaenge agar nahi hai to default use karenge
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") 
OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))
PORT = int(os.environ.get("PORT", 8443))

# Render par domain name yahan sahi daalein (Webhook URL)
# Iska naam aapko pata hoga render par, jaise: https://your-bot-name.onrender.com
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://your-bot-name.onrender.com/webhook")

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    # Auth Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS auth_users (user_id INTEGER PRIMARY KEY)''')
    # Punished Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS punished_users (chat_id INTEGER, user_id, PRIMARY KEY (chat_id, user_id))''')
    conn.commit()
    conn.close()

# --- HELPER FUNCTIONS ---
def is_authorized(user_id):
    if user_id == OWNER_ID:
        return True
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM auth_users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_auth(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO auth_users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_auth(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM auth_users WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def is_punished(chat_id, user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM punished_users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    result = c.fetchone()
    conn.close()
    return result is not None

def punish_user(chat_id, user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO punished_users (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))
        conn.commit()
    except:
        pass
    conn.close()

def unpunish_user(chat_id, user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM punished_users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    conn.commit()
    conn.close()

# --- AUTH CHECK DECORATOR ---
# Yeh function check karega ki command sirf Owner ya Authorized user hi chala sake
async def check_permission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_authorized(user_id):
        return True
    await update.message.reply_text("⛔ Aapko is command chalane ki anumati nahi hai.")
    return False

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot active hai! Commands use karne ke liye authorized rahiye.")

# 1. Auth Commands (Sirf Owner)
async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /auth <user_id>")
        return
    try:
        uid = int(context.args[0])
        add_auth(uid)
        await update.message.reply_text(f"✅ User {uid} ko authorize kar diya gaya.")
    except ValueError:
        await update.message.reply_text("Invalid ID.")

async def unauth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return
    try:
        uid = int(context.args[0])
        remove_auth(uid)
        await update.message.reply_text(f"❌ User {uid} ki authority hatayi gayi.")
    except ValueError:
        pass

# 2. Ban/Unban
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user.id)
            await update.message.reply_text(f"🚫 {user.first_name} ko ban kar diya gaya.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("Kis user ko ban karna hai? Us message ko reply karein.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        uid = int(context.args[0])
        await context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=uid)
        await update.message.reply_text(f"✅ User {uid} ko unban kar diya.")
    except:
        await update.message.reply_text("User ID galat hai ya error aayi.")

# 3. Mute/Unmute
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        permissions = ChatPermissions(can_send_messages=False)
        try:
            await context.bot.restrict_chat_member(chat_id=update.effective_chat.id, user_id=user.id, permissions=permissions)
            await update.message.reply_text(f"🔇 {user.first_name} ko mute kar diya gaya.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("User ko reply karein.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        permissions = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
        try:
            await context.bot.restrict_chat_member(chat_id=update.effective_chat.id, user_id=user.id, permissions=permissions)
            await update.message.reply_text(f"🔊 {user.first_name} ko unmute kar diya gaya.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("User ko reply karein.")

# 4. Kick
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user.id)
            await context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=user.id) 
            await update.message.reply_text(f"👢 {user.first_name} ko kick kar diya gaya.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("User ko reply karein.")

# 5. Punish / Unpunish (Auto Delete Logic)
async def punish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        punish_user(chat_id, user.id)
        await update.message.reply_text(f"👻 {user.first_name} ko punish kar diya. Ab se uske msgs delete honge.")
    else:
        await update.message.reply_text("User ko reply karein.")

async def unpunish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        unpunish_user(chat_id, user.id)
        await update.message.reply_text(f"🔓 {user.first_name} ko unpunish kar diya.")
    else:
        await update.message.reply_text("User ko reply karein.")

# Auto-Delete Handler (Punish Logic)
async def auto_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if is_punished(chat_id, user_id):
            try:
                await update.message.delete()
            except:
                pass 

# 6. Purge
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        start_id = update.message.reply_to_message.message_id
        end_id = update.message.message_id
        await update.message.delete() 
        
        deleted_count = 0
        for msg_id in range(end_id, start_id - 1, -1):
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
                deleted_count += 1
            except:
                pass
        
        msg = await context.bot.send_message(update.effective_chat.id, f"🗑️ {deleted_count} messages delete kiye gaye.")
        import asyncio
        await asyncio.sleep(3)
        await msg.delete()

# 7. Pin
async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        try:
            await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id, disable_notification=True)
            await update.message.reply_text("📌 Message pin kar diya gaya.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

# 8. Lock / Unlock
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: /lock <text|media|stickers|all>")
        return
    
    item = context.args[0].lower()
    perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)
    
    if item == "text":
        perms.can_send_messages = False
    elif item == "media":
        perms.can_send_media_messages = False
    elif item == "stickers":
        perms.can_send_other_messages = False
    elif item == "all":
        perms = ChatPermissions(can_send_messages=False)
    else:
        await update.message.reply_text("Invalid item. Use: text, media, stickers, all")
        return

    try:
        await context.bot.set_chat_permissions(chat_id=update.effective_chat.id, permissions=perms)
        await update.message.reply_text(f"🔒 Group ko {item} ke liye lock kar diya gaya.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)
    try:
        await context.bot.set_chat_permissions(chat_id=update.effective_chat.id, permissions=perms)
        await update.message.reply_text("🔓 Group ko unlock kar diya gaya.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# --- FLASK APP ---
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put(update)
    return "OK"

# --- MAIN SETUP ---
if __name__ == "__main__":
    init_db()
    
    # Application builder
    application = Application.builder().token(BOT_TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth", auth))
    application.add_handler(CommandHandler("unauth", unauth))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("punish", punish))
    application.add_handler(CommandHandler("unpunish", unpunish))
    application.add_handler(CommandHandler("purge", purge))
    application.add_handler(CommandHandler("pin", pin))
    application.add_handler(CommandHandler("lock", lock))
    application.add_handler(CommandHandler("unlock", unlock))

    # Auto Delete Handler (Punish Logic) - Priority -1
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, auto_delete_handler), group=-1)

    # Webhook setup
    application.bot.set_webhook(url=WEBHOOK_URL)
    
    # Run Flask
    app.run(host="0.0.0.0", port=PORT, debug=True)
